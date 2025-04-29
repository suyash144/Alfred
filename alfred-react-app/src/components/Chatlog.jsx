// src/components/ChatLog.jsx
import React, { useRef, useEffect } from 'react';
import CodeBlock from './CodeBlock';
import ReactMarkdown from 'react-markdown'; // Import ReactMarkdown
import remarkGfm from 'remark-gfm'; // Import GFM plugin for tables, strikethrough, etc.
import rehypeRaw from 'rehype-raw'; // Import rehypeRaw for raw HTML support
import './ChatLog.css';

const ChatLog = ({ history = [], expandedCodeBlocks, onToggleCodeExpand, onImageClick }) => {
    const chatEndRef = useRef(null);
    const chatContainerRef = useRef(null); // Ref for the scrollable container

    // Auto-scroll to bottom, more reliably
    useEffect(() => {
        const container = chatContainerRef.current;
        if (container) {
            // Scroll only if user isn't close to the top (allows looking at history)
             const threshold = 150; // Pixels from bottom
             const isScrolledToBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + threshold;

             if (isScrolledToBottom) {
                 // Timeout ensures render is complete before scrolling
                 setTimeout(() => {
                    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
                 }, 100);
            }
        }
    }, [history]);

    const renderContent = (item, index) => {
        const blockId = `code-block-${item.iteration}-${index}`; // Unique ID for code blocks

        switch (item.type) {
            case 'text':
                // Render Markdown content
                return (
                    <div key={`text-${index}`} className="chat-content text-content markdown-body">
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeRaw]}
                        >
                            {item.content || ''}
                        </ReactMarkdown>
                    </div>
                );
            case 'code':
                const codeContent = item.content?.startsWith('Proposed code:')
                    ? item.content.substring('Proposed code:'.length).trim()
                    : item.content || '';
                // CodeBlock is already memoized, should be efficient
                return (
                    <CodeBlock
                        key={blockId}
                        code={codeContent}
                        iteration={item.iteration}
                        blockId={blockId}
                        isExpanded={expandedCodeBlocks.has(blockId)}
                        onToggleExpand={onToggleCodeExpand}
                    />
                );
            case 'output':
                 let outputContent = item.content || '';
                 // Simplified formatting for output/error types
                  if (outputContent.startsWith('Code Output:<br>')) {
                      outputContent = outputContent.substring('Code Output:<br>'.length).trim();
                  } else if (outputContent.startsWith('Error while running code:')) {
                      outputContent = `Error: ${outputContent.substring('Error while running code:'.length).trim()}`;
                  } else if (outputContent.startsWith('Execution error:')) {
                     outputContent = `Execution Error: ${outputContent.substring('Execution error:'.length).trim()}`;
                 } else if (outputContent.startsWith('Execution timed out:')) {
                     outputContent = `Timeout: ${outputContent.substring('Execution timed out:'.length).trim()}`;
                 }
                return (
                    <div key={`output-${index}`} className="chat-content output-content">
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeRaw]}
                        >
                            {outputContent}
                        </ReactMarkdown>
                    </div>
                );
            case 'figure':
                return (
                    <div key={`figure-${index}`} className="chat-content figure-content">
                        <img
                            src={item.content}
                            alt={`Figure from Iteration ${item.iteration}`}
                            className="figure-image expandable-image"
                            onClick={() => onImageClick(item.content)}
                             // Removed inline style, control via CSS
                        />
                    </div>
                );
            default:
                // console.warn("Unknown history item type:", item.type, item);
                return null; // Don't render unknown types
        }
    };

    // --- Grouping Logic (Revised) ---
    const renderedMessageGroups = [];
    let currentAssistantGroup = null;

    history.forEach((item, index) => {
        const itemIteration = Number(item.iteration) || 0;

        if (item.role === 'user') {
            // Push any pending assistant group before the user message
            if (currentAssistantGroup) {
                renderedMessageGroups.push(currentAssistantGroup);
                currentAssistantGroup = null;
            }
            // Push the user message group
            renderedMessageGroups.push({
                key: `user-${itemIteration}-${index}`,
                role: 'user',
                iteration: itemIteration,
                items: [item] // User item is always alone in its bubble
            });
        } else { // Assistant, tool, system messages
            // Determine the type of this specific item
            const itemIsText = item.type === 'text';
            const itemIsToolResponse = item.type === 'code' || item.type === 'output' || item.type === 'figure';

            // Start a new assistant group if:
            // 1. No current group exists or we are in iteration 0 (which is data inventory)
            // 2. The iteration changes
            // 3. We encounter assistant text, and the current group is already a tool response group
            // 4. We encounter a tool response, and the current group is already a text group
             if (!currentAssistantGroup || currentAssistantGroup.iteration == 0 ||
                 currentAssistantGroup.iteration !== itemIteration ||
                 (itemIsText && currentAssistantGroup.type === 'tool_response') ||
                 (itemIsToolResponse && currentAssistantGroup.type === 'text') )
             {
                 // Push the previous group if it existed
                 if (currentAssistantGroup) {
                     renderedMessageGroups.push(currentAssistantGroup);
                 }
                 // Create the new group
                 currentAssistantGroup = {
                     key: `assistant-${itemIteration}-${index}`,
                     role: 'assistant',
                     iteration: itemIteration,
                     type: itemIsText ? 'text' : (itemIsToolResponse ? 'tool_response' : 'unknown'), // Mark group type
                     items: [item]
                 };
             } else {
                 // Add to the existing assistant group (same iteration, compatible type)
                 currentAssistantGroup.items.push(item);
                 // Ensure the group type reflects code/output/figure if present
                 if (itemIsToolResponse) {
                     currentAssistantGroup.type = 'tool_response';
                 }
             }
        }
    });

    // Push the last assistant group if it exists
    if (currentAssistantGroup) {
        renderedMessageGroups.push(currentAssistantGroup);
    }

    return (
        <div ref={chatContainerRef} className="chat-log-area mb-4">
            {renderedMessageGroups.map(({ key, role, iteration, items }) => {
                const messageClass = role === 'user' ? 'user-message' : 'assistant-message';
                // Generate unique block IDs within this group if needed multiple times
                const baseBlockId = `code-block-${iteration}-${key}`;
                let codeBlockCounter = 0;

                return (
                    <div key={key} className={`message-group ${messageClass}`}>
                        <div className="message-bubble">
                            {/* Only show iteration label for assistant messages maybe? */}
                            {role === 'assistant' && <div className="iteration-label">Iteration {iteration}</div>}
                            {/* Render items in order within the bubble */}
                            {items.map((item, idx) => {
                                const uniqueBlockId = `${baseBlockId}-${codeBlockCounter}`;
                                if(item.type === 'code') codeBlockCounter++; // Increment only for code blocks
                                return renderContent(item, `${key}-item-${idx}`, uniqueBlockId);
                            })}
                        </div>
                    </div>
                );
            })}
            <div ref={chatEndRef} />
        </div>
    );
};

export default ChatLog;