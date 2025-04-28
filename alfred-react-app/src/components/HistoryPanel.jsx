// src/components/HistoryPanel.js
import React, { useRef, useEffect } from 'react';
import CodeBlock from './CodeBlock';

const HistoryPanel = ({ title, history = [], type, onImageClick, expandedCodeBlocks, onToggleCodeExpand }) => {
    const panelRef = useRef(null);
    const scrollTimeoutRef = useRef(null);
    const isUserScrollingRef = useRef(false);
    const prevHistoryLengthRef = useRef(history.length);

    // Filter history based on type
    const filteredHistory = history.filter(entry => entry.type === type);

    const handleScroll = () => {
        isUserScrollingRef.current = true;
        clearTimeout(scrollTimeoutRef.current);
        scrollTimeoutRef.current = setTimeout(() => {
            isUserScrollingRef.current = false;
        }, 1500); // User considered inactive after 1.5s
    };

    useEffect(() => {
        const panelElement = panelRef.current;
        if (!panelElement) return;

        // Scroll to bottom only if history length increased and user is not actively scrolling
        if (filteredHistory.length > prevHistoryLengthRef.current && !isUserScrollingRef.current) {
            panelElement.scrollTop = panelElement.scrollHeight;
        }
        prevHistoryLengthRef.current = filteredHistory.length;

        // Add scroll listener
        panelElement.addEventListener('scroll', handleScroll);
        return () => {
            panelElement.removeEventListener('scroll', handleScroll);
            clearTimeout(scrollTimeoutRef.current);
        };
    }, [filteredHistory.length]); // Dependency on length to detect new items


    const renderContent = (entry, index) => {
        const roleClass = entry.role === 'assistant' ? 'assistant' : 'user';
        const iterationLabel = <strong>Iteration {entry.iteration}:</strong>;
        const blockId = `code-block-${entry.iteration}-${index}`; // Unique ID for code blocks

        switch (type) {
            case 'text':
                return (
                    <div className={`history-entry ${roleClass}`} key={index}>
                        {iterationLabel} <strong>{entry.role?.toUpperCase()}</strong>
                        {/* Render raw HTML assuming it's safe or sanitize */}
                        <div dangerouslySetInnerHTML={{ __html: entry.content || '' }} />
                    </div>
                );
            case 'code':
                 // Content might be 'Proposed code: ...'
                const codeContent = entry.content?.startsWith('Proposed code:')
                    ? entry.content.substring('Proposed code:'.length).trim()
                    : entry.content || '';

                return (
                    <CodeBlock
                        key={blockId}
                        code={codeContent}
                        iteration={entry.iteration}
                        blockId={blockId}
                        isExpanded={expandedCodeBlocks.has(blockId)}
                        onToggleExpand={onToggleCodeExpand}
                    />
                );
            case 'output':
                 // Content might be 'Code Output: ...' or 'Error: ...'
                 let outputContent = entry.content || '';
                 let outputLabel = 'CODE OUTPUT';
                 if (outputContent.startsWith('Code Output:<br>')) {
                     outputContent = outputContent.substring('Code Output:<br>'.length).trim();
                 } else if (outputContent.startsWith('Error while running code:')) {
                     outputContent = outputContent.substring('Error while running code:'.length).trim();
                     outputLabel = 'ERROR';
                 } else if (outputContent.startsWith('Execution error:')) {
                    outputContent = outputContent.substring('Execution error:'.length).trim();
                    outputLabel = 'EXECUTION ERROR';
                } else if (outputContent.startsWith('Execution timed out:')) {
                    outputContent = outputContent.substring('Execution timed out:'.length).trim();
                    outputLabel = 'TIMEOUT';
                }
                 return (
                     <div className="history-entry" key={index}>
                         {iterationLabel} <strong>{outputLabel}</strong>
                         <div className="p-2 bg-light border rounded text-break">
                             <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{outputContent}</pre>
                         </div>
                     </div>
                 );
            case 'figure':
                return (
                    <div className="history-entry" key={index}>
                        {iterationLabel} <strong>FIGURE</strong>
                        <img
                            src={entry.content}
                            alt={`Figure from Iteration ${entry.iteration}`}
                            className="figure-image expandable-image"
                            onClick={() => onImageClick(entry.content)}
                            style={{ cursor: 'pointer', maxWidth: '100%', maxHeight: '200px', objectFit: 'contain' }}
                        />
                    </div>
                );
            default:
                return null;
        }
    };

    return (
        <div className="mb-4">
            <h4>{title}</h4>
            <div
                ref={panelRef}
                style={{ maxHeight: '500px', overflowY: 'auto', border: '1px solid #ddd', borderRadius: '5px', padding: '10px' }}
                id={`${type}-history-panel`} // Add ID for potential targeting
            >
                {filteredHistory.length > 0 ? (
                    filteredHistory.map(renderContent)
                ) : (
                    <p>No {title.toLowerCase()} yet.</p>
                )}
            </div>
        </div>
    );
};

export default HistoryPanel;