import { FilesetResolver, GestureRecognizer } from '@mediapipe/tasks-vision';

let recognizer: GestureRecognizer | null = null;
let isInitializing = false;
let lastGestureName = '';
let consecutiveCount = 0;
let lastDispatchedTime = 0;

// Map MediaPipe gesture category names to canonical VESPER gestures
function normalizeGestureName(categoryName: string): string {
  switch (categoryName) {
    case 'Closed_Fist':
      return 'CLOSED_FIST';
    case 'Open_Palm':
      return 'OPEN_PALM';
    case 'Pointing_Up':
      return 'POINTING_UP';
    case 'Thumb_Down':
      return 'VOLUME_DOWN';
    case 'Thumb_Up':
      return 'VOLUME_UP';
    case 'Victory':
      return 'PEACE_SIGN';
    case 'ILoveYou':
      return 'ROCK_ON';
    default:
      return categoryName.toUpperCase();
  }
}

const CDN_WASM_PATH = 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm';

async function resolveVisionFileset() {
  const origin = self.location && self.location.origin && self.location.origin !== 'null'
    ? self.location.origin
    : '';
  const localWasmPath = origin ? `${origin}/wasm` : '/wasm';

  // In ES module workers, useModule MUST be true so vision_wasm_module_internal.js
  // is imported and exports globalThis.ModuleFactory.
  try {
    return await FilesetResolver.forVisionTasks(localWasmPath, true);
  } catch (localErr) {
    console.warn('[WORKER] Local module WASM resolution failed, trying CDN:', localErr);
    try {
      return await FilesetResolver.forVisionTasks(CDN_WASM_PATH, true);
    } catch (cdnErr) {
      console.warn('[WORKER] CDN module WASM resolution failed, attempting fallback:', cdnErr);
      return await FilesetResolver.forVisionTasks(localWasmPath);
    }
  }
}

async function initRecognizer() {
  if (recognizer || isInitializing) return;
  isInitializing = true;

  const origin = self.location && self.location.origin && self.location.origin !== 'null'
    ? self.location.origin
    : '';
  const modelAssetPath = origin ? `${origin}/models/gesture_recognizer.task` : '/models/gesture_recognizer.task';

  try {
    const vision = await resolveVisionFileset();

    // WebKitGTK web workers do not support WebGL contexts (emscripten_webgl_create_context returns error 0).
    // Initialize directly with CPU delegate powered by WebAssembly Xnnpack SIMD.
    recognizer = await GestureRecognizer.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath,
        delegate: 'CPU',
      },
      runningMode: 'IMAGE',
      numHands: 1,
      minHandDetectionConfidence: 0.55,
      minHandPresenceConfidence: 0.55,
      minTrackingConfidence: 0.55,
    });

    self.postMessage({
      type: 'STATUS',
      ready: true,
      info: 'MediaPipe GestureRecognizer initialized with CPU Xnnpack acceleration',
    });
  } catch (err) {
    console.error('[WORKER] Failed to initialize GestureRecognizer:', err);
    self.postMessage({
      type: 'STATUS',
      ready: false,
      error: String(err),
    });
  } finally {
    isInitializing = false;
  }
}

self.onmessage = async (event: MessageEvent) => {
  const { type, frame } = event.data;

  if (type === 'INIT') {
    await initRecognizer();
    return;
  }

  if (type === 'PROCESS_FRAME') {
    if (!recognizer) {
      if (frame && typeof frame.close === 'function') {
        frame.close();
      }
      self.postMessage({
        type: 'FRAME_RESULT',
        activeGesture: 'NONE',
        confidence: 0,
        handedness: '',
        hasHand: false,
      });
      return;
    }

    try {
      const results = recognizer.recognize(frame);
      if (frame && typeof frame.close === 'function') {
        frame.close();
      }

      const gestures = results.gestures || [];
      const handednesses = results.handednesses || [];
      const landmarks = results.landmarks || [];

      if (gestures.length > 0 && gestures[0].length > 0) {
        const topGesture = gestures[0][0];
        const category = topGesture.categoryName;
        const score = topGesture.score;
        const handedness = handednesses[0]?.[0]?.categoryName || 'Unknown';

        const canonicalName = normalizeGestureName(category);
        const isZenGesture = canonicalName === 'PEACE_SIGN';
        const isToggleGesture = canonicalName === 'ROCK_ON';
        const requiredScore = isZenGesture ? 0.75 : (isToggleGesture ? 0.70 : 0.65);
        const requiredStreak = isZenGesture ? 5 : (isToggleGesture ? 6 : 3); // 3 frames = ~160ms hold
        const cooldownMs = isZenGesture ? 2500 : (canonicalName.startsWith('VOLUME_') ? 400 : 1000);

        if (category !== 'None' && score >= 0.45) {
          if (score >= requiredScore) {
            if (canonicalName === lastGestureName) {
              consecutiveCount++;
            } else {
              lastGestureName = canonicalName;
              consecutiveCount = 1;
            }

            const now = Date.now();
            if (consecutiveCount >= requiredStreak && now - lastDispatchedTime > cooldownMs) {
              lastDispatchedTime = now;
              self.postMessage({
                type: 'GESTURE_DETECTED',
                gesture: canonicalName,
                rawCategory: category,
                confidence: score,
                handedness,
                landmarks: landmarks[0] ? landmarks[0].length : 0,
              });
            }
          } else {
            lastGestureName = '';
            consecutiveCount = 0;
          }

          // Report perceived gesture to telemetry when confidence >= 0.45
          self.postMessage({
            type: 'FRAME_RESULT',
            activeGesture: canonicalName,
            confidence: score,
            handedness,
            hasHand: true,
          });
        } else {
          lastGestureName = '';
          consecutiveCount = 0;
          self.postMessage({
            type: 'FRAME_RESULT',
            activeGesture: 'NONE',
            confidence: 0,
            handedness: '',
            hasHand: true,
          });
        }
      } else {
        lastGestureName = '';
        consecutiveCount = 0;
        self.postMessage({
          type: 'FRAME_RESULT',
          activeGesture: 'NONE',
          confidence: 0,
          handedness: '',
          hasHand: false,
        });
      }
    } catch (err) {
      console.error('[WORKER] Error processing frame:', err);
      if (frame && typeof frame.close === 'function') {
        frame.close();
      }
      self.postMessage({
        type: 'FRAME_RESULT',
        activeGesture: 'NONE',
        confidence: 0,
        handedness: '',
        hasHand: false,
      });
    }
  }
};
