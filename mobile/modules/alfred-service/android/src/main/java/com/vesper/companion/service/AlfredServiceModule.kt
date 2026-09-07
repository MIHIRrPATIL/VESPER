package com.vesper.companion.service

import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition

class AlfredServiceModule : Module() {
    override fun definition() = ModuleDefinition {
        Name("AlfredService")

        AsyncFunction("startService") { title: String?, content: String? ->
            val context = appContext.reactContext ?: return@AsyncFunction false
            AlfredForegroundService.start(context, title, content)
            true
        }

        AsyncFunction("stopService") {
            val context = appContext.reactContext ?: return@AsyncFunction false
            AlfredForegroundService.stop(context)
            true
        }

        AsyncFunction("isServiceRunning") {
            AlfredForegroundService.isRunning
        }

        AsyncFunction("requestIgnoreBatteryOptimizations") {
            val activity = appContext.currentActivity ?: appContext.reactContext
            if (activity != null) {
                AlfredForegroundService.requestIgnoreBatteryOptimizations(activity)
            } else {
                false
            }
        }
    }
}
