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
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # Default to script's directory
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

# --- Constants ---
# These will be moved into the MediaPlayerApp class

class MediaPlayerApp:
    # --- Class Attributes (Moved Constants) ---
    BG_COLOR = "#EAEAEA"
    SCREEN_BG = "white"
    TEXT_COLOR = "black"
    SELECT_BG = "#B0B0D0"
    # BUTTON_BG = BG_COLOR # Will be self.BG_COLOR
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
    ICON_PATH = "icons" # Relative path to icons folder
    ALBUM_ART_SIZE = (100, 100)

    REPEAT_OFF = 0
    REPEAT_ONE = 1
    REPEAT_ALL = 2
    # --- End Class Attributes ---

    def __init__(self, root):
        """
        Initializes the MediaPlayerApp.

        Args:
            root: The root Tkinter window.
        """
        self.root = root
        self.root.title("PyPod Plus")
        self.root.geometry("350x600")
        self.root.configure(bg=self.BG_COLOR)
        self.root.resizable(False, False)

        # --- Initialize more class constants that depend on others
        self.BUTTON_BG = self.BG_COLOR # Dependent constant for button backgrounds

        # --- Application State Variables ---
        # self.playlist: Holds the file paths of tracks currently displayed in the listbox.
        # This list can be filtered, sorted differently from original_playlist_order, or shuffled.
        self.playlist = []

        # self.original_playlist_order: Master list of all unique track file paths added by the user.
        # This list maintains the order after explicit sorting and is the source for filtering/shuffling.
        self.original_playlist_order = []

        # self.current_track_index: The index of the currently playing or selected track
        # *relative to the visible self.playlist* in the listbox. -1 if no track is selected/playing.
        self.current_track_index = -1

        # self.playback_history: Stores previous self.current_track_index values,
        # primarily used for the 'previous' button functionality when shuffle is active.
        self.playback_history = []

        self.playing_state = "stopped"  # Can be "stopped", "playing", or "paused"
        self.current_track_duration = 0 # Duration of the current track in seconds
        self.update_seek_job = None     # Stores the .after() job ID for UI updates of the seek bar
        self.browser_window = None      # Reference to the Toplevel file browser window, if open
        self.is_shuffled = False        # Boolean flag for shuffle mode
        self.repeat_mode = self.REPEAT_OFF # Current repeat mode (REPEAT_OFF, REPEAT_ONE, REPEAT_ALL)
        self.current_search_term = ""   # Stores the current search query string

        # self.listbox_path_map: Critical mapping where keys are integer indices of items
        # in the *visible* playlist_box, and values are the actual file paths. This is essential
        # because listbox indices change with filtering/shuffling, but we need the real path.
        self.listbox_path_map = {}

        # State tracking for optimization: these store the last applied filter/shuffle states
        # to avoid unnecessary UI refreshes if the underlying data or settings haven't changed.
        self._last_applied_search = ""
        self._last_applied_shuffle = self.is_shuffled

        # --- Load Icons ---
        self.icons = {} # Stores PhotoImage objects if loaded
        self.icon_fallbacks = {} # Stores fallback text for each icon name
        self.default_album_art = None # Will hold the loaded/created placeholder art
        self.load_icons()

        # --- Initialize Pygame Mixer ---
        try:
            pygame.mixer.init()
            # Set the event type for when music finishes
            self.MUSIC_END_EVENT = pygame.USEREVENT + 1
            pygame.mixer.music.set_endevent(self.MUSIC_END_EVENT)
            print("Pygame mixer initialized.")
        except pygame.error as e:
            # Show error before root might be destroyed
            messagebox.showerror("Pygame Error", f"Could not initialize audio mixer: {e}\nPlease ensure audio drivers are working.")
            self.root.destroy() # Destroy root if mixer fails
            return # Stop initialization

        # --- Build UI ---
        self.create_menu()
        self.create_styles() # Separate style creation
        self.create_ui()
        self._create_ui_helpers() # Call the new helper methods

        # --- Bind Events ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        # Start checking for the music end event
        self.check_music_end()

    def load_icons(self):
        """
        Loads icons from the self.ICON_PATH folder.
        Icons are defined in `icon_definitions` with their filenames and text fallbacks.
        If an icon file is not found or fails to load, a text fallback is used for buttons.
        A default placeholder album art is also loaded or created.
        """
        # Defines icon names, their corresponding filenames, and text for fallback.
        icon_definitions = {
            "play": ("play.png", "Play"), "pause": ("pause.png", "Pause"),
            "next": ("next.png", ">>"), "previous": ("previous.png", "<<"),
            "stop": ("stop.png", "Stop"), "browse": ("folder.png", "Browse"),
            "folder": ("folder_icon.png", ""), "file": ("file_icon.png", ""),
            "shuffle_on": ("shuffle_on.png", "Shfl On"), "shuffle_off": ("shuffle_off.png", "Shfl Off"),
            "repeat_off": ("repeat_off.png", "Rpt Off"), "repeat_one": ("repeat_one.png", "Rpt One"),
            "repeat_all": ("repeat_all.png", "Rpt All"),
            "placeholder": ("placeholder.png", ""),
            "search": ("search.png", "Search"), "clear_search": ("clear_search.png", "Clear"),
        }
        missing_icons = []
        print(f"Looking for icons in: {os.path.abspath(self.ICON_PATH)}")

        for name, (filename, fallback_text) in icon_definitions.items():
            self.icon_fallbacks[name] = fallback_text
            try:
                 fpath = resource_path(os.path.join(self.ICON_PATH, filename))
                 if not os.path.exists(fpath): raise FileNotFoundError(f"Icon not found: {fpath}")

                 if name == 'placeholder':
                      # Resize placeholder immediately
                      pil_img = Image.open(fpath).resize(self.ALBUM_ART_SIZE, Image.Resampling.LANCZOS)
                      self.default_album_art = ImageTk.PhotoImage(pil_img)
                      self.icons[name] = self.default_album_art # Store the PhotoImage
                 else:
                      img = PhotoImage(file=fpath)
                      self.icons[name] = img

            except FileNotFoundError:
                 missing_icons.append(filename)
                 if name == 'placeholder' and not self.default_album_art: # Create dummy if missing and not already created
                      dummy_art = self._create_dummy_placeholder_art()
                      if dummy_art:
                           self.default_album_art = dummy_art
                           self.icons[name] = dummy_art
            except Exception as e:
                 print(f"Error loading icon '{filename}': {e}. Using text fallback.")
                 # Ensure traceback is printed for unexpected errors during loading
                 if not isinstance(e, (FileNotFoundError, tk.TclError)): # Don't trace known/common issues
                     traceback.print_exc()
                 missing_icons.append(f"{filename} (Error)")
                 if name == 'placeholder' and not self.default_album_art: # Create dummy on other errors too
                      dummy_art = self._create_dummy_placeholder_art()
                      if dummy_art:
                           self.default_album_art = dummy_art
                           self.icons[name] = dummy_art

        if missing_icons:
             print(f"Note: Could not load icons: {', '.join(missing_icons)}. Using text fallbacks where applicable.")
        # Final check for default album art
        if not self.default_album_art:
            print("Warning: Default album art could not be loaded or created. Album art display may fail.")
            # Attempt to create a final dummy if all else failed
            dummy_art = self._create_dummy_placeholder_art()
            if dummy_art:
                self.default_album_art = dummy_art
                # self.icons['placeholder'] = dummy_art # Should already be handled or not needed if loop finished


    def _create_dummy_placeholder_art(self):
        """
        Creates a fallback gray placeholder PhotoImage using PIL.
        This is used if the 'placeholder.png' icon is missing or if other icon loading errors occur
        and a default album art is needed.
        Returns:
            ImageTk.PhotoImage: The generated placeholder image, or None if creation fails.
        """
        try:
            pil_img = Image.new('RGBA', self.ALBUM_ART_SIZE, (200, 200, 200, 255)) # Simple gray placeholder
            return ImageTk.PhotoImage(pil_img)
        except Exception as img_e:
            print(f"Error creating dummy placeholder image: {img_e}")
            return None

    def configure_button_icon(self, button, icon_name):
        """Sets button image if icon exists, otherwise sets text fallback.
           Handles both tk.Button and ttk.Button correctly using styles for ttk."""
        if icon_name in self.icons and isinstance(self.icons[icon_name], PhotoImage):
            # Icon exists, apply it
            button.config(image=self.icons[icon_name], text="", width=0, height=0) # Let image dictate size
            # Reset style for ttk buttons to base if they were previously fallback
            if isinstance(button, ttk.Button):
                 button.configure(style="TButton") # Use configure for style change
        else:
            # Icon missing or failed to load, use fallback text
            fallback = self.icon_fallbacks.get(icon_name, "?")
            button.config(image="") # Clear image if any
            if isinstance(button, ttk.Button):
                # For ttk.Button, apply the fallback style
                button.configure(text=fallback, style="Fallback.TButton", width=0) # width=0 allows text to size
            else:
                # For tk.Button, configure directly
                button.config(text=fallback, font=self.FONT_BUTTON_FALLBACK, width=0, height=0, padx=5, pady=2)


    def create_menu(self):
        """Creates the application menu bar."""
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
        repeat_menu.add_radiobutton(label="Repeat Off", variable=self.repeat_menu_var, value=self.REPEAT_OFF, command=self.set_repeat_mode)
        repeat_menu.add_radiobutton(label="Repeat One", variable=self.repeat_menu_var, value=self.REPEAT_ONE, command=self.set_repeat_mode)
        repeat_menu.add_radiobutton(label="Repeat All", variable=self.repeat_menu_var, value=self.REPEAT_ALL, command=self.set_repeat_mode)
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

    def create_styles(self):
        """Configures ttk styles used in the application."""
        style = ttk.Style()
        try:
            # Use a theme that allows more customization if available
            current_theme = style.theme_use()
            print(f"Using ttk theme: {current_theme}")
            # Prefer 'clam' if available for better customization, but check existence first
            if 'clam' in style.theme_names(): style.theme_use('clam')

            # --- Define Styles ---
            # Base style for normal TTK Buttons (used by search/clear/browser)
            style.configure("TButton", padding=5, background=self.BUTTON_BG, relief=tk.FLAT, font=self.FONT_MAIN)
            style.map("TButton", background=[('active', self.ACTIVE_BUTTON_BG)])

            # Style specifically for TTK Buttons when using text fallback
            style.configure("Fallback.TButton", font=self.FONT_BUTTON_FALLBACK, padding=(5, 2)) # Use tuple for padding (LR, TB)
            # Inherit other properties from TButton or define explicitly
            style.map("Fallback.TButton", background=[('active', self.ACTIVE_BUTTON_BG)])

            # Progress bar style
            style.configure("custom.Horizontal.TProgressbar", troughcolor=self.PROGRESS_TROUGH, background=self.PROGRESS_BAR, thickness=8, borderwidth=0)
            # Scale (Volume) style
            style.configure("custom.Horizontal.TScale", background=self.BG_COLOR, troughcolor=self.SCREEN_BG, sliderlength=15)
            # Treeview style
            style.configure("custom.Treeview", background=self.SCREEN_BG, fieldbackground=self.SCREEN_BG, foreground=self.TEXT_COLOR, rowheight=22, font=self.FONT_MAIN)
            style.map('custom.Treeview', background=[('selected', self.SELECT_BG)], foreground=[('selected', self.TEXT_COLOR)])
            # Scrollbar style
            style.configure("TScrollbar", arrowcolor=self.TEXT_COLOR, borderwidth=0, troughcolor=self.BG_COLOR, background=self.BUTTON_BG)
            style.map("TScrollbar", background=[('active', self.ACTIVE_BUTTON_BG)])

        except tk.TclError as e:
            print(f"ttk themes/styles not fully available. Using default. Error: {e}")
        except Exception as e:
            print(f"Unexpected error configuring ttk styles: {e}")
            traceback.print_exc()


    def create_ui(self):
        """
        Creates the main parent frame for all UI elements.
        This frame is stored as `self.main_frame` and serves as the container for
        different sections of the player UI.
        """
        self.main_frame = tk.Frame(self.root, bg=self.BG_COLOR) # Main container for all UI
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    def _create_ui_helpers(self):
        """
        Orchestrates the creation of different UI sections by calling dedicated helper methods.
        This keeps the UI building process modular and organized.
        """
        self._create_screen_area(self.main_frame)
        self._create_search_bar(self.main_frame)
        self._create_playlist_area(self.main_frame)
        self._create_control_area(self.main_frame)

    def _create_screen_area(self, parent_frame):
        """
        Creates the top 'screen' area of the player.
        This includes album art, track title, artist, album labels,
        and the progress bar with time displays.
        Args:
            parent_frame: The tk.Frame to build this UI section into.
        """
        screen_area = tk.Frame(parent_frame, bg=self.BG_COLOR)
        screen_area.pack(fill=tk.X, pady=(0, 10))
        screen_area.columnconfigure(1, weight=1)

        # Album Art
        art_image = self.default_album_art # Use the pre-loaded/created one
        self.album_art_label = tk.Label(screen_area, bg=self.SCREEN_BG, image=art_image,
                                        width=self.ALBUM_ART_SIZE[0], height=self.ALBUM_ART_SIZE[1])
        if not art_image: # Fallback text if image creation totally failed
             self.album_art_label.config(text="Art", width=12, height=6)
        self.album_art_label.image = art_image # Keep reference even if None
        self.album_art_label.grid(row=0, column=0, rowspan=4, sticky='nsew', padx=(0, 10), pady=5) # Use nsew sticky

        # Track Info Labels
        self.track_title_label = tk.Label(screen_area, text="---", anchor='w', bg=self.SCREEN_BG, fg=self.TEXT_COLOR, font=self.FONT_SCREEN)
        self.track_title_label.grid(row=0, column=1, sticky='ew', padx=5)
        self.track_artist_label = tk.Label(screen_area, text="---", anchor='w', bg=self.SCREEN_BG, fg=self.TEXT_COLOR, font=self.FONT_METADATA)
        self.track_artist_label.grid(row=1, column=1, sticky='ew', padx=5)
        self.track_album_label = tk.Label(screen_area, text="---", anchor='w', bg=self.SCREEN_BG, fg=self.TEXT_COLOR, font=self.FONT_METADATA)
        self.track_album_label.grid(row=2, column=1, sticky='ew', padx=5)

        # Progress Bar & Time Frame
        progress_time_frame = tk.Frame(screen_area, bg=self.SCREEN_BG)
        progress_time_frame.grid(row=3, column=1, sticky='sew', padx=5, pady=(2, 0)) # Use sticky 's' to push down
        progress_time_frame.columnconfigure(1, weight=1)
        self.current_time_label = tk.Label(progress_time_frame, text="00:00", anchor='w', bg=self.SCREEN_BG, fg=self.TEXT_COLOR, font=self.FONT_TIME)
        self.current_time_label.grid(row=0, column=0, sticky='w')
        self.progress_bar = ttk.Progressbar(progress_time_frame, orient=tk.HORIZONTAL, length=100, mode='determinate', style="custom.Horizontal.TProgressbar")
        self.progress_bar.grid(row=0, column=1, sticky='ew', padx=5)
        self.total_time_label = tk.Label(progress_time_frame, text="/ 00:00", anchor='e', bg=self.SCREEN_BG, fg=self.TEXT_COLOR, font=self.FONT_TIME)
        self.total_time_label.grid(row=0, column=2, sticky='e')

        # Border around screen area
        border_frame = tk.Frame(screen_area, bg=self.SCREEN_BG, bd=1, relief=tk.SOLID)
        border_frame.place(x=0, y=0, relwidth=1, relheight=1) # Use x, y=0
        border_frame.lower() # Place behind content

    def _create_search_bar(self, parent_frame):
        """
        Creates the search bar section below the screen area.
        This includes the search entry field and search/clear buttons.
        Args:
            parent_frame: The tk.Frame to build this UI section into.
        """
        search_frame = tk.Frame(parent_frame, bg=self.BG_COLOR)
        search_frame.pack(fill=tk.X, pady=(5, 5))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30, font=self.FONT_MAIN)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind("<Return>", self.search_playlist_action)

        # Create ttk buttons first, then configure with icon/fallback
        ttk_button_opts = {"style": "TButton"} # Base style
        self.search_button = ttk.Button(search_frame, **ttk_button_opts, command=self.search_playlist_action)
        self.configure_button_icon(self.search_button, 'search')
        self.search_button.pack(side=tk.LEFT, padx=(0,5))

        self.clear_search_button = ttk.Button(search_frame, **ttk_button_opts, command=self.clear_search_action)
        self.configure_button_icon(self.clear_search_button, 'clear_search')
        self.clear_search_button.pack(side=tk.LEFT)

    def _create_playlist_area(self, parent_frame):
        """
        Creates the playlist display area.
        This includes the Listbox widget for showing tracks and its associated Scrollbar.
        Args:
            parent_frame: The tk.Frame to build this UI section into.
        """
        list_frame = tk.Frame(parent_frame) # Frame to hold listbox and scrollbar
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.playlist_box = tk.Listbox(
            list_frame, bg=self.SCREEN_BG, fg=self.TEXT_COLOR, selectbackground=self.SELECT_BG,
            selectforeground=self.TEXT_COLOR, font=self.FONT_LISTBOX, activestyle='none',
            highlightthickness=0, bd=0, relief=tk.FLAT, yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.playlist_box.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.playlist_box.bind("<Double-Button-1>", self.play_selected)
        list_frame.config(bd=1, relief=tk.SOLID)

    def _create_control_area(self, parent_frame):
        """
        Creates the bottom control area of the player.
        This includes the volume scale and playback control buttons (shuffle, prev, play/pause, next, repeat).
        Args:
            parent_frame: The tk.Frame to build this UI section into.
        """
        control_frame = tk.Frame(parent_frame, bg=self.BG_COLOR)
        control_frame.pack(fill=tk.X)
        self.volume_scale = ttk.Scale(control_frame, from_=0, to=100, orient=tk.HORIZONTAL, command=self.set_volume, style="custom.Horizontal.TScale")
        self.volume_scale.set(70); pygame.mixer.music.set_volume(0.7) # Set initial volume
        self.volume_scale.pack(fill=tk.X, pady=(0, 5))

        button_frame = tk.Frame(control_frame, bg=self.BG_COLOR)
        button_frame.pack()

        # Define options for standard tk Buttons
        tk_button_opts = {'bg': self.BUTTON_BG, 'activebackground': self.ACTIVE_BUTTON_BG,
                          'relief': tk.FLAT, 'bd': 0, 'width': 35, 'height': 35}
        padx = 5

        # Create tk Buttons first, then configure icons/fallbacks
        self.shuffle_button = tk.Button(button_frame, **tk_button_opts, command=self.toggle_shuffle)
        self.update_shuffle_button() # Sets icon/text based on state
        self.shuffle_button.pack(side=tk.LEFT, padx=padx)

        self.prev_button = tk.Button(button_frame, **tk_button_opts, command=self.prev_track)
        self.configure_button_icon(self.prev_button, 'previous')
        self.prev_button.pack(side=tk.LEFT, padx=padx)

        self.play_pause_button = tk.Button(button_frame, **tk_button_opts, command=self.toggle_play_pause)
        self.play_pause_button.config(width=45, height=45) # Larger center button
        self.update_play_pause_button() # Sets icon/text based on state
        self.play_pause_button.pack(side=tk.LEFT, padx=padx)

        self.next_button = tk.Button(button_frame, **tk_button_opts, command=self.next_track)
        self.configure_button_icon(self.next_button, 'next')
        self.next_button.pack(side=tk.LEFT, padx=padx)

        self.repeat_button = tk.Button(button_frame, **tk_button_opts, command=self.cycle_repeat_mode)
        self.update_repeat_button() # Sets icon/text based on state
        self.repeat_button.pack(side=tk.LEFT, padx=padx)

    # --- UI Update Helpers ---
    def update_play_pause_button(self):
        """Updates the Play/Pause button icon/text based on the playing state."""
        icon_name = 'pause' if self.playing_state == "playing" else 'play'
        self.configure_button_icon(self.play_pause_button, icon_name)

    def update_shuffle_button(self):
        """Updates the Shuffle button icon/text based on the shuffle state."""
        icon_name = 'shuffle_on' if self.is_shuffled else 'shuffle_off'
        self.configure_button_icon(self.shuffle_button, icon_name)

    def update_repeat_button(self):
        """Updates the Repeat button icon/text based on the repeat state."""
        if self.repeat_mode == self.REPEAT_ONE: icon_name = 'repeat_one'
        elif self.repeat_mode == self.REPEAT_ALL: icon_name = 'repeat_all'
        else: icon_name = 'repeat_off'
        self.configure_button_icon(self.repeat_button, icon_name)

    # --- Error/Info display ---
    # (Unchanged, already handles parent argument)
    def show_error(self, title, message, parent=None):
        target = parent if parent else self.root
        target.after(0, lambda: messagebox.showerror(title, message, parent=parent))
    def show_warning(self, title, message, parent=None):
        target = parent if parent else self.root
        target.after(0, lambda: messagebox.showwarning(title, message, parent=parent))
    def show_info(self, title, message, parent=None):
        target = parent if parent else self.root
        target.after(0, lambda: messagebox.showinfo(title, message, parent=parent))


    # --- File Browser Methods ---

    def _create_browser_path_frame(self, parent_window):
        """
        Creates the UI frame for path navigation in the file browser.
        Includes an 'Up' button and a non-editable Entry to display the current path.
        Args:
            parent_window: The Toplevel window of the file browser.
        Returns:
            tk.Frame: The created path frame.
        """
        path_frame = tk.Frame(parent_window, bg=self.BG_COLOR)
        path_frame.pack(fill=tk.X, padx=5, pady=5)

        up_button = ttk.Button(path_frame, text="Up", width=5, command=self.browser_navigate_up, style="TButton")
        up_button.pack(side=tk.LEFT, padx=(0, 5))

        self.current_path_var = tk.StringVar() # Used by populate_browser
        path_entry = ttk.Entry(path_frame, textvariable=self.current_path_var, state='readonly', font=self.FONT_MAIN)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return path_frame

    def _create_browser_tree_view(self, parent_window):
        """
        Creates the UI frame for the Treeview in the file browser.
        The Treeview lists files and folders, with a scrollbar.
        Args:
            parent_window: The Toplevel window of the file browser.
        Returns:
            tk.Frame: The created tree view frame.
        """
        tree_frame = tk.Frame(parent_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0,5))

        tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        self.browser_tree = ttk.Treeview(
            tree_frame, columns=("fullpath",), displaycolumns="",
            yscrollcommand=tree_scrollbar.set, selectmode='extended',
            style="custom.Treeview" # Uses style defined in create_styles
        )
        tree_scrollbar.config(command=self.browser_tree.yview)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.browser_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.browser_tree.bind("<Double-1>", self.browser_item_activated)
        return tree_frame

    def _create_browser_action_buttons(self, parent_window):
        """
        Creates the UI frame for action buttons at the bottom of the file browser.
        Includes buttons like "Add Selected", "Add All in Folder", "Clear Playlist", and "Close".
        Args:
            parent_window: The Toplevel window of the file browser.
        Returns:
            tk.Frame: The created action buttons frame.
        """
        action_frame = tk.Frame(parent_window, bg=self.BG_COLOR)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        add_file_button = ttk.Button(action_frame, text="Add Selected", command=self.browser_add_selected, style="TButton")
        add_file_button.pack(side=tk.LEFT, padx=2)

        add_folder_button = ttk.Button(action_frame, text="Add All in Folder", command=self.browser_add_folder, style="TButton")
        add_folder_button.pack(side=tk.LEFT, padx=2)

        clear_playlist_button = ttk.Button(action_frame, text="Clear Playlist", command=self.clear_playlist_action, style="TButton")
        clear_playlist_button.pack(side=tk.LEFT, padx=2)

        close_button = ttk.Button(action_frame, text="Close", command=self.browser_window.destroy, style="TButton")
        close_button.pack(side=tk.RIGHT, padx=2)
        return action_frame

    # --- Start Browser Methods ---
    def open_file_browser(self):
        """
        Opens a Toplevel window for browsing music files and folders.
        If the browser window already exists, it lifts it to the front.
        The UI components (path bar, tree view, action buttons) are created by helper methods.
        """
        if self.browser_window and self.browser_window.winfo_exists():
             self.browser_window.lift() # Bring to front if already open
             return

        self.browser_window = tk.Toplevel(self.root)
        self.browser_window.title("Browse Music")
        self.browser_window.geometry("400x450")
        self.browser_window.configure(bg=self.BG_COLOR)
        self.browser_window.transient(self.root)
        self.browser_window.grab_set()

        # Call helper methods to create UI components
        self._create_browser_path_frame(self.browser_window)
        self._create_browser_tree_view(self.browser_window)
        self._create_browser_action_buttons(self.browser_window)

        # Prepare icons for treeview (check if loaded)
        self.tree_icons = {} # This should be initialized here or in __init__ if browser is always available
        if 'folder' in self.icons and isinstance(self.icons['folder'], PhotoImage):
             self.tree_icons['folder'] = self.icons['folder']
        if 'file' in self.icons and isinstance(self.icons['file'], PhotoImage):
             self.tree_icons['file'] = self.icons['file']
        
        # Set initial path more robustly
        try:
            start_path = os.path.expanduser("~")
            if not os.path.isdir(start_path): # Fallback if home dir invalid or inaccessible
                 start_path = os.path.abspath(".")
        except Exception:
             start_path = os.path.abspath(".") # Further fallback

        self.populate_browser(start_path)

        # Center window relative to root
        self.browser_window.update_idletasks()
        try:
            root_x = self.root.winfo_x()
            root_y = self.root.winfo_y()
            root_w = self.root.winfo_width()
            root_h = self.root.winfo_height()
            win_w = self.browser_window.winfo_width()
            win_h = self.browser_window.winfo_height()
            x = root_x + (root_w // 2) - (win_w // 2)
            y = root_y + (root_h // 2) - (win_h // 2)
            self.browser_window.geometry(f'+{x}+{y}')
        except tk.TclError as e:
            print(f"Could not center browser window (main window might not be mapped yet): {e}")


    def populate_browser(self, path):
        """Fills the browser Treeview with contents of the given path."""
        try:
             if not os.path.isdir(path):
                 self.show_warning("Invalid Path", f"Cannot browse: {path}", parent=self.browser_window)
                 return
             abs_path = os.path.abspath(path)
             self.current_path_var.set(abs_path)
        except OSError as e:
             self.show_error("Path Error", f"Cannot access path properties:\n{e}", parent=self.browser_window)
             return

        # Clear existing tree items safely
        for i in self.browser_tree.get_children():
            try: self.browser_tree.delete(i)
            except tk.TclError: pass # Ignore if item already deleted

        items = []
        try:
            items = os.listdir(path)
            items.sort(key=str.lower)
        except OSError as e:
            self.show_error("Permission Error", f"Cannot read directory:\n{e}", parent=self.browser_window)
            return
        except Exception as e: # Catch other potential errors
            self.show_error("Error", f"Failed to list directory contents:\n{e}", parent=self.browser_window)
            return

        folders, files = [], []
        for item in items:
             full_item_path = os.path.join(path, item)
             try:
                 if os.path.isdir(full_item_path):
                     folders.append((item, full_item_path))
                 elif item.lower().endswith(self.SUPPORTED_FORMATS) and os.path.isfile(full_item_path):
                     files.append((item, full_item_path))
             except OSError as e: # Permission error on specific item
                 print(f"Skipping item due to access error: {full_item_path} ({e})")
                 continue
             except Exception as e: # Other errors accessing item properties
                 print(f"Error processing item {item}: {e}")
                 continue

        folder_icon = self.tree_icons.get('folder') # Get loaded icon image
        for name, fullpath in folders:
            try: # Insert folder items
                 self.browser_tree.insert('', tk.END, text=f" {name}", values=(fullpath,), image=folder_icon, tags=('folder',))
            except Exception as e: print(f"Error inserting folder item {name}: {e}")

        file_icon = self.tree_icons.get('file') # Get loaded icon image
        for name, fullpath in files:
            try: # Insert file items
                 self.browser_tree.insert('', tk.END, text=f" {name}", values=(fullpath,), image=file_icon, tags=('file',))
            except Exception as e: print(f"Error inserting file item {name}: {e}")

    def browser_navigate_up(self):
        """Navigates the browser view to the parent directory."""
        current_path = self.current_path_var.get()
        parent_path = os.path.dirname(current_path)
        # Check if parent is different and is a valid directory
        if parent_path != current_path and os.path.isdir(parent_path):
            self.populate_browser(parent_path)
        elif parent_path == current_path:
            print("Already at root directory.")
        else:
            self.show_warning("Navigation Error", f"Cannot navigate up to parent:\n{parent_path}", parent=self.browser_window)

    def browser_item_activated(self, event):
        """Handles double-click activation in the browser Treeview."""
        item_id = self.browser_tree.focus()
        if not item_id: return # No item focused
        try:
            item_info = self.browser_tree.item(item_id)
            item_tags = item_info.get("tags", [])
            item_values = item_info.get("values", [])

            if not item_values: # Ensure values list is not empty/malformed
                print(f"Error: No path value found for activated item {item_id}")
                return

            item_path = item_values[0] # Get full path

            if 'folder' in item_tags:
                self.populate_browser(item_path) # Navigate into folder
            elif 'file' in item_tags:
                # Add the single file on double-click
                self.add_files_to_playlist([item_path])
                self.show_info("File Added", f"{os.path.basename(item_path)} added.", parent=self.browser_window)
        except Exception as e:
             print(f"Error handling browser item activation: {e}")
             traceback.print_exc()
             self.show_error("Error", f"Could not process item activation:\n{e}", parent=self.browser_window)


    def browser_add_selected(self):
        """Adds selected music files from the browser to the main playlist."""
        selected_items = self.browser_tree.selection() # Get tuple of selected item IDs
        files_to_add = []
        if not selected_items:
             self.show_warning("No Selection", "No items selected in the browser.", parent=self.browser_window)
             return
        try:
            processed_count = 0
            skipped_missing = 0
            for item_id in selected_items:
                item_info = self.browser_tree.item(item_id)
                item_tags = item_info.get("tags", [])
                item_values = item_info.get("values", [])

                if 'file' in item_tags and item_values:
                    item_path = item_values[0]
                    processed_count += 1
                    # Check existence before adding
                    if os.path.isfile(item_path):
                        files_to_add.append(item_path)
                    else:
                        skipped_missing += 1
                        print(f"Skipping missing file from selection: {item_path}")
        except Exception as e:
             print(f"Error processing selected items: {e}")
             traceback.print_exc()
             self.show_error("Error", f"Could not process selection:\n{e}", parent=self.browser_window)
             return

        # Add the valid files found
        if files_to_add:
            self.add_files_to_playlist(files_to_add)
            msg = f"{len(files_to_add)} file(s) added."
            if skipped_missing > 0:
                msg += f"\n({skipped_missing} selected files were missing)"
            self.show_info("Files Added", msg, parent=self.browser_window)
        elif processed_count > 0: # Files were selected, but none were valid/existing music files
             msg = "Selected items did not contain supported music files."
             if skipped_missing > 0:
                  msg += f"\n({skipped_missing} were missing)"
             self.show_warning("No Music Files Added", msg, parent=self.browser_window)
        elif not selected_items: # Should be caught earlier, but defensive check
             self.show_warning("No Selection", "No items selected in the browser.", parent=self.browser_window)

    def browser_add_folder(self):
        """Adds all supported music files from the currently viewed folder."""
        current_path = self.current_path_var.get()
        if not current_path or not os.path.isdir(current_path):
            self.show_error("Invalid Path", "Cannot add folder, path is invalid.", parent=self.browser_window)
            return

        files_to_add = []
        try:
            for item in os.listdir(current_path):
                if item.lower().endswith(self.SUPPORTED_FORMATS):
                    filepath = os.path.join(current_path, item)
                    # Check if it's actually a file and exists
                    if os.path.isfile(filepath):
                         files_to_add.append(filepath)
        except OSError as e:
            self.show_error("Error Reading Folder", f"Could not read folder contents:\n{e}", parent=self.browser_window)
            return
        except Exception as e:
            self.show_error("Error", f"An unexpected error occurred while scanning folder:\n{e}", parent=self.browser_window)
            traceback.print_exc()
            return

        if files_to_add:
             files_to_add.sort(key=str.lower) # Sort files within the folder
             self.add_files_to_playlist(files_to_add)
             self.show_info("Folder Added", f"{len(files_to_add)} file(s) from folder added.", parent=self.browser_window)
        else:
             self.show_warning("Empty Folder", "No supported music files found in this folder.", parent=self.browser_window)
    # --- End Browser Methods ---


    # --- Playlist Management ---
    def _repopulate_listbox(self, path_list=None):
        """Helper to clear and refill the listbox from a given list of paths.
           Updates the crucial self.listbox_path_map."""
        start_time = time.time()
        self.playlist_box.delete(0, tk.END)
        if path_list is None:
            path_list = self.playlist # Default to the current view

        self.listbox_path_map = {} # Reset the map

        # Consider using list comprehension for slight speedup if needed
        # items_to_insert = [f"{i+1}. {os.path.basename(filepath)}" for i, filepath in enumerate(path_list)]
        # self.playlist_box.insert(tk.END, *items_to_insert) # Insert all at once? Check performance

        for i, filepath in enumerate(path_list):
            display_name = os.path.basename(filepath)
            self.playlist_box.insert(tk.END, f"{i+1}. {display_name}")
            self.listbox_path_map[i] = filepath # Map listbox index to file path

        end_time = time.time()
        # print(f"Repopulated listbox with {len(path_list)} items in {end_time - start_time:.4f} seconds.")


    def add_files_to_playlist(self, files_to_add):
        """Adds a list of valid file paths to the master playlist order and updates the view."""
        newly_added_paths = []
        skipped_count = 0
        duplicate_count = 0
        for filepath in files_to_add:
            try:
                # Ensure path is absolute and normalized for consistency
                abs_path = os.path.abspath(os.path.normpath(filepath))
                if not os.path.isfile(abs_path): # Use isfile which implies exists
                     print(f"Skipping non-existent or non-file path: {abs_path}")
                     skipped_count += 1
                     continue
                if abs_path not in self.original_playlist_order:
                    self.original_playlist_order.append(abs_path)
                    newly_added_paths.append(abs_path)
                else:
                     duplicate_count += 1
            except OSError as e: # Handle errors during path normalization/checking
                print(f"Error processing path '{filepath}': {e}")
                skipped_count += 1
            except Exception as e:
                print(f"Unexpected error adding path '{filepath}': {e}")
                traceback.print_exc()
                skipped_count += 1


        if skipped_count > 0:
             self.show_warning("Files Skipped", f"{skipped_count} path(s) could not be added or were invalid.")
        if duplicate_count > 0:
             print(f"{duplicate_count} duplicate tracks ignored.")

        if not newly_added_paths:
            if skipped_count == 0 and duplicate_count > 0:
                 self.show_info("No New Files", "The selected file(s) are already in the playlist.")
            elif skipped_count == 0 and duplicate_count == 0:
                 print("No valid, new files provided to add.")
            return # Nothing new was actually added

        # Update the view (applies filter/shuffle)
        self._apply_filters_and_shuffle()

        # Auto-select first track if playlist was previously empty
        if len(self.original_playlist_order) == len(newly_added_paths) and self.playing_state == "stopped":
            if self.playlist: # Check if the current view is not empty after filtering
                 self.current_track_index = 0
                 self.select_listbox_item(0)
                 self.preload_track_info(0)


    def preload_track_info(self, listbox_index):
         """Loads metadata for a track at the given listbox index without playing it."""
         if 0 <= listbox_index < self.playlist_box.size():
             filepath = self.listbox_path_map.get(listbox_index)
             if filepath:
                 # Check existence *before* getting metadata (get_track_metadata also checks, but good practice here too)
                 if not os.path.isfile(filepath):
                      self.show_warning("File Missing", f"Cannot load info: File not found\n{os.path.basename(filepath)}")
                      self.update_track_display(title=f"[Missing] {os.path.basename(filepath)}", artist="", album="")
                      self.update_album_art({'art_data': None}) # Reset art
                      self.progress_bar['value'] = 0
                      self.progress_bar['maximum'] = 100
                      return

                 # Use a thread to avoid blocking UI for metadata loading? (More complex)
                 # For now, load directly:
                 metadata = self.get_track_metadata(filepath) # Safe to call now
                 self.current_track_duration = metadata.get('duration', 0)
                 self.update_track_display(metadata['title'], metadata['artist'], metadata['album'])
                 self.update_album_art(metadata)
                 self.progress_bar['value'] = 0
                 self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100
             else:
                  print(f"Error: No path found for listbox index {listbox_index} in map.")
                  self.update_track_display(clear=True)
         else:
             # Index out of bounds, clear display
             self.update_track_display(clear=True)


    # --- Playlist Loading/Saving ---
    # (Unchanged, already includes reasonable error handling)
    def load_playlist_dialog(self):
        filepath = filedialog.askopenfilename(
            title="Load Playlist",
            filetypes=[("M3U Playlist", "*.m3u"), ("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not filepath: return

        paths = []
        try:
            # Try UTF-8 first, then fallback to default system encoding
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    paths = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            except UnicodeDecodeError:
                print("UTF-8 decode failed, trying default system encoding...")
                with open(filepath, 'r') as f: # Use system default encoding
                    paths = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        except FileNotFoundError:
            self.show_error("Load Error", f"Playlist file not found:\n{filepath}")
            return
        except OSError as e:
            self.show_error("Load Error", f"Could not read playlist file:\n{e}")
            return
        except Exception as e:
            self.show_error("Load Error", f"An unexpected error occurred while reading playlist:\n{e}")
            traceback.print_exc()
            return

        if paths:
            print(f"Read {len(paths)} lines from playlist.")
            # Filter out paths that don't exist *at load time*
            existing_paths = []
            skipped = 0
            for p in paths:
                abs_p = os.path.abspath(os.path.normpath(p)) # Normalize before check
                if os.path.isfile(abs_p):
                     existing_paths.append(abs_p)
                else:
                     print(f"Skipping missing/invalid path from playlist: {p}")
                     skipped += 1

            if skipped > 0:
                 self.show_warning("Files Skipped", f"{skipped} file(s) from the playlist were not found or invalid and were skipped.")

            if existing_paths:
                if messagebox.askyesno("Load Playlist", f"Found {len(existing_paths)} valid tracks. Replace current playlist?"):
                    self.stop_track()
                    self.playlist = []
                    self.original_playlist_order = []
                    self.current_track_index = -1
                    self.playback_history = [] # Clear history too
                    self.add_files_to_playlist(existing_paths) # Adds the verified paths
                    self.show_info("Playlist Loaded", f"Loaded {len(existing_paths)} tracks.")
            elif paths: # Paths were read, but none exist
                self.show_warning("Empty Playlist", "All files listed in the playlist could not be found or were invalid.")
            else: # File was empty or only comments
                self.show_warning("Empty Playlist", "The selected file contained no valid paths.")
        else:
            self.show_warning("Empty Playlist", "The selected file contained no valid paths.")


    def save_playlist_dialog(self):
        # (Unchanged, save logic is usually less error-prone)
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
                f.write("#EXTM3U\n") # Standard M3U header
                for path in self.original_playlist_order:
                    # Could add #EXTINF here with duration/title if metadata is cached
                    f.write(path + "\n")
            self.show_info("Playlist Saved", f"Playlist saved to:\n{filepath}")
        except OSError as e:
            self.show_error("Save Error", f"Could not write playlist file:\n{e}")
        except Exception as e:
            self.show_error("Save Error", f"An unexpected error occurred during save:\n{e}")
            traceback.print_exc()


    # --- Metadata fetching ---
    def get_track_metadata(self, filepath):
        """
        Reads metadata (title, artist, album, duration, album art) from a given audio file
        using the Mutagen library. Handles various audio formats (MP3, Ogg, FLAC, WAV).

        Args:
            filepath (str): The absolute path to the audio file.

        Returns:
            dict: A dictionary containing metadata. Defaults are provided if tags are missing
                  or if the file cannot be read. Includes 'art_data' which can be None.
        """
        # Check file existence first to avoid Mutagen errors on non-existent files
        if not os.path.isfile(filepath): # Use isfile for robustness
             print(f"Metadata fetch skipped: File not found or not a file: {filepath}")
             # Return a default structure indicating the file is missing
             return {'title': f"[Missing] {os.path.basename(filepath)}", 'artist': "", 'album': "", 'duration': 0, 'art_data': None}

        # Default metadata structure
        metadata = {'title': os.path.basename(filepath), 'artist': 'Unknown Artist', 'album': 'Unknown Album', 'duration': 0, 'art_data': None}
        try:
            ext = os.path.splitext(filepath)[1].lower() # Get file extension
            audio = None; art_data = None # Initialize

            # --- Format-specific metadata extraction ---
            if ext == '.mp3':
                try: audio = MP3(filepath, ID3=ID3)
                except ID3NoHeaderError: audio = MP3(filepath)
                if audio and audio.tags:
                    metadata['title'] = str(audio.tags.get('TIT2', [metadata['title']])[0])
                    metadata['artist'] = str(audio.tags.get('TPE1', [metadata['artist']])[0])
                    metadata['album'] = str(audio.tags.get('TALB', [metadata['album']])[0])
                    apic_frames = audio.tags.getall('APIC')
                    if apic_frames: art_data = apic_frames[0].data
            elif ext == '.ogg':
                audio = OggVorbis(filepath)
                if audio:
                    metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                    metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
                    metadata['album'] = str(audio.get('album', [metadata['album']])[0])
                    pictures = audio.get('metadata_block_picture')
                    if pictures:
                         try:
                             from mutagen.flac import Picture
                             picture_info = Picture(pictures[0]) # Assumes mutagen parses it
                             art_data = picture_info.data
                         except Exception as e: print(f"Error parsing Ogg picture block: {e}")
            elif ext == '.flac':
                audio = FLAC(filepath)
                if audio:
                    metadata['title'] = str(audio.get('title', [metadata['title']])[0])
                    metadata['artist'] = str(audio.get('artist', [metadata['artist']])[0])
                    metadata['album'] = str(audio.get('album', [metadata['album']])[0])
                    if audio.pictures: art_data = audio.pictures[0].data
            elif ext == '.wav': audio = WAVE(filepath)

            if audio and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                 metadata['duration'] = int(audio.info.length)
            metadata['art_data'] = art_data

            # Cleanup potentially empty tags
            if not metadata['title'] or metadata['title'].startswith("[Missing]"): metadata['title'] = os.path.basename(filepath)
            if not metadata['artist']: metadata['artist'] = 'Unknown Artist'
            if not metadata['album']: metadata['album'] = 'Unknown Album'

        except MutagenError as e: print(f"Mutagen error reading {filepath}: {e}")
        # FileNotFoundError should be caught by the initial check
        except Exception as e:
             print(f"Unexpected error reading metadata for {filepath}: {e}")
             traceback.print_exc()
             # Return defaults but indicate error?
             metadata['title'] += " (Meta Error)"

        return metadata

    # --- Playback ---
    def _validate_track_for_playback(self, listbox_index):
        """
        Validates if the track at listbox_index is playable before attempting to play.
        Checks for valid index, existing file path in map, and actual file existence.
        Prompts the user via a dialog if a file is missing, allowing removal from playlist.
        Calls appropriate UI feedback methods (show_warning, stop_track, remove_track_from_playlist).

        Args:
            listbox_index (int): The index of the track in the `playlist_box`.

        Returns:
            str | None: The validated file path if the track is playable, otherwise None.
        """
        # Check if the playlist is empty or if the index is out of bounds
        if not self.playlist or not (0 <= listbox_index < len(self.playlist)):
            print(f"Validation failed: Invalid index {listbox_index} for playlist size {len(self.playlist)}.")
            self.stop_track() # Stop playback if index is clearly out of bounds
            return None

        filepath = self.listbox_path_map.get(listbox_index) # Get path from current view map

        # Check if the filepath was found and if the file actually exists on disk

        if not filepath or not os.path.isfile(filepath):
            basename = os.path.basename(filepath) if filepath else f"Track (Index {listbox_index})"
            print(f"Validation failed: File missing or path invalid: {filepath}")
            if messagebox.askyesno("File Missing",
                                   f"The file cannot be found:\n{basename}\n\n"
                                   f"Remove this track from the playlist?",
                                   icon='warning'):
                self.remove_track_from_playlist(filepath, listbox_index)
                # remove_track_from_playlist might stop playback if current track removed.
                # Ensure it's stopped if this was the target.
                self.stop_track() # Explicitly stop after removal dialog.
            else:
                self.show_warning("Playback Skipped", f"Skipped missing file:\n{basename}")
                self.stop_track() # Stop if user chooses not to remove.
            return None # Signal that playback should not proceed

        return filepath # All checks passed

    def play_track(self, listbox_index):
        """
        Plays the track corresponding to the given listbox_index.
        This method first validates the track using `_validate_track_for_playback`.
        If valid, it updates playback history, sets the current track index,
        loads metadata, updates the UI display, and starts audio playback via Pygame.
        Handles Pygame errors during playback initiation.
        """
        filepath = self._validate_track_for_playback(listbox_index)
        if not filepath:
            return # Validation failed or user chose not to proceed (helper method handles UI feedback)

        # --- Proceed with playback ---
        # Update playback history: Add the previous track's listbox index to history
        # if this is a new track selection (not a replay of the same track).
        # This is crucial for the 'previous' button functionality, especially in shuffle mode.
        if self.current_track_index != -1 and self.current_track_index != listbox_index:
             prev_path = self.listbox_path_map.get(self.current_track_index)
             if prev_path != filepath: # Only add if it's truly a different track
                  self.playback_history.append(self.current_track_index)
                  # Limit history size
                  if len(self.playback_history) > 30: self.playback_history.pop(0)

        # --- Set Current Index and Load ---
        self.current_track_index = listbox_index # Update index *after* history logic

        try:
            # Load metadata (file known to exist)
            metadata = self.get_track_metadata(filepath)
            self.current_track_duration = metadata.get('duration', 0)

            # Update display elements
            self.update_track_display(metadata['title'], metadata['artist'], metadata['album'])
            self.update_album_art(metadata) # Update art *before* potential pygame load delay
            self.select_listbox_item(self.current_track_index)
            self.progress_bar['value'] = 0
            self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100

            # Load and play with pygame
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            self.playing_state = "playing"
            self.update_play_pause_button()
            # self.start_time_update() # Time update now handled by check_music_end/pygame event loop
            print(f"Playing [{self.current_track_index}]: {filepath}")

        except pygame.error as e:
            self.show_error("Playback Error", f"Could not play file:\n{os.path.basename(filepath)}\n\nPygame Error: {e}")
            self.stop_track()
        except Exception as e:
             self.show_error("Playback Error", f"An unexpected error occurred during playback initiation:\n{e}")
             traceback.print_exc()
             self.stop_track()

    def remove_track_from_playlist(self, filepath, listbox_index_hint):
        """Removes a given filepath from original_playlist_order and refreshes the UI."""
        if not filepath:
             print("Removal requested for invalid filepath.")
             return

        removed_from_original = False
        try:
            # Remove from the source of truth
            if filepath in self.original_playlist_order:
                 self.original_playlist_order.remove(filepath)
                 print(f"Removed track from master list: {filepath}")
                 removed_from_original = True
            else:
                 print(f"Warning: Track {filepath} not found in original_playlist_order for removal.")
                 # Attempt to remove from current view if it exists there somehow? Risky.
                 # Best to rely on original_playlist_order as the source.

            if removed_from_original:
                 # Refresh the playlist view (applies filters/shuffle again)
                 self._apply_filters_and_shuffle()

                 # If the removed track *was* the currently playing/selected one,
                 # the index is implicitly handled by _apply_filters_and_shuffle finding nothing playing.
                 # We might want to select the *next* available track instead of just the first.
                 if self.playlist: # Check if playlist is not empty after removal and refresh
                    new_index = min(listbox_index_hint, len(self.playlist) - 1) # Try to select item at same position or last
                    if new_index >= 0:
                        self.select_listbox_item(new_index)
                        # If stopped, preload info for the newly selected track
                        if self.playing_state == "stopped":
                            self.preload_track_info(new_index)
                 else: # Playlist became empty
                     self.current_track_index = -1
                     self.update_track_display(clear=True)

        except Exception as e:
             print(f"Error during track removal: {e}")
             traceback.print_exc()
             self.show_error("Removal Error", f"Could not properly remove track:\n{e}")


    # --- Playback Controls ---
    def toggle_play_pause(self):
        """Toggles playback state between playing and paused, or starts playback."""
        if not self.playlist:
             self.show_info("Empty Playlist", "Load some tracks first!")
             return

        if self.playing_state == "playing":
            try:
                pygame.mixer.music.pause()
                self.playing_state = "paused"
                # Time update stops naturally via check_music_end loop condition
                print("Playback paused.")
            except pygame.error as e: print(f"Error pausing music: {e}")
        elif self.playing_state == "paused":
            try:
                pygame.mixer.music.unpause()
                self.playing_state = "playing"
                # Time update restarts naturally via check_music_end loop condition
                print("Playback resumed.")
            except pygame.error as e: print(f"Error unpausing music: {e}")
        else: # "stopped"
             self.play_from_selection_or_start()

        self.update_play_pause_button() # Update button state


    def play_from_selection_or_start(self):
        """Plays the selected track, or the current, or the first if none selected/current."""
        target_index = -1
        selected_indices = self.playlist_box.curselection()
        if selected_indices:
            target_index = selected_indices[0]
        elif self.current_track_index != -1:
             # If stopped but an index exists (e.g. after 'Stop'), play that track
             target_index = self.current_track_index
        elif self.playlist:
             target_index = 0 # Default to first track

        if target_index != -1:
             self.play_track(target_index)
        else:
             self.show_info("Empty Playlist", "No tracks to play.")


    def stop_track(self):
        """Stops playback completely."""
        try:
            pygame.mixer.music.stop()
            # pygame.mixer.music.unload() # Optional: Frees memory but needs reload
        except pygame.error as e: print(f"Error stopping music: {e}")
        self.playing_state = "stopped"
        self.update_play_pause_button()
        self.update_track_display(clear=True) # Clear display
        self.progress_bar['value'] = 0
        # Keep self.current_track_index so 'Play' can resume from the stopped track
        print("Playback stopped.")


    def next_track(self, from_event=False): # from_event differentiates user click from auto-advance
        """
        Plays the next track in the playlist, considering repeat and shuffle modes.

        Args:
            from_event (bool): True if called automatically by MUSIC_END_EVENT,
                               False if called by user action (e.g., 'Next' button).
                               This affects behavior for REPEAT_ONE.
        """
        if not self.playlist: return # No playlist, nothing to do

        current_list_size = len(self.playlist)
        if current_list_size == 0: return # Playlist is empty

        next_index = -1

        # REPEAT_ONE: If repeating one track and this is an auto-advance (not user skip)
        if self.repeat_mode == self.REPEAT_ONE and from_event: # Note: was `and not from_event` which is usually for user clicks
            next_index = self.current_track_index # Play the same track again
        # Standard next track
        elif self.current_track_index < current_list_size - 1:
             next_index = self.current_track_index + 1
        # REPEAT_ALL: If at the end of the playlist and repeating all, wrap to the beginning
        elif self.repeat_mode == self.REPEAT_ALL:
             next_index = 0
        else:
             # End of playlist and not repeating all (or user clicked next at the end without repeat all)
             # Only stop and show message if it's an auto-advance from an event.
             if from_event: # Corrected from `not from_event`
                 self.stop_track()
                 self.show_info("Playback Finished", "End of playlist.")
             return # Do nothing further if user clicked 'Next' at the end without repeat.

        if next_index != -1:
             self.play_track(next_index)


    def prev_track(self):
        """
        Plays the previous track or restarts the current one.
        - If the current track has played for more than 3 seconds, it restarts the current track.
        - If shuffle is on and history exists, it plays the last track from history.
        - Otherwise, it plays the standard previous track, wrapping around if REPEAT_ALL is on.
        """
        if not self.playlist: return

        current_list_size = len(self.playlist)
        if current_list_size == 0: return

        # If current track played for more than 3 seconds, restart it
        try:
            if self.playing_state == "playing" and pygame.mixer.music.get_busy() and pygame.mixer.music.get_pos() > 3000:
                 if self.current_track_index != -1: # Ensure there's a current track
                     print("Restarting current track.")
                     self.play_track(self.current_track_index)
                     return
        except pygame.error: pass # Ignore if get_pos fails (e.g., mixer stopped or not playing)


        prev_index = -1

        # Shuffle mode: try to play from history
        if self.is_shuffled and self.playback_history:
             try:
                 prev_index = self.playback_history.pop()
                 # Validate if this historic index is still valid in the *current* (possibly changed) playlist view
                 if not (0 <= prev_index < current_list_size and self.listbox_path_map.get(prev_index)):
                     print(f"History index {prev_index} invalid for current playlist view, reverting to standard previous.")
                     prev_index = -1 # Fallback to standard logic
             except IndexError:
                 print("Playback history empty for shuffle-previous, using standard previous.")
                 prev_index = -1 # Fallback

        # Standard previous logic (or fallback from shuffle history)
        if prev_index == -1: # If not determined by shuffle history
             if self.current_track_index > 0:
                 prev_index = self.current_track_index - 1
             elif self.repeat_mode == self.REPEAT_ALL: # If at the start and repeating all, wrap to end
                 prev_index = current_list_size - 1
             else: # At the start, not repeating all. Restart the first track.
                 prev_index = 0 if current_list_size > 0 else -1


        if prev_index != -1 and (0 <= prev_index < current_list_size):
             self.play_track(prev_index)
        # If only one track and prev_index logic didn't catch it (e.g. not REPEAT_ALL), restart it.
        elif current_list_size > 0 and self.current_track_index == 0 and prev_index == 0 :
             print("Restarting single/first track on previous.")
             self.play_track(self.current_track_index)
        else:
             # Should ideally not be reached if logic above is comprehensive
             print("Could not determine previous track or playlist empty.")
             self.stop_track()


    def play_selected(self, event=None): # event arg is for Tkinter binding
        """Plays the track double-clicked in the listbox."""
        try:
            selected_indices = self.playlist_box.curselection()
            if selected_indices:
                self.play_track(selected_indices[0])
        except IndexError:
            pass # No item selected


    # --- Volume, Time, Display Updates ---
    def set_volume(self, val):
        """Sets the mixer volume."""
        try:
            volume = float(val) / 100
            pygame.mixer.music.set_volume(volume)
        except ValueError: pass # Ignore invalid scale values
        except pygame.error as e: print(f"Error setting volume: {e}")

    def format_time(self, seconds):
        """Formats seconds into MM:SS string."""
        try:
            seconds = int(seconds)
            if seconds < 0: seconds = 0
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes:02d}:{secs:02d}"
        except Exception: # Catch potential errors with non-numeric input
            return "00:00"

    def update_time_display(self):
        """Updates the time labels and progress bar based on mixer position."""
        if self.playing_state == "playing" and pygame.mixer.music.get_busy():
             try:
                current_pos_ms = pygame.mixer.music.get_pos() # Milliseconds
                if current_pos_ms >= 0: # Check if position is valid
                    current_pos_sec = current_pos_ms / 1000.0
                    current_time_str = self.format_time(current_pos_sec)
                    self.current_time_label.config(text=current_time_str)

                    # Update progress bar
                    if self.current_track_duration > 0:
                        # Value should be seconds, matching the maximum
                        progress_value = min(current_pos_sec, self.current_track_duration)
                        self.progress_bar['value'] = progress_value
                    else:
                         self.progress_bar['value'] = 0
             except pygame.error as e:
                  # This can happen if the mixer stops unexpectedly between checks
                  print(f"Pygame error during time update: {e}")
                  # Don't stop playback here, let the main event loop handle MUSIC_END
             except Exception as e:
                  print(f"Unexpected error during time update: {e}")
                  traceback.print_exc()
        # No need for rescheduling here, handled by check_music_end

    def check_music_end(self):
        """
        Periodically checks for Pygame custom events, primarily MUSIC_END_EVENT.
        This acts as a custom event loop for Pygame events integrated into Tkinter's main loop.
        It also triggers periodic updates of the time display if music is playing.
        This method reschedules itself using `root.after` to run continuously.
        """
        try:
            for event in pygame.event.get(): # Process all Pygame events
                if event.type == self.MUSIC_END_EVENT:
                    print("Received MUSIC_END_EVENT.")
                    # Music finished, advance to the next track respecting repeat modes.
                    # 'from_event=True' indicates this is an automatic advance, not user action.
                    self.next_track(from_event=True)

            # If music is playing and the mixer is busy, update the time display.
            if self.playing_state == "playing" and pygame.mixer.music.get_busy():
                 self.update_time_display()

        except Exception as e:
            print(f"Error in pygame event loop: {e}")
            traceback.print_exc()
        finally:
            # Always reschedule this check to keep the event loop alive.
            self.root.after(250, self.check_music_end) # Check approx. 4 times per second

    # update_track_display and update_album_art are called when needed (play_track, stop_track, preload_track_info)
    def update_track_display(self, title="---", artist="---", album="---", clear=False):
        """Updates the Title, Artist, Album, and Time labels."""
        # Trim function for long strings
        def trim(s, length=40): return (s[:length-1] + '…') if len(s) > length else s

        if clear:
            self.track_title_label.config(text="---")
            self.track_artist_label.config(text="---")
            self.track_album_label.config(text="---")
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text="/ 00:00")
            self.progress_bar['value'] = 0
            self.progress_bar['maximum'] = 100 # Reset max
            self.current_track_duration = 0
            # Reset album art to default (handled by update_album_art)
            self.update_album_art({'art_data': None})
        else:
            # Use defaults if metadata is missing/empty
            display_title = title if title else "Unknown Title"
            display_artist = artist if artist else "Unknown Artist"
            display_album = album if album else "Unknown Album"

            self.track_title_label.config(text=trim(display_title))
            self.track_artist_label.config(text=trim(display_artist, 35))
            self.track_album_label.config(text=trim(display_album, 35))

            # Reset current time display, total time depends on duration
            total_time_str = self.format_time(self.current_track_duration)
            self.current_time_label.config(text="00:00")
            self.total_time_label.config(text=f"/ {total_time_str}")
            # Set progress bar max (value reset in play_track/stop_track)
            self.progress_bar['maximum'] = self.current_track_duration if self.current_track_duration > 0 else 100


    def update_album_art(self, metadata):
        """Updates the album art label using data from metadata dict."""
        art_label = self.album_art_label
        art_data = metadata.get('art_data')
        # Get the current default art image (might be None if loading failed)
        current_default_art = self.default_album_art

        if art_data:
            try:
                img_data = io.BytesIO(art_data)
                pil_img = Image.open(img_data)
                pil_img.thumbnail(self.ALBUM_ART_SIZE, Image.Resampling.LANCZOS)
                tk_img = ImageTk.PhotoImage(pil_img)
                art_label.config(image=tk_img)
                art_label.image = tk_img # Keep reference! Important.
            except Exception as e:
                print(f"Error processing album art: {e}")
                # Fallback to default art if processing fails
                art_label.config(image=current_default_art)
                art_label.image = current_default_art
        else:
            # Use default placeholder if no art data provided
            art_label.config(image=current_default_art)
            art_label.image = current_default_art


    def select_listbox_item(self, index):
         """Selects and makes visible the item at the given listbox index."""
         try:
             if 0 <= index < self.playlist_box.size():
                 self.playlist_box.selection_clear(0, tk.END)
                 self.playlist_box.selection_set(index)
                 self.playlist_box.activate(index)
                 self.playlist_box.see(index) # Ensure item is visible
         except tk.TclError as e:
             # Can happen if listbox is updated while selection is attempted
             print(f"Error selecting listbox item {index}: {e}")


    # --- Shuffle, Repeat, Sort, Search ---
    def toggle_shuffle(self):
        """Toggles shuffle mode on/off and updates the view."""
        self.is_shuffled = not self.is_shuffled
        self.shuffle_menu_var.set(self.is_shuffled)
        self.update_shuffle_button()
        # Clear history when toggling shuffle to avoid weird back behavior
        self.playback_history = []
        self._apply_filters_and_shuffle()
        print(f"Shuffle {'enabled' if self.is_shuffled else 'disabled'}.")

    def set_repeat_mode(self):
        """Sets repeat mode based on menu selection."""
        self.repeat_mode = self.repeat_menu_var.get()
        self.update_repeat_button()
        mode_str = {0: "Off", 1: "One", 2: "All"}.get(self.repeat_mode, "Unknown")
        print(f"Repeat mode set to: {mode_str}")

    def cycle_repeat_mode(self):
        """Cycles through repeat modes via button click."""
        self.repeat_mode = (self.repeat_mode + 1) % 3 # Cycle 0, 1, 2
        self.repeat_menu_var.set(self.repeat_mode)
        self.update_repeat_button()
        mode_str = {0: "Off", 1: "One", 2: "All"}.get(self.repeat_mode, "Unknown")
        print(f"Repeat mode cycled to: {mode_str}")


    def sort_playlist_action(self, sort_key):
        """
        Sorts the `self.original_playlist_order` based on the given `sort_key`.
        For metadata-based sorts (title, artist, album), it fetches metadata for all tracks.
        After sorting, it turns off shuffle mode and refreshes the playlist view.

        Args:
            sort_key (str): The key to sort by ('title', 'artist', 'album', or 'path').
        """
        if not self.original_playlist_order:
            self.show_info("Empty Playlist", "Nothing to sort.")
            return

        print(f"Sorting playlist by: {sort_key}...")
        # TODO: Consider adding a busy cursor feedback for long sorts.

        metadata_list = []
        # Fetch metadata only if sorting by a metadata field.
        # This can be slow for large playlists.
        if sort_key in ('title', 'artist', 'album'):
            fetch_start_time = time.time()
            missing_files = 0
            # This loop can be time-consuming for large playlists as get_track_metadata reads each file.
            # For very large libraries, a background thread or pre-cached metadata DB would be better.
            for i, path in enumerate(self.original_playlist_order):
                 meta = self.get_track_metadata(path) # Fetches metadata, handles missing files internally
                 if meta['title'].startswith("[Missing]"): missing_files += 1
                 metadata_list.append({ # Store path along with relevant metadata for sorting
                     'path': path,
                     'title': meta.get('title', '').lower(),
                     'artist': meta.get('artist', '').lower(),
                     'album': meta.get('album', '').lower(),
                 })
            fetch_end_time = time.time()
            print(f"Metadata fetched for {len(metadata_list)} items in {fetch_end_time - fetch_start_time:.2f}s.")
            if missing_files > 0: print(f"Note: {missing_files} missing files encountered.")

        # --- Perform Sort ---
        try:
             if sort_key == 'path':
                  self.original_playlist_order.sort(key=lambda p: p.lower()) # Case-insensitive path sort
             elif sort_key in ('title', 'artist', 'album'):
                  # Sort the metadata list first
                  metadata_list.sort(key=lambda x: x.get(sort_key, ''))
                  # Update original_playlist_order based on sorted metadata
                  self.original_playlist_order = [item['path'] for item in metadata_list]
             else:
                  print(f"Unknown sort key: {sort_key}"); return

        except Exception as e:
             self.show_error("Sort Error", f"Could not sort by {sort_key}:\n{e}")
             traceback.print_exc(); return

        # --- Update UI ---
        print("Sort complete. Refreshing view.")
        self.is_shuffled = False # Turn off shuffle when sorting explicitly
        self.shuffle_menu_var.set(self.is_shuffled)
        self.update_shuffle_button()
        self._apply_filters_and_shuffle()


    def _apply_filters_and_shuffle(self, force_refresh=False):
        """
        Applies the current search filter and shuffle state to `self.original_playlist_order`
        to generate the `self.playlist` (the viewable list).
        It then repopulates the listbox and attempts to maintain the selection of the
        currently playing track.

        Args:
            force_refresh (bool): If True, bypasses the optimization check and always refreshes.
                                  Useful after actions that modify original_playlist_order directly.
        """

        # Optimization: Avoids re-filtering/shuffling if search term and shuffle state haven't changed.
        search_changed = self.current_search_term != self._last_applied_search
        shuffle_changed = self.is_shuffled != self._last_applied_shuffle

        if not force_refresh and not search_changed and not shuffle_changed:
             # print("Skipping refresh: search/shuffle state unchanged or not forced.")
             return # No change in relevant state, so no need to update the view.

        print(f"Applying filters/shuffle (Force={force_refresh}, Search='{self.current_search_term}', Shuffle={self.is_shuffled})...")
        start_time = time.time()

        # Always start with a fresh copy of the original, sorted/added-order playlist
        temp_playlist = list(self.original_playlist_order)

        # Apply search filter: currently a simple case-insensitive check on the filename.
        # For more advanced search (e.g., metadata), this would need to be more complex,
        # potentially involving cached metadata.
        if self.current_search_term:
            try:
                temp_playlist = [
                    path for path in temp_playlist
                    if self.current_search_term in os.path.basename(path).lower()
                ]
            except Exception as e:
                 print(f"Error during search filtering: {e}")
                 # Decide on error handling: continue without filter, or show user error?
                 # For now, it continues with the potentially unfiltered or partially filtered list.

        # Apply shuffle if enabled
        if self.is_shuffled:
            random.shuffle(temp_playlist) # Shuffles in-place

        # Update the main `self.playlist` which represents the current view
        self.playlist = temp_playlist

        # --- Preserve playing track's context ---
        # Store the path of the currently playing/selected track *before* the listbox is repopulated.
        # This is crucial to find its new position in the potentially reordered/filtered list.
        playing_path = None
        current_lb_index = self.current_track_index # This is the index in the *old* listbox_path_map
        if self.playing_state != "stopped" and current_lb_index != -1:
            playing_path = self.listbox_path_map.get(current_lb_index)

        # --- Repopulate UI ---
        self._repopulate_listbox() # Clears and refills the listbox, also updates self.listbox_path_map

        # --- Try to re-select the playing track in the new view ---
        self._find_and_select_playing_track_after_update(playing_path)

        # Update state tracking variables for future optimization checks
        self._last_applied_search = self.current_search_term
        self._last_applied_shuffle = self.is_shuffled
        end_time = time.time()
        print(f"Applied filters/shuffle in {end_time - start_time:.4f} seconds.")

    def _find_and_select_playing_track_after_update(self, playing_path):
        """
        Finds the new index for a given playing_path after the playlist view
        (and `self.listbox_path_map`) has been updated (e.g., after filtering or shuffling).
        It attempts to find the `playing_path` in the new map, and if found, updates
        `self.current_track_index` and selects the item in the listbox.
        Handles cases where the track is no longer visible or if no track was playing.

        Args:
            playing_path (str | None): The file path of the track that was playing/selected
                                       before the playlist view was updated. None if no track was selected.
        """
        new_playing_index = -1
        if playing_path:
            # Efficiently find the new index of playing_path by creating a reverse mapping
            # from path to index from the updated self.listbox_path_map.
            try:
                # This assumes paths in listbox_path_map.values() are unique.
                # If duplicates are allowed and meaningful, this might need adjustment.
                inverted_map = {path: idx for idx, path in self.listbox_path_map.items()}
                if playing_path in inverted_map:
                    new_playing_index = inverted_map[playing_path]
            except Exception as e: # Catch potential errors during map inversion/lookup
                print(f"Error finding playing track's new index after update: {e}")

        # --- Update current_track_index and listbox selection based on findings ---
        if new_playing_index != -1:
             # Track found in the new view, update index and select it.
             self.current_track_index = new_playing_index
             self.select_listbox_item(self.current_track_index)
             # No need to call preload_track_info here, as the track's info should already be
             # displayed if it was playing or just selected.
        else:
             # Case 1: A track was playing/selected (playing_path is not None) but is no longer in the view.
             if self.playing_state != "stopped" and playing_path:
                  print(f"Playing track '{os.path.basename(playing_path)}' disappeared from view after filter/shuffle/sort.")
                  # Music might still be playing, but it's no longer selectable in the listbox.
                  # Invalidate current_track_index for listbox purposes.
                  self.current_track_index = -1
                  # Optionally, clear visual selection in listbox: self.playlist_box.selection_clear(0, tk.END)
             # Case 2: No track was playing OR playlist is not empty after update: select first item.
             elif self.playlist: # If there are items in the new playlist view
                  self.current_track_index = 0
                  self.select_listbox_item(0)
                  # If player was fully stopped, preload info for this new first item.
                  # If paused, info for the (now gone) track might still be there,
                  # preloading here would update display to the new first track.
                  if self.playing_state == "stopped":
                    self.preload_track_info(0)
             # Case 3: Playlist is empty after update.
             else:
                  self.current_track_index = -1
                  self.update_track_display(clear=True) # Clear all track info displays

    def search_playlist_action(self, event=None): # event arg is for Tkinter binding
        """Initiated search based on the search entry."""
        self.current_search_term = self.search_var.get().lower().strip()
        self._apply_filters_and_shuffle() # Will refresh if term changed

    def clear_search_action(self):
        """Clears the search term and refreshes the playlist view."""
        self.search_var.set("")
        self.current_search_term = ""
        self._apply_filters_and_shuffle() # Will refresh if term changed


    # --- Closing ---
    def on_closing(self):
        """Handles application close event."""
        print("Closing application...")
        # Stop scheduled tasks
        # if self.update_seek_job: self.root.after_cancel(self.update_seek_job) # Handled by root.destroy()
        if self.browser_window and self.browser_window.winfo_exists():
            try: self.browser_window.destroy()
            except tk.TclError: pass # Ignore if already destroyed
        try:
            self.stop_track() # Stop music playback
            # Explicitly quit pygame modules
            pygame.mixer.music.set_endevent() # Clear end event listener
            pygame.mixer.quit()
            pygame.quit()
            print("Pygame quit successfully.")
        except Exception as e:
            print(f"Error during Pygame quit: {e}")
        finally:
            # Destroy the Tkinter window
            try:
                if self.root.winfo_exists():
                    self.root.destroy()
                    print("Tkinter root window destroyed.")
            except Exception as e:
                print(f"Error destroying Tkinter root: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    print(f"Running Python {sys.version}")
    # Ensure pygame is quit if script is run multiple times in some environments (like IDEs)
    try:
         # Check if pygame is initialized before trying to quit
         if pygame.get_init():
             pygame.quit()
             print("Cleaned up previous pygame instance.")
    except Exception as e:
         print(f"Note: Error during initial pygame cleanup (may be harmless): {e}")

    # Initialize Tkinter root
    root = tk.Tk()

    # Set application icon (optional)
    try:
        # Look for platform-specific or standard icon names
        icon_filename = "app_icon.ico" if sys.platform == "win32" else "app_icon.png"
        icon_path = resource_path(icon_filename)
        alt_icon_path = resource_path("app_icon.png") # Try PNG as fallback

        if os.path.exists(icon_path):
             if sys.platform == "win32":
                 root.iconbitmap(default=icon_path)
                 print(f"Using icon: {icon_path}")
             else: # Other platforms typically use PhotoImage
                 img = PhotoImage(file=icon_path)
                 root.tk.call('wm', 'iconphoto', root._w, img)
                 print(f"Using icon: {icon_path}")
        elif os.path.exists(alt_icon_path): # Fallback to PNG if specific not found
             img = PhotoImage(file=alt_icon_path)
             root.tk.call('wm', 'iconphoto', root._w, img)
             print(f"Using fallback icon: {alt_icon_path}")
        else:
             print("App icon ('app_icon.ico' or 'app_icon.png') not found.")
    except tk.TclError as e:
         print(f"Could not set application icon (TclError, often happens if OS blocks it or format wrong): {e}")
    except Exception as e:
        print(f"Could not set application icon (Unexpected Error): {e}")
        traceback.print_exc()

    # Create and run the application
    app = None # Define app outside try block for finally clause
    initialization_ok = False
    try:
        app = MediaPlayerApp(root)
        # Check if root was destroyed during init (e.g., pygame mixer failed)
        if app and root.winfo_exists():
            initialization_ok = True
            print("Starting Tkinter main loop...")
            root.mainloop()
            print("Tkinter main loop finished.")
        else:
            print("Application initialization failed or window destroyed during init.")
    except Exception as e:
        print("An unexpected error occurred during application setup or runtime:")
        traceback.print_exc()
        # Ensure cleanup even if mainloop fails
        if app and root.winfo_exists():
             app.on_closing()
        elif root.winfo_exists():
             root.destroy()