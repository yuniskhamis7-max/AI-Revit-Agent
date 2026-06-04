import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import type { ChatMessage, ToolCall } from '@/types';
import { ToolCallCard } from './ToolCallCard';

interface MessageBubbleProps {
  message: ChatMessage;
}

/** Detect if text is predominantly RTL (Arabic, Hebrew, etc.) */
function detectDir(text: string): 'rtl' | 'ltr' {
  if (!text) return 'ltr';
  const rtlChars = (text.match(/[\u0591-\u07FF\uFB1D-\uFDFD\uFE70-\uFEFC]/g) || []).length;
  const ltrChars  = (text.match(/[a-zA-Z]/g) || []).length;
  return rtlChars > ltrChars ? 'rtl' : 'ltr';
}

/**
 * Strip [object Object] serialisation artifacts that can appear when the SDK
 * accidentally serialises a React state object instead of a string value.
 * This guards the single remaining sanitisation point — the root cause has
 * been fixed in providerStore.ts but legacy DB content may still contain this.
 */
function sanitiseContent(text: string): string {
  return text.replace(/\[object Object\]\s*/g, '').trim();
}

// Custom react-markdown component overrides — applies project CSS classes
// so markdown elements match the existing design system without inline styles.
const markdownComponents: Components = {
  // Code blocks
  pre: ({ children }) => (
    <div className="markdown-code-block">
      <pre>{children}</pre>
    </div>
  ),
  code: ({ node, className, children, ...props }) => {
    // Inline code (no language class)
    const isBlock = Boolean(className);
    if (isBlock) {
      const lang = className?.replace('language-', '');
      return (
        <>
          {lang && <div className="code-lang-label">{lang}</div>}
          <code className={className} {...props}>{children}</code>
        </>
      );
    }
    return <code className="inline-code" {...props}>{children}</code>;
  },
  // Paragraphs
  p: ({ children }) => <p className="markdown-p">{children}</p>,
  // Headings
  h1: ({ children }) => <h1 className="markdown-h1">{children}</h1>,
  h2: ({ children }) => <h2 className="markdown-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="markdown-h3">{children}</h3>,
  // Lists
  ul: ({ children }) => <ul className="markdown-ul">{children}</ul>,
  ol: ({ children }) => <ol className="markdown-ol">{children}</ol>,
  li: ({ children }) => <li className="markdown-li">{children}</li>,
  // Links — open in new tab
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="markdown-link">
      {children}
    </a>
  ),
  // Horizontal rule
  hr: () => <hr className="markdown-hr" />,
  // Blockquote
  blockquote: ({ children }) => <blockquote className="markdown-blockquote">{children}</blockquote>,
  // Table (GFM)
  table: ({ children }) => (
    <div className="markdown-table-wrapper">
      <table className="markdown-table">{children}</table>
    </div>
  ),
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser      = message.role === 'user';
  const isStreaming  = message.role === 'streaming' || message.isStreaming;
  const dir          = useMemo(() => detectDir(message.content), [message.content]);

  const [thinkingOpen,      setThinkingOpen]      = useState(false);
  const [agentThoughtsOpen, setAgentThoughtsOpen] = useState(false);

  const hasThinking     = message.thinking      && message.thinking.length > 0;
  const hasAgentThoughts = message.agentThoughts && message.agentThoughts.length > 0;

  const cleanedContent = useMemo(
    () => sanitiseContent(message.content),
    [message.content],
  );

  return (
    <div className={`message-bubble-wrapper ${isUser ? 'user-wrapper' : 'assistant-wrapper'}`} dir={dir}>
      <div className="message-avatar">
        {isUser ? (
          <div className="avatar user-avatar">U</div>
        ) : (
          <div className="avatar assistant-avatar">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M12 2A10 10 0 0 0 2 12c0 4.42 2.87 8.17 6.84 9.39.5.08.66-.21.66-.48 0-.25-.01-.9-.01-1.78-2.78.6-3.37-1.34-3.37-1.34-.46-1.16-1.11-1.47-1.11-1.47-.9-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.9 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.1.39-1.99 1.03-2.69-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.65.7 1.03 1.6 1.03 2.69 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85 0 1.34-.01 2.42-.01 2.75 0 .27.16.57.67.48C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z"/>
            </svg>
          </div>
        )}
      </div>

      <div className="message-content-area">
        {/* Agent Thoughts block — synthetic [agent thought] events from the orchestrator */}
        {!isUser && hasAgentThoughts && (
          <div className="agent-thoughts-block">
            <button
              className="thinking-toggle agent-thought-toggle"
              onClick={() => setAgentThoughtsOpen(!agentThoughtsOpen)}
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
              </svg>
              <span>
                Agent activity ({message.agentThoughts!.length} step{message.agentThoughts!.length !== 1 ? 's' : ''})
              </span>
              <span className={`thinking-arrow ${agentThoughtsOpen ? 'open' : ''}`}>{'\u25BC'}</span>
            </button>
            {agentThoughtsOpen && (
              <div className="agent-thoughts-content">
                {message.agentThoughts!.map((thought, idx) => (
                  <div key={idx} className="agent-thought-line">
                    {thought}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Thinking / Reasoning block (from model's chain-of-thought) */}
        {!isUser && hasThinking && (
          <div className="thinking-block">
            <button className="thinking-toggle" onClick={() => setThinkingOpen(!thinkingOpen)}>
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"/>
              </svg>
              <span>Model reasoning</span>
              <span className={`thinking-arrow ${thinkingOpen ? 'open' : ''}`}>{'\u25BC'}</span>
            </button>
            {thinkingOpen && (
              <div className="thinking-content">{message.thinking}</div>
            )}
          </div>
        )}

        <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
          <div className="message-text">
            {cleanedContent ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={markdownComponents}
              >
                {cleanedContent}
              </ReactMarkdown>
            ) : (
              isStreaming && <span className="streaming-cursor">█</span>
            )}
            {isStreaming && cleanedContent && (
              <span className="streaming-cursor">█</span>
            )}
          </div>

          <div className="message-time">
            {message.createdAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
        </div>

        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="message-tool-calls">
            {message.toolCalls.map((tc: ToolCall) => (
              <ToolCallCard key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
