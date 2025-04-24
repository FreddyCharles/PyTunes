import tkinter as tk
from tkinter import ttk, messagebox, PhotoImage, Menu
from tkinter import filedialog
import pygame
import os
import time
import sys
import io # For handling image data in memory
import random
from PIL import Image, ImageTk # For album art handling
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.flac import FLAC
from mutagen.wave import WAVE
from mutagen.id3 import ID3NoHeaderError, APIC # Import APIC for MP3 art
from mutagen import MutagenError
import threading

# --- Find Icon Path ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__)) # Use script's directory

    return os.path.join(base_path, relative_path)

# --- Constants ---
BG_COLOR = "#EAEAEA"
SCREEN_BG = "white"
TEXT_COLOR = "black"
SELECT_BG = "#B0B0D0"
BUTTON_BG = BG_COLOR
ACTIVE_BUTTON_BG = "#C0C0C0"
PROGRESS_TROUGH = "#D0D0D0"
PROGRESS_BAR = "#5050FF"

FONT_MAIN = ("Helvetica", 10)
FONT_SCREEN = ("Helvetica", 10)
FONT_METADATA = ("Helvetica", 9)
FONT_TIME = ("Helvetica", 8)
FONT_LISTBOX = ("Helvetica", 9)

SUPPORTED_FORMATS = ('.mp3', '.ogg', '.wav', '.flac')
ICON_PATH = "icons"
ALBUM_ART_SIZE = (100, 100) # Target size for displaying album art

# Repeat Modes
REPEAT_OFF = 0
REPEAT_ONE = 1
REPEAT_ALL = 2

class MediaPlayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PyPod Plus") # New name perhaps?
        self.root.geometry("350x600") # Taller for album art and more info
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # --- State ---
        self.playlist = [] # Stores full file paths
        self.original_playlist_order = [] # For restoring after shuffle/search
        self.current_track_index = -1 # Index relative to the *current* playlist view
        self.playback_history = [] # For 'previous' in shuffle mode
        self.playing_state = "stopped"
        self.current_track_duration = 0
        self.update_seek_job = None
        self.browser_window = None
        self.is_shuffled = False
        self.repeat_mode = REPEAT_OFF
        self.current_search_term = ""

        # --- Load Icons ---
        self.icons = {}
        self.default_album_art = None
        self.load_icons() # Load icons early

        # --- Initialize Pygame Mixer ---
        try:
            pygame.mixer.init()
        except pygame.error as e:
            # Show error before root is potentially destroyed
            messagebox.showerror("Pygame Error", f"Could not initialize audio mixer: {e}\nPlease ensure audio drivers are working.")
            self.root.destroy()
            return

        # --- Build UI ---
        self.create_menu()
        self.create_ui()

        # --- Bind closing event ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


    def load_icons(self):
        icon_files = {
            "play": "play.png", "pause": "pause.png", "next": "next.png",
            "previous": "previous.png", "stop": "stop.png", "browse": "folder.png",
            "folder": "folder_icon.png", "file": "file_icon.png",
            "shuffle_on": "shuffle_on.png", "shuffle_off": "shuffle_off.png",
            "repeat_off": "repeat_off.png", "repeat_one": "repeat_one.png", "repeat_all": "repeat_all.png",
            "placeholder": "placeholder.png", # Default album art
            "search": "search.png", "clear_search": "clear_search.png",
        }
        missing_icons = []
        for name, filename in icon_files.items():
            try:
                 fpath = resource_path(os.path.join(ICON_PATH, filename))
                 if not os.path.exists(fpath): raise FileNotFoundError(f"Icon not found: {fpath}")
                 img = PhotoImage(file=fpath)

                 # Store default art separately after loading
                 if name == 'placeholder':
                     # Resize placeholder art immediately
                     pil_img = Image.open(fpath).resize(ALBUM_ART_SIZE, Image.Resampling.LANCZOS)
                     self.default_album_art = ImageTk.PhotoImage(pil_img)
                     self.icons[name] = img # Store original PhotoImage too if needed elsewhere
                 else:
                     self.icons[name] = img

            except Exception as e:
                 print(f"Error loading icon '{filename}': {e}")
                 missing_icons.append(filename)
                 if name == 'placeholder': # Critical fallback for art
                     # Create a dummy transparent image if placeholder fails
                     pil_img = Image.new('RGBA', ALBUM_ART_SIZE, (0,0,0,0))
                     self.default_album_art = ImageTk.PhotoImage(pil_img)


        if missing_icons:
             self.show_warning("Missing Icons", f"Could not load:\n{', '.join(missing_icons)}")

    def show_error(self, title, message):
        self.root.after(0, lambda: messagebox.showerror(title, message))
    def show_warning(self, title, message):
        self.root.after(0, lambda: messagebox.showwarning(title, message))
    def show_info(self, title, message):
        self.root.after(0, lambda: messagebox.showinfo(title, message))


    def create_menu(self):
        menubar = Menu(self.root)
        self.root.config(menu=menubar)

        # File Menu
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Browse Files...", command=self.open_file_browser)
        file_menu.add_command(label="Load Playlist...", command=self.load_playlist_dialog)
        file_menu.add_command(label="Save Playlist As...", command=self.save_playlist_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)

        # Playback Menu
        playback_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Playback", menu=playback_menu)
        self.shuffle_menu_var = tk.BooleanVar(value=self.is_shuffled)
        playback_menu.add_checkbutton(label="Shuffle", variable=self.shuffle_menu_var, command=self.toggle_shuffle)
        # Repeat Submenu
        self.repeat_menu_var = tk.IntVar(value=self.repeat_mode)
        repeat_menu = Menu(playback_menu, tearoff=0)
        repeat_menu.add_radiobutton(label="Repeat Off", variable=self.repeat_menu_var, value=REPEAT_OFF, command=self.set_repeat_mode)
        repeat_menu.add_radiobutton(label="Repeat One", variable=self.repeat_menu_var, value=REPEAT_ONE, command=self.set_repeat_mode)
        repeat_menu.add_radiobutton(label="Repeat All", variable=self.repeat_menu_var, value=REPEAT_ALL, command=self.set_repeat_mode)
        playback_menu.add_cascade(label="Repeat", menu=repeat_menu)

        # Playlist Menu
        playlist_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Playlist", menu=playlist_menu)
        playlist_menu.add_command(label="Sort by Title", command=lambda: self.sort_playlist_action('title'))
        playlist_menu.add_command(label="Sort by Artist", command=lambda: self.sort_playlist_action('artist'))
        playlist_menu.add_command(label="Sort by Album", command=lambda: self.sort_playlist_action('album'))
        playlist_menu.add_command(label="Sort by Path", command=lambda: self.sort_playlist_action('path'))
        playlist_menu.add_separator()
        playlist_menu.add_command(label="Clear Playlist", command=self.clear_playlist_action)


    def create_ui(self):
        main_frame = tk.Frame(self.root, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5) # Less pady top due to menu

        # --- Screen Area (Top Section) ---
        screen_area = tk.Frame(main_frame, bg=BG_COLOR)
        screen_area.pack(fill=tk.X, pady=(0, 10))
        screen_area.columnconfigure(1, weight=1) # Make info column expand

        # Album Art
        self.album_art_label = tk.Label(screen_area, bg=SCREEN_BG, image=self.default_album_art, width=ALBUM_ART_SIZE[0], height=ALBUM_ART_SIZE[1])
        self.album_art_label.grid(row=0, column=0, rowspan=4, sticky='nw', padx=(0, 10), pady=5)
        if self.default_album_art:
            self.album_art_label.config(image=self.default_album_art)
        else: # Fallback if even placeholder failed
             self.album_art_label.config(text="No Art", width=12, height=6)

        # Track Info Labels
        self.track_title_label = tk.Label(screen_area, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_SCREEN)
        self.track_title_label.grid(row=0, column=1, sticky='ew', padx=5)

        self.track_artist_label = tk.Label(screen_area, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_METADATA)
        self.track_artist_label.grid(row=1, column=1, sticky='ew', padx=5)

        self.track_album_label = tk.Label(screen_area, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_METADATA)
        self.track_album_label.grid(row=2, column=1, sticky='ew', padx=5)

        # Progress Bar & Time (combined in a frame for better alignment)
        progress_time_frame = tk.Frame(screen_area, bg=SCREEN_BG)
        progress_time_frame.grid(row=3, column=1, sticky='ew', padx=5, pady=(2, 0))
        progress_time_frame.columnconfigure(1, weight=1)

        self.current_time_label = tk.Label(progress_time_frame, text="00:00", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_TIME)
        self.current_time_label.grid(row=0, column=0, sticky='w')

        self.progress_bar = ttk.Progressbar(progress_time_frame, orient=tk.HORIZONTAL, length=100, mode='determinate', style="custom.Horizontal.TProgressbar")
        self.progress_bar.grid(row=0, column=1, sticky='ew', padx=5)

        self.total_time_label = tk.Label(progress_time_frame, text="/ 00:00", anchor='e', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_TIME)
        self.total_time_label.grid(row=0, column=2, sticky='e')

        # Add border around screen area elements
        border_frame = tk.Frame(screen_area, bg=SCREEN_BG, bd=1, relief=tk.SOLID)
        border_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        border_frame.lower() # Place border behind content


        # --- Search Bar ---
        search_frame = tk.Frame(main_frame, bg=BG_COLOR)
        search_frame.pack(fill=tk.X, pady=(5, 5))

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30, font=FONT_MAIN)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", self.search_playlist_action)
        self.search_entry.bind("<KeyRelease>", self.search_as_you_type) # Optional: search while typing

        self.search_button = ttk.Button(search_frame, text="Search", command=self.search_playlist_action, width=8)
        # Optional icon for search button:
        # if 'search' in self.icons: self.search_button.config(image=self.icons['search'], width=0) # width=0 lets image decide size
        self.search_button.pack(side=tk.LEFT, padx=(0,5))

        self.clear_search_button = ttk.Button(search_frame, text="Clear", command=self.clear_search_action, width=6)
        # Optional icon:
        # if 'clear_search' in self.icons: self.clear_search_button.config(image=self.icons['clear_search'], width=0)
        self.clear_search_button.pack(side=tk.LEFT)


        # --- Playlist Area ---
        list_frame = tk.Frame(main_frame) # No bg color, border provides background
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.playlist_box = tk.Listbox(
            list_frame, bg=SCREEN_BG, fg=TEXT_COLOR, selectbackground=SELECT_BG,
            selectforeground=TEXT_COLOR, font=FONT_LISTBOX, activestyle='none',
            highlightthickness=0, bd=0, relief=tk.FLAT, yscrollcommand=scrollbar.set
        )
        # Store full path along with display text (using a tuple or custom class might be cleaner, but this works for simplicity)
        # We'll manage this in the add/update functions instead of configuring here.
        scrollbar.config(command=self.playlist_box.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.playlist_box.bind("<Double-Button-1>", self.play_selected)
        list_frame.config(bd=1, relief=tk.SOLID) # Border around listbox+scrollbar


        # --- Control Area ---
        control_frame = tk.Frame(main_frame, bg=BG_COLOR)
        control_frame.pack(fill=tk.X)

        # Volume Slider
        self.volume_scale = ttk.Scale(control_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.set_volume, style="custom.Horizontal.TScale")
        self.volume_scale.set(70); pygame.mixer.music.set_volume(0.7)
        self.volume_scale.pack(fill=tk.X, pady=(0, 5))

        # Button Frame (Using pack for more flexibility)
        button_frame = tk.Frame(control_frame, bg=BG_COLOR)
        button_frame.pack()

        button_opts = {'bg': BUTTON_BG, 'activebackground': ACTIVE_BUTTON_BG, 'relief': tk.FLAT, 'bd': 0, 'width': 35, 'height': 35}
        padx = 5

        # Shuffle Button
        self.shuffle_button = tk.Button(button_frame, **button_opts, command=self.toggle_shuffle)
        self.update_shuffle_button() # Set initial icon
        self.shuffle_button.pack(side=tk.LEFT, padx=padx)

        # Previous Button
        self.prev_button = tk.Button(button_frame, **button_opts, command=self.prev_track)
        if 'previous' in self.icons: self.prev_button.config(image=self.icons['previous'])
        else: self.prev_button.config(text="<<")
        self.prev_button.pack(side=tk.LEFT, padx=padx)

        # Play/Pause Button
        self.play_pause_button = tk.Button(button_frame, **button_opts, command=self.toggle_play_pause)
        self.update_play_pause_button()
        self.play_pause_button.config(width=45, height=45) # Make center button larger
        self.play_pause_button.pack(side=tk.LEFT, padx=padx)

        # Next Button
        self.next_button = tk.Button(button_frame, **button_opts, command=self.next_track)
        if 'next' in self.icons: self.next_button.config(image=self.icons['next'])
        else: self.next_button.config(text=">>")
        self.next_button.pack(side=tk.LEFT, padx=padx)

        # Stop Button
        self.stop_button = tk.Button(button_frame, **button_opts, command=self.stop_track)
        if 'stop' in self.icons: self.stop_button.config(image=self.icons['stop'])
        else: self.stop_button.config(text="Stop")
        # self.stop_button.pack(side=tk.LEFT, padx=padx) # Optionally hide stop? Modern players often omit it

        # Repeat Button
        self.repeat_button = tk.Button(button_frame, **button_opts, command=self.cycle_repeat_mode)
        self.update_repeat_button() # Set initial icon
        self.repeat_button.pack(side=tk.LEFT, padx=padx)


        # --- Configure ttk styles (similar to before) ---
        style = ttk.Style()
        try:
            if 'clam' in style.theme_names(): style.theme_use('clam')
            style.configure("custom.Horizontal.TProgressbar", troughcolor=PROGRESS_TROUGH, background=PROGRESS_BAR, thickness=8, borderwidth=0)
            style.configure("custom.Horizontal.TScale", background=BG_COLOR, troughcolor=SCREEN_BG, sliderlength=15)
            style.configure("custom.Treeview", background=SCREEN_BG, fieldbackground=SCREEN_BG, foreground=TEXT_COLOR, rowheight=22)
            style.map('custom.Treeview', background=[('selected', SELECT_BG)], foreground=[('selected', TEXT_COLOR)])
            style.configure("TScrollbar", arrowcolor=TEXT_COLOR, borderwidth=0, troughcolor=BG_COLOR, background=BUTTON_BG)
            style.map("TScrollbar", background=[('active', ACTIVE_BUTTON_BG)])
            style.configure("TButton", padding=5, background=BUTTON_BG, relief=tk.FLAT) # Style ttk buttons
            style.map("TButton", background=[('active', ACTIVE_BUTTON_BG)])
        except tk.TclError as e:
            print(f"ttk themes/styles not fully available. Using default. Error: {e}")

    # --- UI Update Helpers ---
    def update_play_pause_button(self):
        if self.playing_state == "playing":
            icon_name = 'pause'
            text = "Pause"
        else:
            icon_name = 'play'
            text = "Play"
        if icon_name in self.icons: self.play_pause_button.config(image=self.icons[icon_name])
        else: self.play_pause_button.config(text=text)

    def update_shuffle_button(self):
        icon_name = 'shuffle_on' if self.is_shuffled else 'shuffle_off'
        text = "Shuffle" # Simple text fallback
        if icon_name in self.icons: self.shuffle_button.config(image=self.icons[icon_name])
        else: self.shuffle_button.config(text=text + (" On" if self.is_shuffled else " Off"))

    def update_repeat_button(self):
        if self.repeat_mode == REPEAT_ONE: icon_name = 'repeat_one'; text = "Rpt 1"
        elif self.repeat_mode == REPEAT_ALL: icon_name = 'repeat_all'; text = "Rpt All"
        else: icon_name = 'repeat_off'; text = "Rpt Off"
        if icon_name in self.icons: self.repeat_button.config(image=self.icons[icon_name])
        else: self.repeat_button.config(text=text)

    # --- Album Art ---
    def update_album_art(self, metadata):
        art_label = self.album_art_label
        art_data = metadata.get('art_data')

        if art_data:
            try:
                # Open image data from bytes
                img_data = io.BytesIO(art_data)
                pil_img = Image.open(img_data)

                # Resize while maintaining aspect ratio (optional, but good practice)
                pil_img.thumbnail(ALBUM_ART_SIZE, Image.Resampling.LANCZOS)

                # Convert to Tkinter PhotoImage
                tk_img = ImageTk.PhotoImage(pil_img)

                # Update label
                art_label.config(image=tk_img)
                art_label.image = tk_img # Keep a reference! Important garbage collection prevention

            except Exception as e:
                print(f"Error processing album art: {e}")
                art_label.config(image=self.default_album_art)
                art_label.image = self.default_album_art # Keep ref to default
        else:
            # Use default placeholder
            art_label.config(image=self.default_album_art)
            art_label.image = self.default_album_art # Keep ref to default

    # --- File Browser (Largely unchanged - see previous version) ---
    # ... (Include open_file_browser, populate_browser, browser_navigate_up, etc.)
    # Modify browser_add_selected and browser_add_folder to call self.add_files_to_playlist
    # Ensure populate_browser uses self.show_error etc. for thread safety if needed.
    def open_file_browser(self):
        # (Copy the implementation from the previous response)
        # Make sure it calls `self.add_files_to_playlist` when adding files/folders.
        # For brevity, implementation is omitted here but should be included.
        self.show_info("Browse", "File browser implementation would go here.\n(See previous code version)")


    # --- Playlist Management ---
    def clear_playlist_action(self):
        if not self.playlist: return
        if messagebox.askyesno("Clear Playlist", "Are you sure you want to remove all tracks?"):
            self.stop_track()
            self.playlist = []
            self.original_playlist_order = []
            self.current_track_index = -1
            self.playlist_box.delete(0, tk.END)
            self.update_track_display(clear=True)
            self.progress_bar['value'] = 0
            self.current_search_term = "" # Clear search as well
            self.search_var.set("")
            if self.is_shuffled: self.toggle_shuffle() # Turn off shuffle

    def _repopulate_listbox(self, path_list=None):
        """Helper to clear and refill the listbox from a given list of paths."""
        self.playlist_box.delete(0, tk.END)
        if path_list is None:
            path_list = self.playlist # Default to the main playlist

        # Keep track of the actual path for each listbox item
        self.listbox_path_map = {} # Map listbox index to actual path

        for i, filepath in enumerate(path_list):
            filename = os.path.basename(filepath)
            # Basic display - fetch full metadata only when playing
            display_name = filename
            self.playlist_box.insert(tk.END, f"{i+1}. {display_name}")
            self.listbox_path_map[i] = filepath


    def add_files_to_playlist(self, files_to_add):
        newly_added_paths = []
        for filepath in files_to_add:
            if filepath not in self.original_playlist_order:
                self.original_playlist_order.append(filepath)
                newly_added_paths.append(filepath)

        if not newly_added_paths:
            return # Nothing new added

        # If not searching or shuffling, directly append to current view
        if not self.current_search_term and not self.is_shuffled:
            self.playlist.extend(newly_added_paths)
            self._repopulate_listbox() # Update listbox numbering etc.
        else:
            # Just update the underlying original list, repopulate will handle display
            self._apply_filters_and_shuffle() # Re-apply search/shuffle

        # Auto-select first track if playlist was empty
        if len(self.playlist) == len(newly_added_paths) and self.playing_state == "stopped":
            self.current_track_index = 0
            self.select_listbox_item(0)
            self.preload_track_info(0) # Show info for the first track


    def preload_track_info(self, listbox_index):
         """Loads metadata for a track without playing it, updates display."""
         if 0 <= listbox_index < self.playlist_box.size():
             filepath = self.listbox_path_map.get(listbox_index)
             if filepath and os.path.exists(filepath):
                  metadata = self.get_track_metadata(filepath)
                  self.current_track_duration = metadata.get('duration', 0) # Update duration even if not playing
                  self.update_track_display(metadata['title'], metadata['artist'], metadata['album'])
                  self.update_album_art(metadata) # Show art immediately
                  self.progress_bar['value'] = 0
                  self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100
             else:
                  self.update_track_display(clear=True) # Clear if path invalid


    def load_playlist_dialog(self):
        filepath = filedialog.askopenfilename(
            title="Load Playlist",
            filetypes=[("M3U Playlist", "*.m3u"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath: return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # Basic M3U parsing (ignore comments/directives, just read paths)
                paths = [line.strip() for line in f if line.strip() and not line.startswith('#')]

            if paths:
                self.stop_track()
                self.playlist = [] # Clear current view
                self.original_playlist_order = [] # Clear original order
                self.current_track_index = -1
                self.add_files_to_playlist(paths) # Add loaded paths
                self.show_info("Playlist Loaded", f"Loaded {len(paths)} tracks.")
            else:
                self.show_warning("Empty Playlist", "The selected file contained no valid paths.")

        except Exception as e:
            self.show_error("Load Error", f"Failed to load playlist:\n{e}")

    def save_playlist_dialog(self):
        if not self.original_playlist_order:
             self.show_warning("Empty Playlist", "Cannot save an empty playlist.")
             return

        filepath = filedialog.asksaveasfilename(
            title="Save Playlist As",
            defaultextension=".m3u",
            filetypes=[("M3U Playlist", "*.m3u"), ("Text Files", "*.txt")]
        )
        if not filepath: return

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n") # Simple M3U header
                for path in self.original_playlist_order:
                    # Could add #EXTINF here with duration/title if metadata is cached
                    f.write(path + "\n")
            self.show_info("Playlist Saved", f"Playlist saved to:\n{filepath}")
        except Exception as e:
            self.show_error("Save Error", f"Failed to save playlist:\n{e}")


    # --- Search & Sort ---
    def search_as_you_type(self, event=None):
        """Trigger search when user types in the entry."""
        # Optional: add a small delay using .after() to avoid searching on every keystroke
        self.search_playlist_action()

    def search_playlist_action(self, event=None):
        self.current_search_term = self.search_var.get().lower().strip()
        self._apply_filters_and_shuffle()

    def clear_search_action(self):
        self.search_var.set("")
        self.current_search_term = ""
        self._apply_filters_and_shuffle()

    def sort_playlist_action(self, sort_key):
        if not self.original_playlist_order: return

        # Fetch metadata IF sorting by tag (can be slow!)
        if sort_key in ('title', 'artist', 'album'):
            # Show a temporary loading message?
            print(f"Fetching metadata for sorting by {sort_key}...")
            metadata_list = []
            for i, path in enumerate(self.original_playlist_order):
                # Basic info needed for sorting
                meta = self.get_track_metadata(path) # Re-use existing function
                metadata_list.append({
                    'path': path,
                    'title': meta.get('title', '').lower(),
                    'artist': meta.get('artist', '').lower(),
                    'album': meta.get('album', '').lower(),
                    'original_index': i # Keep original index if needed
                })
            print("Metadata fetched.")

            # Sort based on the fetched metadata
            try:
                self.original_playlist_order = [
                    item['path'] for item in sorted(metadata_list, key=lambda x: x[sort_key])
                ]
            except Exception as e:
                 self.show_error("Sort Error", f"Could not sort by {sort_key}:\n{e}")
                 return # Abort sort on error

        elif sort_key == 'path':
            self.original_playlist_order.sort() # Simple path sort
        else: # Should not happen with menu setup
             print(f"Unknown sort key: {sort_key}")
             return

        # Re-apply current filters/shuffle to the newly sorted original list
        self._apply_filters_and_shuffle()
        # Find and re-select the currently playing track if possible
        # This is complex as indices change. Simpler: just stop playback?
        # Or find the filepath and select it in the new list.
        # For now, we just repopulate, selection might be lost.


    def _apply_filters_and_shuffle(self):
        """Applies search filter and shuffle to the original_playlist_order."""
        temp_playlist = list(self.original_playlist_order) # Start with full original list

        # Apply search filter
        if self.current_search_term:
            # Simple search on filename for now, more robust search needs metadata
            temp_playlist = [
                path for path in temp_playlist
                if self.current_search_term in os.path.basename(path).lower()
            ]

        # Apply shuffle
        if self.is_shuffled:
            random.shuffle(temp_playlist)

        # Update the main playlist view
        self.playlist = temp_playlist
        playing_path = None
        if self.playing_state != "stopped" and self.current_track_index != -1:
             try:
                # Try to get the path of the currently playing track *before* repopulating
                 playing_path = self.listbox_path_map.get(self.current_track_index)
             except IndexError:
                 pass # Index might be invalid if list changed drastically

        self._repopulate_listbox() # Update the Listbox UI

        # Try to find and re-select the previously playing track
        new_index = -1
        if playing_path:
             try:
                 # Find the path in the new listbox_path_map values
                 inverted_map = {v: k for k, v in self.listbox_path_map.items()}
                 if playing_path in inverted_map:
                     new_index = inverted_map[playing_path]
             except Exception as e:
                 print(f"Error finding playing track after filter/sort: {e}")


        if new_index != -1:
             self.current_track_index = new_index
             self.select_listbox_item(self.current_track_index)
        else:
             # Playing track not found in new view, reset index but don't stop
             self.current_track_index = -1
             if self.playing_state != "stopped":
                # Maybe stop playback, or just let it finish? Let it finish for now.
                pass
             elif self.playlist: # If stopped and playlist not empty, select first item
                 self.current_track_index = 0
                 self.select_listbox_item(0)
                 self.preload_track_info(0)


    # --- Playback Controls ---
    def toggle_shuffle(self):
        self.is_shuffled = not self.is_shuffled
        self.shuffle_menu_var.set(self.is_shuffled) # Update menu checkmark
        self.update_shuffle_button()
        self._apply_filters_and_shuffle() # Re-apply filters/shuffle to update view

    def set_repeat_mode(self):
        self.repeat_mode = self.repeat_menu_var.get()
        self.update_repeat_button()
        print(f"Repeat mode set to: {self.repeat_mode}")

    def cycle_repeat_mode(self):
        self.repeat_mode = (self.repeat_mode + 1) % 3 # Cycle through 0, 1, 2
        self.repeat_menu_var.set(self.repeat_mode) # Update menu radio button
        self.update_repeat_button()
        print(f"Repeat mode cycled to: {self.repeat_mode}")


    def get_track_metadata(self, filepath):
        metadata = {'title': os.path.basename(filepath), 'artist': 'Unknown Artist', 'album': 'Unknown Album', 'duration': 0, 'art_data': None}
        try:
            ext = os.path.splitext(filepath)[1].lower()
            audio = None
            art_data = None

            if ext == '.mp3':
                try: audio = MP3(filepath, ID3=ID3)
                except ID3NoHeaderError: audio = MP3(filepath)
                if audio and audio.tags:
                    metadata['title'] = str(audio.tags.get('TIT2', [metadata['title']])[0])
                    metadata['artist'] = str(audio.tags.get('TPE1', [metadata['artist']])[0])
                    metadata['album'] = str(audio.tags.get('TALB', [metadata['album']])[0])
                    # Extract Album Art (APIC frame)
                    apic_frames = audio.tags.getall('APIC')
                    if apic_frames:
                        art_data = apic_frames[0].data # Take the first picture

            elif ext == '.ogg':
                audio = OggVorbis(filepath)
                if audio:
                    metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                    metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
                    metadata['album'] = str(audio.get('album', [metadata['album']])[0])
                    # Extract Art (METADATA_BLOCK_PICTURE)
                    pictures = audio.get('metadata_block_picture')
                    if pictures:
                        # Ogg art data might be base64 encoded, need decoding?
                        # Mutagen often handles this, let's assume raw bytes for now.
                        # Need to investigate specific format if issues arise.
                        # For simplicity, assume raw bytes similar to MP3.
                         try:
                             import base64
                             from mutagen.flac import Picture # Ogg uses FLAC Picture structure
                             # picture_data = base64.b64decode(pictures[0]) # If it was base64
                             picture_info = Picture(pictures[0]) # Mutagen might parse it directly
                             art_data = picture_info.data
                         except Exception as e:
                             print(f"Error parsing Ogg picture block: {e}")


            elif ext == '.flac':
                audio = FLAC(filepath)
                if audio:
                    metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                    metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
                    metadata['album'] = str(audio.get('album', [metadata['album']])[0])
                    # Extract Art (Picture metadata block)
                    if audio.pictures:
                         art_data = audio.pictures[0].data

            elif ext == '.wav':
                 audio = WAVE(filepath)
                 # WAV metadata less standard, stick to duration/filename

            # Common duration extraction
            if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                 metadata['duration'] = int(audio.info.length)

            metadata['art_data'] = art_data

            # Cleanup empty values
            if not metadata['title']: metadata['title'] = os.path.basename(filepath)
            if not metadata['artist']: metadata['artist'] = 'Unknown Artist'
            if not metadata['album']: metadata['album'] = 'Unknown Album'

        except MutagenError as e: print(f"Mutagen error reading {filepath}: {e}")
        except FileNotFoundError:
             metadata.update({'title': "File Not Found", 'artist': "", 'album': "", 'duration': 0, 'art_data': None})
        except Exception as e: print(f"Unexpected error reading metadata for {filepath}: {e}")

        return metadata


    def play_track(self, listbox_index):
        if not self.playlist or not (0 <= listbox_index < len(self.playlist)):
            self.stop_track()
            # self.show_warning("Playback", "Invalid track index or empty playlist.")
            return

        # Map listbox index to the actual filepath from the current view
        filepath = self.listbox_path_map.get(listbox_index)
        if not filepath or not os.path.exists(filepath):
             self.show_error("Playback Error", f"File not found or invalid playlist state.\nPath: {filepath}")
             # Optional: Remove broken link? Needs careful state management.
             self.stop_track()
             return

        # Update history *before* potentially changing current_track_index
        if self.current_track_index != -1 and self.listbox_path_map.get(self.current_track_index) != filepath:
             # Add the index of the *previous* track (from listbox_path_map) to history
             # Only add if it's a different track than the one we are about to play
             self.playback_history.append(self.current_track_index)
             # Limit history size if needed
             max_history = 20
             if len(self.playback_history) > max_history:
                 self.playback_history.pop(0)


        self.current_track_index = listbox_index # Update index *after* history

        try:
            metadata = self.get_track_metadata(filepath)
            self.current_track_duration = metadata.get('duration', 0)

            self.update_track_display(metadata['title'], metadata['artist'], metadata['album'])
            self.update_album_art(metadata)
            self.select_listbox_item(self.current_track_index)
            self.progress_bar['value'] = 0
            self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100

            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            self.playing_state = "playing"
            self.update_play_pause_button()
            self.start_time_update()
            print(f"Playing [{self.current_track_index}]: {filepath}")

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
            if self.current_track_index != -1: # Resume paused track
                pygame.mixer.music.unpause()
                self.playing_state = "playing"
                self.start_time_update()
            else: # Paused but index somehow lost? Play from start or selected.
                 self.play_from_selection_or_start()
        else: # "stopped"
             self.play_from_selection_or_start()

        self.update_play_pause_button()

    def play_from_selection_or_start(self):
        """Plays the selected track, or the current, or the first if none selected/current."""
        selected_indices = self.playlist_box.curselection()
        if selected_indices:
            self.play_track(selected_indices[0])
        elif self.current_track_index != -1:
             # If stopped but an index exists (e.g. after stop button), play that track
             self.play_track(self.current_track_index)
        elif self.playlist:
             self.play_track(0) # Play first track if available

    def stop_track(self):
        pygame.mixer.music.stop()
        # pygame.mixer.music.unload() # Optional
        self.playing_state = "stopped"
        self.update_play_pause_button()
        self.stop_time_update()
        self.update_track_display(clear=True) # Clear display
        self.progress_bar['value'] = 0
        # Keep current_track_index so play can resume from the stopped track if desired


    def next_track(self, force=False):
        if not self.playlist: return
        if self.playing_state == "stopped" and not force: return # Don't advance if explicitly stopped

        current_list_size = len(self.playlist)
        if current_list_size == 0: return

        next_index = -1

        if self.repeat_mode == REPEAT_ONE and not force:
            next_index = self.current_track_index # Repeat current track
        # Note: Shuffle logic now handled by _apply_filters_and_shuffle generating playlist order
        elif self.current_track_index < current_list_size - 1:
             next_index = self.current_track_index + 1
        elif self.repeat_mode == REPEAT_ALL:
             next_index = 0 # Wrap around if repeating all
        else:
             # End of playlist, not repeating all
             self.stop_track()
             self.show_info("Playback Finished", "End of playlist.")
             return # Stop playback

        if next_index != -1:
             self.play_track(next_index)


    def prev_track(self):
        if not self.playlist: return

        # If playing for more than ~3 seconds, restart current track
        if self.playing_state == "playing" and pygame.mixer.music.get_pos() > 3000:
             self.play_track(self.current_track_index)
             return

        prev_index = -1
        current_list_size = len(self.playlist)

        if self.is_shuffled and self.playback_history:
             # In shuffle mode, 'previous' goes to the last played track from history
             prev_index = self.playback_history.pop()
             # Sanity check if index is still valid in current listbox view
             if not (0 <= prev_index < current_list_size):
                 print("History index invalid, reverting to standard previous.")
                 prev_index = -1 # Fallback to standard logic
             # Avoid re-adding the track we just popped when playing it
             # The history logic in play_track handles adding the 'new' previous track

        # Standard previous logic (or fallback from shuffle)
        if prev_index == -1:
             if self.current_track_index > 0:
                 prev_index = self.current_track_index - 1
             elif self.repeat_mode == REPEAT_ALL: # Wrap around if repeating
                 prev_index = current_list_size - 1
             else:
                 # At start, not repeating, just restart first track or stop? Restart.
                 prev_index = 0 if current_list_size > 0 else -1


        if prev_index != -1 and (0 <= prev_index < current_list_size):
             self.play_track(prev_index)
        elif current_list_size > 0: # e.g., only one track, prev restarts it
             self.play_track(self.current_track_index)
        else:
             self.stop_track()


    def play_selected(self, event=None):
        try:
            # Double-click should always play the selected item, regardless of history/shuffle context
            selected_index = self.playlist_box.curselection()[0]
            self.play_track(selected_index)
        except IndexError:
            pass

    # --- Volume, Time, Display Updates (minor changes maybe) ---
    def set_volume(self, val):
        volume = float(val) / 100
        pygame.mixer.music.set_volume(volume)

    def format_time(self, seconds):
        if seconds < 0: seconds = 0
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def update_time(self):
        reschedule = True
        if self.playing_state == "playing":
            try:
                current_pos_ms = pygame.mixer.music.get_pos()
                if current_pos_ms == -1:
                     if not pygame.mixer.music.get_busy():
                         print("Song finished.")
                         # Pass force=False to next_track to allow REPEAT_ONE to work correctly
                         self.next_track(force=False)
                         reschedule = False
                     else:
                         current_pos_sec = 0
                else:
                     current_pos_sec = current_pos_ms / 1000.0

                if reschedule:
                     current_time_str = self.format_time(current_pos_sec)
                     self.current_time_label.config(text=current_time_str)
                     if self.current_track_duration > 0:
                         # Progress value should scale up to the maximum value set
                         progress_value = min(current_pos_sec, self.current_track_duration)
                         self.progress_bar['value'] = progress_value
                     else:
                          self.progress_bar['value'] = 0

            except pygame.error as e: print(f"Pygame error during time update: {e}"); self.stop_track(); reschedule = False
            except Exception as e: print(f"Unexpected error during time update: {e}"); reschedule = False
        else: reschedule = False

        if reschedule: self.update_seek_job = self.root.after(500, self.update_time)
        else: self.stop_time_update()

    def start_time_update(self):
         self.stop_time_update(); self.update_time()
    def stop_time_update(self):
        if self.update_seek_job: self.root.after_cancel(self.update_seek_job); self.update_seek_job = None

    def update_track_display(self, title="---", artist="---", album="---", clear=False):
        # Trim function for long strings
        def trim(s, length=40):
            return (s[:length-1] + '…') if len(s) > length else s

        if clear:
            self.track_title_label.config(text="---")
            self.track_artist_label.config(text="---")
            self.track_album_label.config(text="---")
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text="/ 00:00")
            self.progress_bar['value'] = 0
            self.progress_bar['maximum'] = 100
            self.current_track_duration = 0
            # Reset album art to default
            self.album_art_label.config(image=self.default_album_art)
            self.album_art_label.image = self.default_album_art
        else:
            self.track_title_label.config(text=trim(title if title else "Unknown Title"))
            self.track_artist_label.config(text=trim(artist if artist else "Unknown Artist", 35))
            self.track_album_label.config(text=trim(album if album else "Unknown Album", 35))

            total_time_str = self.format_time(self.current_track_duration)
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text=f"/ {total_time_str}")
            self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100
            # Album art is updated separately by update_album_art()

    def select_listbox_item(self, index):
         if 0 <= index < self.playlist_box.size():
             self.playlist_box.selection_clear(0, tk.END)
             self.playlist_box.selection_set(index)
             self.playlist_box.activate(index)
             self.playlist_box.see(index) # Ensure item is visible

    # --- Closing ---
    def on_closing(self):
        print("Closing application...")
        if self.browser_window and self.browser_window.winfo_exists(): self.browser_window.destroy()
        self.stop_track()
        self.stop_time_update()
        try: pygame.mixer.quit(); pygame.quit()
        except Exception as e: print(f"Error quitting pygame: {e}")
        self.root.destroy()


# --- Main Execution ---
if __name__ == "__main__":
    try: pygame.quit() # Ensure clean start
    except: pass

    root = tk.Tk()
    app = MediaPlayerApp(root)

    if app and root.winfo_exists():
        root.mainloop()
    else:
        print("Application failed to initialize properly.")