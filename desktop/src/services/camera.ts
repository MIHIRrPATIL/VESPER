import { FilesetResolver, GestureRecognizer } from '@mediapipe/tasks-vision';
import { gatewayService } from './gateway';

export interface GestureStatus {
  isWorkerReady: boolean;
  workerInfo?: string;
  workerError?: string;
  isCameraActive: boolean;
  activeGesture: string;
  lastConfirmedGesture: string;
  confidence: number;
  handedness: string;
  hasHand: boolean;
  isSafetyLocked: boolean;
}

export type GestureStatusListener = (status: GestureStatus) => void;

interface Landmark {
  x: number;
  y: number;
  z: number;
}

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

/** Geometric fallback classifier based on 3D landmark finger configurations */
function classifyLandmarkGeometry(landmarks: Landmark[]): { gesture: string; confidence: number } | null {
  if (!landmarks || landmarks.length < 21) return null;

  const wrist = landmarks[0];
  const indexMcp = landmarks[5];
  const indexPip = landmarks[6];
  const indexTip = landmarks[8];
  const middleMcp = landmarks[9];
  const middlePip = landmarks[10];
  const middleTip = landmarks[12];
  const ringMcp = landmarks[13];
  const ringPip = landmarks[14];
  const ringTip = landmarks[16];
  const pinkyMcp = landmarks[17];
  const pinkyPip = landmarks[18];
  const pinkyTip = landmarks[20];

  const isFolded = (tip: Landmark, pip: Landmark, _mcp: Landmark) => {
    const distTip = Math.hypot(tip.x - wrist.x, tip.y - wrist.y);
    const distPip = Math.hypot(pip.x - wrist.x, pip.y - wrist.y);
    return distTip < distPip * 1.15;
  };

  const isExtended = (tip: Landmark, pip: Landmark, _mcp: Landmark) => {
    const distTip = Math.hypot(tip.x - wrist.x, tip.y - wrist.y);
    const distPip = Math.hypot(pip.x - wrist.x, pip.y - wrist.y);
    return distTip > distPip * 1.25;
  };

  const indexExt = isExtended(indexTip, indexPip, indexMcp);
  const middleExt = isExtended(middleTip, middlePip, middleMcp);
  const ringExt = isExtended(ringTip, ringPip, ringMcp);
  const pinkyExt = isExtended(pinkyTip, pinkyPip, pinkyMcp);

  const indexFold = isFolded(indexTip, indexPip, indexMcp);
  const middleFold = isFolded(middleTip, middlePip, middleMcp);
  const ringFold = isFolded(ringTip, ringPip, ringMcp);
  const pinkyFold = isFolded(pinkyTip, pinkyPip, pinkyMcp);

  // Closed Fist: All 4 fingers folded into palm
  if (indexFold && middleFold && ringFold && pinkyFold) {
    return { gesture: 'CLOSED_FIST', confidence: 0.90 };
  }

  // Open Palm: All 4 fingers extended
  if (indexExt && middleExt && ringExt && pinkyExt) {
    return { gesture: 'OPEN_PALM', confidence: 0.92 };
  }

  // Pointing Up: Index extended, others folded
  if (indexExt && middleFold && ringFold && pinkyFold) {
    return { gesture: 'POINTING_UP', confidence: 0.88 };
  }

  // Peace Sign / Victory: Index & Middle extended, ring & pinky folded
  if (indexExt && middleExt && ringFold && pinkyFold) {
    return { gesture: 'PEACE_SIGN', confidence: 0.90 };
  }

  // Rock On: Index & Pinky extended, middle & ring folded
  if (indexExt && pinkyExt && middleFold && ringFold) {
    return { gesture: 'ROCK_ON', confidence: 0.88 };
  }

  // Finger Gun (Pistol): Index extended & straight, thumb extended, ring & pinky folded
  const thumbTip = landmarks[4];
  const thumbMcp = landmarks[2];
  const thumbExt = Math.hypot(thumbTip.x - wrist.x, thumbTip.y - wrist.y) > Math.hypot(thumbMcp.x - wrist.x, thumbMcp.y - wrist.y) * 1.05;

  if (indexExt && ringFold && pinkyFold && thumbExt && (middleFold || middleExt)) {
    // Check horizontal orientation of index barrel (from MCP to TIP)
    // In mirrored coordinates (matching user perspective): dx = indexMcp.x - indexTip.x
    const dxMirrored = indexMcp.x - indexTip.x;
    const dy = indexTip.y - indexMcp.y;

    if (Math.abs(dxMirrored) >= 0.08 && Math.abs(dxMirrored) > 1.20 * Math.abs(dy)) {
      if (dxMirrored > 0) {
        return { gesture: 'GUN_RIGHT', confidence: 0.90 };
      } else {
        return { gesture: 'GUN_LEFT', confidence: 0.90 };
      }
    }
  }

  return null;
}

