import React from 'react';
import { Volume2, VolumeX, Shield, ShieldAlert, Square, Activity } from 'lucide-react';
import { gatewayService } from '../services/gateway';

interface HUDHeaderProps {
  isConnected: boolean;
  isConnecting: boolean;
  volume: number;
  zenMode: boolean;
  safetyLocked: boolean;
  onToggleSafetyLock: () => void;
}

export const HUDHeader: React.FC<HUDHeaderProps> = ({
  isConnected,
  isConnecting,
  volume,
  zenMode,
  safetyLocked,
  onToggleSafetyLock,
}) => {
  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    gatewayService.sendSetVolume(val);
  };

  const handleToggleMute = () => {
    gatewayService.sendSetVolume(volume > 0 ? 0 : 50);
  };

  const handleToggleZen = () => {
    gatewayService.sendZenModeToggle();
  };

  const handleInterrupt = () => {
    gatewayService.sendInterrupt('USER_BARGE_IN');
  };

  return (
    <header className="hud-header">
      <div className="hud-brand">
        <div className="brand-logo">VESPER</div>
        <div className="brand-sub">DESK COMPANION HUD</div>
      </div>

      <div className="hud-controls">
        {/* Connection Status Badge */}
        <div className={`status-badge ${isConnected ? 'connected' : isConnecting ? 'connecting' : 'disconnected'}`}>
          <Activity size={14} className="badge-icon" />
          <span>{isConnected ? 'CLUSTER ONLINE' : isConnecting ? 'CONNECTING...' : 'OFFLINE'}</span>
        </div>

        {/* Volume Slider & Mute */}
        <div className="control-group volume-control">
          <button
            type="button"
            className="icon-btn"
            onClick={handleToggleMute}
            title={volume === 0 ? 'Unmute' : 'Mute'}
          >
            {volume === 0 ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
          <input
            type="range"
            min="0"
            max="100"
            value={volume}
            onChange={handleVolumeChange}
            className="volume-slider"
            title={`Master Volume: ${volume}%`}
          />
          <span className="volume-text">{volume}%</span>
        </div>

        {/* Zen Mode Toggle */}
        <button
          type="button"
          className={`toggle-btn ${zenMode ? 'active' : ''}`}
          onClick={handleToggleZen}
          title="Toggle Zen Mode"
        >
          ZEN MODE {zenMode ? 'ON' : 'OFF'}
        </button>

        {/* Gesture Safety Lock */}
        <button
          type="button"
          className={`toggle-btn ${safetyLocked ? 'locked' : ''}`}
          onClick={onToggleSafetyLock}
          title={safetyLocked ? 'Gesture shortcuts locked' : 'Gesture shortcuts armed'}
        >
          {safetyLocked ? <ShieldAlert size={14} /> : <Shield size={14} />}
          <span>{safetyLocked ? 'GESTURES LOCKED' : 'GESTURES ARMED'}</span>
        </button>

        {/* Emergency Stop / Barge-In */}
        <button
          type="button"
          className="danger-btn"
          onClick={handleInterrupt}
          title="Interrupt current agent speech and tasks"
        >
          <Square size={14} />
          <span>BARGE-IN</span>
        </button>
      </div>
    </header>
  );
};
