// src/components/ChatInputArea.jsx
import React, { useRef, useEffect } from 'react';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import InputGroup from 'react-bootstrap/InputGroup'; // Use InputGroup for better layout

const ChatInputArea = ({
    feedbackInput,
    onFeedbackChange,
    onSendFeedback,
    buttonState, // 'analyse', 'stop'
    onActionClick,
    isLoading,
    isInitialized,
    processingStatus,
    onFileUpload
}) => {

    const textareaRef = useRef(null);
    const fileInputRef = useRef(null);

    // Auto-resize function
    const adjustTextareaHeight = () => {
        const textarea = textareaRef.current;
        if (textarea) {
            // Reset height to auto to get the correct scrollHeight
            textarea.style.height = 'auto';
            
            // Calculate the new height
            const newHeight = Math.min(textarea.scrollHeight, 100); // 100px max height
            
            // Set the new height
            textarea.style.height = `${newHeight}px`;
        }
    };

    // Adjust height whenever feedbackInput changes
    useEffect(() => {
        adjustTextareaHeight();
    }, [feedbackInput]);

    // Also adjust on mount
    useEffect(() => {
        adjustTextareaHeight();
    }, []);

    const handleKeyDown = (event) => {
        // Send message on Enter, allow newline with Shift+Enter
        if (event.key === 'Enter' && !event.shiftKey && !isLoading && feedbackInput.trim()) {
            event.preventDefault(); // Prevent default newline behavior
            onSendFeedback();
        }
    };

    const handleFeedbackChange = (event) => {
        onFeedbackChange(event);
        // Trigger resize after state update
        setTimeout(adjustTextareaHeight, 0);
    };

    // Handle file upload
    const handleFileUpload = (event) => {
        const files = event.target.files;
        if (files && files.length > 0 && onFileUpload) {
            onFileUpload(files);
        }
        // Reset the input so the same file can be selected again if needed
        event.target.value = '';
    };

    // Trigger file input click
    const triggerFileUpload = () => {
        if (fileInputRef.current) {
            fileInputRef.current.click();
        }
    };

    // Determine main action button text and variant
    const actionButtonVariant = buttonState === 'stop' ? 'danger' : 'warning';
    const actionButtonText = buttonState === 'stop' ? 'Stop' : 'Analyse'; // Shorter text

    // Only render if initialized
    if (!isInitialized) {
        return null;
    }

    return (
        <div className="chat-input-area p-3 border-top bg-light">
            {/* Optional Loading Indicator above input */}
             {isLoading && (
                <div className="loading-indicator text-center mb-2 small text-muted">
                    <Spinner animation="border" size="sm" variant="secondary" /> {processingStatus || 'Processing...'}
                </div>
             )}

            <InputGroup>

            <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileUpload}
                style={{ display: 'none' }}
                accept=".txt,.csv,.json,.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.gif,.py,.ipynb,.md"
            />
            
            {/* File upload button */}
            <Button
                variant="secondary"
                onClick={triggerFileUpload}
                disabled={isLoading}
                className="file-upload-button me-2"
                title="Upload files"
            >
                <i className="bi bi-paperclip"></i>
            </Button>

            <Form.Control
                    ref={textareaRef}
                    as="textarea"
                    rows={1}
                    placeholder={isLoading ? "Processing..." : "Enter feedback or instruction..."}
                    value={feedbackInput}
                    onChange={handleFeedbackChange}
                    onKeyDown={handleKeyDown}
                    disabled={isLoading}
                    style={{ 
                        resize: 'none', 
                        maxHeight: '100px', 
                        minHeight: '38px', // Ensure minimum height
                        overflowY: 'auto',
                        lineHeight: '1.5' // Better line spacing
                    }}
                    className="chat-textarea me-2"
                />

                {/* Conditional rendering for Analyse/Stop vs Send */}
                {!isLoading && buttonState !== 'stop' && (
                    <Button
                        variant="info"
                        onClick={onSendFeedback}
                        disabled={isLoading || !feedbackInput.trim()}
                        className="send-button" // Add class for styling
                    >
                       <i className="bi bi-send"></i> Chat
                    </Button>
                 )}

                 {/* Analyse/Stop button appears when relevant */}
                 {!isLoading && (
                    <Button
                         variant={actionButtonVariant}
                         onClick={onActionClick}
                         disabled={isLoading}
                         className="action-button ms-2" // Added margin-start
                    >
                         {actionButtonText}
                    </Button>
                 )}

                 {/* Show spinner in place of buttons when loading */}
                 {isLoading && (
                    <Button variant="secondary" disabled className="ms-2">
                       <Spinner animation="border" size="sm" />
                    </Button>
                 )}

            </InputGroup>
        </div>
    );
};

export default ChatInputArea;