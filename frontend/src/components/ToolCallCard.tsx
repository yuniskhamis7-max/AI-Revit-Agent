import React, { useState } from 'react';
import type { ToolCall } from '@/types';

/**
 * Props for the ToolCallCard component.
 *
 * @property toolCall - The ToolCall object containing name, args, status, and result.
 */
interface ToolCallCardProps {
  toolCall: ToolCall;
}

/**
 * ToolCallCard — collapsible card displaying a single tool call.
 *
 * Shows:
 * - Tool name with a read (magnifier) or write (wrench) icon
 * - Status badge (Ready, Awaiting Approval, Executing, Success, Rejected)
 * - Expandable body with formatted JSON arguments and result
 *
 * Visually distinguishes read tools (fetch_*, get_*) from write tools
 * via different card colour classes.
 *
 * @component
 * @param props.toolCall - The tool call to render.
 */
export const ToolCallCard: React.FC<ToolCallCardProps> = ({ toolCall }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const isRead = toolCall.name.startsWith('fetch_') || toolCall.name.startsWith('get_');
  const cardTypeClass = isRead ? 'tool-read' : 'tool-write';
  
  // Format arguments & results nicely
  const formattedArgs = JSON.stringify(toolCall.args, null, 2);
  const formattedResult = toolCall.result ? JSON.stringify(toolCall.result, null, 2) : '';

  // Get human-readable status text & style
  const getStatusBadge = () => {
    switch (toolCall.status) {
      case 'pending':
        return <span className="status-badge status-pending">Ready</span>;
      case 'awaiting':
        return <span className="status-badge status-awaiting"><span className="pulse-dot"></span>Awaiting Approval</span>;
      case 'executing':
        return <span className="status-badge status-executing"><span className="pulse-dot"></span>Executing</span>;
      case 'done':
        return <span className="status-badge status-done">Success</span>;
      case 'rejected':
        return <span className="status-badge status-rejected">Rejected</span>;
      default:
        return <span className="status-badge">{toolCall.status}</span>;
    }
  };

  return (
    <div className={`tool-call-card ${cardTypeClass} ${toolCall.status}`}>
      <div className="tool-call-header" onClick={() => setIsExpanded(!isExpanded)}>
        <div className="tool-info">
          <svg className="tool-icon" viewBox="0 0 24 24" width="16" height="16">
            {isRead ? (
              <path fill="currentColor" d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
            ) : (
              <path fill="currentColor" d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/>
            )}
          </svg>
          <span className="tool-name">{toolCall.name}</span>
        </div>
        <div className="tool-meta">
          {getStatusBadge()}
          <span className={`expand-arrow ${isExpanded ? 'open' : ''}`}>▼</span>
        </div>
      </div>

      {isExpanded && (
        <div className="tool-call-body">
          <div className="code-section">
            <div className="code-header">Arguments</div>
            <pre className="code-content"><code>{formattedArgs}</code></pre>
          </div>
          
          {toolCall.result && (
            <div className="code-section result-section">
              <div className="code-header">Result</div>
              <pre className="code-content"><code>{formattedResult}</code></pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
