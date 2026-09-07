package com.vesper.companion.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

class AlfredBootReceiver : BroadcastReceiver() {
    companion object {
        private const val TAG = "AlfredBootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action
        Log.i(TAG, "Device boot signal received: $action")
        if (Intent.ACTION_BOOT_COMPLETED == action || "android.intent.action.QUICKBOOT_POWERON" == action) {
            AlfredForegroundService.start(
                context,
                "Alfred (VESPER Nexus)",
                "Alfred has resumed vigilance following system restart, sir."
            )
        }
    }
}
