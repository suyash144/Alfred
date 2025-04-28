// src/components/CurrentAnalysis.js
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Card from 'react-bootstrap/Card';
import Form from 'react-bootstrap/Form';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import Collapse from 'react-bootstrap/Collapse';

const CurrentAnalysis = ({
    summary,
    buttonState, // 'analyse', 'stop'
    onActionClick,
    feedbackInput,
    onFeedbackChange,
    onSendFeedback,
    isLoading,
    processingStatus,
    isInitialized, // To show/hide sections
}) => {

    const getButtonVariant = () => {
        switch (buttonState) {
            case 'stop': return 'danger';
            case 'analyse': return 'warning'; // Assuming 'analyse' means ready to execute
            default: return 'secondary'; // Fallback
        }
    };

     const getButtonText = () => {
        switch (buttonState) {
            case 'stop': return 'Stop Analysis';
            case 'analyse': return 'Analyse';
            default: return 'Analyse'; // Default
        }
    };

    const showSummary = isInitialized && summary;
    const showFeedback = isInitialized && !isLoading; // Show feedback only when not loading and initialized

    return (
        <div>
            <Collapse in={showSummary}>
                <div id="summary-section"> {/* Needed for Collapse */}
                    <div className="d-flex justify-content-between align-items-center mb-3">
                        <h3>Current Analysis</h3>
                        <Button
                             id="action-btn" // Keep ID if needed for specific styling/testing
                             variant={getButtonVariant()}
                             onClick={onActionClick}
                             disabled={isLoading || !isInitialized} // Disable when loading or not ready
                        >
                             {getButtonText()}
                        </Button>
                    </div>
                    <Card className="mb-4">
                        <Card.Body id="summary-content">
                             {/* Use ReactMarkdown for safe rendering */}
                             <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                 {summary || ''}
                             </ReactMarkdown>
                        </Card.Body>
                    </Card>
                 </div>
            </Collapse>

            <Collapse in={showFeedback}>
                <div id="feedback-section"> {/* Needed for Collapse */}
                    <h4>Provide Feedback</h4>
                     <Form.Control
                        as="textarea"
                        id="feedback-input" // Keep ID if needed
                        className="feedback-input mb-2"
                        placeholder="Enter feedback for the model..."
                        value={feedbackInput}
                        onChange={(e) => onFeedbackChange(e.target.value)}
                        disabled={isLoading}
                    />
                    <Button
                        id="send-feedback-btn"
                        variant="info"
                        onClick={onSendFeedback}
                        disabled={isLoading || !feedbackInput.trim()} // Disable if loading or no feedback
                    >
                        Send Feedback
                    </Button>
                 </div>
            </Collapse>

             {isLoading && (
                <div className="loading text-center mt-4">
                    <Spinner animation="border" variant="primary" style={{ width: '3rem', height: '3rem' }} />
                    <p id="processing-status" className="mt-2">{processingStatus || 'Processing...'}</p>
                </div>
            )}
        </div>
    );
};

export default CurrentAnalysis;