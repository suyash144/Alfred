// src/components/FiguresDisplay.js
import React from 'react';
import Card from 'react-bootstrap/Card';
import Collapse from 'react-bootstrap/Collapse';

const FiguresDisplay = ({ figures = [], onImageClick }) => {
     const hasFigures = figures && figures.length > 0;

    return (
        <Collapse in={hasFigures}>
             <div id="figures-container"> {/* Needed for Collapse */}
                {figures.map((figure, index) => (
                    <Card key={index} className="figure-container mb-3">
                        <Card.Body>
                            <Card.Title as="h5">Figure {index + 1}</Card.Title>
                            <img
                                src={`data:image/png;base64,${figure.data}`}
                                alt={`Generated Figure ${index + 1}`}
                                className="figure-image expandable-image img-fluid" // Use img-fluid for responsiveness
                                onClick={() => onImageClick(`data:image/png;base64,${figure.data}`)}
                                style={{ cursor: 'pointer', border: '1px solid #ddd', borderRadius: '4px', padding: '5px' }}
                            />
                        </Card.Body>
                    </Card>
                ))}
            </div>
        </Collapse>
    );
};

export default FiguresDisplay;