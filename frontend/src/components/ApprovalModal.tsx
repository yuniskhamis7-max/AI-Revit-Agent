import React from 'react';
import { useChat } from '@/hooks/useChat';
import { useChatStore } from '@/store/chatStore';

export const ApprovalModal: React.FC = () => {
  const { pendingApproval } = useChatStore();
  const { approve } = useChat();

  if (!pendingApproval) return null;

  const { toolCall } = pendingApproval;
  const formattedArgs = JSON.stringify(toolCall.args, null, 2);

  return (
    <div className="modal-backdrop">
      <div className="modal-content approval-modal">
        <div className="modal-header">
          <div className="modal-title-row">
            <span className="warning-shield">⚠️</span>
            <h3>Approval Required</h3>
          </div>
        </div>

        <div className="modal-body">
          <p className="modal-description">
            The AI assistant wants to execute a write action on the active Revit document. 
            Please review the parameters before proceeding:
          </p>

          <div className="tool-details">
            <div className="detail-row">
              <span className="detail-label">Action:</span>
              <span className="detail-value tool-name-highlight">{toolCall.name}</span>
            </div>
            
            <div className="detail-row args-row">
              <span className="detail-label">Arguments:</span>
              <pre className="detail-args">
                <code>{formattedArgs}</code>
              </pre>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button 
            className="modal-btn btn-reject" 
            onClick={() => approve(false)}
          >
            Reject Action
          </button>
          
          <button 
            className="modal-btn btn-approve" 
            onClick={() => approve(true)}
          >
            Approve & Execute
          </button>
        </div>
      </div>
    </div>
  );
};
