import tkinter as tk
from tkinter import ttk, messagebox  # Use ttk for better widgets
from tkinter import PhotoImage
import pygame
import os
import time
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.flac import FLAC
from mutagen.wave import WAVE
from mutagen.id3 import ID3NoHeaderError
from mutagen import MutagenError
import threading
import sys # To find script path for icons

# --- Find Icon Path ---
# Helper function to find the correct path for resources (icons)
# Handles running from different directories and works with PyInstaller freezing
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".") # Use script's directory

    return os.path.join(base_path, relative_path)

# --- Constants ---
BG_COLOR = "#EAEAEA"
SCREEN_BG = "white"
TEXT_COLOR = "black"
SELECT_BG = "#B0B0D0" # Slightly different selection color
BUTTON_BG = BG_COLOR # Make buttons blend with background
ACTIVE_BUTTON_BG = "#C0C0C0"
PROGRESS_TROUGH = "#D0D0D0"
PROGRESS_BAR = "#5050FF" # A blue progress bar

FONT_MAIN = ("Helvetica", 10)
FONT_SCREEN = ("Helvetica", 10)
FONT_NOW_PLAYING = ("Helvetica", 9, "bold")
FONT_TIME = ("Helvetica", 8)

SUPPORTED_FORMATS = ('.mp3', '.ogg', '.wav', '.flac')
ICON_PATH = "icons" # Folder containing icons relative to script

class MediaPlayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PyPod")
        self.root.geometry("320x500") # Slightly wider/taller for progress bar/icons
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # --- State ---
        self.playlist = []
        self.current_track_index = -1
        self.playing_state = "stopped"
        self.current_track_duration = 0
        self.update_seek_job = None
        self.browser_window = None # To keep track of the browser Toplevel

        # --- Load Icons ---
        self.icons = {}
        self.load_icons() # Load icons early

        # --- Initialize Pygame Mixer ---
        try:
            pygame.mixer.init()
        except pygame.error as e:
            self.show_error("Pygame Error", f"Could not initialize audio mixer: {e}\nPlease ensure audio drivers are working.")
            self.root.destroy()
            return # Stop initialization

        # --- Build UI ---
        self.create_ui()

        # --- Bind closing event ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


    def load_icons(self):
        icon_files = {
            "play": "play.png", "pause": "pause.png", "next": "next.png",
            "previous": "previous.png", "stop": "stop.png", "browse": "folder.png",
            "folder": "folder_icon.png", "file": "file_icon.png"
        }
        icon_folder = os.path.join(os.path.dirname(__file__), ICON_PATH) # Path relative to script

        missing_icons = []
        for name, filename in icon_files.items():
            try:
                 # Use resource_path to handle running from different locations/PyInstaller
                 fpath = resource_path(os.path.join(ICON_PATH, filename))
                 if not os.path.exists(fpath):
                      raise FileNotFoundError(f"Icon not found at calculated path: {fpath}")
                 self.icons[name] = PhotoImage(file=fpath)
            except tk.TclError as e:
                 print(f"Error loading icon '{filename}': {e}. Tkinter might not support the image format or file is corrupt.")
                 missing_icons.append(filename)
            except FileNotFoundError as e:
                 print(f"Error finding icon '{filename}': {e}. Looked in '{os.path.abspath(ICON_PATH)}'")
                 missing_icons.append(filename)
            except Exception as e:
                 print(f"Unexpected error loading icon '{filename}': {e}")
                 missing_icons.append(filename)

        if missing_icons:
             self.show_warning("Missing Icons", f"Could not load the following icons:\n{', '.join(missing_icons)}\nButtons might be blank or text-based.")
             # Provide fallbacks if needed, e.g., using text if icons['play'] doesn't exist


    def show_error(self, title, message):
        # Schedule messagebox to run in the main loop, safer if called from threads
        self.root.after(0, lambda: messagebox.showerror(title, message))

    def show_warning(self, title, message):
        self.root.after(0, lambda: messagebox.showwarning(title, message))

    def show_info(self, title, message):
        self.root.after(0, lambda: messagebox.showinfo(title, message))

    def create_ui(self):
        main_frame = tk.Frame(self.root, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Screen Area ---
        screen_frame = tk.Frame(main_frame, bg=SCREEN_BG, bd=1, relief=tk.SOLID)
        screen_frame.pack(fill=tk.X, pady=(0, 10))
        screen_frame.columnconfigure(1, weight=1) # Allow progress bar/time label to expand

        # Now Playing Label (less prominent)
        # self.now_playing_label = tk.Label(screen_frame, text="Now Playing:", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_NOW_PLAYING)
        # self.now_playing_label.grid(row=0, column=0, columnspan=3, sticky='ew', padx=5, pady=(5,0))

        self.track_title_label = tk.Label(screen_frame, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_SCREEN)
        self.track_title_label.grid(row=0, column=0, columnspan=3, sticky='ew', padx=5, pady=(5, 0))

        self.track_artist_label = tk.Label(screen_frame, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_SCREEN)
        self.track_artist_label.grid(row=1, column=0, columnspan=3, sticky='ew', padx=5)

        # Progress Bar
        self.progress_bar = ttk.Progressbar(
            screen_frame, orient=tk.HORIZONTAL, length=100, mode='determinate',
            style="custom.Horizontal.TProgressbar"
        )
        self.progress_bar.grid(row=2, column=0, columnspan=3, sticky='ew', padx=5, pady=(2, 0))

        # Time Display (Current / Total)
        self.current_time_label = tk.Label(screen_frame, text="00:00", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_TIME)
        self.current_time_label.grid(row=3, column=0, sticky='w', padx=5, pady=(0, 5))

        self.total_time_label = tk.Label(screen_frame, text="/ 00:00", anchor='e', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_TIME)
        self.total_time_label.grid(row=3, column=2, sticky='e', padx=5, pady=(0, 5))


        # --- Playlist Area ---
        list_frame = tk.Frame(main_frame, bg=BG_COLOR)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL) # Use ttk scrollbar
        self.playlist_box = tk.Listbox(
            list_frame,
            bg=SCREEN_BG,
            fg=TEXT_COLOR,
            selectbackground=SELECT_BG, # Use new selection color
            selectforeground=TEXT_COLOR,
            font=FONT_SCREEN,
            activestyle='none',
            highlightthickness=0,
            bd=0, # No border for listbox itself
            relief=tk.FLAT,
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.playlist_box.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.playlist_box.bind("<Double-Button-1>", self.play_selected)
        # Add border around the frame containing listbox+scrollbar
        list_frame.config(bd=1, relief=tk.SOLID)


        # --- Control Area (Simulating Click Wheel) ---
        control_frame = tk.Frame(main_frame, bg=BG_COLOR)
        control_frame.pack(fill=tk.X)

        # Volume Slider
        self.volume_scale = ttk.Scale(
            control_frame, from_=0, to=100, orient=tk.HORIZONTAL,
            command=self.set_volume, style="custom.Horizontal.TScale"
        )
        self.volume_scale.set(70)
        pygame.mixer.music.set_volume(0.7)
        self.volume_scale.pack(fill=tk.X, pady=(0, 10))

        # Button Frame (Grid Layout)
        button_frame = tk.Frame(control_frame, bg=BG_COLOR)
        button_frame.pack()

        # Define button style using icons
        button_opts = {
             'bg': BUTTON_BG, 'activebackground': ACTIVE_BUTTON_BG,
             'relief': tk.FLAT, 'bd': 0, 'width': 40, 'height': 40 # Fixed size for icons
        }

        # Row 0: Browse
        self.browse_button = tk.Button(button_frame, **button_opts, command=self.open_file_browser)
        if 'browse' in self.icons: self.browse_button.config(image=self.icons['browse'])
        else: self.browse_button.config(text="Browse") # Fallback text
        self.browse_button.grid(row=0, column=1, pady=3)

        # Row 1: Previous, Play/Pause, Next
        self.prev_button = tk.Button(button_frame, **button_opts, command=self.prev_track)
        if 'previous' in self.icons: self.prev_button.config(image=self.icons['previous'])
        else: self.prev_button.config(text="<<")
        self.prev_button.grid(row=1, column=0, padx=10)

        self.play_pause_button = tk.Button(button_frame, **button_opts, command=self.toggle_play_pause)
        # Set initial icon later based on state (in update_play_pause_button)
        self.update_play_pause_button() # Set initial icon/text
        self.play_pause_button.grid(row=1, column=1, padx=10)


        self.next_button = tk.Button(button_frame, **button_opts, command=self.next_track)
        if 'next' in self.icons: self.next_button.config(image=self.icons['next'])
        else: self.next_button.config(text=">>")
        self.next_button.grid(row=1, column=2, padx=10)

        # Row 2: Stop
        self.stop_button = tk.Button(button_frame, **button_opts, command=self.stop_track)
        if 'stop' in self.icons: self.stop_button.config(image=self.icons['stop'])
        else: self.stop_button.config(text="Stop")
        self.stop_button.grid(row=2, column=1, pady=3)


        # --- Configure ttk styles ---
        style = ttk.Style()
        try:
            # Use a theme that allows more customization if available
            if 'clam' in style.theme_names(): style.theme_use('clam')

            # Style for Progress bar
            style.configure("custom.Horizontal.TProgressbar",
                            troughcolor=PROGRESS_TROUGH,
                            background=PROGRESS_BAR, # Color of the bar itself
                            thickness=8, borderwidth=0) # Adjust thickness

            # Style for Scale (Volume)
            style.configure("custom.Horizontal.TScale",
                            background=BG_COLOR, troughcolor=SCREEN_BG, sliderlength=15) # Slider length

            # Style for Treeview (in browser)
            style.configure("custom.Treeview", background=SCREEN_BG,
                    fieldbackground=SCREEN_BG, foreground=TEXT_COLOR,
                    rowheight=22) # Adjust row height
            style.map('custom.Treeview', background=[('selected', SELECT_BG)], foreground=[('selected', TEXT_COLOR)])

            # Style for Scrollbar
            style.configure("TScrollbar", arrowcolor=TEXT_COLOR, borderwidth=0, troughcolor=BG_COLOR, background=BUTTON_BG)
            style.map("TScrollbar", background=[('active', ACTIVE_BUTTON_BG)])

        except tk.TclError as e:
            print(f"ttk themes/styles not fully available. Using default. Error: {e}")

    # --- UI Update Helpers ---

    def update_play_pause_button(self):
        """Updates the Play/Pause button icon based on the playing state."""
        if self.playing_state == "playing":
             if 'pause' in self.icons: self.play_pause_button.config(image=self.icons['pause'])
             else: self.play_pause_button.config(text="Pause")
        else: # stopped or paused
             if 'play' in self.icons: self.play_pause_button.config(image=self.icons['play'])
             else: self.play_pause_button.config(text="Play")

    # --- File Browser Logic ---

    def open_file_browser(self):
        if self.browser_window and self.browser_window.winfo_exists():
             self.browser_window.lift() # Bring existing browser to front
             return

        self.browser_window = tk.Toplevel(self.root)
        self.browser_window.title("Browse Music")
        self.browser_window.geometry("400x450")
        self.browser_window.configure(bg=BG_COLOR)
        self.browser_window.transient(self.root) # Keep it above the main window
        self.browser_window.grab_set() # Modal behavior

        # Frame for path display and Up button
        path_frame = tk.Frame(self.browser_window, bg=BG_COLOR)
        path_frame.pack(fill=tk.X, padx=5, pady=5)

        up_button = ttk.Button(path_frame, text="Up", width=5, command=self.browser_navigate_up)
        up_button.pack(side=tk.LEFT, padx=(0, 5))

        self.current_path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=self.current_path_var, state='readonly')
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Treeview for file listing
        tree_frame = tk.Frame(self.browser_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))

        tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.browser_tree = ttk.Treeview(
            tree_frame,
            columns=("fullpath",), # Hidden column to store full path
            displaycolumns="",    # Don't show the hidden column
            yscrollcommand=tree_scrollbar.set,
            selectmode='extended', # Allow multiple selections
            style="custom.Treeview"
        )
        tree_scrollbar.config(command=self.browser_tree.yview)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.browser_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.browser_tree.bind("<Double-1>", self.browser_item_activated)

        # --- Load icons for Treeview ---
        self.tree_icons = {}
        if 'folder' in self.icons: self.tree_icons['folder'] = self.icons['folder']
        if 'file' in self.icons: self.tree_icons['file'] = self.icons['file']


        # Frame for action buttons
        action_frame = tk.Frame(self.browser_window, bg=BG_COLOR)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        add_file_button = ttk.Button(action_frame, text="Add Selected", command=self.browser_add_selected)
        add_file_button.pack(side=tk.LEFT, padx=2)

        add_folder_button = ttk.Button(action_frame, text="Add All in Folder", command=self.browser_add_folder)
        add_folder_button.pack(side=tk.LEFT, padx=2)

        clear_playlist_button = ttk.Button(action_frame, text="Clear Playlist", command=self.clear_playlist_action)
        clear_playlist_button.pack(side=tk.LEFT, padx=2)

        close_button = ttk.Button(action_frame, text="Close", command=self.browser_window.destroy)
        close_button.pack(side=tk.RIGHT, padx=2)

        # Populate initial view (e.g., home directory or last path)
        start_path = os.path.expanduser("~") # Start at home directory
        self.populate_browser(start_path)

        # Center the browser window (optional)
        self.browser_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (self.browser_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (self.browser_window.winfo_height() // 2)
        self.browser_window.geometry(f'+{x}+{y}')


    def populate_browser(self, path):
        if not os.path.isdir(path):
            self.show_warning("Invalid Path", f"Cannot browse: {path}")
            return

        self.current_path_var.set(os.path.abspath(path))
        # Clear existing tree items
        for i in self.browser_tree.get_children():
            self.browser_tree.delete(i)

        items = []
        try:
            items = os.listdir(path)
            items.sort(key=str.lower) # Sort case-insensitively
        except OSError as e:
            self.show_error("Permission Error", f"Cannot read directory:\n{e}")
            return # Don't proceed if listing fails

        # Separate folders and files
        folders = []
        files = []
        for item in items:
             full_item_path = os.path.join(path, item)
             try: # Handle potential permission issues on individual items
                 if os.path.isdir(full_item_path):
                      folders.append((item, full_item_path))
                 elif item.lower().endswith(SUPPORTED_FORMATS):
                      files.append((item, full_item_path))
             except OSError:
                  print(f"Skipping due to access error: {full_item_path}")
                  continue # Skip item if cannot access properties

        # Add folders to treeview
        for name, fullpath in folders:
            try:
                 icon = self.tree_icons.get('folder', None)
                 self.browser_tree.insert('', tk.END, text=f" {name}", values=(fullpath,), image=icon, open=False, tags=('folder',))
            except Exception as e:
                 print(f"Error inserting folder {name} into tree: {e}")


        # Add supported files to treeview
        for name, fullpath in files:
             try:
                 icon = self.tree_icons.get('file', None)
                 self.browser_tree.insert('', tk.END, text=f" {name}", values=(fullpath,), image=icon, tags=('file',))
             except Exception as e:
                  print(f"Error inserting file {name} into tree: {e}")


    def browser_navigate_up(self):
        current_path = self.current_path_var.get()
        parent_path = os.path.dirname(current_path)
        if parent_path != current_path: # Prevent going up from root
            self.populate_browser(parent_path)

    def browser_item_activated(self, event):
        item_id = self.browser_tree.focus() # Get the focused item
        if not item_id: return

        item_tags = self.browser_tree.item(item_id, "tags")
        item_path = self.browser_tree.item(item_id, "values")[0] # Get full path from hidden column

        if 'folder' in item_tags:
            self.populate_browser(item_path)

        elif 'file' in item_tags:
             # Optional: Add and play on double click? Or just add? Let's just add.
             self.add_files_to_playlist([item_path])
             # Maybe close browser after adding? Or keep open? Keep open for now.


    def browser_add_selected(self):
        selected_items = self.browser_tree.selection()
        files_to_add = []
        for item_id in selected_items:
            item_tags = self.browser_tree.item(item_id, "tags")
            if 'file' in item_tags:
                item_path = self.browser_tree.item(item_id, "values")[0]
                files_to_add.append(item_path)
        if files_to_add:
            self.add_files_to_playlist(files_to_add)
            self.show_info("Files Added", f"{len(files_to_add)} file(s) added to the playlist.")
        else:
             self.show_warning("No Selection", "No music files selected.")

    def browser_add_folder(self):
        current_path = self.current_path_var.get()
        files_to_add = []
        try:
            for item in os.listdir(current_path):
                if item.lower().endswith(SUPPORTED_FORMATS):
                    filepath = os.path.join(current_path, item)
                    if os.path.isfile(filepath): # Double check it's a file
                         files_to_add.append(filepath)
        except OSError as e:
            self.show_error("Error Reading Folder", f"Could not read folder contents:\n{e}")
            return

        if files_to_add:
             files_to_add.sort()
             self.add_files_to_playlist(files_to_add)
             self.show_info("Folder Added", f"{len(files_to_add)} file(s) from folder added.")
        else:
             self.show_warning("Empty Folder", "No supported music files found in this folder.")

    def clear_playlist_action(self):
         if messagebox.askyesno("Clear Playlist", "Are you sure you want to remove all tracks from the playlist?"):
             self.stop_track()
             self.playlist = []
             self.playlist_box.delete(0, tk.END)
             self.current_track_index = -1
             self.update_track_display(clear=True)
             self.progress_bar['value'] = 0


    # --- Playlist Management ---

    def add_files_to_playlist(self, files_to_add):
        """Adds a list of file paths to the playlist and updates the listbox."""
        initial_playlist_size = len(self.playlist)
        newly_added_count = 0
        for filepath in files_to_add:
            if filepath not in self.playlist: # Avoid duplicates
                self.playlist.append(filepath)
                filename = os.path.basename(filepath)
                # Try getting Title tag for display, fallback to filename
                try:
                    # Only get title here, avoid full metadata scan for speed
                    if filepath.lower().endswith('.mp3'):
                         audio = MP3(filepath, ID3=ID3)
                         display_name = audio.get('TIT2', [filename])[0]
                    # Add similar quick checks for other formats if needed, or default to filename
                    else:
                         display_name = filename

                    if not display_name: display_name = filename
                except Exception:
                    display_name = filename

                # Add to listbox with updated index number
                listbox_index = len(self.playlist)
                self.playlist_box.insert(tk.END, f"{listbox_index}. {display_name}")
                newly_added_count += 1

        # If playlist was empty and we added tracks, select the first one
        if initial_playlist_size == 0 and newly_added_count > 0 and self.playing_state == "stopped":
             self.current_track_index = 0
             # No automatic play, user has to press play. Highlight it though.
             self.select_listbox_item(0)
             # Load metadata for the first track now
             metadata = self.get_track_metadata(self.playlist[0])
             self.current_track_duration = metadata.get('duration', 0)
             self.update_track_display(metadata['title'], metadata['artist'])


    # --- Core Playback Logic (Mostly unchanged, but check updates) ---

    def get_track_metadata(self, filepath):
        """Reads metadata using mutagen. Returns dict with title, artist, duration."""
        # Keep the original robust metadata fetching
        metadata = {'title': os.path.basename(filepath), 'artist': 'Unknown Artist', 'duration': 0}
        try:
            ext = os.path.splitext(filepath)[1].lower()
            audio = None
            if ext == '.mp3':
                try: audio = MP3(filepath, ID3=ID3)
                except ID3NoHeaderError: audio = MP3(filepath)
                if audio:
                    metadata['title'] = str(audio.get('TIT2', [metadata['title']])[0]) # Ensure string
                    metadata['artist'] = str(audio.get('TPE1', [metadata['artist']])[0])
            elif ext == '.ogg':
                audio = OggVorbis(filepath)
                metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
            elif ext == '.flac':
                audio = FLAC(filepath)
                metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
            elif ext == '.wav':
                 audio = WAVE(filepath)
                 # WAV metadata is less standard, stick to duration

            # Common duration extraction
            if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                 metadata['duration'] = int(audio.info.length)

             # Cleanup empty values
            if not metadata['title']: metadata['title'] = os.path.basename(filepath)
            if not metadata['artist']: metadata['artist'] = 'Unknown Artist'

        except MutagenError as e:
            print(f"Mutagen error reading {filepath}: {e}")
        except FileNotFoundError:
             print(f"File not found during metadata read: {filepath}") # May happen if file deleted between adding and playing
             metadata['title'] = "File Not Found"
             metadata['artist'] = ""
             metadata['duration'] = 0
        except Exception as e:
            print(f"Unexpected error reading metadata for {filepath}: {e}")

        return metadata


    def play_track(self, track_index=None):
        # If track_index is explicitly given, use it. Otherwise, figure it out.
        play_idx = -1
        if track_index is not None:
            play_idx = track_index
        elif self.current_track_index != -1:
             play_idx = self.current_track_index # Resume current if paused/stopped
        elif self.playlist:
             play_idx = 0 # Start from beginning if nothing was playing

        if not self.playlist or not (0 <= play_idx < len(self.playlist)):
            self.stop_track()
            self.show_warning("Playback", "No track selected or playlist empty.")
            return

        self.current_track_index = play_idx
        filepath = self.playlist[self.current_track_index]

        # --- Check if file exists before trying to load ---
        if not os.path.exists(filepath):
            self.show_error("Playback Error", f"File not found:\n{os.path.basename(filepath)}\n\nIt may have been moved or deleted.")
            # Remove the broken track from the playlist? (More complex state management)
            # For now, just stop and let user handle it.
            self.stop_track()
            # Maybe try playing next? Risky if many files are missing.
            return

        try:
            # Get metadata *before* loading
            metadata = self.get_track_metadata(filepath)
            self.current_track_duration = metadata.get('duration', 0)

            # Update display immediately
            self.update_track_display(metadata['title'], metadata['artist'])
            self.select_listbox_item(self.current_track_index)
            self.progress_bar['value'] = 0 # Reset progress bar
            self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100 # Avoid division by zero


            # Load and play using pygame
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            self.playing_state = "playing"
            self.update_play_pause_button()
            self.start_time_update() # Start updating the time display
            print(f"Playing: {filepath}")

        except pygame.error as e:
            self.show_error("Playback Error", f"Could not play file:\n{os.path.basename(filepath)}\n\nError: {e}")
            self.stop_track()
        except Exception as e:
             self.show_error("Error", f"An unexpected error occurred during playback:\n{e}")
             self.stop_track()


    def toggle_play_pause(self):
        if not self.playlist: return

        if self.playing_state == "playing":
            pygame.mixer.music.pause()
            self.playing_state = "paused"
            self.stop_time_update()
        elif self.playing_state == "paused":
            pygame.mixer.music.unpause()
            self.playing_state = "playing"
            self.start_time_update()
        else: # "stopped"
             # If stopped, play either the selected track or the first one
             selected_indices = self.playlist_box.curselection()
             if selected_indices:
                 self.play_track(selected_indices[0])
             elif self.current_track_index != -1:
                  self.play_track(self.current_track_index) # Play last track
             elif self.playlist:
                  self.play_track(0) # Play first track
        self.update_play_pause_button()


    def stop_track(self):
        pygame.mixer.music.stop()
        # pygame.mixer.music.unload() # Might help release file handles sooner
        self.playing_state = "stopped"
        self.update_play_pause_button()
        self.stop_time_update()
        self.update_track_display(clear=True)
        self.progress_bar['value'] = 0
        # Keep current_track_index, don't reset fully


    def next_track(self, force=False):
        if not self.playlist: return
        next_index = self.current_track_index + 1
        if next_index >= len(self.playlist):
            next_index = 0 # Wrap around
        self.play_track(next_index)

    def prev_track(self):
        if not self.playlist: return

        prev_index = -1
        # If playing for more than ~3 seconds, restart current track
        if self.playing_state == "playing" and pygame.mixer.music.get_pos() > 3000:
             prev_index = self.current_track_index # Signal to replay current
        else:
             prev_index = self.current_track_index - 1
             if prev_index < 0:
                 prev_index = len(self.playlist) - 1 # Wrap around to end

        if prev_index >= 0: # Check if playlist is not empty after wrap/logic
             self.play_track(prev_index)
        else:
             self.stop_track()


    def play_selected(self, event=None):
        try:
            selected_index = self.playlist_box.curselection()[0]
            self.play_track(selected_index)
        except IndexError:
            pass # No item selected

    def set_volume(self, val):
        volume = float(val) / 100
        pygame.mixer.music.set_volume(volume)

    def format_time(self, seconds):
        if seconds < 0: seconds = 0
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def update_time(self):
        reschedule = True # Assume we continue updating
        if self.playing_state == "playing":
            try:
                current_pos_ms = pygame.mixer.music.get_pos()
                if current_pos_ms == -1:
                     # Song likely ended. Check if mixer is *actually* not busy.
                     # Sometimes get_pos() returns -1 briefly before stopping.
                     if not pygame.mixer.music.get_busy():
                         print("Song finished.")
                         self.next_track(force=True) # Auto-advance
                         reschedule = False # Don't reschedule for the finished track
                     else:
                         # Still busy or state unclear, treat as 0 time for this update cycle
                         current_pos_sec = 0
                else:
                     current_pos_sec = current_pos_ms / 1000.0

                # Update labels and progress bar only if still relevant
                if reschedule:
                     current_time_str = self.format_time(current_pos_sec)
                     self.current_time_label.config(text=current_time_str)

                     # Update progress bar
                     if self.current_track_duration > 0:
                         progress_percent = (current_pos_sec / self.current_track_duration) * self.current_track_duration # Use duration as max value
                         self.progress_bar['value'] = progress_percent
                     else:
                          self.progress_bar['value'] = 0

            except pygame.error as e:
                 print(f"Pygame error during time update: {e}")
                 self.stop_track()
                 reschedule = False
            except Exception as e:
                 print(f"Unexpected error during time update: {e}")
                 # Decide if stopping is appropriate
                 reschedule = False # Stop updates on unexpected errors

        else: # Not playing (paused or stopped)
            reschedule = False

        # Schedule next update only if needed
        if reschedule:
             self.update_seek_job = self.root.after(500, self.update_time)
        else:
             self.stop_time_update() # Ensure job is cleared if we stop


    def start_time_update(self):
         self.stop_time_update() # Cancel any existing job first
         self.update_time() # Start the update loop

    def stop_time_update(self):
        if self.update_seek_job:
            self.root.after_cancel(self.update_seek_job)
            self.update_seek_job = None


    def update_track_display(self, title="---", artist="---", clear=False):
        if clear:
            self.track_title_label.config(text="---")
            self.track_artist_label.config(text="---")
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text="/ 00:00")
            self.progress_bar['value'] = 0
            self.progress_bar['maximum'] = 100 # Reset max
            self.current_track_duration = 0
        else:
            # Limit length
            max_len = 38 # Adjusted slightly
            display_title = (title[:max_len] + '…') if len(title) > max_len else title # Use ellipsis
            display_artist = (artist[:max_len] + '…') if len(artist) > max_len else artist

            self.track_title_label.config(text=display_title if display_title else "Unknown Title")
            self.track_artist_label.config(text=display_artist if display_artist else "Unknown Artist")

            total_time_str = self.format_time(self.current_track_duration)
            self.current_time_label.config(text="00:00") # Reset current time display
            self.total_time_label.config(text=f"/ {total_time_str}")
            self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100


    def select_listbox_item(self, index):
         if 0 <= index < self.playlist_box.size():
             self.playlist_box.selection_clear(0, tk.END)
             self.playlist_box.selection_set(index)
             self.playlist_box.activate(index)
             self.playlist_box.see(index)

    def deselect_listbox_item(self):
         self.playlist_box.selection_clear(0, tk.END)


    def on_closing(self):
        print("Closing application...")
        if self.browser_window and self.browser_window.winfo_exists():
            self.browser_window.destroy() # Close browser if open
        self.stop_track()
        self.stop_time_update()
        try:
            pygame.mixer.quit()
            pygame.quit() # Quit pygame fully
        except Exception as e:
            print(f"Error quitting pygame: {e}")
        self.root.destroy()


# --- Main Execution ---
if __name__ == "__main__":
    # Ensure pygame is quit if script is run multiple times in some environments
    try:
         pygame.quit()
    except:
         pass

    root = tk.Tk()
    # Create app instance only after root is created
    app = MediaPlayerApp(root)

    # Check if app initialization failed (e.g., pygame mixer failed)
    # The check `root.winfo_exists()` ensures we don't start mainloop if root was destroyed during init
    if app and root.winfo_exists():
        root.mainloop()
    else:
         print("Application failed to initialize properly.")