import React, { useState, useRef } from 'react';
import { Send, Terminal } from 'lucide-react';
import BorderGlow from './ui/BorderGlow';

interface CommandInputProps {
  onSubmit: (val: string) => void;
}

export const CommandInput: React.FC<CommandInputProps> = ({ onSubmit }) => {
  const [value, setValue] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && value.trim()) {
      onSubmit(value);
      setValue('');
    }
  };

  return (
    <div 
      className="command-input-wrapper-glow"
      style={{ width: '100%', maxWidth: '72rem', margin: 0, zIndex: 20 }}
      onClick={() => inputRef.current?.focus()}
    >
      <BorderGlow 
        animated={isFocused} 
        glowColor="0 0 100"
        colors={['#ffffff', '#ffffff', '#ffffff']}
        backgroundColor="#141414"
        borderRadius={9999}
        glowRadius={10}
        glowIntensity={0.2}
        coneSpread={50}
        fillOpacity={0.02}
        className="w-full"
      >
        <div className="command-input-container" style={{ background: 'transparent', border: 'none', boxShadow: 'none' }}>
          <div className="command-input-prompt-icon" title="Command Directive">
            <Terminal size={14} />
          </div>

          <input
            ref={inputRef}
            className="command-input-field"
            placeholder="Enter command directive or ask Alfred anything..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
          />

          <div className="command-input-actions">
            <button 
              type="button"
              className="command-input-submit group transition-all duration-300 ease-out cursor-pointer hover:scale-110 active:scale-90"
              onClick={(e) => {
                e.stopPropagation();
                if (value.trim()) {
                  onSubmit(value);
                  setValue('');
                }
              }}
              title="Execute directive"
            >
              <Send size={13} className="transition-all duration-500 ease-out group-hover:rotate-180 group-active:rotate-180 group-active:scale-75" />
            </button>
          </div>
        </div>
      </BorderGlow>
    </div>
  );
};

