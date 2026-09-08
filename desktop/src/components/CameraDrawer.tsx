import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Camera, CameraOff, Hand, CheckCircle2, X } from 'lucide-react';
import { cameraGestureManager, GestureStatus } from '../services/camera';
import { gatewayService } from '../services/gateway';

interface CameraDrawerProps {
  status: GestureStatus;
  isOpen: boolean;
  onClose: () => void;
  onToggleSafetyLock: () => void;
}

export const CameraDrawer: React.FC<CameraDrawerProps> = ({
  status,
  isOpen,
  onClose,
  onToggleSafetyLock,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
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
      cameraGestureManager.attachDisplayCanvas(element);
    }
  }, []);

  // Stable ref callback for browser WebRTC video element
  const setVideoRef = useCallback((element: HTMLVideoElement | null) => {
    videoRef.current = element;
    if (element) {
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
        cameraGestureManager.startCamera(videoRef.current);
      }
    }
  }, [streamMode, isBackendStreaming]);

  const handleToggleCam = async () => {
    if (streamMode === 'backend') {
      const nextState = !isBackendStreaming;
      setIsBackendStreaming(nextState);
      cameraGestureManager.setBackendMode(nextState);
    } else {
      if (status.isCameraActive) {
        cameraGestureManager.stopCamera();
      } else if (videoRef.current) {
        await cameraGestureManager.startCamera(videoRef.current);
      }
    }
  };

  const isCamActive = streamMode === 'backend' ? isBackendStreaming : status.isCameraActive;

  return (
    <>
      {/* Hidden WebRTC Video Anchor (Kept permanently in DOM for continuous vision processing) */}
      <video
        ref={setVideoRef}
        style={{ display: 'none' }}
        autoPlay
        playsInline
        muted
      />

      {/* Floating Glass Vision HUD Drawer */}
      <div className={`camera-floating-drawer ${isOpen ? 'open' : 'closed'}`}>
        <div className="drawer-header">
          <div className="drawer-title-group">
            <Hand size={15} className="title-icon" />
            <span className="drawer-title">OPTICAL GESTURE PERCEPTION</span>
          </div>
          <button type="button" className="drawer-close-btn" onClick={onClose} title="Close Drawer">
            <X size={15} />
          </button>
        </div>

        <div className="drawer-body">
          {/* Stream Mode & Controls */}
          <div className="stream-mode-pills">
            <button
              type="button"
              className={`mode-pill ${streamMode === 'backend' ? 'active' : ''}`}
              onClick={() => setStreamMode('backend')}
            >
              BACKEND SINK
            </button>
            <button
              type="button"
              className={`mode-pill ${streamMode === 'browser' ? 'active' : ''}`}
              onClick={() => setStreamMode('browser')}
            >
              LOCAL WEBRTC
            </button>
            <button
              type="button"
              className={`mode-pill ${isCamActive ? 'active' : 'inactive'}`}
              onClick={handleToggleCam}
            >
              {isCamActive ? <Camera size={13} /> : <CameraOff size={13} />}
              <span>{isCamActive ? 'ACTIVE' : 'MUTED'}</span>
            </button>
          </div>

          {/* Canvas Viewport */}
          <div className="canvas-frame">
            <canvas
              ref={setCanvasRef}
              className="gesture-display-canvas"
              width={300}
              height={225}
            />
            {!isCamActive && (
              <div className="canvas-offline-scrim">
                <span>Camera Stream Standby</span>
              </div>
            )}
            {status.hasHand && (
              <div className="hand-tracking-pill">
                <span>{status.handedness || 'Hand'} Detected</span>
              </div>
            )}
            {status.activeGesture !== 'NONE' && (
              <div className="active-gesture-overlay">
                <span>{status.activeGesture}</span>
              </div>
            )}
          </div>

          {/* Perception Telemetry */}
          <div className="telemetry-grid">
            <div className="telemetry-item">
              <span className="telemetry-label">Active:</span>
              <span className="telemetry-value highlight">
                {status.activeGesture} {status.confidence > 0 ? `(${(status.confidence * 100).toFixed(0)}%)` : ''}
              </span>
            </div>
            <div className="telemetry-item">
              <span className="telemetry-label">Last Confirmed:</span>
              <span className="telemetry-value confirmed">
                <CheckCircle2 size={12} />
                <span>{status.lastConfirmedGesture}</span>
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
            <button
              type="button"
              className={`mode-pill ${status.isSafetyLocked ? 'active' : ''}`}
              onClick={onToggleSafetyLock}
              style={{ flex: 1 }}
            >
              LOCK: {status.isSafetyLocked ? 'ENGAGED' : 'ARMED'}
            </button>
            <button
              type="button"
              className={`mode-pill ${isWakeWordArmed ? 'active' : ''}`}
              onClick={handleToggleWakeWord}
              style={{ flex: 1 }}
            >
              WAKE: {isWakeWordArmed ? 'ARMED' : 'MUTED'}
            </button>
          </div>

          {/* Quick Shortcuts */}
          <div className="touchless-shortcuts-sheet">
            <div className="sheet-title">TOUCHLESS GESTURE MAPPINGS</div>
            <div className="sheet-row">
              <span className="cmd">VOLUME_UP / DOWN</span>
              <span className="desc">Thumb Up / Down</span>
            </div>
            <div className="sheet-row">
              <span className="cmd">OPEN_PALM</span>
              <span className="desc">Pause Media / Resume Wake</span>
            </div>
            <div className="sheet-row">
              <span className="cmd">CLOSED_FIST</span>
              <span className="desc">Stop / Mute Wake Word</span>
            </div>
            <div className="sheet-row">
              <span className="cmd">PEACE_SIGN</span>
              <span className="desc">Toggle Zen Mode</span>
            </div>
            <div className="sheet-row">
              <span className="cmd">THREE_FINGERS</span>
              <span className="desc">Media Play / Pause</span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};
