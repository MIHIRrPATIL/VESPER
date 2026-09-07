const { withAndroidManifest } = require('@expo/config-plugins');

function withAlfredService(config) {
  return withAndroidManifest(config, async (config) => {
    const manifest = config.modResults.manifest;
    if (!manifest) {
      return config;
    }

    // 1. Ensure uses-permission array exists
    if (!Array.isArray(manifest['uses-permission'])) {
      manifest['uses-permission'] = [];
    }

    const requiredPermissions = [
      'android.permission.FOREGROUND_SERVICE',
      'android.permission.FOREGROUND_SERVICE_DATA_SYNC',
      'android.permission.WAKE_LOCK',
      'android.permission.POST_NOTIFICATIONS',
      'android.permission.RECEIVE_BOOT_COMPLETED',
      'android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS',
    ];

    for (const perm of requiredPermissions) {
      const exists = manifest['uses-permission'].some(
        (p) => p.$ && p.$['android:name'] === perm
      );
      if (!exists) {
        manifest['uses-permission'].push({
          $: { 'android:name': perm },
        });
      }
    }

    // 2. Locate or initialize application node
    const application = Array.isArray(manifest.application)
      ? manifest.application[0]
      : manifest.application;

    if (application) {
      if (!Array.isArray(application.service)) {
        application.service = application.service ? [application.service] : [];
      }

      const serviceName = 'com.vesper.companion.service.AlfredForegroundService';
      const serviceExists = application.service.some(
        (s) => s.$ && s.$['android:name'] === serviceName
      );

      if (!serviceExists) {
        application.service.push({
          $: {
            'android:name': serviceName,
            'android:foregroundServiceType': 'dataSync',
            'android:exported': 'false',
          },
        });
      }

      if (!Array.isArray(application.receiver)) {
        application.receiver = application.receiver ? [application.receiver] : [];
      }

      const receiverName = 'com.vesper.companion.service.AlfredBootReceiver';
      const receiverExists = application.receiver.some(
        (r) => r.$ && r.$['android:name'] === receiverName
      );

      if (!receiverExists) {
        application.receiver.push({
          $: {
            'android:name': receiverName,
            'android:enabled': 'true',
            'android:exported': 'true',
          },
          'intent-filter': [
            {
              action: [
                { $: { 'android:name': 'android.intent.action.BOOT_COMPLETED' } },
                { $: { 'android:name': 'android.intent.action.QUICKBOOT_POWERON' } },
              ],
            },
          ],
        });
      }
    }

    return config;
  });
}

module.exports = withAlfredService;
