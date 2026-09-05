import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, Sparkles } from 'lucide-react';
import { ConversationMessage } from '../types/vesper';
import { gatewayService } from '../services/gateway';

interface ChatStreamProps {
  messages: ConversationMessage[];
  onSimulateWakeWord: () => void;
}

export const ChatStream: React.FC<ChatStreamProps> = ({ messages, onSimulateWakeWord }) => {
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    gatewayService.sendVoiceCommand(inputText);
    setInputText('');
  };

  const handleQuickPrompt = (prompt: string) => {
    gatewayService.sendVoiceCommand(prompt);
  };

  return (
    <div className="chat-stream-container">
      <div className="chat-stream-header">
        <div className="chat-title">
          <Sparkles size={16} />
          <span>COGNITIVE LOG & DIALOGUE</span>
        </div>
        <div className="chat-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={onSimulateWakeWord}
            title="Simulate Wake Word: Hey Alfred"
          >
            <Mic size={14} />
            <span>WAKE WORD</span>
          </button>
        </div>
      </div>

      <div className="chat-messages-scroll">
        {messages.length === 0 ? (
          <div className="chat-empty-state">
            <div className="empty-title">Alfred System Online</div>
            <div className="empty-desc">
              Speak &apos;Hey Alfred&apos; via edge microphone, enter a command below, or perform a hand gesture.
            </div>
            <div className="quick-prompts">
              <button
                type="button"
                className="chip-btn"
                onClick={() => handleQuickPrompt('Give me a brief system and cluster status report')}
              >
                System Status
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => handleQuickPrompt('What is the weather today?')}
              >
                Weather Briefing
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => handleQuickPrompt('Help me plan my deep work block for today')}
              >
                Deep Work Plan
              </button>
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={`chat-bubble-row ${msg.sender}`}>
              <div className="chat-bubble">
                <div className="bubble-header">
                  <span className="bubble-sender">{msg.sender.toUpperCase()}</span>
                  {msg.intent && <span className="bubble-intent">{msg.intent}</span>}
                  {msg.latencyMs && (
                    <span className="bubble-latency">{msg.latencyMs.toFixed(0)}ms</span>
                  )}
                  <span className="bubble-time">
                    {new Date(msg.timestamp).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </span>
                </div>

                <div className="bubble-content">{msg.text}</div>

                {msg.cards && msg.cards.length > 0 && (
                  <div className="bubble-cards">
                    {msg.cards.map((card, idx) => (
                      <div key={idx} className="hud-card">
                        {card.title && <div className="card-title">{card.title}</div>}
                        {card.content && <div className="card-body">{card.content}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-form" onSubmit={handleSubmit}>
        <input
          type="text"
          className="chat-input"
          placeholder="Send voice command or query to Alfred Swarm..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
        />
        <button type="submit" className="send-btn" disabled={!inputText.trim()}>
          <Send size={16} />
        </button>
      </form>
    </div>
  );
};
