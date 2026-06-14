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

function sanitiseContent(text: string): string {
  return text.replace(/\[object Object\]\s*/g, '').trim();
}

/**
 * Extract the workflow phase label + icon from an agent-thought string.
 * The backend emits thoughts like "[BIM Orchestrator] Classifying request…"
 * We parse the bracket prefix and map it to a phase badge.
 */
function parseThoughtPhase(thought: string): { agent: string; rest: string } {
  const match = thought.match(/^\[([^\]]+)\]\s*(.*)/s);
  if (match) return { agent: match[1], rest: match[2] };
  return { agent: '', rest: thought };
}

const AGENT_COLORS: Record<string, string> = {
  'BIM Orchestrator':       'phase-orchestrator',
  'Simple Task Agent':      'phase-simple',
  'BIM Intent Clarifier':   'phase-clarifier',
  'BIM Design Manual':      'phase-spec',
  'BIM Execution Planner':  'phase-planner',
  'BIM Parser':             'phase-executor',
  'BIM Validator':          'phase-qa',
};

const AGENT_ICONS: Record<string, string> = {
  'BIM Orchestrator':       '🧠',
  'Simple Task Agent':      '⚡',
  'BIM Intent Clarifier':   '🔍',
  'BIM Design Manual':      '📋',
  'BIM Execution Planner':  '📐',
  'BIM Parser':             '⚙️',
  'BIM Validator':          '✅',
};

// Markdown component overrides
const markdownComponents: Components = {
  pre: ({ children }) => (
    <div className="markdown-code-block">
      <pre>{children}</pre>
    </div>
  ),
  code: ({ className, children, ...props }) => {
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
  p: ({ children }) => <p className="markdown-p">{children}</p>,
  h1: ({ children }) => <h1 className="markdown-h1">{children}</h1>,
  h2: ({ children }) => <h2 className="markdown-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="markdown-h3">{children}</h3>,
  ul: ({ children }) => <ul className="markdown-ul">{children}</ul>,
  ol: ({ children }) => <ol className="markdown-ol">{children}</ol>,
  li: ({ children }) => <li className="markdown-li">{children}</li>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="markdown-link">
      {children}
    </a>
  ),
  hr: () => <hr className="markdown-hr" />,
  blockquote: ({ children }) => <blockquote className="markdown-blockquote">{children}</blockquote>,
  table: ({ children }) => (
    <div className="markdown-table-wrapper">
      <table className="markdown-table">{children}</table>
    </div>
  ),
};

/**
 * MessageBubble — renders a single chat turn.
 *
 * User bubbles show:
 *   - Text content
 *   - Attached image thumbnails (with lightbox on click)
 *
 * Assistant bubbles show:
 *   - Collapsible "Agent Activity" panel with per-agent phase labels & icons
 *   - Collapsible model reasoning (chain-of-thought)
 *   - Markdown-rendered text
 *   - Tool call cards
 */
export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser      = message.role === 'user';
  const isStreaming  = message.role === 'streaming' || message.isStreaming;
  const dir          = useMemo(() => detectDir(message.content), [message.content]);

  const [thinkingOpen,      setThinkingOpen]      = useState(false);
  const [agentThoughtsOpen, setAgentThoughtsOpen] = useState(true); // default open for live feedback
  const [lightboxSrc,       setLightboxSrc]       = useState<string | null>(null);

  const hasThinking      = Boolean(message.thinking?.length);
  const hasAgentThoughts = Boolean(message.agentThoughts?.length);

  const cleanedContent = useMemo(
    () => sanitiseContent(message.content),
    [message.content],
  );

  return (
    <>
      <div
        className={`message-bubble-wrapper ${isUser ? 'user-wrapper' : 'assistant-wrapper'}`}
        dir={dir}
      >
        {/* Avatar */}
        <div className="message-avatar">
          {isUser ? (
            <div className="avatar user-avatar">U</div>
          ) : (
            <div className="avatar assistant-avatar">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14l-5-5 1.41-1.41L12 14.17l7.59-7.59L21 8l-9 9z"/>
              </svg>
            </div>
          )}
        </div>

        <div className="message-content-area">
          {/* ── Agent Activity panel (assistant only) ─────────────────────── */}
          {!isUser && hasAgentThoughts && (
            <div className="agent-thoughts-block">
              <button
                className="thinking-toggle agent-thought-toggle"
                onClick={() => setAgentThoughtsOpen(!agentThoughtsOpen)}
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                  <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 14l-5-5 1.41-1.41L12 14.17l7.59-7.59L21 8l-9 9z"/>
                </svg>
                <span>
                  Agent activity ({message.agentThoughts!.length} step{message.agentThoughts!.length !== 1 ? 's' : ''})
                </span>
                {isStreaming && <span className="live-badge">LIVE</span>}
                <span className={`thinking-arrow ${agentThoughtsOpen ? 'open' : ''}`}>{'▼'}</span>
              </button>

              {agentThoughtsOpen && (
                <div className="agent-thoughts-content">
                  {message.agentThoughts!.map((thought, idx) => {
                    const { agent, rest } = parseThoughtPhase(thought);
                    const colorClass = AGENT_COLORS[agent] ?? 'phase-default';
                    const icon = AGENT_ICONS[agent] ?? '•';
                    return (
                      <div key={idx} className={`agent-thought-line ${colorClass}`}>
                        <span className="thought-icon">{icon}</span>
                        {agent && (
                          <span className={`thought-agent-badge ${colorClass}`}>{agent}</span>
                        )}
                        <span className="thought-rest">{rest || thought}</span>
                      </div>
                    );
                  })}
                  {isStreaming && (
                    <div className="agent-thought-line phase-default thought-typing">
                      <span className="thought-icon">⋯</span>
                      <span className="thought-rest streaming-cursor">working</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* ── Model reasoning block ─────────────────────────────────────── */}
          {!isUser && hasThinking && (
            <div className="thinking-block">
              <button className="thinking-toggle" onClick={() => setThinkingOpen(!thinkingOpen)}>
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                  <path d="M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z"/>
                </svg>
                <span>Model reasoning</span>
                <span className={`thinking-arrow ${thinkingOpen ? 'open' : ''}`}>{'▼'}</span>
              </button>
              {thinkingOpen && (
                <div className="thinking-content">{message.thinking}</div>
              )}
            </div>
          )}

          {/* ── Message bubble ────────────────────────────────────────────── */}
          <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
            {/* Attached images (user messages) */}
            {isUser && message.images && message.images.length > 0 && (
              <div className="message-image-grid">
                {message.images.map((src, idx) => (
                  <img
                    key={idx}
                    src={src}
                    alt={`attachment-${idx}`}
                    className="message-image-thumb"
                    onClick={() => setLightboxSrc(src)}
                    title="Click to enlarge"
                  />
                ))}
              </div>
            )}

            <div className="message-text">
              {cleanedContent ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
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

          {/* ── Tool call cards ───────────────────────────────────────────── */}
          {message.toolCalls && message.toolCalls.length > 0 && (
            <div className="message-tool-calls">
              {message.toolCalls.map((tc: ToolCall) => (
                <ToolCallCard key={tc.id} toolCall={tc} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Image lightbox ──────────────────────────────────────────────────── */}
      {lightboxSrc && (
        <div className="lightbox-backdrop" onClick={() => setLightboxSrc(null)}>
          <div className="lightbox-inner" onClick={e => e.stopPropagation()}>
            <img src={lightboxSrc} alt="enlarged" className="lightbox-image" />
            <button className="lightbox-close" onClick={() => setLightboxSrc(null)}>✕</button>
          </div>
        </div>
      )}
    </>
  );
};
