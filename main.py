import os
import hashlib
import json
import threading
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.recycleview import RecycleView
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivy.lang import Builder
from kivy.core.clipboard import Clipboard
from kivy.uix.textinput import TextInput
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.button import Button
from PIL import Image as PILImage
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.progressbar import ProgressBar
from kivy.utils import platform
import queue
from kivy.uix.filechooser import FileChooserIconView

class SelectableImage(BoxLayout):
    note = StringProperty()  # <-- Add this property to fix the error

def get_thumbnail_path(original_path):
    image_dir = os.path.dirname(original_path)
    thumb_dir = os.path.join(image_dir, ".thumbs")
    os.makedirs(thumb_dir, exist_ok=True)

    # Prevent Android from indexing .thumbs
    nomedia_path = os.path.join(thumb_dir, ".nomedia")
    if not os.path.exists(nomedia_path):
        with open(nomedia_path, "w") as f:
            f.write("")

    thumb_filename = hashlib.md5(original_path.encode()).hexdigest() + ".png"
    return os.path.join(thumb_dir, thumb_filename)


def generate_thumbnail(original_path, size=(200, 200)):
    thumb_path = get_thumbnail_path(original_path)

    # Only generate the thumbnail if it doesn't already exist
    if not os.path.exists(thumb_path):
        try:
            img = PILImage.open(original_path)
            img.thumbnail(size)
            img.save(thumb_path, "PNG")
            print(f"Thumbnail created: {thumb_path}")
        except Exception as e:
            print(f"Thumbnail generation error for {original_path}: {e}")
            return original_path  # fallback to original image

    return thumb_path


