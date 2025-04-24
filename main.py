import tkinter as tk
from tkinter import ttk, messagebox, PhotoImage, Menu
from tkinter import filedialog
import pygame
import os
import time
import sys
import io
import random
from PIL import Image, ImageTk
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.flac import FLAC
from mutagen.wave import WAVE
from mutagen.id3 import ID3NoHeaderError, APIC
from mutagen import MutagenError
import threading
import traceback # For detailed error logging

# --- Find Icon Path ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
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
FONT_BUTTON_FALLBACK = ("Helvetica", 8) # Smaller font for text buttons

SUPPORTED_FORMATS = ('.mp3', '.ogg', '.wav', '.flac')
ICON_PATH = "icons"
ALBUM_ART_SIZE = (100, 100)

REPEAT_OFF = 0
REPEAT_ONE = 1
REPEAT_ALL = 2

class MediaPlayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PyPod Plus")
        self.root.geometry("350x600")
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False)

        # --- State ---
        self.playlist = []
        self.original_playlist_order = []
        self.current_track_index = -1
        self.playback_history = []
        self.playing_state = "stopped"
        self.current_track_duration = 0
        self.update_seek_job = None
        self.browser_window = None
        self.is_shuffled = False
        self.repeat_mode = REPEAT_OFF
        self.current_search_term = ""
        self.listbox_path_map = {} # Crucial for mapping listbox index to path

        # --- Load Icons ---
        self.icons = {} # Stores PhotoImage objects if loaded
        self.icon_fallbacks = {} # Stores fallback text
        self.default_album_art = None
        self.load_icons()

        # --- Initialize Pygame Mixer ---
        try:
            pygame.mixer.init()
        except pygame.error as e:
            messagebox.showerror("Pygame Error", f"Could not initialize audio mixer: {e}\nPlease ensure audio drivers are working.")
            self.root.destroy()
            return

        # --- Build UI ---
        self.create_menu()
        self.create_ui()

        # --- Bind closing event ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_icons(self):
        # Define icons and their text fallbacks
        icon_definitions = {
            "play": ("play.png", "Play"), "pause": ("pause.png", "Pause"),
            "next": ("next.png", ">>"), "previous": ("previous.png", "<<"),
            "stop": ("stop.png", "Stop"), "browse": ("folder.png", "Browse"),
            "folder": ("folder_icon.png", ""), "file": ("file_icon.png", ""), # Treeview icons, no text fallback needed
            "shuffle_on": ("shuffle_on.png", "Shfl On"), "shuffle_off": ("shuffle_off.png", "Shfl Off"),
            "repeat_off": ("repeat_off.png", "Rpt Off"), "repeat_one": ("repeat_one.png", "Rpt One"),
            "repeat_all": ("repeat_all.png", "Rpt All"),
            "placeholder": ("placeholder.png", ""), # Placeholder art
            "search": ("search.png", "Search"), "clear_search": ("clear_search.png", "Clear"),
        }
        missing_icons = []
        for name, (filename, fallback_text) in icon_definitions.items():
            self.icon_fallbacks[name] = fallback_text # Store fallback text regardless
            try:
                 fpath = resource_path(os.path.join(ICON_PATH, filename))
                 if not os.path.exists(fpath): raise FileNotFoundError(f"Icon not found: {fpath}")

                 if name == 'placeholder':
                      # Special handling for resizing placeholder art
                      pil_img = Image.open(fpath).resize(ALBUM_ART_SIZE, Image.Resampling.LANCZOS)
                      self.default_album_art = ImageTk.PhotoImage(pil_img)
                      # Still store original PhotoImage in self.icons if needed? Maybe not.
                      self.icons[name] = self.default_album_art # Use the resized one directly
                 else:
                      # Load standard icons
                      img = PhotoImage(file=fpath)
                      self.icons[name] = img # Store PhotoImage if successful

            except FileNotFoundError:
                 # Don't print error if it's just missing, fallback will be used
                 missing_icons.append(filename)
                 if name == 'placeholder': # Create dummy if placeholder is missing
                     pil_img = Image.new('RGBA', ALBUM_ART_SIZE, (200, 200, 200, 255)) # Gray placeholder
                     self.default_album_art = ImageTk.PhotoImage(pil_img)
                     self.icons[name] = self.default_album_art
            except Exception as e:
                 print(f"Error loading icon '{filename}': {e}. Using text fallback.")
                 missing_icons.append(f"{filename} (Error: {e})")
                 if name == 'placeholder': # Create dummy on other errors too
                     if not self.default_album_art: # Only if not already created by FileNotFoundError
                        pil_img = Image.new('RGBA', ALBUM_ART_SIZE, (200, 200, 200, 255)) # Gray placeholder
                        self.default_album_art = ImageTk.PhotoImage(pil_img)
                        self.icons[name] = self.default_album_art

        if missing_icons:
             print(f"Note: Could not load icons: {', '.join(missing_icons)}. Using text fallbacks.")

    # --- Helper to configure button with icon or text ---
    def configure_button_icon(self, button, icon_name):
        """Sets button image if icon exists, otherwise sets text from fallbacks."""
        if icon_name in self.icons and isinstance(self.icons[icon_name], PhotoImage):
             button.config(image=self.icons[icon_name], text="") # Clear text if image is set
        else:
             fallback = self.icon_fallbacks.get(icon_name, "?") # Get fallback text, default to "?"
             button.config(image="", text=fallback, font=FONT_BUTTON_FALLBACK, padx=5, pady=2) # Clear image, set text
             # Adjust padding for text buttons

    # --- UI Creation (uses configure_button_icon) ---
    def create_ui(self):
        main_frame = tk.Frame(self.root, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # --- Screen Area (Top Section) ---
        screen_area = tk.Frame(main_frame, bg=BG_COLOR)
        screen_area.pack(fill=tk.X, pady=(0, 10))
        screen_area.columnconfigure(1, weight=1)

        # Album Art (ensure default art exists)
        art_image = self.default_album_art if self.default_album_art else None
        self.album_art_label = tk.Label(screen_area, bg=SCREEN_BG, image=art_image, width=ALBUM_ART_SIZE[0], height=ALBUM_ART_SIZE[1])
        if not art_image: # Fallback if even dummy creation failed
             self.album_art_label.config(text="Art", width=12, height=6)
        self.album_art_label.grid(row=0, column=0, rowspan=4, sticky='nw', padx=(0, 10), pady=5)

        # Track Info Labels (same as before)
        self.track_title_label = tk.Label(screen_area, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_SCREEN)
        self.track_title_label.grid(row=0, column=1, sticky='ew', padx=5)
        self.track_artist_label = tk.Label(screen_area, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_METADATA)
        self.track_artist_label.grid(row=1, column=1, sticky='ew', padx=5)
        self.track_album_label = tk.Label(screen_area, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_METADATA)
        self.track_album_label.grid(row=2, column=1, sticky='ew', padx=5)

        # Progress Bar & Time (same as before)
        progress_time_frame = tk.Frame(screen_area, bg=SCREEN_BG)
        progress_time_frame.grid(row=3, column=1, sticky='ew', padx=5, pady=(2, 0))
        progress_time_frame.columnconfigure(1, weight=1)
        self.current_time_label = tk.Label(progress_time_frame, text="00:00", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_TIME)
        self.current_time_label.grid(row=0, column=0, sticky='w')
        self.progress_bar = ttk.Progressbar(progress_time_frame, orient=tk.HORIZONTAL, length=100, mode='determinate', style="custom.Horizontal.TProgressbar")
        self.progress_bar.grid(row=0, column=1, sticky='ew', padx=5)
        self.total_time_label = tk.Label(progress_time_frame, text="/ 00:00", anchor='e', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_TIME)
        self.total_time_label.grid(row=0, column=2, sticky='e')

        border_frame = tk.Frame(screen_area, bg=SCREEN_BG, bd=1, relief=tk.SOLID)
        border_frame.place(relx=0, rely=0, relwidth=1, relheight=1); border_frame.lower()

        # --- Search Bar (uses configure_button_icon) ---
        search_frame = tk.Frame(main_frame, bg=BG_COLOR)
        search_frame.pack(fill=tk.X, pady=(5, 5))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30, font=FONT_MAIN)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", self.search_playlist_action)
        # self.search_entry.bind("<KeyRelease>", self.search_as_you_type) # Optional

        self.search_button = ttk.Button(search_frame, command=self.search_playlist_action) # Use ttk button
        self.configure_button_icon(self.search_button, 'search') # Configure with icon/text
        self.search_button.config(width=8) # Keep width for text fallback
        self.search_button.pack(side=tk.LEFT, padx=(0,5))

        self.clear_search_button = ttk.Button(search_frame, command=self.clear_search_action)
        self.configure_button_icon(self.clear_search_button, 'clear_search')
        self.clear_search_button.config(width=6)
        self.clear_search_button.pack(side=tk.LEFT)

        # --- Playlist Area (same as before) ---
        list_frame = tk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.playlist_box = tk.Listbox(
            list_frame, bg=SCREEN_BG, fg=TEXT_COLOR, selectbackground=SELECT_BG,
            selectforeground=TEXT_COLOR, font=FONT_LISTBOX, activestyle='none',
            highlightthickness=0, bd=0, relief=tk.FLAT, yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.playlist_box.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.playlist_box.bind("<Double-Button-1>", self.play_selected)
        list_frame.config(bd=1, relief=tk.SOLID)

        # --- Control Area (uses configure_button_icon) ---
        control_frame = tk.Frame(main_frame, bg=BG_COLOR)
        control_frame.pack(fill=tk.X)
        self.volume_scale = ttk.Scale(control_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.set_volume, style="custom.Horizontal.TScale")
        self.volume_scale.set(70); pygame.mixer.music.set_volume(0.7)
        self.volume_scale.pack(fill=tk.X, pady=(0, 5))

        button_frame = tk.Frame(control_frame, bg=BG_COLOR)
        button_frame.pack()
        button_opts = {'bg': BUTTON_BG, 'activebackground': ACTIVE_BUTTON_BG, 'relief': tk.FLAT, 'bd': 0, 'width': 35, 'height': 35}
        padx = 5

        self.shuffle_button = tk.Button(button_frame, **button_opts, command=self.toggle_shuffle)
        self.update_shuffle_button()
        self.shuffle_button.pack(side=tk.LEFT, padx=padx)

        self.prev_button = tk.Button(button_frame, **button_opts, command=self.prev_track)
        self.configure_button_icon(self.prev_button, 'previous')
        self.prev_button.pack(side=tk.LEFT, padx=padx)

        self.play_pause_button = tk.Button(button_frame, **button_opts, command=self.toggle_play_pause)
        self.play_pause_button.config(width=45, height=45) # Larger center button
        self.update_play_pause_button() # Must call *after* creation and config
        self.play_pause_button.pack(side=tk.LEFT, padx=padx)

        self.next_button = tk.Button(button_frame, **button_opts, command=self.next_track)
        self.configure_button_icon(self.next_button, 'next')
        self.next_button.pack(side=tk.LEFT, padx=padx)

        self.repeat_button = tk.Button(button_frame, **button_opts, command=self.cycle_repeat_mode)
        self.update_repeat_button()
        self.repeat_button.pack(side=tk.LEFT, padx=padx)

        # Stop button is omitted for cleaner look, like modern players

        # --- Configure ttk styles ---
        style = ttk.Style()
        # (Style config same as previous version - TProgressbar, TScale, Treeview, TScrollbar, TButton)
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

            # Style for TTK Buttons (Search, Clear Search, Browser buttons)
            style.configure("TButton", padding=5, background=BUTTON_BG, relief=tk.FLAT, font=FONT_MAIN)
            style.map("TButton", background=[('active', ACTIVE_BUTTON_BG)])

        except tk.TclError as e:
            print(f"ttk themes/styles not fully available. Using default. Error: {e}")

    # --- UI Update Helpers (use configure_button_icon) ---
    def update_play_pause_button(self):
        icon_name = 'pause' if self.playing_state == "playing" else 'play'
        self.configure_button_icon(self.play_pause_button, icon_name)

    def update_shuffle_button(self):
        icon_name = 'shuffle_on' if self.is_shuffled else 'shuffle_off'
        self.configure_button_icon(self.shuffle_button, icon_name)

    def update_repeat_button(self):
        if self.repeat_mode == REPEAT_ONE: icon_name = 'repeat_one'
        elif self.repeat_mode == REPEAT_ALL: icon_name = 'repeat_all'
        else: icon_name = 'repeat_off'
        self.configure_button_icon(self.repeat_button, icon_name)

    # --- Error/Info display with optional parent ---
    def show_error(self, title, message, parent=None):
        target = parent if parent else self.root
        target.after(0, lambda: messagebox.showerror(title, message, parent=parent))
    def show_warning(self, title, message, parent=None):
        target = parent if parent else self.root
        target.after(0, lambda: messagebox.showwarning(title, message, parent=parent))
    def show_info(self, title, message, parent=None):
        target = parent if parent else self.root
        target.after(0, lambda: messagebox.showinfo(title, message, parent=parent))

    # --- File Browser Methods (Paste previously added methods here) ---
    # open_file_browser, populate_browser, browser_navigate_up,
    # browser_item_activated, browser_add_selected, browser_add_folder
    # (Ensure they use the updated show_error etc. with parent argument)
    # --- Paste Browser Methods Start ---
    def open_file_browser(self):
        if self.browser_window and self.browser_window.winfo_exists():
             self.browser_window.lift()
             return

        self.browser_window = tk.Toplevel(self.root)
        self.browser_window.title("Browse Music")
        self.browser_window.geometry("400x450")
        self.browser_window.configure(bg=BG_COLOR)
        self.browser_window.transient(self.root)
        self.browser_window.grab_set()

        path_frame = tk.Frame(self.browser_window, bg=BG_COLOR)
        path_frame.pack(fill=tk.X, padx=5, pady=5)

        up_button = ttk.Button(path_frame, text="Up", width=5, command=self.browser_navigate_up)
        up_button.pack(side=tk.LEFT, padx=(0, 5))

        self.current_path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=self.current_path_var, state='readonly')
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tree_frame = tk.Frame(self.browser_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))

        tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.browser_tree = ttk.Treeview(
            tree_frame, columns=("fullpath",), displaycolumns="",
            yscrollcommand=tree_scrollbar.set, selectmode='extended',
            style="custom.Treeview"
        )
        tree_scrollbar.config(command=self.browser_tree.yview)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.browser_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.browser_tree.bind("<Double-1>", self.browser_item_activated)

        self.tree_icons = {}
        if 'folder' in self.icons and isinstance(self.icons['folder'], PhotoImage):
             self.tree_icons['folder'] = self.icons['folder']
        if 'file' in self.icons and isinstance(self.icons['file'], PhotoImage):
             self.tree_icons['file'] = self.icons['file']

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

        try:
            start_path = os.path.expanduser("~")
            if not os.path.isdir(start_path): # Fallback if home dir invalid
                 start_path = os.path.abspath(".")
        except Exception:
             start_path = os.path.abspath(".") # Further fallback

        self.populate_browser(start_path)

        # Center window
        self.browser_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (self.browser_window.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (self.browser_window.winfo_height() // 2)
        self.browser_window.geometry(f'+{x}+{y}')

    def populate_browser(self, path):
        try:
             if not os.path.isdir(path):
                 self.show_warning("Invalid Path", f"Cannot browse: {path}", parent=self.browser_window)
                 return
             abs_path = os.path.abspath(path)
             self.current_path_var.set(abs_path)
        except OSError as e:
             self.show_error("Path Error", f"Cannot access path properties:\n{e}", parent=self.browser_window)
             return # Don't proceed if path itself is bad

        for i in self.browser_tree.get_children():
            self.browser_tree.delete(i)

        items = []
        try:
            items = os.listdir(path)
            items.sort(key=str.lower)
        except OSError as e:
            self.show_error("Permission Error", f"Cannot read directory:\n{e}", parent=self.browser_window)
            return

        folders, files = [], []
        for item in items:
             full_item_path = os.path.join(path, item)
             try:
                 if os.path.isdir(full_item_path):
                     folders.append((item, full_item_path))
                 elif item.lower().endswith(SUPPORTED_FORMATS) and os.path.isfile(full_item_path):
                     files.append((item, full_item_path))
             except OSError as e:
                 print(f"Skipping due to access error: {full_item_path} ({e})")
                 continue

        folder_icon = self.tree_icons.get('folder')
        for name, fullpath in folders:
            try:
                 self.browser_tree.insert('', tk.END, text=f" {name}", values=(fullpath,), image=folder_icon, tags=('folder',))
            except Exception as e: print(f"Error inserting folder {name}: {e}")

        file_icon = self.tree_icons.get('file')
        for name, fullpath in files:
            try:
                 self.browser_tree.insert('', tk.END, text=f" {name}", values=(fullpath,), image=file_icon, tags=('file',))
            except Exception as e: print(f"Error inserting file {name}: {e}")

    def browser_navigate_up(self):
        current_path = self.current_path_var.get()
        parent_path = os.path.dirname(current_path)
        if parent_path != current_path:
            self.populate_browser(parent_path)

    def browser_item_activated(self, event):
        item_id = self.browser_tree.focus()
        if not item_id: return
        try:
            item_tags = self.browser_tree.item(item_id, "tags")
            item_path = self.browser_tree.item(item_id, "values")[0]

            if 'folder' in item_tags:
                self.populate_browser(item_path)
            elif 'file' in item_tags:
                self.add_files_to_playlist([item_path])
                self.show_info("File Added", f"{os.path.basename(item_path)} added.", parent=self.browser_window)
        except IndexError:
            print("Error getting item data on activation.")
            self.show_error("Error", "Failed to process item activation.", parent=self.browser_window)
        except Exception as e:
             print(f"Error handling browser item activation: {e}")
             self.show_error("Error", f"Could not process item activation:\n{e}", parent=self.browser_window)


    def browser_add_selected(self):
        selected_items = self.browser_tree.selection()
        files_to_add = []
        if not selected_items:
             self.show_warning("No Selection", "No items selected in the browser.", parent=self.browser_window)
             return
        try:
            for item_id in selected_items:
                item_tags = self.browser_tree.item(item_id, "tags")
                if 'file' in item_tags:
                    item_path = self.browser_tree.item(item_id, "values")[0]
                    # Check existence before adding
                    if os.path.isfile(item_path):
                        files_to_add.append(item_path)
                    else:
                         print(f"Skipping missing file from selection: {item_path}")
        except IndexError:
             print("Error reading selected item data.")
             self.show_error("Error", "Could not read selected item data.", parent=self.browser_window)
             return
        except Exception as e:
             print(f"Error processing selected items: {e}")
             self.show_error("Error", f"Could not process selection:\n{e}", parent=self.browser_window)
             return

        if files_to_add:
            self.add_files_to_playlist(files_to_add)
            self.show_info("Files Added", f"{len(files_to_add)} file(s) added.", parent=self.browser_window)
        elif selected_items: # Items were selected, but none were valid music files
            self.show_warning("No Music Files", "Selected items did not contain supported music files.", parent=self.browser_window)
        # If !files_to_add and !selected_items, the initial warning was already shown.

    def browser_add_folder(self):
        current_path = self.current_path_var.get()
        files_to_add = []
        try:
            for item in os.listdir(current_path):
                if item.lower().endswith(SUPPORTED_FORMATS):
                    filepath = os.path.join(current_path, item)
                    if os.path.isfile(filepath): # Check existence and if it's a file
                         files_to_add.append(filepath)
        except OSError as e:
            self.show_error("Error Reading Folder", f"Could not read folder contents:\n{e}", parent=self.browser_window)
            return
        except Exception as e:
            self.show_error("Error", f"An unexpected error occurred while scanning folder:\n{e}", parent=self.browser_window)
            return

        if files_to_add:
             files_to_add.sort()
             self.add_files_to_playlist(files_to_add)
             self.show_info("Folder Added", f"{len(files_to_add)} file(s) from folder added.", parent=self.browser_window)
        else:
             self.show_warning("Empty Folder", "No supported music files found in this folder.", parent=self.browser_window)
    # --- Paste Browser Methods End ---


    # --- Playlist Management (robust file checking) ---
    def _repopulate_listbox(self, path_list=None):
        self.playlist_box.delete(0, tk.END)
        if path_list is None:
            path_list = self.playlist

        self.listbox_path_map = {}
        invalid_count = 0
        for i, filepath in enumerate(path_list):
            # Basic check during repopulation (optional, can slow down large lists)
            # if not os.path.exists(filepath):
            #     display_name = f"[Missing] {os.path.basename(filepath)}"
            #     invalid_count += 1
            # else:
            #     display_name = os.path.basename(filepath)
            display_name = os.path.basename(filepath) # Keep it simple for speed
            self.playlist_box.insert(tk.END, f"{i+1}. {display_name}")
            self.listbox_path_map[i] = filepath
        # if invalid_count > 0:
        #     print(f"Warning: {invalid_count} missing files detected during listbox refresh.")

    def add_files_to_playlist(self, files_to_add):
        newly_added_paths = []
        skipped_count = 0
        for filepath in files_to_add:
            # Ensure path is absolute and normalized for consistency
            abs_path = os.path.abspath(filepath)
            if not os.path.exists(abs_path): # Check before adding to original list
                 print(f"Skipping non-existent file: {abs_path}")
                 skipped_count += 1
                 continue
            if abs_path not in self.original_playlist_order:
                self.original_playlist_order.append(abs_path)
                newly_added_paths.append(abs_path)

        if skipped_count > 0:
             self.show_warning("Files Skipped", f"{skipped_count} file(s) were not found and were skipped.")

        if not newly_added_paths:
            if skipped_count == 0: # Only show if nothing was skipped either
                 print("No new valid files to add.")
            return

        # Update the view
        self._apply_filters_and_shuffle()

        # Auto-select first track if playlist was empty and now isn't
        if len(self.playlist) == len(newly_added_paths) and newly_added_paths and self.playing_state == "stopped":
             self.current_track_index = 0
             self.select_listbox_item(0)
             self.preload_track_info(0)


    def preload_track_info(self, listbox_index):
         if 0 <= listbox_index < self.playlist_box.size():
             filepath = self.listbox_path_map.get(listbox_index)
             if filepath:
                 # Check existence *before* getting metadata
                 if not os.path.exists(filepath):
                      self.show_warning("File Missing", f"Cannot load info: File not found\n{os.path.basename(filepath)}")
                      self.update_track_display(title=f"[Missing] {os.path.basename(filepath)}", artist="", album="")
                      self.update_album_art({'art_data': None}) # Reset art
                      return

                 metadata = self.get_track_metadata(filepath) # Safe to call now
                 self.current_track_duration = metadata.get('duration', 0)
                 self.update_track_display(metadata['title'], metadata['artist'], metadata['album'])
                 self.update_album_art(metadata)
                 self.progress_bar['value'] = 0
                 self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100
             else:
                  # This case (valid index but no path in map) should ideally not happen
                  print(f"Error: No path found for listbox index {listbox_index}")
                  self.update_track_display(clear=True)
         else:
             self.update_track_display(clear=True) # Clear if index out of bounds

    # --- Playlist Loading/Saving (with error handling) ---
    def load_playlist_dialog(self):
        filepath = filedialog.askopenfilename(
            title="Load Playlist",
            filetypes=[("M3U Playlist", "*.m3u"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath: return

        paths = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                paths = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        except FileNotFoundError:
            self.show_error("Load Error", f"Playlist file not found:\n{filepath}")
            return
        except UnicodeDecodeError:
            self.show_error("Load Error", "Could not decode playlist file.\nPlease ensure it's UTF-8 encoded.")
            return
        except OSError as e:
            self.show_error("Load Error", f"Could not read playlist file:\n{e}")
            return
        except Exception as e:
            self.show_error("Load Error", f"An unexpected error occurred:\n{e}")
            traceback.print_exc() # Log detailed error
            return

        if paths:
            # Filter out paths that don't exist *at load time*
            existing_paths = [p for p in paths if os.path.exists(p)]
            skipped = len(paths) - len(existing_paths)
            if skipped > 0:
                 self.show_warning("Files Skipped", f"{skipped} file(s) from the playlist were not found and skipped.")

            if existing_paths:
                self.stop_track()
                self.playlist = []
                self.original_playlist_order = []
                self.current_track_index = -1
                self.add_files_to_playlist(existing_paths) # Adds the verified paths
                self.show_info("Playlist Loaded", f"Loaded {len(existing_paths)} tracks.")
            elif paths: # Paths were read, but none exist
                self.show_warning("Empty Playlist", "All files listed in the playlist could not be found.")
            else: # File was empty or only comments
                self.show_warning("Empty Playlist", "The selected file contained no valid paths.")
        else:
            self.show_warning("Empty Playlist", "The selected file contained no valid paths.")


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
                f.write("#EXTM3U\n")
                for path in self.original_playlist_order:
                    f.write(path + "\n")
            self.show_info("Playlist Saved", f"Playlist saved to:\n{filepath}")
        except OSError as e:
            self.show_error("Save Error", f"Could not write playlist file:\n{e}")
        except Exception as e:
            self.show_error("Save Error", f"An unexpected error occurred:\n{e}")
            traceback.print_exc()


    # --- Metadata fetching with file check ---
    def get_track_metadata(self, filepath):
        # Check file existence *first*
        if not os.path.exists(filepath):
             print(f"Metadata fetch skipped: File not found at {filepath}")
             return {'title': f"[Missing] {os.path.basename(filepath)}", 'artist': "", 'album': "", 'duration': 0, 'art_data': None}

        # Proceed with metadata reading (same logic as before)
        metadata = {'title': os.path.basename(filepath), 'artist': 'Unknown Artist', 'album': 'Unknown Album', 'duration': 0, 'art_data': None}
        try:
            ext = os.path.splitext(filepath)[1].lower()
            audio = None; art_data = None
            # --- MP3 ---
            if ext == '.mp3':
                try: audio = MP3(filepath, ID3=ID3)
                except ID3NoHeaderError: audio = MP3(filepath)
                if audio and audio.tags:
                    metadata['title'] = str(audio.tags.get('TIT2', [metadata['title']])[0])
                    metadata['artist'] = str(audio.tags.get('TPE1', [metadata['artist']])[0])
                    metadata['album'] = str(audio.tags.get('TALB', [metadata['album']])[0])
                    apic_frames = audio.tags.getall('APIC')
                    if apic_frames: art_data = apic_frames[0].data
            # --- Ogg ---
            elif ext == '.ogg':
                audio = OggVorbis(filepath)
                if audio:
                    metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                    metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
                    metadata['album'] = str(audio.get('album', [metadata['album']])[0])
                    pictures = audio.get('metadata_block_picture')
                    if pictures:
                         try:
                             # Assuming mutagen provides raw data directly for Ogg/FLAC Picture
                             from mutagen.flac import Picture
                             picture_info = Picture(pictures[0])
                             art_data = picture_info.data
                         except Exception as e: print(f"Error parsing Ogg picture block: {e}")
            # --- FLAC ---
            elif ext == '.flac':
                audio = FLAC(filepath)
                if audio:
                    metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                    metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
                    metadata['album'] = str(audio.get('album', [metadata['album']])[0])
                    if audio.pictures: art_data = audio.pictures[0].data
            # --- WAV ---
            elif ext == '.wav': audio = WAVE(filepath)

            # --- Duration & Art ---
            if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                 metadata['duration'] = int(audio.info.length)
            metadata['art_data'] = art_data

            # --- Cleanup ---
            if not metadata['title'] or metadata['title'].startswith("[Missing]"):
                 metadata['title'] = os.path.basename(filepath) # Ensure valid title if possible
            if not metadata['artist']: metadata['artist'] = 'Unknown Artist'
            if not metadata['album']: metadata['album'] = 'Unknown Album'

        except MutagenError as e: print(f"Mutagen error reading {filepath}: {e}")
        except FileNotFoundError: # Should be caught earlier, but handle defensively
             metadata.update({'title': f"[Missing] {os.path.basename(filepath)}", 'artist': "", 'album': "", 'duration': 0, 'art_data': None})
        except Exception as e:
             print(f"Unexpected error reading metadata for {filepath}: {e}")
             traceback.print_exc()

        return metadata

    # --- Playback with file check and removal option ---
    def play_track(self, listbox_index):
        if not self.playlist or not (0 <= listbox_index < len(self.playlist)):
            self.stop_track()
            return

        filepath = self.listbox_path_map.get(listbox_index)

        # --- Robust File Check ---
        if not filepath or not os.path.exists(filepath):
            basename = os.path.basename(filepath) if filepath else "Unknown"
            if messagebox.askyesno("File Missing",
                                   f"The file cannot be found:\n{basename}\n\n"
                                   f"Do you want to remove this track from the playlist?",
                                   icon='warning'):
                 # Remove the track if user agrees
                 self.remove_track_from_playlist(filepath, listbox_index)
                 # Optional: Automatically play the next track? Be careful with recursion/loops.
                 # For simplicity, just stop here. User can press play/next again.
                 self.stop_track() # Stop playback as the intended track failed
            else:
                 # User chose not to remove, just stop playback
                 self.show_warning("Playback Skipped", f"Skipped missing file:\n{basename}")
                 self.stop_track() # Still stop, as the selected track is invalid
            return # Exit play_track function

        # --- Proceed with playback if file exists ---
        # Update history (same logic as before)
        if self.current_track_index != -1 and self.current_track_index != listbox_index:
             # Check if the path is actually different, prevents adding same index on restart
             prev_path = self.listbox_path_map.get(self.current_track_index)
             if prev_path != filepath:
                  self.playback_history.append(self.current_track_index)
                  if len(self.playback_history) > 20: self.playback_history.pop(0)


        self.current_track_index = listbox_index # Update index *after* history

        try:
            # Metadata reading now happens *after* the definite file check
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
            self.show_error("Playback Error", f"Could not play file:\n{os.path.basename(filepath)}\n\nPygame Error: {e}")
            self.stop_track()
        except Exception as e:
             self.show_error("Playback Error", f"An unexpected error occurred:\n{e}")
             traceback.print_exc()
             self.stop_track()

    # --- Helper to remove a track ---
    def remove_track_from_playlist(self, filepath, listbox_index_hint):
        """Removes a given filepath from the playlist and refreshes the UI."""
        if not filepath: return

        removed = False
        # Remove from the source of truth
        if filepath in self.original_playlist_order:
             self.original_playlist_order.remove(filepath)
             print(f"Removed missing track: {filepath}")
             removed = True
        else:
             # This shouldn't happen if listbox_path_map is correct, but handle defensively
             print(f"Warning: Track {filepath} not found in original_playlist_order for removal.")
             return # Cannot proceed if not in original list

        # If the removed track was playing or selected, reset index
        if self.current_track_index == listbox_index_hint:
             self.current_track_index = -1 # Reset index as it's now invalid

        # Refresh the playlist view (applies filters/shuffle again)
        self._apply_filters_and_shuffle()

        # Optional: Select the item now at the removed index, if playlist not empty
        if self.playlist and listbox_index_hint >= 0:
             new_index = min(listbox_index_hint, len(self.playlist) - 1) # Select same or last index
             self.select_listbox_item(new_index)
             self.preload_track_info(new_index) # Show info for the newly selected track


    # --- Other Methods (Menu, Album Art, Sort, Playback Controls, Time, Display updates) ---
    # These remain largely the same as the previous "WMP features" version,
    # but benefit from the improved file existence checks in get_track_metadata, preload_track_info, play_track.
    # Ensure create_menu is called in __init__
    def create_menu(self):
        # (Menu creation code identical to previous version)
        menubar = Menu(self.root)
        self.root.config(menu=menubar)

        # File Menu
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Browse Files...", command=self.open_file_browser) # Use integrated browser
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

    def update_album_art(self, metadata):
        # (Identical to previous version)
        art_label = self.album_art_label
        art_data = metadata.get('art_data')

        # Use default art if current is None or invalid
        current_default_art = self.default_album_art if self.default_album_art else None

        if art_data:
            try:
                img_data = io.BytesIO(art_data)
                pil_img = Image.open(img_data)
                pil_img.thumbnail(ALBUM_ART_SIZE, Image.Resampling.LANCZOS)
                tk_img = ImageTk.PhotoImage(pil_img)
                art_label.config(image=tk_img)
                art_label.image = tk_img # Keep reference
            except Exception as e:
                print(f"Error processing album art: {e}")
                art_label.config(image=current_default_art)
                art_label.image = current_default_art
        else:
            art_label.config(image=current_default_art)
            art_label.image = current_default_art

    def sort_playlist_action(self, sort_key):
        # (Identical to previous version, relies on get_track_metadata checking file existence)
        if not self.original_playlist_order: return
        print(f"Sorting playlist by: {sort_key}")

        # --- Cache Metadata for Sorting (Optional but recommended for performance) ---
        # This part can be slow. Caching could help if sorting often.
        # For now, fetch fresh metadata each time.
        metadata_list = []
        sort_errors = 0
        missing_files = 0
        for i, path in enumerate(self.original_playlist_order):
             # get_track_metadata now handles missing files internally
             meta = self.get_track_metadata(path)
             if meta['title'].startswith("[Missing]"):
                  missing_files += 1
             metadata_list.append({
                 'path': path,
                 'title': meta.get('title', '').lower(),
                 'artist': meta.get('artist', '').lower(),
                 'album': meta.get('album', '').lower(),
                 'original_index': i
             })
        if missing_files > 0: print(f"Note: {missing_files} missing files encountered during sort metadata fetch.")

        # --- Perform Sort ---
        try:
             # Path sort doesn't need the metadata list
             if sort_key == 'path':
                  self.original_playlist_order.sort()
             # Metadata sort uses the fetched list
             elif sort_key in ('title', 'artist', 'album'):
                  # Handle potential missing keys gracefully during sort
                  metadata_list.sort(key=lambda x: x.get(sort_key, '')) # Default to empty string if key missing
                  self.original_playlist_order = [item['path'] for item in metadata_list]
             else:
                  print(f"Unknown sort key: {sort_key}")
                  return # Should not happen

        except Exception as e:
             self.show_error("Sort Error", f"Could not sort by {sort_key}:\n{e}")
             traceback.print_exc()
             return

        # --- Update UI ---
        print("Sort complete. Refreshing view.")
        self._apply_filters_and_shuffle() # Re-apply filters and refresh listbox


    def _apply_filters_and_shuffle(self):
        # (Identical to previous version)
        """Applies search filter and shuffle to the original_playlist_order."""
        temp_playlist = list(self.original_playlist_order) # Start with full original list

        # Apply search filter
        if self.current_search_term:
            # Simple search on filename for now, more robust search needs metadata
            temp_playlist = [
                path for path in temp_playlist
                if self.current_search_term in os.path.basename(path).lower()
                # Example metadata search (slower if metadata not cached):
                # meta = self.get_track_metadata(path) # Needs optimization!
                # if self.current_search_term in meta['title'].lower() or \
                #    self.current_search_term in meta['artist'].lower() or \
                #    self.current_search_term in meta['album'].lower()
            ]

        # Apply shuffle
        if self.is_shuffled:
            random.shuffle(temp_playlist)

        # Update the main playlist view
        self.playlist = temp_playlist
        playing_path = None
        current_lb_index = self.current_track_index # Store index before repopulating

        if self.playing_state != "stopped" and current_lb_index != -1:
             try:
                # Try to get the path of the currently playing track *before* repopulating
                 playing_path = self.listbox_path_map.get(current_lb_index)
             except Exception as e:
                 print(f"Error getting playing path before repopulate: {e}")
                 playing_path = None # Assume lost

        self._repopulate_listbox() # Update the Listbox UI (and self.listbox_path_map)

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
             # Don't preload here, it should already be displayed if it was playing
        else:
             # Playing track not found in new view OR wasn't playing
             if self.playing_state != "stopped" and playing_path:
                  print("Playing track disappeared from view after filter/sort.")
                  # Option: Stop playback, or let it finish? Let it finish.
                  self.current_track_index = -1 # Index is now invalid relative to view
             elif self.playlist: # If stopped/paused and playlist not empty, select first item
                  self.current_track_index = 0
                  self.select_listbox_item(0)
                  self.preload_track_info(0)
             else: # Playlist is empty
                  self.current_track_index = -1
                  self.update_track_display(clear=True) # Clear info display


    def toggle_shuffle(self):
        # (Identical to previous version)
        self.is_shuffled = not self.is_shuffled
        self.shuffle_menu_var.set(self.is_shuffled) # Update menu checkmark
        self.update_shuffle_button()
        self._apply_filters_and_shuffle() # Re-apply filters/shuffle to update view

    def set_repeat_mode(self):
        # (Identical to previous version)
        self.repeat_mode = self.repeat_menu_var.get()
        self.update_repeat_button()
        print(f"Repeat mode set to: {self.repeat_mode}")

    def cycle_repeat_mode(self):
        # (Identical to previous version)
        self.repeat_mode = (self.repeat_mode + 1) % 3 # Cycle through 0, 1, 2
        self.repeat_menu_var.set(self.repeat_mode) # Update menu radio button
        self.update_repeat_button()
        print(f"Repeat mode cycled to: {self.repeat_mode}")

    def toggle_play_pause(self):
        # (Identical to previous version)
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
        # (Identical to previous version)
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
        # (Identical to previous version)
        pygame.mixer.music.stop()
        # pygame.mixer.music.unload() # Optional
        self.playing_state = "stopped"
        self.update_play_pause_button()
        self.stop_time_update()
        self.update_track_display(clear=True) # Clear display
        self.progress_bar['value'] = 0
        # Keep current_track_index so play can resume from the stopped track if desired

    def next_track(self, force=False): # force=True ignores REPEAT_ONE
        # (Identical to previous version)
        if not self.playlist: return
        if self.playing_state == "stopped" and not force: return # Don't advance if explicitly stopped

        current_list_size = len(self.playlist)
        if current_list_size == 0: return

        next_index = -1

        if self.repeat_mode == REPEAT_ONE and not force:
            next_index = self.current_track_index # Repeat current track
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
        # (Identical to previous version)
        if not self.playlist: return

        # If playing for more than ~3 seconds, restart current track
        if self.playing_state == "playing" and pygame.mixer.music.get_pos() > 3000:
             if self.current_track_index != -1: # Make sure index is valid
                 self.play_track(self.current_track_index)
             return

        prev_index = -1
        current_list_size = len(self.playlist)
        if current_list_size == 0: return

        if self.is_shuffled and self.playback_history:
             # In shuffle mode, 'previous' goes to the last played track from history
             try:
                 prev_index = self.playback_history.pop()
                 # Sanity check if index is still valid in current listbox view
                 if not (0 <= prev_index < current_list_size and self.listbox_path_map.get(prev_index)):
                     print("History index invalid, reverting to standard previous.")
                     prev_index = -1 # Fallback to standard logic
             except IndexError:
                 print("Playback history empty for shuffle-previous.")
                 prev_index = -1 # Fallback if history somehow empty


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
        elif current_list_size > 0 and self.current_track_index != -1: # e.g., only one track, prev restarts it
             self.play_track(self.current_track_index)
        else:
             # Cannot determine previous track (e.g., empty playlist after checks)
             self.stop_track()


    def play_selected(self, event=None):
        # (Identical to previous version)
        try:
            selected_index = self.playlist_box.curselection()[0]
            self.play_track(selected_index)
        except IndexError:
            pass

    def set_volume(self, val):
        # (Identical to previous version)
        volume = float(val) / 100
        pygame.mixer.music.set_volume(volume)

    def format_time(self, seconds):
        # (Identical to previous version)
        if seconds < 0: seconds = 0
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def update_time(self):
        # (Identical to previous version, relies on next_track handling repeat modes)
        reschedule = True
        if self.playing_state == "playing":
            try:
                current_pos_ms = pygame.mixer.music.get_pos()
                if current_pos_ms == -1:
                     if not pygame.mixer.music.get_busy():
                         print("Song finished.")
                         # Pass force=False to allow REPEAT_ONE to work
                         self.next_track(force=False)
                         reschedule = False
                     else:
                         current_pos_sec = 0 # Treat as 0 if busy but pos is -1
                else:
                     current_pos_sec = current_pos_ms / 1000.0

                if reschedule:
                     current_time_str = self.format_time(current_pos_sec)
                     self.current_time_label.config(text=current_time_str)
                     if self.current_track_duration > 0:
                         progress_value = min(current_pos_sec, self.current_track_duration)
                         self.progress_bar['value'] = progress_value
                     else:
                          self.progress_bar['value'] = 0

            except pygame.error as e: print(f"Pygame error during time update: {e}"); self.stop_track(); reschedule = False
            except Exception as e: print(f"Unexpected error during time update: {e}"); traceback.print_exc(); reschedule = False
        else: reschedule = False

        if reschedule: self.update_seek_job = self.root.after(500, self.update_time)
        else: self.stop_time_update()

    def start_time_update(self):
         # (Identical to previous version)
         self.stop_time_update(); self.update_time()
    def stop_time_update(self):
        # (Identical to previous version)
        if self.update_seek_job: self.root.after_cancel(self.update_seek_job); self.update_seek_job = None

    def update_track_display(self, title="---", artist="---", album="---", clear=False):
        # (Identical to previous version)
        def trim(s, length=40): return (s[:length-1] + '…') if len(s) > length else s
        if clear:
            self.track_title_label.config(text="---")
            self.track_artist_label.config(text="---")
            self.track_album_label.config(text="---")
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text="/ 00:00")
            self.progress_bar['value'] = 0
            self.progress_bar['maximum'] = 100
            self.current_track_duration = 0
            art_image = self.default_album_art if self.default_album_art else None
            self.album_art_label.config(image=art_image)
            self.album_art_label.image = art_image
        else:
            self.track_title_label.config(text=trim(title if title else "Unknown Title"))
            self.track_artist_label.config(text=trim(artist if artist else "Unknown Artist", 35))
            self.track_album_label.config(text=trim(album if album else "Unknown Album", 35))
            total_time_str = self.format_time(self.current_track_duration)
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text=f"/ {total_time_str}")
            self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100
            # Album art updated separately

    def select_listbox_item(self, index):
        # (Identical to previous version)
         if 0 <= index < self.playlist_box.size():
             self.playlist_box.selection_clear(0, tk.END)
             self.playlist_box.selection_set(index)
             self.playlist_box.activate(index)
             self.playlist_box.see(index)

    def search_playlist_action(self, event=None):
        # (Identical to previous version)
        self.current_search_term = self.search_var.get().lower().strip()
        self._apply_filters_and_shuffle()

    def clear_search_action(self):
        # (Identical to previous version)
        self.search_var.set("")
        self.current_search_term = ""
        self._apply_filters_and_shuffle()

    def clear_playlist_action(self):
        # (Identical to previous version)
        if not self.playlist and not self.original_playlist_order: return
        if messagebox.askyesno("Clear Playlist", "Are you sure you want to remove all tracks?"):
            self.stop_track()
            self.playlist = []
            self.original_playlist_order = []
            self.current_track_index = -1
            self.playlist_box.delete(0, tk.END)
            self.listbox_path_map = {} # Clear map
            self.update_track_display(clear=True)
            self.progress_bar['value'] = 0
            self.current_search_term = ""
            self.search_var.set("")
            if self.is_shuffled: self.toggle_shuffle() # Turn off shuffle

    # --- Closing ---
    def on_closing(self):
        # (Identical to previous version)
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
    # Set application icon (optional, requires an .ico file on Windows, .png/.icns on others)
    try:
        icon_path = resource_path("app_icon.png") # Or .ico for windows
        if os.path.exists(icon_path):
             # For cross-platform icon setting:
             img = PhotoImage(file=icon_path)
             root.tk.call('wm', 'iconphoto', root._w, img)
             # For Windows specifically (if using .ico):
             # root.iconbitmap(default=icon_path)
        else:
             print("App icon not found.")
    except Exception as e:
        print(f"Could not set application icon: {e}")


    app = MediaPlayerApp(root)

    if app and root.winfo_exists():
        root.mainloop()
    else:
        print("Application failed to initialize properly.")