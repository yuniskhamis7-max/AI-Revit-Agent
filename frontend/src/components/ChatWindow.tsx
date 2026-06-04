import React, { useState, useRef, useEffect } from 'react';
import { useChat } from '@/hooks/useChat';
import { useMessageStore } from '@/store/messageStore';
import { useSessionStore } from '@/store/sessionStore';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '@/types';

export const ChatWindow: React.FC = () => {
  const { messages, isStreaming } = useMessageStore();
  const { activeSessionId } = useSessionStore();
  const { sendMessage, cancelStream } = useChat();
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isStreaming) return;
    
    sendMessage(inputText.trim());
    setInputText('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(e);
    }
  };

  // Example starter prompts for Revit
  const starterPrompts = [
    { text: 'List all levels in the project', icon: '📋' },
    { text: 'Create a new level named L3 at 9.0 meters elevation', icon: '🏗️' },
    { text: 'Count how many walls are in this document', icon: '🧱' },
  ];

  if (!activeSessionId) {
    return (
      <div className="chat-window empty-state">
        <div className="empty-state-content">
          <div className="icon-badge">💬</div>
          <h2>No Session Selected</h2>
          <p>Create or select a chat session from the sidebar to begin automating Revit.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-window">
      <div className="chat-messages-container">
        {messages.length === 0 ? (
          <div className="empty-chat-welcome">
            <h3>How can I help you in Revit today?</h3>
            <p>Type a natural language instruction or try one of these quick starts:</p>
            <div className="starter-prompts-grid">
              {starterPrompts.map((p, idx) => (
                <button
                  key={idx}
                  className="starter-prompt-card"
                  onClick={() => setInputText(p.text)}
                >
                  <span className="starter-icon">{p.icon}</span>
                  <span className="starter-text">{p.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="messages-list">
            {messages.map((msg: ChatMessage) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <div className="chat-input-area">
        <form onSubmit={handleSend} className="chat-input-form">
          <textarea
            className="chat-textarea"
            placeholder="Ask Revit to list elements, create sheets, or run tools..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
          />
          
          {isStreaming ? (
            <button type="button" className="stop-btn" onClick={cancelStream}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M6 19h12V5H6v14z"/>
              </svg>
              Stop
            </button>
          ) : (
            <button 
              type="submit" 
              className="send-btn" 
              disabled={!inputText.trim()}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
              </svg>
              Send
            </button>
          )}
        </form>
      </div>
    </div>
  );
};
