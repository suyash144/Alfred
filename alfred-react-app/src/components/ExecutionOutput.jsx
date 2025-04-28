// src/components/ExecutionOutput.js
import React from 'react';
import Collapse from 'react-bootstrap/Collapse';

const ExecutionOutput = ({ output }) => {
    const hasOutput = Boolean(output);

    return (
        <Collapse in={hasOutput}>
             <div id="output-section"> {/* Needed for Collapse */}
                <h4>Execution Output</h4>
                <pre id="output-content" className="p-3 border rounded bg-light" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {output}
                </pre>
            </div>
        </Collapse>
    );
};

export default ExecutionOutput;