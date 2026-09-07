import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Camera, CameraOff, Eye, EyeOff, Hand, CheckCircle2 } from 'lucide-react';
import { cameraGestureManager, GestureStatus } from '../services/camera';
import { gatewayService } from '../services/gateway';

interface CameraDrawerProps {
  status: GestureStatus;
  onToggleSafetyLock: () => void;
}

export const CameraDrawer: React.FC<CameraDrawerProps> = ({ status, onToggleSafetyLock }) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [showPreview, setShowPreview] = useState(true);
  const [streamMode, setStreamMode] = useState<'backend' | 'browser'>('backend');
  const [isBackendStreaming, setIsBackendStreaming] = useState<boolean>(true);
  const [isWakeWordArmed, setIsWakeWordArmed] = useState<boolean>(true);
  const hasAutoStarted = useRef(false);

  // Synchronize Wake Word Armed/Muted state from Gateway
  useEffect(() => {
    const unsub = gatewayService.subscribe((env) => {
      if (env.type === 'WAKE_WORD_STATE' && env.payload) {
        if (typeof env.payload.wakeword_active === 'boolean') {
          setIsWakeWordArmed(env.payload.wakeword_active);
        }
      } else if (env.type === 'SET_VOLUME' && env.payload) {
        if (typeof env.payload.wakeword_active === 'boolean') {
          setIsWakeWordArmed(env.payload.wakeword_active);
        }
      }
    });
    return unsub;
  }, []);

  const handleToggleWakeWord = () => {
    const next = !isWakeWordArmed;
    setIsWakeWordArmed(next);
    gatewayService.sendWakeWordToggle(next);
  };

  // Stable ref callback for display canvas element (renders optical stream + landmarks)
  const setCanvasRef = useCallback((element: HTMLCanvasElement | null) => {
    canvasRef.current = element;
    if (element) {
      console.log('[CAMERA_DRAWER] Canvas element mounted, attaching to manager');
      cameraGestureManager.attachDisplayCanvas(element);
    }
  }, []);

  // Stable ref callback for browser WebRTC video element
  const setVideoRef = useCallback((element: HTMLVideoElement | null) => {
    videoRef.current = element;
    if (element) {
      console.log('[CAMERA_DRAWER] Video element mounted, attaching to manager');
      cameraGestureManager.attachVideoElement(element);
    }
  }, []);

  // Ensure active mode is synchronized with gesture manager
  useEffect(() => {
    if (streamMode === 'backend') {
      cameraGestureManager.setBackendMode(isBackendStreaming);
    } else if (streamMode === 'browser') {
      cameraGestureManager.setBackendMode(false);
      if (videoRef.current && !hasAutoStarted.current) {
        hasAutoStarted.current = true;
        console.log('[CAMERA_DRAWER] Starting browser WebRTC camera');
        cameraGestureManager.startCamera(videoRef.current);
      }
    }
  }, [streamMode, isBackendStreaming]);

  const handleToggleCamera = () => {
    if (streamMode === 'backend') {
      setIsBackendStreaming((prev) => {
        const next = !prev;
        cameraGestureManager.setBackendMode(next);
        return next;
      });
    } else {
      if (status.isCameraActive) {
        cameraGestureManager.stopCamera();
      } else if (videoRef.current) {
        cameraGestureManager.startCamera(videoRef.current);
      }
    }
  };

  const isCamActive = streamMode === 'backend' ? isBackendStreaming : status.isCameraActive;

  return (
    <div className="camera-drawer">
      <div className="camera-header">
        <div className="camera-title">
          <Hand size={16} />
          <span>CLIENT-SIDE GESTURE PERCEPTION</span>
        </div>

        <div className="camera-actions">
          {/* Mode Switcher: OpenCV Native Stream vs Browser WebRTC */}
          <button
            type="button"
            className="secondary-btn"
            style={{ fontSize: '10px', padding: '3px 7px' }}
            onClick={() => {
              const next = streamMode === 'backend' ? 'browser' : 'backend';
              setStreamMode(next);
              if (next === 'browser') {
                cameraGestureManager.setBackendMode(false);
                if (videoRef.current) {
                  cameraGestureManager.startCamera(videoRef.current);
                }
              } else {
                cameraGestureManager.stopCamera();
                setIsBackendStreaming(true);
                cameraGestureManager.setBackendMode(true);
              }
            }}
            title={streamMode === 'backend' ? 'Using backend optical stream. Click for browser WebRTC.' : 'Using browser WebRTC. Click for backend optical stream.'}
          >
            <span>{streamMode === 'backend' ? 'OPENCV STREAM' : 'WEBRTC CAM'}</span>
          </button>

          <button
            type="button"
            className="icon-btn"
            onClick={() => setShowPreview(!showPreview)}
            title={showPreview ? 'Hide camera preview' : 'Show camera preview'}
          >
            {showPreview ? <Eye size={15} /> : <EyeOff size={15} />}
          </button>

          <button
            type="button"
            className={`secondary-btn ${isCamActive ? 'active' : ''}`}
            onClick={handleToggleCamera}
            title={isCamActive ? 'Stop Camera' : 'Start Camera'}
          >
            {isCamActive ? <CameraOff size={14} /> : <Camera size={14} />}
            <span>{isCamActive ? 'DISABLE CAM' : 'ENABLE CAM'}</span>
          </button>
        </div>
      </div>

      <div className="camera-body">
        {/* Real-time Hardware Video / Landmark Canvas Preview */}
        <div className={`video-wrapper ${showPreview ? 'visible' : 'hidden'}`}>
          {/* Hidden video element used as media stream frame source in WebRTC mode */}
          <video
            ref={setVideoRef}
            style={{ display: 'none' }}
            autoPlay
            playsInline
            muted
          />

          {/* Unified High-Performance Canvas Display (Supports WebKitGTK without MJPEG codec limitations) */}
          <canvas
            ref={setCanvasRef}
            className="camera-video"
            width={320}
            height={240}
          />

          {!isCamActive && (
            <div className="video-placeholder">
              <span className="placeholder-main">Camera Offline</span>
              <span className="placeholder-sub">Click ENABLE CAM or switch to WEBRTC.</span>
            </div>
          )}

          {status.hasHand && (
            <div className="hand-badge">
              <span>{status.handedness || 'Hand'} Tracked</span>
            </div>
          )}

          {status.activeGesture !== 'NONE' && (
            <div className="gesture-overlay-banner">
              <span className="gesture-glow-text">{status.activeGesture}</span>
            </div>
          )}
        </div>

        {/* Gesture Status and Feedback */}
        <div className="gesture-telemetry">
          <div className="telemetry-row">
            <span className="label">Vision Worker:</span>
            <span className={`val ${status.isWorkerReady ? 'ready' : 'loading'}`}>
              {status.isWorkerReady ? 'READY (MediaPipe GPU/CPU)' : 'INITIALIZING...'}
            </span>
          </div>

          <div className="telemetry-row">
            <span className="label">Live Perception:</span>
            <span className="val highlight">
              {status.activeGesture} {status.confidence > 0 ? `(${(status.confidence * 100).toFixed(0)}%)` : ''}
            </span>
          </div>

          <div className="telemetry-row">
            <span className="label">Last Confirmed:</span>
            <span className="val confirmed">
              <CheckCircle2 size={13} className="val-icon" />
              <span>{status.lastConfirmedGesture}</span>
            </span>
          </div>

          <div className="telemetry-row">
            <span className="label">Wake Word:</span>
            <button
              type="button"
              className={`pill-btn ${isWakeWordArmed ? 'armed' : 'locked'}`}
              onClick={handleToggleWakeWord}
              title={isWakeWordArmed ? 'Continuous wake word listener armed. Click to mute/pause.' : 'Wake word listener muted. Click to arm.'}
            >
              {isWakeWordArmed ? 'ARMED' : 'MUTED'}
            </button>
          </div>

          <div className="telemetry-row">
            <span className="label">Safety Lock:</span>
            <button
              type="button"
              className={`pill-btn ${status.isSafetyLocked ? 'locked' : 'armed'}`}
              onClick={onToggleSafetyLock}
            >
              {status.isSafetyLocked ? 'LOCKED' : 'ARMED'}
            </button>
          </div>

          <div className="gesture-shortcuts">
            <div className="shortcuts-title">MAPPED TOUCHLESS SHORTCUTS</div>
            <div className="shortcut-item">
              <span className="shortcut-name">CLOSED_FIST</span>
              <span className="shortcut-desc">Mute / Stop Wake Word</span>
            </div>
            <div className="shortcut-item">
              <span className="shortcut-name">OPEN_PALM</span>
              <span className="shortcut-desc">Unmute / Resume Wake Word</span>
            </div>
            <div className="shortcut-item">
              <span className="shortcut-name">POINTING_UP</span>
              <span className="shortcut-desc">Toggle Wake Word (Arm/Mute)</span>
            </div>
            <div className="shortcut-item">
              <span className="shortcut-name">VOLUME_UP</span>
              <span className="shortcut-desc">Volume +10%</span>
            </div>
            <div className="shortcut-item">
              <span className="shortcut-name">VOLUME_DOWN</span>
              <span className="shortcut-desc">Volume -10%</span>
            </div>
            <div className="shortcut-item">
              <span className="shortcut-name">GUN_RIGHT</span>
              <span className="shortcut-desc">Next Track (Finger Gun Right)</span>
            </div>
            <div className="shortcut-item">
              <span className="shortcut-name">GUN_LEFT</span>
              <span className="shortcut-desc">Prev Track (Finger Gun Left)</span>
            </div>
            <div className="shortcut-item">
              <span className="shortcut-name">PEACE_SIGN</span>
              <span className="shortcut-desc">Toggle Zen Mode</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