class CameraGestureManager {
  private videoElement: HTMLVideoElement | null = null;
  private imageElement: HTMLImageElement | null = null;
  private displayCanvas: HTMLCanvasElement | null = null;
  private isBackendActive: boolean = true;
  private stream: MediaStream | null = null;
  private recognizer: GestureRecognizer | null = null;
  private visionCanvas: HTMLCanvasElement | null = null;
  private isVisionInitializing: boolean = false;
  private animationFrameId: number | null = null;
  private isProcessing: boolean = false;
  private lastProcessingStartTime: number = 0;
  private startPromise: Promise<boolean> | null = null;
  private isSafetyLocked: boolean = false;
  private lastFrameTime: number = 0;
  private targetFps: number = 24; // 24 FPS smooth perception and preview loop

  private lastGestureName: string = '';
  private consecutiveCount: number = 0;
  private lastDispatchedTime: number = 0;

  private status: GestureStatus = {
    isWorkerReady: false,
    isCameraActive: false,
    activeGesture: 'NONE',
    lastConfirmedGesture: 'NONE',
    confidence: 0,
    handedness: '',
    hasHand: false,
    isSafetyLocked: false,
  };

  private listeners: Set<GestureStatusListener> = new Set();

  constructor() {
    this.initVision();
  }

  private async initVision(): Promise<void> {
    if (this.recognizer || this.isVisionInitializing) return;
    this.isVisionInitializing = true;

    try {
      const origin = typeof window !== 'undefined' && window.location ? window.location.origin : '';
      const localWasmPath = origin ? `${origin}/wasm` : '/wasm';
      const modelAssetPath = origin ? `${origin}/models/gesture_recognizer.task` : '/models/gesture_recognizer.task';

      let vision: any;
      try {
        vision = await FilesetResolver.forVisionTasks(localWasmPath);
      } catch (localErr) {
        console.warn('[GESTURE_MANAGER] Local WASM failed, falling back to CDN:', localErr);
        vision = await FilesetResolver.forVisionTasks('https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm');
      }

      // WebKitGTK loads wasm loader via document.createElement('script') without type='module'.
      // If wasmLoaderPath contains '_module_', classic script execution throws SyntaxError on import.meta.
      // Normalize to non-module vision_wasm_internal.js to guarantee clean initialization.
      if (vision?.wasmLoaderPath && vision.wasmLoaderPath.includes('_module_')) {
        vision.wasmLoaderPath = vision.wasmLoaderPath.replace('_module_', '_');
      }
      if (vision?.wasmBinaryPath && vision.wasmBinaryPath.includes('_module_')) {
        vision.wasmBinaryPath = vision.wasmBinaryPath.replace('_module_', '_');
      }

      this.visionCanvas = document.createElement('canvas');
      this.visionCanvas.width = 320;
      this.visionCanvas.height = 240;

      try {
        this.recognizer = await GestureRecognizer.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath,
            delegate: 'GPU',
          },
          canvas: this.visionCanvas,
          runningMode: 'IMAGE',
          numHands: 1,
          minHandDetectionConfidence: 0.50,
          minHandPresenceConfidence: 0.50,
          minTrackingConfidence: 0.50,
        });
        console.log('[GESTURE_MANAGER] GestureRecognizer initialized with WebGL GPU acceleration');
      } catch (gpuErr) {
        console.warn('[GESTURE_MANAGER] WebGL GPU delegate init failed, falling back to CPU delegate:', gpuErr);
        this.recognizer = await GestureRecognizer.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath,
            delegate: 'CPU',
          },
          canvas: this.visionCanvas,
          runningMode: 'IMAGE',
          numHands: 1,
          minHandDetectionConfidence: 0.50,
          minHandPresenceConfidence: 0.50,
          minTrackingConfidence: 0.50,
        });
        console.log('[GESTURE_MANAGER] GestureRecognizer initialized with CPU SIMD delegate');
      }

      this.updateStatus({
        isWorkerReady: true,
        workerInfo: 'MediaPipe GestureRecognizer Ready',
        workerError: undefined,
      });
    } catch (err) {
      console.error('[GESTURE_MANAGER] Failed to initialize MediaPipe GestureRecognizer:', err);
      this.updateStatus({
        isWorkerReady: false,
        workerError: `Gesture engine failed to initialize: ${err}`,
      });
    } finally {
      this.isVisionInitializing = false;
    }
  }

  private handleGestureResults(results: any): void {
    const gestures = results.gestures || [];
    const handednesses = results.handednesses || [];
    const rawLandmarks = results.landmarks || [];
    const hasHand = rawLandmarks.length > 0 && rawLandmarks[0].length > 0;
    const handedness = handednesses[0]?.[0]?.categoryName || (hasHand ? 'Hand' : '');

    let detectedGesture = 'NONE';
    let detectedScore = 0;

    // 1. Check MediaPipe built-in classifier category
    if (gestures.length > 0 && gestures[0].length > 0) {
      const topGesture = gestures[0][0];
      const category = topGesture.categoryName;
      const score = topGesture.score;
      if (category !== 'None' && score >= 0.50) {
        detectedGesture = normalizeGestureName(category);
        detectedScore = score;
      }
    }

    // 2. Geometric landmark fallback if built-in model outputs None or low confidence
    if (detectedGesture === 'NONE' && hasHand) {
      const geomResult = classifyLandmarkGeometry(rawLandmarks[0]);
      if (geomResult) {
        detectedGesture = geomResult.gesture;
        detectedScore = geomResult.confidence;
      }
    }

    if (detectedGesture !== 'NONE' && detectedScore >= 0.50) {
      const isZenGesture = detectedGesture === 'PEACE_SIGN';
      const isToggleGesture = detectedGesture === 'ROCK_ON';
      const requiredStreak = isZenGesture ? 3 : (isToggleGesture ? 4 : 2);
      const cooldownMs = isZenGesture ? 2000 : (detectedGesture.startsWith('VOLUME_') ? 350 : (detectedGesture.startsWith('GUN_') ? 1600 : 800));

      if (detectedGesture === this.lastGestureName) {
        this.consecutiveCount++;
      } else {
        this.lastGestureName = detectedGesture;
        this.consecutiveCount = 1;
      }

      const now = Date.now();
      if (this.consecutiveCount >= requiredStreak && now - this.lastDispatchedTime > cooldownMs) {
        this.lastDispatchedTime = now;
        if (this.isSafetyLocked) {
          console.log('[GESTURE_MANAGER] Gesture ignored (Safety Locked):', detectedGesture);
        } else {
          console.log('[GESTURE_MANAGER] Confirmed gesture:', detectedGesture, detectedScore);
          this.updateStatus({ lastConfirmedGesture: detectedGesture });
          gatewayService.sendGesture(detectedGesture, detectedScore, handedness);
        }
      }

      this.updateStatus({
        activeGesture: detectedGesture,
        confidence: detectedScore,
        handedness,
        hasHand: true,
      });
      return;
    }

    this.lastGestureName = '';
    this.consecutiveCount = 0;
    this.updateStatus({
      activeGesture: 'NONE',
      confidence: 0,
      handedness: hasHand ? handedness : '',
      hasHand,
    });
  }

  public attachDisplayCanvas(canvas: HTMLCanvasElement | null): void {
    console.log('[GESTURE_MANAGER] attachDisplayCanvas called. Has canvas:', !!canvas);
    this.displayCanvas = canvas;
    if (canvas && this.isBackendActive) {
      this.startProcessingLoop();
    }
  }

  public setBackendMode(active: boolean): void {
    this.isBackendActive = active;
    if (active) {
      this.updateStatus({ isCameraActive: true, workerError: undefined });
      this.startProcessingLoop();
    } else if (!this.stream) {
      this.updateStatus({ isCameraActive: false, activeGesture: 'NONE', hasHand: false });
    }
  }

  public attachImageElement(imgRef: HTMLImageElement | null): void {
    console.log('[GESTURE_MANAGER] attachImageElement called. Has element:', !!imgRef);
    this.imageElement = imgRef;
    this.setBackendMode(!!imgRef);
  }

  public getImageElement(): HTMLImageElement | null {
    return this.imageElement;
  }

  public attachVideoElement(videoRef: HTMLVideoElement): void {
    console.log('[GESTURE_MANAGER] attachVideoElement called. Has active stream:', !!this.stream);
    this.videoElement = videoRef;
    if (this.stream && this.stream.active && this.stream.getVideoTracks().some((t) => t.readyState === 'live')) {
      videoRef.autoplay = true;
      videoRef.playsInline = true;
      videoRef.defaultMuted = true;
      videoRef.muted = true;
      if (videoRef.srcObject !== this.stream) {
        videoRef.srcObject = this.stream;
        console.log('[GESTURE_MANAGER] Assigned active stream to video element');
      }
      videoRef.play()
        .then(() => {
          console.log('[GESTURE_MANAGER] Video playback started:', videoRef.videoWidth, 'x', videoRef.videoHeight);
        })
        .catch((err) => {
          if (err?.name !== 'AbortError') {
            console.warn('[GESTURE_MANAGER] Play warning on attach:', err);
          }
        });
    }
  }

  public async startCamera(videoRef?: HTMLVideoElement): Promise<boolean> {
    if (this.startPromise) {
      return this.startPromise;
    }

    this.startPromise = (async () => {
      if (videoRef) {
        this.videoElement = videoRef;
      }

      if (this.stream && this.stream.active) {
        if (this.videoElement && this.videoElement.srcObject !== this.stream) {
          this.attachVideoElement(this.videoElement);
        }
        this.updateStatus({ isCameraActive: true, workerError: undefined });
        this.startProcessingLoop();
        return true;
      }

      if (!navigator?.mediaDevices?.getUserMedia) {
        console.error('[GESTURE_MANAGER] getUserMedia API not supported');
        this.updateStatus({
          isCameraActive: false,
          workerError: 'Webcam API not supported in this environment',
        });
        return false;
      }

      const fetchWithTimeout = (constraints: MediaStreamConstraints, ms = 7000): Promise<MediaStream> => {
        return Promise.race([
          navigator.mediaDevices.getUserMedia(constraints),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error(`Camera request timed out after ${ms}ms`)), ms)
          ),
        ]);
      };

      let stream: MediaStream | null = null;
      try {
        stream = await fetchWithTimeout({
          video: true,
          audio: false,
        }, 5000);
      } catch (e1) {
        console.warn('[GESTURE_MANAGER] Generic video:true failed or timed out:', e1, 'Attempting ideal 640x480...');
        try {
          stream = await fetchWithTimeout({
            video: { width: 640, height: 480 },
            audio: false,
          }, 6000);
          console.log('[GESTURE_MANAGER] 640x480 constraints succeeded.');
        } catch (fallbackErr) {
          console.error('[GESTURE_MANAGER] All getUserMedia attempts failed:', fallbackErr);
          this.updateStatus({
            isCameraActive: false,
            workerError: `Camera access failed: ${fallbackErr}`,
          });
          return false;
        }
      }

      if (!stream) {
        this.updateStatus({
          isCameraActive: false,
          workerError: 'Unable to obtain video stream from device',
        });
        return false;
      }

      console.log('[GESTURE_MANAGER] Stream acquired successfully. Video tracks:', stream.getVideoTracks().map((t) => t.label));
      this.stream = stream;

      const tracks = stream.getVideoTracks();
      if (tracks.length > 0) {
        tracks[0].onended = () => {
          console.warn('[GESTURE_MANAGER] Camera hardware track ended');
          this.stopCamera();
        };
      }

      if (this.videoElement) {
        this.attachVideoElement(this.videoElement);
      }

      this.updateStatus({ isCameraActive: true, workerError: undefined });
      this.startProcessingLoop();
      return true;
    })();

    try {
      return await this.startPromise;
    } finally {
      this.startPromise = null;
    }
  }

  public stopCamera(): void {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    if (this.stream) {
      try {
        this.stream.getTracks().forEach((track) => track.stop());
      } catch (e) {
        // Ignored
      }
      this.stream = null;
    }

    if (this.videoElement) {
      try {
        this.videoElement.pause();
      } catch (e) {
        // Ignored
      }
      this.videoElement.srcObject = null;
      this.videoElement = null;
    }

    this.imageElement = null;
    this.isBackendActive = false;
    this.isProcessing = false;
    if (this.displayCanvas) {
      const ctx = this.displayCanvas.getContext('2d');
      if (ctx) {
        ctx.fillStyle = '#020408';
        ctx.fillRect(0, 0, this.displayCanvas.width, this.displayCanvas.height);
      }
    }
    this.updateStatus({
      isCameraActive: false,
      activeGesture: 'NONE',
      hasHand: false,
    });
  }

  public toggleSafetyLock(): boolean {
    this.isSafetyLocked = !this.isSafetyLocked;
    this.updateStatus({ isSafetyLocked: this.isSafetyLocked });
    return this.isSafetyLocked;
  }

  public subscribe(listener: GestureStatusListener): () => void {
    this.listeners.add(listener);
    listener({ ...this.status });
    return () => {
      this.listeners.delete(listener);
    };
  }

  private renderLandmarks(ctx: CanvasRenderingContext2D, landmarks: any[], width: number, height: number): void {
    const connections = [
      [0, 1], [1, 2], [2, 3], [3, 4], // Thumb
      [0, 5], [5, 6], [6, 7], [7, 8], // Index
      [9, 10], [10, 11], [11, 12], [5, 9], // Middle
      [13, 14], [14, 15], [15, 16], [9, 13], // Ring
      [0, 17], [17, 18], [18, 19], [19, 20], [13, 17], // Pinky
    ];

    ctx.save();
    ctx.strokeStyle = 'rgba(0, 242, 254, 0.75)';
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    for (const [i, j] of connections) {
      const p1 = landmarks[i];
      const p2 = landmarks[j];
      if (p1 && p2) {
        ctx.beginPath();
        ctx.moveTo(p1.x * width, p1.y * height);
        ctx.lineTo(p2.x * width, p2.y * height);
        ctx.stroke();
      }
    }

    for (let i = 0; i < landmarks.length; i++) {
      const p = landmarks[i];
      if (!p) continue;
      const isTip = i === 4 || i === 8 || i === 12 || i === 16 || i === 20;
      ctx.beginPath();
      ctx.arc(p.x * width, p.y * height, isTip ? 4 : 2.5, 0, 2 * Math.PI);
      ctx.fillStyle = isTip ? '#4ade80' : '#38bdf8';
      ctx.fill();
    }
    ctx.restore();
  }

  private startProcessingLoop(): void {
    const minInterval = 1000 / this.targetFps;

    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }

    const processFrame = async () => {
      if (!this.isBackendActive && (!this.stream || !this.videoElement)) {
        this.animationFrameId = null;
        return;
      }

      if (!this.recognizer || !this.status.isWorkerReady) {
        this.animationFrameId = requestAnimationFrame(processFrame);
        return;
      }

      const now = performance.now();
      if (this.isProcessing && now - this.lastProcessingStartTime > 600) {
        this.isProcessing = false;
      }

      if (now - this.lastFrameTime >= minInterval && !this.isProcessing) {
        this.lastFrameTime = now;

        // 1. Process from Backend Optical Stream Snapshot
        if (this.isBackendActive) {
          try {
            this.isProcessing = true;
            this.lastProcessingStartTime = performance.now();
            const res = await fetch('http://127.0.0.1:8000/api/camera/snapshot');
            if (res.ok) {
              const blob = await res.blob();
              const bitmap = await createImageBitmap(blob);
              const results = this.recognizer.recognize(bitmap);

              // Render live camera feed and landmark overlay to display canvas
              if (this.displayCanvas) {
                const ctx = this.displayCanvas.getContext('2d');
                if (ctx) {
                  ctx.drawImage(bitmap, 0, 0, this.displayCanvas.width, this.displayCanvas.height);
                  if (results.landmarks && results.landmarks[0]) {
                    this.renderLandmarks(ctx, results.landmarks[0], this.displayCanvas.width, this.displayCanvas.height);
                  }
                }
              }

              bitmap.close();
              this.handleGestureResults(results);
            }
          } catch (err) {
            console.warn('[GESTURE_MANAGER] Frame processing error from snapshot:', err);
          } finally {
            this.isProcessing = false;
          }
        }
        // 2. Process from Browser WebRTC Stream (Video Element)
        else if (
          this.videoElement &&
          this.videoElement.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
          this.videoElement.videoWidth > 0 &&
          this.videoElement.videoHeight > 0
        ) {
          try {
            this.isProcessing = true;
            this.lastProcessingStartTime = performance.now();
            const results = this.recognizer.recognize(this.videoElement);

            if (this.displayCanvas) {
              const ctx = this.displayCanvas.getContext('2d');
              if (ctx) {
                ctx.drawImage(this.videoElement, 0, 0, this.displayCanvas.width, this.displayCanvas.height);
                if (results.landmarks && results.landmarks[0]) {
                  this.renderLandmarks(ctx, results.landmarks[0], this.displayCanvas.width, this.displayCanvas.height);
                }
              }
            }

            this.handleGestureResults(results);
          } catch (err) {
            console.warn('[GESTURE_MANAGER] Frame processing error from video:', err);
          } finally {
            this.isProcessing = false;
          }
        }
      }

      this.animationFrameId = requestAnimationFrame(processFrame);
    };

    this.animationFrameId = requestAnimationFrame(processFrame);
  }

  private updateStatus(patch: Partial<GestureStatus>): void {
    let hasChanges = false;
    for (const key of Object.keys(patch) as (keyof GestureStatus)[]) {
      if (this.status[key] !== patch[key]) {
        hasChanges = true;
        break;
      }
    }
    if (!hasChanges) {
      return;
    }

    this.status = { ...this.status, ...patch };
    for (const listener of this.listeners) {
      listener({ ...this.status });
    }
  }
}

export const cameraGestureManager = new CameraGestureManager();
