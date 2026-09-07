const { withAndroidManifest } = require('@expo/config-plugins');

function withAndroidAllowBackup(config) {
  return withAndroidManifest(config, async (config) => {
    const androidManifest = config.modResults.manifest;
    if (!androidManifest) {
      return config;
    }

    // Ensure tools namespace is declared on <manifest>
    if (!androidManifest.$) {
      androidManifest.$ = {};
    }
    if (!androidManifest.$['xmlns:tools']) {
      androidManifest.$['xmlns:tools'] = 'http://schemas.android.com/tools';
    }

    // Locate the <application> element
    const application = Array.isArray(androidManifest.application)
      ? androidManifest.application[0]
      : androidManifest.application;

    if (application) {
      if (!application.$) {
        application.$ = {};
      }

      // Ensure tools:replace includes android:allowBackup
      const currentReplace = application.$['tools:replace'];
      if (!currentReplace) {
        application.$['tools:replace'] = 'android:allowBackup';
      } else {
        const parts = currentReplace.split(',').map((p) => p.trim());
        if (!parts.includes('android:allowBackup')) {
          parts.push('android:allowBackup');
          application.$['tools:replace'] = parts.join(',');
        }
      }

      application.$['android:allowBackup'] = 'false';
      application.$['android:usesCleartextTraffic'] = 'true';
    }

    return config;
  });
}

module.exports = withAndroidAllowBackup;
