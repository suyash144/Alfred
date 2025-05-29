// src/components/ApiConfig.js
import React from 'react';
import Form from 'react-bootstrap/Form';
import Card from 'react-bootstrap/Card';

const ApiConfig = ({ apiKey, selectedModel, onApiKeyChange, onModelChange, isDisabled }) => {
    return (
        <Card className="mt-3 mb-3 p-3 bg-light">
            <Card.Body>
                <Card.Title as="h4">API Configuration</Card.Title>
                 <Form.Group className="mb-3" controlId="apiKey">
                    <Form.Label>API Key</Form.Label>
                    <Form.Control
                        type="password"
                        placeholder="Leave blank if using environment variable"
                        value={apiKey}
                        onChange={(e) => onApiKeyChange(e.target.value)}
                        disabled={isDisabled}
                    />
                    <Form.Text className="text-muted">
                        Stored in memory only for this session.
                    </Form.Text>
                </Form.Group>

                <Form.Group className="mb-3" controlId="modelSelect">
                    <Form.Label>Select Model</Form.Label>
                    <Form.Select
                        value={selectedModel}
                        onChange={(e) => onModelChange(e.target.value)}
                        disabled={isDisabled}
                    >
                        <option value="gemini">Gemini 2.5 Pro (Free, rate-limited)</option>
                        <option value="claude">Claude 4 Sonnet</option>
                        <option value="o1">OpenAI o1</option>
                        <option value="gpt">OpenAI GPT-4.1</option>
                    </Form.Select>
                </Form.Group>
            </Card.Body>
        </Card>
    );
};

export default ApiConfig;