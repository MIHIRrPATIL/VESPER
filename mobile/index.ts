import { registerRootComponent } from 'expo';
import { AppRegistry, Platform } from 'react-native';
import App from './App';
import { gatewayClient } from './src/services/gateway';

// Register Android Native Notification Interceptor (Active in standalone APK)
if (Platform.OS === 'android') {
  try {
    const { RNAndroidNotificationListenerHeadlessJsName } = require('react-native-android-notification-listener');

    const IGNORED_PACKAGES = new Set([
      'android',
      'com.android.systemui',
      'com.google.android.gms',
      'com.google.android.googlequicksearchbox',
      'com.sec.android.app.launcher',
      'com.vesper.companion',
      'host.exp.exponent',
    ]);

    const SILENCED_TRACKER_PACKAGES = new Set([
      'com.noisefit',
      'com.fitbit',
      'com.huami.watch',
      'com.garmin.android.apps.connectmobile',
      'com.samsung.android.app.watchmanager',
      'com.google.android.apps.fitness',
      'com.sec.android.app.shealth',
    ]);

    // Track recent notification state by app package + title (OS Notification Panel model)
    const recentNotifs = new Map<string, { text: string; time: number }>();

    const headlessNotificationListener = async ({ notification }: { notification: string }) => {
      if (!notification) return;
      try {
        const parsed = typeof notification === 'string' ? JSON.parse(notification) : notification;
        const pkg = (parsed.app || '').toLowerCase();

        // 1. Ignore internal and system noise (never drop telephony / phone calls)
        const isTelephony =
          pkg.includes('dialer') ||
          pkg.includes('incallui') ||
          pkg.includes('telecom') ||
          pkg.includes('telephony');

        if (!isTelephony && (IGNORED_PACKAGES.has(pkg) || pkg.startsWith('com.android.internal'))) {
          return;
        }

        const isMaskedText = (val: string): boolean => {
          const v = (val || '').toLowerCase().trim();
          return (
            v === 'content hidden' ||
            v === 'hidden content' ||
            v === 'sensitive content' ||
            v === '1 new message' ||
            v === 'new message' ||
            v === 'hidden message' ||
            /^[*•\s]{3,}$/.test(v)
          );
        };

        const title = (parsed.title || parsed.titleBig || '').trim();

        // Deep extra inspection: Prioritize unmasked bigText and textLines over masked EXTRA_TEXT
        let rawText = '';
        if (parsed.bigText && typeof parsed.bigText === 'string' && !isMaskedText(parsed.bigText)) {
          rawText = parsed.bigText.trim();
        } else if (Array.isArray(parsed.groupedMessages) && parsed.groupedMessages.length > 0) {
          const lines = parsed.groupedMessages
            .map((m: any) => (typeof m === 'string' ? m : m?.text || ''))
            .filter((l: string) => l && !isMaskedText(l));
          if (lines.length > 0) {
            rawText = lines.join(' \u2022 ').trim();
          }
        }

        if (!rawText && parsed.text && typeof parsed.text === 'string' && !isMaskedText(parsed.text)) {
          rawText = parsed.text.trim();
        }
        if (!rawText && parsed.subText && typeof parsed.subText === 'string' && !isMaskedText(parsed.subText)) {
          rawText = parsed.subText.trim();
        }
        if (!rawText && parsed.extraInfoText && typeof parsed.extraInfoText === 'string' && !isMaskedText(parsed.extraInfoText)) {
          rawText = parsed.extraInfoText.trim();
        }
        if (!rawText) {
          rawText = (parsed.text || parsed.bigText || parsed.subText || '').trim();
        }

        const text = rawText;
        const isMasked = isMaskedText(text);

        // 2. Ignore empty / blank notifications
        if (!title && !text) {
          return;
        }

        const lowerText = text.toLowerCase();
        const lowerTitle = title.toLowerCase();

        // 3. Filter persistent background service keep-alives (e.g. "NoiseFit is running")
        const isKeepAlive =
          lowerText.includes('is running') ||
          lowerTitle.includes('is running') ||
          lowerText.includes('running in background') ||
          lowerText.includes('running in the background') ||
          lowerText.includes('tap for info') ||
          lowerText.includes('touch for more information') ||
          lowerText.includes('syncing in background');

        if (isKeepAlive && (SILENCED_TRACKER_PACKAGES.has(pkg) || pkg.includes('fit') || pkg.includes('wear'))) {
          return;
        }

        // 3b. Filter WhatsApp summary headers and own outgoing messages
        if (
          /\b\d+\s+messages?\s+from\s+\d+\s+chats?\b/i.test(text) ||
          /\b\d+\s+new\s+messages?\b/i.test(text) ||
          lowerTitle === 'you' ||
          lowerTitle === 'me' ||
          lowerText === 'just now' ||
          lowerText === 'online'
        ) {
          return;
        }

        const now = Date.now();

        // Clean up old entries from cache if it grows large
        if (recentNotifs.size > 120) {
          for (const [k, v] of recentNotifs.entries()) {
            if (now - v.time > 120000) {
              recentNotifs.delete(k);
            }
          }
        }

        // 4. In-place OS notification shade key: `${pkg}:${title}`
        const notifKey = `${pkg}:${title}`;
        const existing = recentNotifs.get(notifKey);

        const isProgress =
          /\d+(\.\d+)?\s*(MB|KB|GB|B|%)\s*\//i.test(text) ||
          lowerText.includes('downloading') ||
          /\d+%\s*•/i.test(text);
        const isComplete =
          lowerText.includes('complete') ||
          lowerText.includes('finished') ||
          lowerTitle.includes('download complete');

        const isFinancial =
          /\b(debited|credited|spent|paid|sent|transferred|txn|balance|withdrawn|refund|deposit|upi|emi|bank|salary)\b/i.test(`${title} ${text}`) ||
          /\b(bank|hdfc|sbi|icici|axis|kotak|paytm|phonepe|gpay|cred)\b/i.test(pkg);
        const isOtp =
          /\b(otp|verification code|security code|auth code|secret code)\b/i.test(`${title} ${text}`);

        if (existing) {
          // If previous notification was masked (e.g. screen was locked) and this one is unmasked (screen unlocked), ALWAYS process!
          const wasMasked = existing.text && isMaskedText(existing.text);
          if (wasMasked && !isMasked) {
            console.log(`[NativeListener] Screen unlocked / de-masking update received for ${pkg}: "${text}"`);
          } else {
            // Throttling byte-by-byte download updates to at most once every 10 seconds
            if (isProgress && !isComplete && now - existing.time < 10000) {
              existing.text = text;
              return;
            }

            // Suppress identical alert text within 30 seconds (do not suppress distinct financial transactions)
            if (existing.text === text && now - existing.time < 30000) {
              return;
            }
          }
        }

        recentNotifs.set(notifKey, { text, time: now });

        console.log('[NativeListener] Intercepted live OS notification:', parsed.app, title, isMasked ? '(MASKED)' : '');

        let priority: 'URGENT' | 'HIGH' | 'MEDIUM' | 'LOW' = 'MEDIUM';
        if (isTelephony || isOtp) {
          priority = 'URGENT';
        } else if (isFinancial) {
          priority = 'HIGH';
        }

        let category = 'GENERAL';
        if (isOtp) category = 'URGENT';
        else if (isFinancial) category = 'FINANCIAL';
        else if (isTelephony) category = 'DIRECT';

        const payload = {
          package_name: parsed.app || 'com.unknown.app',
          app_name: parsed.app || 'Android App',
          title: title || 'Notification',
          text: text,
          subtext: parsed.subText,
          priority: priority,
          category: category,
          is_masked: isMasked,
          post_time: now / 1000.0,
        };

        // 1. Try sending over WebSocket if already connected
        const sentWs = gatewayClient.sendNotificationRelay(payload);

        // 2. If WebSocket is not connected (e.g. phone screen off or app backgrounded),
        // await direct HTTP relay so Headless JS task holds wake lock until delivery
        if (!sentWs) {
          console.log('[NativeListener] WebSocket not connected in background. Delivering via direct HTTP relay...');
          await gatewayClient.postNotificationDirectly(payload);
        }

        // 3. Trigger reconnect in background
        if (gatewayClient.getStatus() !== 'connected') {
          gatewayClient.connect();
        }
      } catch (err) {
        console.warn('[NativeListener] Failed to parse intercepted notification:', err);
      }
    };

    if (RNAndroidNotificationListenerHeadlessJsName) {
      AppRegistry.registerHeadlessTask(
        RNAndroidNotificationListenerHeadlessJsName,
        () => headlessNotificationListener
      );
    }
  } catch {
    // Expected in Expo Go where native module is not compiled into the sandbox APK
  }
}

// registerRootComponent calls AppRegistry.registerComponent('main', () => App);
registerRootComponent(App);
