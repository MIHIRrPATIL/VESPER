# VESPER Mobile Companion (Native Android & iOS)

This folder contains the companion mobile client for notification mirroring, calendar sync, and quick capture.

* **Android**: Persistent Foreground Service implementing `NotificationListenerService` to capture, sanitize, and relay prioritized alerts from WhatsApp, Slack, Telegram, and Gmail.
* **iOS**: Native `EventKit` integration for Calendar/Reminders synchronization + Action/Share Sheet Extension.
