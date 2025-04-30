// src/components/CodeBlock.js
import React from 'react';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import { github } from 'react-syntax-highlighter/dist/esm/styles/hljs'; // Or choose another style
import python from 'react-syntax-highlighter/dist/esm/languages/hljs/python';
import Button from 'react-bootstrap/Button';

SyntaxHighlighter.registerLanguage('python', python);

const CodeBlock = ({ code, iteration, blockId, isExpanded, onToggleExpand }) => {
    const codeLines = code ? code.split('\n').length : 0;

    return (
        <div className={`history-entry code-block expandable-code ${isExpanded ? '' : 'collapsed'}`} data-block-id={blockId}>
            <div className="code-header">
                <strong>CODE</strong>
                <span className="code-line-count">{codeLines} lines</span>
                <Button
                    variant="outline-secondary"
                    size="sm"
                    className="expand-code-btn"
                    onClick={() => onToggleExpand(blockId)}
                    aria-expanded={isExpanded}
                >
                    {isExpanded ? '▲' : '▼'}
                </Button>
            </div>
            {isExpanded && (
                <div className="code-full">
                    <SyntaxHighlighter language="python" style={github} showLineNumbers>
                        {code || ''}
                    </SyntaxHighlighter>
                </div>
            )}
        </div>
    );
};

export default React.memo(CodeBlock); // Memoize for performance