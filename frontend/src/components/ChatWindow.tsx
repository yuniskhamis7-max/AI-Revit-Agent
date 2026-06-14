import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useChat } from '@/hooks/useChat';
import { useMessageStore } from '@/store/messageStore';
import { useSessionStore } from '@/store/sessionStore';
import { useUIStore } from '@/store/uiStore';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '@/types';

/**
 * ChatWindow — the main conversation interface for the multi-agent BIM workflow.
 *
 * Features:
 * - Image attachment via file-picker or paste (PNG, JPG, WEBP)
 * - Auto-growing textarea (Shift+Enter for newline, Enter to send)
 * - Streaming stop button
 * - Starter prompt cards when session is empty
 * - Revit offline banner
 * - Auto-scroll to latest message
 */
export const ChatWindow: React.FC = () => {
  const { messages, isStreaming } = useMessageStore();
  const { activeSessionId } = useSessionStore();
  const { revitStatus } = useUIStore();
  const { sendMessage, cancelStream } = useChat();

  const [inputText, setInputText] = useState('');
  const [attachedImages, setAttachedImages] = useState<string[]>([]); // base64 data URLs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

  // ── Auto-resize textarea ──────────────────────────────────────────────────
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    // Use max(72, scrollHeight) so the textarea never shrinks below its CSS min-height
    ta.style.height = `${Math.max(72, Math.min(ta.scrollHeight, 180))}px`;
  }, [inputText]);

  // ── Image helpers ─────────────────────────────────────────────────────────
  const readFileAsBase64 = (file: File): Promise<string> =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });

  const addImages = useCallback(async (files: FileList | File[]) => {
    const allowed = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
    const valid = Array.from(files).filter(f => allowed.includes(f.type));
    if (!valid.length) return;
    const b64s = await Promise.all(valid.map(readFileAsBase64));
    setAttachedImages(prev => [...prev, ...b64s].slice(0, 4)); // max 4 images
  }, []);

  const handlePaste = useCallback(
    async (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const imageItems = Array.from(e.clipboardData.items).filter(
        item => item.type.startsWith('image/'),
      );
      if (!imageItems.length) return;
      const files = imageItems.map(item => item.getAsFile()!).filter(Boolean);
      await addImages(files);
    },
    [addImages],
  );

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) {
        await addImages(e.target.files);
        e.target.value = ''; // reset so same file can be re-added
      }
    },
    [addImages],
  );

  const removeImage = (idx: number) =>
    setAttachedImages(prev => prev.filter((_, i) => i !== idx));

  // ── Send ──────────────────────────────────────────────────────────────────
  const handleSend = (e?: React.FormEvent) => {
    e?.preventDefault();
    const text = inputText.trim();
    if ((!text && !attachedImages.length) || isStreaming) return;
    sendMessage(text, attachedImages.length ? attachedImages : undefined);
    setInputText('');
    setAttachedImages([]);
    if (textareaRef.current) textareaRef.current.style.height = '72px';
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── Starter prompts ───────────────────────────────────────────────────────
  const starterPrompts = [
    { text: 'List all levels in the project', icon: '📋', tag: 'fetch' },
    { text: 'Create a 3×3 column grid spaced 20 ft apart', icon: '🏗️', tag: 'complex' },
    { text: 'Create a new level named L5 at 15 m elevation', icon: '📐', tag: 'simple' },
    { text: 'Count how many walls are in this document', icon: '🧱', tag: 'fetch' },
  ];

  // ── No session ────────────────────────────────────────────────────────────
  if (!activeSessionId) {
    return (
      <div className="chat-window empty-state">
        <div className="empty-state-content">
          <div className="icon-badge">🤖</div>
          <h2>No Session Selected</h2>
          <p>Create or select a chat session from the sidebar to begin automating Revit with AI.</p>
        </div>
      </div>
    );
  }

  const canSend = (inputText.trim().length > 0 || attachedImages.length > 0) && !isStreaming;

  return (
    <div className="chat-window">
      {/* Revit offline banner */}
      {revitStatus === 'disconnected' && (
        <div className="revit-offline-banner">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
          </svg>
          Revit connection offline — ensure the Revit bridge is running before sending commands.
        </div>
      )}

      {/* Messages area */}
      <div className="chat-messages-container">
        {messages.length === 0 ? (
          <div className="empty-chat-welcome">
            <div className="welcome-agent-icon">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="currentColor">
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14l-5-5 1.41-1.41L12 14.17l7.59-7.59L21 8l-9 9z"/>
              </svg>
            </div>
            <h3>BIM AI Agent</h3>
            <p>Describe what you want to do in Revit — the agent will plan, validate, and execute automatically.</p>
            <div className="starter-prompts-grid">
              {starterPrompts.map((p, idx) => (
                <button
                  key={idx}
                  className="starter-prompt-card"
                  onClick={() => setInputText(p.text)}
                >
                  <span className="starter-icon">{p.icon}</span>
                  <div className="starter-body">
                    <span className={`starter-tag starter-tag-${p.tag}`}>{p.tag}</span>
                    <span className="starter-text">{p.text}</span>
                  </div>
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

      {/* Input area */}
      <div className="chat-input-area">
        <div className="chat-input-wrapper">
          {/* Image thumbnails */}
          {attachedImages.length > 0 && (
            <div className="image-attachments-row">
              {attachedImages.map((src, idx) => (
                <div key={idx} className="attachment-thumb-wrap">
                  <img src={src} alt={`attachment-${idx}`} className="attachment-thumb" />
                  <button
                    className="attachment-remove-btn"
                    onClick={() => removeImage(idx)}
                    title="Remove image"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}

          <form onSubmit={handleSend} className="chat-input-form">
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              multiple
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />

            {/* Attach image button */}
            <button
              type="button"
              className="attach-btn"
              title="Attach image (or paste from clipboard)"
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming || attachedImages.length >= 4}
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
              </svg>
            </button>

            <textarea
              ref={textareaRef}
              id="chat-input"
              className="chat-textarea"
              placeholder="Ask the BIM agent anything — list elements, create geometry, coordinate changes…"
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              rows={1}
              disabled={isStreaming}
            />

            {isStreaming ? (
              <button type="button" className="stop-btn" onClick={cancelStream} title="Stop generation">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M6 19h12V5H6v14z"/>
                </svg>
                Stop
              </button>
            ) : (
              <button
                type="submit"
                id="send-btn"
                className="send-btn"
                disabled={!canSend}
                title="Send message (Enter)"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
                Send
              </button>
            )}
          </form>

          <div className="input-hint-row">
            <span className="input-hint">
              <kbd>Enter</kbd> to send · <kbd>Shift+Enter</kbd> for newline · paste images directly
            </span>
            {attachedImages.length > 0 && (
              <span className="input-hint-count">{attachedImages.length}/4 images</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