class BlackOverlay(ModalView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_color = (0, 0, 0, 1)  # Fully black background
        self.auto_dismiss = False  # Do not dismiss on outside tap

        layout = FloatLayout()

        # Close button in top-right corner
        close_btn = Button(
            text='X',
            size_hint=(None, None),
            size=(50, 50),
            pos_hint={'right': 0.98, 'top': 0.98},
            background_color=(0.2, 0.2, 0.2, 0.8),
            color=(1, 1, 1, 1),
            font_size='18sp',
            bold=True
        )
        close_btn.bind(on_release=self.dismiss)

        layout.add_widget(close_btn)
        self.add_widget(layout)




GALLERY_PATH = "/Storage/emulated/0"
DB_PATH = "db.json"
SETTINGS_PATH = "settings.json"

Builder.load_file("gallery.kv")

def get_image_hash(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def load_json(filepath, default):
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        with open(filepath, 'w') as f:
            json.dump(default, f)
        return default
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(filepath, 'w') as f:
            json.dump(default, f)
        return default

def save_json(filepath, data):
    with open(filepath, 'w') as f:
        json.dump(data, f)

class ThumbnailProgressOverlay(ModalView):
    total = NumericProperty(0)
    current = NumericProperty(0)

    def __init__(self, total, **kwargs):
        super().__init__(**kwargs)
        self.total = total
        self.current = 0

    def update(self, current):
        self.current = current

class UploadProgressOverlay(ModalView):
    total = NumericProperty(0)
    current = NumericProperty(0)
    summary = StringProperty("")
    on_cancel = None  # callback for cancel

    def __init__(self, total, on_cancel=None, **kwargs):
        super().__init__(**kwargs)
        self.total = total
        self.current = 0
        self.summary = ""
        self.on_cancel = on_cancel

    def update(self, current, summary=""):
        self.current = current
        self.summary = summary

    def cancel_upload(self):
        if self.on_cancel:
            self.on_cancel()
        self.dismiss()

class UploadManager:
    def __init__(self, app, max_workers=4, max_uploads_per_minute=20):
        self.app = app
        self.queue = queue.Queue()
        self.max_workers = max_workers
        self.max_uploads_per_minute = max_uploads_per_minute
        self._last_upload_times = []
        self._running = False
        self._lock = threading.Lock()
        self._progress_callback = None
        self._thread = None
        self.cancel_requested = False

    def set_progress_callback(self, callback):
        self._progress_callback = callback

    def add_tasks(self, paths):
        self.cancel_requested = False  # Reset cancel flag on new tasks
        for path in paths:
            self.queue.put(path)
        self.start()

    def cancel(self):
        with self._lock:
            self.cancel_requested = True

    def start(self):
        with self._lock:
            if not self._running:
                self._running = True
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()

    def _worker(self):
        total = self.queue.qsize()
        completed = [0]
        def upload_task(path):
            # Check cancel before starting upload
            with self._lock:
                if self.cancel_requested:
                    return
            # Rate limiting (shared among threads)
            while True:
                now = time.time()
                with self._lock:
                    if self.cancel_requested:
                        return
                    self._last_upload_times = [t for t in self._last_upload_times if now - t < 60]
                    if len(self._last_upload_times) < self.max_uploads_per_minute:
                        self._last_upload_times.append(now)
                        break
                time.sleep(1)
            # Check cancel again before upload
            with self._lock:
                if self.cancel_requested:
                    return
            self.app._upload_image_internal(path)
            with self._lock:
                completed[0] += 1
                if self._progress_callback:
                    Clock.schedule_once(lambda dt, c=completed[0], t=total: self._progress_callback(c, t))

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            while not self.queue.empty():
                with self._lock:
                    if self.cancel_requested:
                        # Don't start new uploads if cancel requested
                        break
                path = self.queue.get()
                futures.append(executor.submit(upload_task, path))
            # Wait for all started uploads to finish
            for f in futures:
                f.result()

        # Final UI update
        Clock.schedule_once(lambda dt: self.app.sm.get_screen('gallery').load_images())
        with self._lock:
            self._running = False
            self.cancel_requested = False

class GalleryScreen(Screen):
    selected = ListProperty([])
    _auto_sync_event = None  # <-- Add this line

    def show_black_overlay(self):
        if not hasattr(self, '_overlay') or self._overlay is None:
            self._overlay = BlackOverlay()
        self._overlay.open()

    def on_enter(self):
        self.load_images()
        app = App.get_running_app()
        interval = app.settings.get("auto_sync_interval", 0)
        # Prevent multiple intervals
        if interval:
            if not hasattr(self, '_auto_sync_event') or self._auto_sync_event is None:
                def auto_sync(dt):
                    self.start_sync_with_overlay()
                self._auto_sync_event = Clock.schedule_interval(auto_sync, interval * 60)
        else:
            # If interval is 0, cancel any existing event
            if hasattr(self, '_auto_sync_event') and self._auto_sync_event is not None:
                self._auto_sync_event.cancel()
                self._auto_sync_event = None

    def on_leave(self):
        # Optionally, cancel auto-sync when leaving the screen
        if hasattr(self, '_auto_sync_event') and self._auto_sync_event is not None:
            self._auto_sync_event.cancel()
            self._auto_sync_event = None

    def load_images(self):
        app = App.get_running_app()
        image_files = app.scan_images()
        image_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)

        # Find images missing thumbnails
        missing_thumbs = []
        for f in image_files:
            thumb_path = get_thumbnail_path(f)
            if not os.path.exists(thumb_path):
                missing_thumbs.append(f)

        if missing_thumbs:
            overlay = ThumbnailProgressOverlay(total=len(missing_thumbs))
            overlay.open()

            def create_thumbs():
                from concurrent.futures import ThreadPoolExecutor, as_completed
                completed = [0]

                def make_thumb(path):
                    generate_thumbnail(path)
                    completed[0] += 1
                    Clock.schedule_once(lambda dt: overlay.update(completed[0]))

                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = [executor.submit(make_thumb, f) for f in missing_thumbs]
                    for _ in as_completed(futures):
                        pass

                Clock.schedule_once(lambda dt: overlay.dismiss())
                Clock.schedule_once(lambda dt: self._finish_load_images(image_files))

            threading.Thread(target=create_thumbs, daemon=True).start()
        else:
            self._finish_load_images(image_files)

    def _finish_load_images(self, image_files):
        app = App.get_running_app()
        self.ids.rv.data = [{
            'source': generate_thumbnail(f),
            'path': f,
            'status': app.db.get(f, {}).get('status', 'pending'),
            'note': app.db.get(f, {}).get('note', '')
        } for f in image_files]
        # self.update_status_label()  # Remove this line

    def sync_now(self):
        self.start_sync_with_overlay()

    def start_sync_with_overlay(self):
        app = App.get_running_app()
        to_upload = [p for p, i in app.db.items() if i.get("status") != "uploaded" and os.path.exists(p)]
        if to_upload:
            app.upload_manager.add_tasks(to_upload)
            self.show_upload_progress(len(to_upload))

    def backup_selected(self):
        app = App.get_running_app()
        selected = list(self.selected)
        if not selected:
            return
        to_upload = []
        for path in selected:
            if app.db.get(path, {}).get("status") != "uploaded":
                app.upload_manager.add_tasks([path])
                to_upload.append(path)
            else:
                # If already uploaded, just re-upload without DB update, but suppress popup
                app.upload_image_without_db(path, show_progress=False)
                to_upload.append(path)
        self.selected.clear()
        # Always show upload overlay for the batch
        if to_upload:
            self.show_upload_progress(len(to_upload))

    def get_upload_summary(self):
        app = App.get_running_app()
        db = app.db
        total = len(db)
        uploading = sum(1 for v in db.values() if v.get("status") == "uploading")
        uploaded = sum(1 for v in db.values() if v.get("status") == "uploaded")
        failed = sum(1 for v in db.values() if v.get("status") == "failed")
        pending = sum(1 for v in db.values() if v.get("status") == "pending" or not v.get("status"))
        return (
            f"Total: {total} | "
            f"Uploaded: {uploaded} | "
            f"Uploading: {uploading} | "
            f"Failed: {failed} | "
            f"Pending: {pending}"
        )

    def show_upload_progress(self, total):
        if total == 0:
            return
        def on_cancel():
            app = App.get_running_app()
            app.upload_manager.cancel()
            # After current uploads finish, go back to main screen
            def go_home(dt):
                app.sm.current = 'gallery'
            # Wait a bit to allow overlay to close and uploads to finish
            Clock.schedule_once(go_home, 0.5)
        overlay = UploadProgressOverlay(total=total, on_cancel=on_cancel)
        overlay.summary = self.get_upload_summary()
        overlay.open()
        def progress_callback(completed, total):
            overlay.update(completed, self.get_upload_summary())
            if completed >= total or App.get_running_app().upload_manager.cancel_requested:
                overlay.dismiss()
        App.get_running_app().upload_manager.set_progress_callback(progress_callback)

    def open_settings(self):
        App.get_running_app().sm.current = 'settings'

    def toggle_select(self, path, checkbox, value):
        if value:
            if path not in self.selected:
                self.selected.append(path)
        else:
            if path in self.selected:
                self.selected.remove(path)

class PreviewScreen(Screen):
    images = ListProperty([])
    current_index = 0
    current_path = StringProperty("")  # Add this property

    def set_images(self, images, index):
        self.images = images
        self.current_index = index
        self.update_view()

    def update_view(self):
        if not self.images:
            self.ids.img.source = "assets/placeholder.png"
            self.current_path = ""
        else:
            self.ids.img.source = self.images[self.current_index]
            self.current_path = self.images[self.current_index]

    def swipe_left(self):
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            self.update_view()

    def swipe_right(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_view()

    def backup_now(self):
        app = App.get_running_app()
        if not self.images:
            return
        current_image = self.images[self.current_index]
        # If not uploaded, update DB and use normal upload logic
        if app.db.get(current_image, {}).get("status") != "uploaded":
            app.upload_manager.add_tasks([current_image])
            # Show upload overlay for 1 image
            gallery_screen = app.sm.get_screen('gallery')
            gallery_screen.show_upload_progress(1)
        else:
            # If already uploaded, just re-upload without DB update, but show progress
            app.upload_image_without_db(current_image, show_progress=True)

class SettingsScreen(Screen):
    def paste_to_focused(self):
        for child in self.walk():
            if isinstance(child, TextInput) and child.focus:
                child.text = Clipboard.paste()
                break
    def on_pre_enter(self):
        s = App.get_running_app().settings
        self.ids.token_input.text = s.get("bot_token", "")
        self.ids.chat_id_input.text = s.get("chat_id", "")
        self.ids.auto_input.text = str(s.get("auto_sync_interval", ""))
        self.ids.wifi_checkbox.active = s.get("wifi_only", False)
        self.ids.subfolder_checkbox.active = s.get("scan_subfolders", True)
        self.ids.exclude_input.text = ",".join(s.get("exclude_paths", []))
        self.ids.include_input.text = ",".join(s.get("include_paths", []))



    def save_settings(self):
        s = App.get_running_app().settings
        s["bot_token"] = self.ids.token_input.text.strip()
        s["chat_id"] = self.ids.chat_id_input.text.strip()
        s["auto_sync_interval"] = int(self.ids.auto_input.text or 0)
        s["wifi_only"] = self.ids.wifi_checkbox.active
        s["scan_subfolders"] = self.ids.subfolder_checkbox.active
        s["exclude_paths"] = [p.strip() for p in self.ids.exclude_input.text.split(",") if p.strip()]
        s["include_paths"] = [p.strip() for p in self.ids.include_input.text.split(",") if p.strip()]

        save_json(SETTINGS_PATH, s)
        self.show_popup("Settings saved!")

    def show_popup(self, text):
        Popup(title="Info", content=Label(text=text), size_hint=(0.8, 0.2)).open()

    def backup_database(self):
        if platform == "android":
            # Always save to Download folder on Android
            dest = "/storage/emulated/0/Download/db_backup.json"
            try:
                with open(DB_PATH, "r") as src, open(dest, "w") as dst:
                    dst.write(src.read())
                self.show_popup(f"Database backed up to:\n{dest}")
            except Exception as e:
                self.show_popup(f"Backup failed: {e}")
            return
        def do_backup(folder):
            if folder:
                dest = os.path.join(folder, "db_backup.json")
                try:
                    with open(DB_PATH, "r") as src, open(dest, "w") as dst:
                        dst.write(src.read())
                    self.show_popup(f"Database backed up to:\n{dest}")
                except Exception as e:
                    self.show_popup(f"Backup failed: {e}")
                return
            # Fallback to Kivy file chooser
            content = FileChooserIconView()
            popup = Popup(title="Select folder to save DB backup", content=content, size_hint=(0.9, 0.9))
            def on_selection(instance, selection):
                if selection:
                    dest = os.path.join(selection[0], "db_backup.json") if os.path.isdir(selection[0]) else selection[0]
                    try:
                        with open(DB_PATH, "r") as src, open(dest, "w") as dst:
                            dst.write(src.read())
                        self.show_popup(f"Database backed up to:\n{dest}")
                    except Exception as e:
                        self.show_popup(f"Backup failed: {e}")
                    popup.dismiss()
            content.bind(on_submit=on_selection)
            popup.open()
        pick_folder("Select folder to save DB backup", callback=do_backup)

    def restore_database(self):
        if platform == "android":
            # Always restore from Download folder if file exists
            src = "/storage/emulated/0/Download/db_backup.json"
            if os.path.exists(src):
                try:
                    with open(src, "r") as fsrc, open(DB_PATH, "w") as fdst:
                        fdst.write(fsrc.read())
                    self.show_popup("Database restored from Download. Please restart app.")
                except Exception as e:
                    self.show_popup(f"Restore failed: {e}")
                return
            else:
                self.show_popup("No db_backup.json found in Download folder.")
                return
        # ...existing code for other platforms...
        def do_restore(file):
            if file:
                try:
                    with open(file, "r") as fsrc, open(DB_PATH, "w") as fdst:
                        fdst.write(fsrc.read())
                    self.show_popup("Database restored. Please restart app.")
                except Exception as e:
                    self.show_popup(f"Restore failed: {e}")
                return
            # Fallback to Kivy file chooser
            content = FileChooserIconView()
            popup = Popup(title="Select DB backup to restore", content=content, size_hint=(0.9, 0.9))
            def on_selection(instance, selection):
                if selection:
                    src = selection[0]
                    try:
                        with open(src, "r") as fsrc, open(DB_PATH, "w") as fdst:
                            fdst.write(fsrc.read())
                        self.show_popup("Database restored. Please restart app.")
                    except Exception as e:
                        self.show_popup(f"Restore failed: {e}")
                    popup.dismiss()
            content.bind(on_submit=on_selection)
            popup.open()
        pick_file("Select DB backup to restore", callback=do_restore)

    def backup_settings(self):
        if platform == "android":
            # Always save to Download folder on Android
            dest = "/storage/emulated/0/Download/settings_backup.json"
            try:
                with open(SETTINGS_PATH, "r") as src, open(dest, "w") as dst:
                    dst.write(src.read())
                self.show_popup(f"Settings backed up to:\n{dest}")
            except Exception as e:
                self.show_popup(f"Backup failed: {e}")
            return
        # ...existing code for other platforms...
        def do_backup(folder):
            if folder:
                dest = os.path.join(folder, "settings_backup.json")
                try:
                    with open(SETTINGS_PATH, "r") as src, open(dest, "w") as dst:
                        dst.write(src.read())
                    self.show_popup(f"Settings backed up to:\n{dest}")
                except Exception as e:
                    self.show_popup(f"Backup failed: {e}")
                return
            # Fallback to Kivy file chooser
            content = FileChooserIconView()
            popup = Popup(title="Select folder to save settings backup", content=content, size_hint=(0.9, 0.9))
            def on_selection(instance, selection):
                if selection:
                    dest = os.path.join(selection[0], "settings_backup.json") if os.path.isdir(selection[0]) else selection[0]
                    try:
                        with open(SETTINGS_PATH, "r") as src, open(dest, "w") as dst:
                            dst.write(src.read())
                        self.show_popup(f"Settings backed up to:\n{dest}")
                    except Exception as e:
                        self.show_popup(f"Backup failed: {e}")
                    popup.dismiss()
            content.bind(on_submit=on_selection)
            popup.open()
        pick_folder("Select folder to save settings backup", callback=do_backup)

    def restore_settings(self):
        if platform == "android":
            # Always restore from Download folder if file exists
            src = "/storage/emulated/0/Download/settings_backup.json"
            if os.path.exists(src):
                try:
                    with open(src, "r") as fsrc, open(SETTINGS_PATH, "w") as fdst:
                        fdst.write(fsrc.read())
                    self.show_popup("Settings restored from Download. Please restart app.")
                except Exception as e:
                    self.show_popup(f"Restore failed: {e}")
                return
            else:
                self.show_popup("No settings_backup.json found in Download folder.")
                return
        # ...existing code for other platforms...
        def do_restore(file):
            if file:
                try:
                    with open(file, "r") as fsrc, open(SETTINGS_PATH, "w") as fdst:
                        fdst.write(fsrc.read())
                    self.show_popup("Settings restored. Please restart app.")
                except Exception as e:
                    self.show_popup(f"Restore failed: {e}")
                return
            # Fallback to Kivy file chooser
            content = FileChooserIconView()
            popup = Popup(title="Select settings backup to restore", content=content, size_hint=(0.9, 0.9))
            def on_selection(instance, selection):
                if selection:
                    src = selection[0]
                    try:
                        with open(src, "r") as fsrc, open(SETTINGS_PATH, "w") as fdst:
                            fdst.write(fsrc.read())
                        self.show_popup("Settings restored. Please restart app.")
                    except Exception as e:
                        self.show_popup(f"Restore failed: {e}")
                popup.dismiss()
            content.bind(on_submit=on_selection)
            popup.open()
        pick_file("Select settings backup to restore", callback=do_restore)

def pick_folder(title="Select Folder", callback=None):
    if platform == "win":
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            folder = filedialog.askdirectory(title=title)
            root.destroy()
            if callback:
                callback(folder)
            return folder
        except Exception as e:
            print("Tkinter folder picker failed:", e)
            if callback:
                callback(None)
            return None
    elif platform == "android":
        try:
            from plyer import filechooser
            def _on_selection(selection):
                if callback:
                    callback(selection[0] if selection else None)
            filechooser.open_dir(on_selection=_on_selection)
            return None  # Result will be handled asynchronously
        except Exception as e:
            print("Android folder picker failed:", e)
            if callback:
                callback(None)
            return None
    return None

def pick_file(title="Select File", callback=None):
    if platform == "win":
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            file = filedialog.askopenfilename(title=title)
            root.destroy()
            if callback:
                callback(file)
            return file
        except Exception as e:
            print("Tkinter file picker failed:", e)
            if callback:
                callback(None)
            return None
    elif platform == "android":
        try:
            from plyer import filechooser
            def _on_selection(selection):
                if callback:
                    callback(selection[0] if selection else None)
            filechooser.open_file(on_selection=_on_selection)
            return None  # Result will be handled asynchronously
        except Exception as e:
            print("Android file picker failed:", e)
            if callback:
                callback(None)
            return None
    return None

class ImageRecycleView(RecycleView):
    pass

class ImageBackupApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.uploading_count = 0
        self.total_to_upload = 0
        self.max_workers = 4  # Max concurrent uploads
        self.max_uploads_per_minute = 30  # Rate limit
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self._last_upload_times = []
        self.upload_manager = UploadManager(self, max_workers=self.max_workers, max_uploads_per_minute=self.max_uploads_per_minute)
        self._last_upload_time_per_chat = {}  # Add this class attribute

    def build(self):
        self.db = load_json(DB_PATH, {})
        self.settings = load_json(SETTINGS_PATH, {})
        self.last_sync = None
        self.sm = ScreenManager()
        self.sm.add_widget(GalleryScreen(name='gallery'))
        self.sm.add_widget(PreviewScreen(name='preview'))
        self.sm.add_widget(SettingsScreen(name='settings'))
        if platform == "android":
            self._acquire_wake_lock()
        return self.sm

    def _acquire_wake_lock(self):
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            Context = autoclass('android.content.Context')
            PowerManager = autoclass('android.os.PowerManager')
            pm = activity.getSystemService(Context.POWER_SERVICE)
            self._wake_lock = pm.newWakeLock(PowerManager.FULL_WAKE_LOCK, "ImageBackupApp:WakeLock")
            self._wake_lock.acquire()
        except Exception as e:
            print("Could not acquire wake lock:", e)

    def on_stop(self):
        # Release the wake lock when the app stops
        if hasattr(self, '_wake_lock'):
            try:
                self._wake_lock.release()
            except Exception:
                pass

    def scan_images(self):
        found = []
        include_paths = self.settings.get("include_paths", [GALLERY_PATH])  # fallback to legacy
        exclude = set(os.path.abspath(p) for p in self.settings.get("exclude_paths", []))

        for base_path in include_paths:
            for root, dirs, files in os.walk(base_path):
                root_abs = os.path.abspath(root)

                # Exclude user-defined paths
                if any(root_abs.startswith(e) for e in exclude):
                    continue

                # Exclude all `.thumbs` folders and hidden folders
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                if not self.settings.get("scan_subfolders", True):
                    dirs[:] = []  # stop recursion

                for file in files:
                    # Exclude hidden files
                    if file.startswith('.'):
                        continue
                    IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.tiff', '.tif', '.heic', '.heif', '.ico', '.jfif', '.pjpeg', '.pjp')
                    if file.lower().endswith(IMAGE_EXTS):
                        path = os.path.join(root, file)
                        if path not in self.db:
                            self.db[path] = {"hash": get_image_hash(path)}
                        found.append(path)

        save_json(DB_PATH, self.db)
        return found





    def sync_images(self):
        # Deprecated: use GalleryScreen.sync_now instead
        pass

    def upload_image(self, path, force=False):
        # Deprecated: use UploadManager.add_tasks instead
        pass

    def _upload_image_internal(self, path):
        token = self.settings.get("bot_token")
        chat_id = self.settings.get("chat_id")
        if not token or not chat_id:
            return

        if self.db.get(path, {}).get("status") == "uploaded":
            return

        self.db[path]["status"] = "uploading"
        save_json(DB_PATH, self.db)
        # Clock.schedule_once(lambda dt: self.sm.get_screen('gallery').update_status_label())  # Remove

        photo_success = False
        doc_success = False

        # --- Begin Telegram rate limiting logic ---
        def rate_limit(chat_id):
            now = time.time()
            last_time = self._last_upload_time_per_chat.get(chat_id, 0)
            elapsed = now - last_time
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)
            self._last_upload_time_per_chat[chat_id] = time.time()

        try:
            rate_limit(chat_id)
            with open(path, 'rb') as photo_file:
                photo_response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id},
                    files={"photo": photo_file}
                )
                photo_success = (photo_response.status_code == 200)
            # Wait 1 second after sending photo
            time.sleep(1)
        except Exception as e:
            print(f"[Photo] Upload failed: {e}")

        try:
            rate_limit(chat_id)
            with open(path, 'rb') as doc_file:
                doc_response = requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": chat_id},
                    files={"document": doc_file}
                )
                doc_success = (doc_response.status_code == 200)
            # Wait 1 second after sending document
            time.sleep(1)
        except Exception as e:
            print(f"[Document] Upload failed: {e}")

        # Update status
        if doc_success:
            self.db[path]["status"] = "uploaded"
            if not photo_success:
                self.db[path]["note"] = "Image not uploaded"
            else:
                self.db[path].pop("note", None)
        else:
            self.db[path]["status"] = "failed"
            if photo_success:
                self.db[path]["note"] = "File not uploaded"
            else:
                self.db[path]["note"] = "Image and file upload failed"

        save_json(DB_PATH, self.db)
        # Clock.schedule_once(lambda dt: self.sm.get_screen('gallery').update_status_label())  # Remove

    def _show_popup(self, text):
        def show():
            Popup(title="Notice", content=Label(text=text), size_hint=(0.75, 0.25)).open()
        Clock.schedule_once(lambda dt: show())

    def upload_image_without_db(self, path, show_progress=True):
        """Upload image to Telegram without updating the database."""
        token = self.settings.get("bot_token")
        chat_id = self.settings.get("chat_id")
        if not token or not chat_id:
            if show_progress:
                self._show_popup("Bot token or chat id not set.")
            return

        def do_upload():
            photo_success = False
            doc_success = False
            try:
                with open(path, 'rb') as photo_file:
                    photo_response = requests.post(
                        f"https://api.telegram.org/bot{token}/sendPhoto",
                        data={"chat_id": chat_id},
                        files={"photo": photo_file}
                    )
                    photo_success = (photo_response.status_code == 200)
            except Exception as e:
                print(f"[Photo] Upload failed: {e}")

            try:
                with open(path, 'rb') as doc_file:
                    doc_response = requests.post(
                        f"https://api.telegram.org/bot{token}/sendDocument",
                        data={"chat_id": chat_id},
                        files={"document": doc_file}
                    )
                    doc_success = (doc_response.status_code == 200)
            except Exception as e:
                print(f"[Document] Upload failed: {e}")

            if show_progress:
                if doc_success or photo_success:
                    self._show_popup("Upload complete!")
                else:
                    self._show_popup("Upload failed.")

        threading.Thread(target=do_upload, daemon=True).start()

if __name__ == '__main__':
    ImageBackupApp().run()
