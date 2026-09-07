package com.vesper.companion.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.provider.Settings
import android.util.Log
import androidx.core.app.NotificationCompat

class AlfredForegroundService : Service() {

    companion object {
        private const val TAG = "AlfredForegroundService"
        const val CHANNEL_ID = "vesper_alfred_service_channel"
        const val NOTIFICATION_ID = 1842
        var isRunning = false

        fun start(context: Context, title: String? = null, content: String? = null) {
            try {
                val intent = Intent(context, AlfredForegroundService::class.java).apply {
                    putExtra("title", title ?: "Alfred (VESPER Nexus)")
                    putExtra("content", content ?: "Alfred is vigilantly standing watch, sir.")
                }
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    context.startForegroundService(intent)
                } else {
                    context.startService(intent)
                }
                Log.i(TAG, "Alfred foreground service start intent dispatched")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start Alfred foreground service: ${e.message}")
            }
        }

        fun stop(context: Context) {
            try {
                val intent = Intent(context, AlfredForegroundService::class.java)
                context.stopService(intent)
                isRunning = false
                Log.i(TAG, "Alfred foreground service stop intent dispatched")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to stop Alfred foreground service: ${e.message}")
            }
        }

        fun requestIgnoreBatteryOptimizations(context: Context): Boolean {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                try {
                    val powerManager = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
                    if (powerManager != null && !powerManager.isIgnoringBatteryOptimizations(context.packageName)) {
                        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                            data = Uri.parse("package:${context.packageName}")
                            flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        }
                        context.startActivity(intent)
                        return true
                    }
                } catch (e: Exception) {
                    try {
                        val intent = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS).apply {
                            flags = Intent.FLAG_ACTIVITY_NEW_TASK
                        }
                        context.startActivity(intent)
                        return true
                    } catch (err: Exception) {
                        Log.e(TAG, "Could not open battery optimization settings: ${err.message}")
                    }
                }
            }
            return false
        }
    }

    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        isRunning = true
        createNotificationChannel()

        try {
            val powerManager = getSystemService(Context.POWER_SERVICE) as? PowerManager
            if (powerManager != null) {
                wakeLock = powerManager.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "VESPER:AlfredWakeLock"
                ).apply {
                    setReferenceCounted(false)
                    acquire(12 * 60 * 60 * 1000L) // 12 hours max safety limit
                }
                Log.i(TAG, "Alfred partial wake lock acquired")
            }
        } catch (e: Exception) {
            Log.w(TAG, "PowerManager wake lock acquisition exception: ${e.message}")
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val title = intent?.getStringExtra("title") ?: "Alfred (VESPER Nexus)"
        val content = intent?.getStringExtra("content") ?: "Alfred is vigilantly standing watch, sir."

        val notification = buildNotification(title, content)

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
                } else {
                    0
                }
                startForeground(NOTIFICATION_ID, notification, type)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
            isRunning = true
            Log.i(TAG, "Alfred foreground service running with ongoing notification")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to startForeground: ${e.message}")
        }

        return START_STICKY
    }

    override fun onDestroy() {
        isRunning = false
        try {
            if (wakeLock?.isHeld == true) {
                wakeLock?.release()
                Log.i(TAG, "Alfred partial wake lock released")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Error releasing wake lock: ${e.message}")
        }
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Alfred Persistent Monitor",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Maintains continuous background notification relay and cluster synchronization."
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(title: String, content: String): Notification {
        val launchIntent = packageManager.getLaunchIntentForPackage(packageName)
        val pendingIntent = if (launchIntent != null) {
            PendingIntent.getActivity(
                this,
                0,
                launchIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
            )
        } else {
            null
        }

        val appIcon = applicationInfo.icon
        val iconRes = if (appIcon != 0) appIcon else android.R.drawable.ic_dialog_info

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(title)
            .setContentText(content)
            .setSubText("VESPER Autonomous Nexus")
            .setSmallIcon(iconRes)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)

        if (pendingIntent != null) {
            builder.setContentIntent(pendingIntent)
        }

        return builder.build()
    }
}
