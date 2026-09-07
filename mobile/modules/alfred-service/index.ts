import { requireNativeModule, Platform } from "expo-modules-core";

export interface AlfredServiceModuleInterface {
  startService(title?: string, content?: string): Promise<boolean>;
  stopService(): Promise<boolean>;
  isServiceRunning(): Promise<boolean>;
  requestIgnoreBatteryOptimizations(): Promise<boolean>;
}

let nativeModule: AlfredServiceModuleInterface | null = null;

if (Platform.OS === "android") {
  try {
    nativeModule = requireNativeModule("AlfredService");
  } catch {
    nativeModule = null;
  }
}

export const AlfredService: AlfredServiceModuleInterface = {
  async startService(
    title = "Alfred (VESPER Nexus)",
    content = "Alfred is vigilantly standing watch, sir."
  ): Promise<boolean> {
    if (nativeModule?.startService) {
      return await nativeModule.startService(title, content);
    }
    return false;
  },

  async stopService(): Promise<boolean> {
    if (nativeModule?.stopService) {
      return await nativeModule.stopService();
    }
    return false;
  },

  async isServiceRunning(): Promise<boolean> {
    if (nativeModule?.isServiceRunning) {
      return await nativeModule.isServiceRunning();
    }
    return false;
  },

  async requestIgnoreBatteryOptimizations(): Promise<boolean> {
    if (nativeModule?.requestIgnoreBatteryOptimizations) {
      return await nativeModule.requestIgnoreBatteryOptimizations();
    }
    return false;
  },
};

export default AlfredService;
