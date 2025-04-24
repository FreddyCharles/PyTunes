import tkinter as tk
from tkinter import filedialog, ttk, messagebox
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

# --- Constants ---
BG_COLOR = "#EAEAEA" # iPod-like off-white/grey
SCREEN_BG = "white"
TEXT_COLOR = "black"
BUTTON_BG = "#D0D0D0"
ACTIVE_BUTTON_BG = "#B0B0B0"
FONT_MAIN = ("Helvetica", 10)
FONT_SCREEN = ("Helvetica", 10)
FONT_NOW_PLAYING = ("Helvetica", 9, "bold")
FONT_TIME = ("Helvetica", 8)

SUPPORTED_FORMATS = ('.mp3', '.ogg', '.wav', '.flac') # Add more if needed

class MediaPlayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PyPod")
        self.root.geometry("300x450") # Typical portrait aspect ratio
        self.root.configure(bg=BG_COLOR)
        self.root.resizable(False, False) # Keep fixed size for iPod look

        # --- Playback State ---
        self.playlist = []
        self.current_track_index = -1
        self.playing_state = "stopped" # stopped, playing, paused
        self.current_track_duration = 0
        self.update_seek_job = None # To store the .after() job ID

        # --- Initialize Pygame Mixer ---
        try:
            pygame.mixer.init()
        except pygame.error as e:
            messagebox.showerror("Pygame Error", f"Could not initialize audio mixer: {e}\nPlease ensure audio drivers are working.")
            self.root.destroy()
            return

        # --- Build UI ---
        self.create_ui()

        # --- Bind closing event ---
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_ui(self):
        # --- Main Frame ---
        main_frame = tk.Frame(self.root, bg=BG_COLOR)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # --- Screen Area ---
        screen_frame = tk.Frame(main_frame, bg=SCREEN_BG, bd=1, relief=tk.SOLID)
        screen_frame.pack(fill=tk.X, pady=(0, 10))
        screen_frame.columnconfigure(0, weight=1) # Make label column expandable

        # Now Playing Label
        self.now_playing_label = tk.Label(screen_frame, text="Now Playing:", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_NOW_PLAYING)
        self.now_playing_label.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=(5,0))

        self.track_title_label = tk.Label(screen_frame, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_SCREEN)
        self.track_title_label.grid(row=1, column=0, sticky='ew', padx=5)

        self.track_artist_label = tk.Label(screen_frame, text="---", anchor='w', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_SCREEN)
        self.track_artist_label.grid(row=2, column=0, sticky='ew', padx=5)

        # Time Display
        self.time_label = tk.Label(screen_frame, text="00:00 / 00:00", anchor='e', bg=SCREEN_BG, fg=TEXT_COLOR, font=FONT_TIME)
        self.time_label.grid(row=3, column=0, sticky='ew', padx=5, pady=(0, 5))

        # --- Playlist Area ---
        list_frame = tk.Frame(main_frame, bg=BG_COLOR)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.playlist_box = tk.Listbox(
            list_frame,
            bg=SCREEN_BG,
            fg=TEXT_COLOR,
            selectbackground=BUTTON_BG,
            selectforeground=TEXT_COLOR,
            font=FONT_SCREEN,
            activestyle='none',
            highlightthickness=0,
            bd=1,
            relief=tk.SOLID,
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=self.playlist_box.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.playlist_box.bind("<Double-Button-1>", self.play_selected)

        # --- Control Area (Simulating Click Wheel) ---
        control_frame = tk.Frame(main_frame, bg=BG_COLOR)
        control_frame.pack(fill=tk.X)

        # Volume Slider
        self.volume_scale = ttk.Scale(
            control_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            command=self.set_volume,
            style="Horizontal.TScale" # Use ttk style for better look if available
        )
        self.volume_scale.set(70) # Default volume
        pygame.mixer.music.set_volume(0.7)
        self.volume_scale.pack(fill=tk.X, pady=(0, 10))

        # Button Frame (Grid Layout)
        button_frame = tk.Frame(control_frame, bg=BG_COLOR)
        button_frame.pack()

        # Define button style
        button_opts = {
            'width': 6, 'font': FONT_MAIN, 'bg': BUTTON_BG, 'fg': TEXT_COLOR,
            'activebackground': ACTIVE_BUTTON_BG, 'activeforeground': TEXT_COLOR,
            'relief': tk.RAISED, 'bd': 1
        }

        # Row 0: Menu (Load)
        self.load_button = tk.Button(button_frame, text="Menu", **button_opts, command=self.load_folder)
        self.load_button.grid(row=0, column=1, pady=2)

        # Row 1: Previous, Play/Pause, Next
        self.prev_button = tk.Button(button_frame, text="<<", **button_opts, command=self.prev_track)
        self.prev_button.grid(row=1, column=0, padx=5)

        self.play_pause_button = tk.Button(button_frame, text="Play", **button_opts, command=self.toggle_play_pause)
        self.play_pause_button.grid(row=1, column=1, padx=5)

        self.next_button = tk.Button(button_frame, text=">>", **button_opts, command=self.next_track)
        self.next_button.grid(row=1, column=2, padx=5)

        # Row 2: Stop
        self.stop_button = tk.Button(button_frame, text="Stop", **button_opts, command=self.stop_track)
        self.stop_button.grid(row=2, column=1, pady=2)

        # --- Configure ttk style for slider (optional, improves look on some systems) ---
        style = ttk.Style()
        try:
            # Check if theme exists to avoid errors
            if 'clam' in style.theme_names():
                 style.theme_use('clam')
            elif 'alt' in style.theme_names():
                 style.theme_use('alt')
            style.configure("Horizontal.TScale", background=BG_COLOR, troughcolor=SCREEN_BG)
        except tk.TclError:
            print("ttk themes not fully available. Using default.") # Inform user, but continue


    # --- Backend Logic ---

    def load_folder(self):
        folder_path = filedialog.askdirectory()
        if not folder_path:
            return

        self.playlist = []
        self.playlist_box.delete(0, tk.END) # Clear existing listbox
        self.stop_track() # Stop current playback
        self.update_track_display(clear=True)

        # Scan folder in a separate thread to avoid freezing GUI for large folders
        threading.Thread(target=self._scan_folder, args=(folder_path,), daemon=True).start()

    def _scan_folder(self, folder_path):
        found_files = []
        try:
            for filename in os.listdir(folder_path):
                if filename.lower().endswith(SUPPORTED_FORMATS):
                    filepath = os.path.join(folder_path, filename)
                    found_files.append(filepath)
        except OSError as e:
             # Use schedule to run GUI update from main thread
             self.root.after(0, lambda: messagebox.showerror("Error", f"Could not read directory:\n{e}"))
             return

        if not found_files:
            self.root.after(0, lambda: messagebox.showinfo("Empty", "No supported audio files found in the selected folder."))
            return

        found_files.sort() # Sort alphabetically

        # Update GUI from the main thread
        self.root.after(0, self._update_playlist_gui, found_files)

    def _update_playlist_gui(self, files):
        self.playlist = files
        for i, filepath in enumerate(self.playlist):
            filename = os.path.basename(filepath)
            # Try getting Title tag for better display, fallback to filename
            try:
                 display_name = self.get_track_metadata(filepath).get('title', filename)
                 if not display_name: display_name = filename # Handle empty title tag case
            except Exception: # Broad catch for any mutagen issue during initial list population
                 display_name = filename
            self.playlist_box.insert(tk.END, f"{i+1}. {display_name}")
        self.current_track_index = -1 # Reset index


    def get_track_metadata(self, filepath):
        """Reads metadata using mutagen. Returns dict with title, artist, duration."""
        metadata = {'title': os.path.basename(filepath), 'artist': 'Unknown Artist', 'duration': 0}
        try:
            if filepath.lower().endswith('.mp3'):
                try:
                    audio = MP3(filepath, ID3=ID3)
                except ID3NoHeaderError:
                     audio = MP3(filepath) # Try without ID3 header specific parsing
                if audio:
                    metadata['title'] = audio.get('TIT2', [metadata['title']])[0]
                    metadata['artist'] = audio.get('TPE1', [metadata['artist']])[0]
                    metadata['duration'] = int(audio.info.length) if hasattr(audio, 'info') else 0
            elif filepath.lower().endswith('.ogg'):
                audio = OggVorbis(filepath)
                metadata['title'] = audio.get('title', [metadata['title']])[0]
                metadata['artist'] = audio.get('artist', [metadata['artist']])[0]
                metadata['duration'] = int(audio.info.length) if hasattr(audio, 'info') else 0
            elif filepath.lower().endswith('.flac'):
                audio = FLAC(filepath)
                metadata['title'] = audio.get('title', [metadata['title']])[0]
                metadata['artist'] = audio.get('artist', [metadata['artist']])[0]
                metadata['duration'] = int(audio.info.length) if hasattr(audio, 'info') else 0
            elif filepath.lower().endswith('.wav'):
                 audio = WAVE(filepath)
                 # WAV doesn't have standard tags like ID3, might have RIFF INFO, etc.
                 # Keep it simple for now, just get duration. Title/Artist rely on filename.
                 metadata['duration'] = int(audio.info.length) if hasattr(audio, 'info') else 0

             # Cleanup empty values
            if not metadata['title']: metadata['title'] = os.path.basename(filepath)
            if not metadata['artist']: metadata['artist'] = 'Unknown Artist'

        except MutagenError as e:
            print(f"Mutagen error reading {filepath}: {e}") # Log error but continue
        except Exception as e:
            print(f"Unexpected error reading metadata for {filepath}: {e}")

        return metadata

    def play_track(self, track_index=None):
        if track_index is None:
            if self.current_track_index == -1 and self.playlist:
                track_index = 0 # Start from beginning if nothing selected
            else:
                track_index = self.current_track_index # Resume current

        if not self.playlist or not (0 <= track_index < len(self.playlist)):
            # print("Invalid track index or empty playlist.")
            self.stop_track() # Ensure clean state if invalid index somehow reached
            return

        self.current_track_index = track_index
        filepath = self.playlist[self.current_track_index]

        try:
            # Get metadata *before* loading, as loading can be slow
            metadata = self.get_track_metadata(filepath)
            self.current_track_duration = metadata.get('duration', 0)

            # Update display immediately
            self.update_track_display(metadata['title'], metadata['artist'])
            self.select_listbox_item(self.current_track_index)

            # Load and play
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.play()
            self.playing_state = "playing"
            self.play_pause_button.config(text="Pause")
            self.start_time_update() # Start updating the time display
            print(f"Playing: {filepath}")

        except pygame.error as e:
            messagebox.showerror("Playback Error", f"Could not play file:\n{os.path.basename(filepath)}\n\nError: {e}")
            self.stop_track() # Reset state on error
            # Optionally try next track?
            # self.next_track(force=True)
        except Exception as e:
             messagebox.showerror("Error", f"An unexpected error occurred:\n{e}")
             self.stop_track()


    def toggle_play_pause(self):
        if not self.playlist: return

        if self.playing_state == "playing":
            pygame.mixer.music.pause()
            self.playing_state = "paused"
            self.play_pause_button.config(text="Play")
            self.stop_time_update() # Stop updating time when paused
        elif self.playing_state == "paused":
            pygame.mixer.music.unpause()
            self.playing_state = "playing"
            self.play_pause_button.config(text="Pause")
            self.start_time_update() # Resume time update
        else: # "stopped"
            if self.current_track_index == -1:
                 self.current_track_index = 0 # Default to first track if stopped and nothing selected
            self.play_track(self.current_track_index)


    def stop_track(self):
        pygame.mixer.music.stop()
        # pygame.mixer.music.unload() # Unload might be good practice but can cause issues if rapidly switching
        self.playing_state = "stopped"
        self.play_pause_button.config(text="Play")
        self.stop_time_update()
        self.update_track_display(clear=True) # Clear display
        # Don't reset current_track_index here, so play starts from last stopped track
        # If you want 'stop' to fully reset, uncomment next line:
        # self.current_track_index = -1
        # self.deselect_listbox_item() # Optional: deselect visually


    def next_track(self, force=False): # force=True used internally for auto-advance
        if not self.playlist: return
        if self.current_track_index < len(self.playlist) - 1:
            self.current_track_index += 1
        else:
            self.current_track_index = 0 # Wrap around
        self.play_track(self.current_track_index)

    def prev_track(self):
        if not self.playlist: return
        # If playing for more than ~3 seconds, restart current track, else go previous
        if self.playing_state == "playing" and pygame.mixer.music.get_pos() > 3000:
             self.play_track(self.current_track_index) # Restart current
        elif self.current_track_index > 0:
            self.current_track_index -= 1
            self.play_track(self.current_track_index)
        else:
            self.current_track_index = len(self.playlist) - 1 # Wrap around to end
            if self.current_track_index >= 0: # Check if playlist is not empty after wrap
                self.play_track(self.current_track_index)
            else:
                self.stop_track() # Playlist became empty somehow?


    def play_selected(self, event=None):
        try:
            selected_index = self.playlist_box.curselection()[0]
            self.play_track(selected_index)
        except IndexError:
            pass # No item selected

    def set_volume(self, val):
        # Tkinter scale goes 0-100, pygame volume 0.0-1.0
        volume = float(val) / 100
        pygame.mixer.music.set_volume(volume)

    def format_time(self, seconds):
        if seconds < 0: seconds = 0 # Ensure non-negative time
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def update_time(self):
        if self.playing_state == "playing":
            try:
                current_pos_ms = pygame.mixer.music.get_pos() # Milliseconds
                if current_pos_ms == -1 and self.playing_state == "playing":
                     # Song likely ended, get_pos returns -1
                     print("Song finished.")
                     # Check if it *really* finished, not just a temporary glitch
                     if not pygame.mixer.music.get_busy():
                         self.next_track(force=True) # Auto-advance
                         return # Exit update loop for this cycle
                     else:
                          # Still busy? Maybe a glitch, keep updating
                          current_pos_sec = 0 # Avoid error if -1 persisted
                else:
                     current_pos_sec = current_pos_ms / 1000.0

                total_time_str = self.format_time(self.current_track_duration)
                current_time_str = self.format_time(current_pos_sec)
                self.time_label.config(text=f"{current_time_str} / {total_time_str}")

                # Schedule next update only if still playing
                self.update_seek_job = self.root.after(500, self.update_time) # Update every 500ms

            except pygame.error as e:
                 # This can happen if the mixer stops unexpectedly
                 print(f"Pygame error during time update: {e}")
                 self.stop_track() # Stop cleanly if mixer error occurs
            except Exception as e:
                 print(f"Unexpected error during time update: {e}")
                 # Decide if stopping is appropriate here too
        else:
            # Ensure the job is cancelled if state changed while waiting for .after()
            self.stop_time_update()


    def start_time_update(self):
         self.stop_time_update() # Cancel any existing job first
         self.update_time() # Start the update loop

    def stop_time_update(self):
        if self.update_seek_job:
            self.root.after_cancel(self.update_seek_job)
            self.update_seek_job = None
        # Reset time display when stopping fully? Optional.
        # if self.playing_state != "paused":
        #     self.time_label.config(text="00:00 / " + self.format_time(self.current_track_duration if self.current_track_duration > 0 else 0))


    def update_track_display(self, title="---", artist="---", clear=False):
        if clear:
            self.track_title_label.config(text="---")
            self.track_artist_label.config(text="---")
            self.time_label.config(text="00:00 / 00:00")
            self.current_track_duration = 0
        else:
            # Limit length to prevent layout issues
            max_len = 35
            display_title = (title[:max_len] + '...') if len(title) > max_len else title
            display_artist = (artist[:max_len] + '...') if len(artist) > max_len else artist

            self.track_title_label.config(text=display_title if display_title else "Unknown Title")
            self.track_artist_label.config(text=display_artist if display_artist else "Unknown Artist")
            total_time_str = self.format_time(self.current_track_duration)
            self.time_label.config(text=f"00:00 / {total_time_str}") # Reset current time display


    def select_listbox_item(self, index):
         if 0 <= index < self.playlist_box.size():
             self.playlist_box.selection_clear(0, tk.END)
             self.playlist_box.selection_set(index)
             self.playlist_box.activate(index)
             self.playlist_box.see(index) # Ensure item is visible

    def deselect_listbox_item(self):
         self.playlist_box.selection_clear(0, tk.END)


    def on_closing(self):
        print("Closing application...")
        self.stop_track()
        self.stop_time_update() # Ensure timer is cancelled
        try:
            pygame.mixer.quit() # Cleanly shut down mixer
        except Exception as e:
            print(f"Error quitting pygame mixer: {e}")
        try:
             pygame.quit() # Quit pygame itself if initialized elsewhere (though mixer.init is usually enough)
        except Exception as e:
            print(f"Error quitting pygame: {e}")
        self.root.destroy()


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = MediaPlayerApp(root)
    # Only start mainloop if initialization didn't fail
    if app and not root.winfo_exists(): # Check if root was destroyed during init
         pass # Don't start mainloop
    elif app:
         root.mainloop()