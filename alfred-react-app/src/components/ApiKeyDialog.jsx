// src/components/ApiKeyDialog.jsx
import React, { useState } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Form from 'react-bootstrap/Form';
import Alert from 'react-bootstrap/Alert';

const ApiKeyDialog = ({ show, onClose, onSubmit, modelName, errorMessage }) => {
  const [apiKey, setApiKey] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState('');

  const handleSubmit = async () => {
    if (!apiKey.trim()) {
      setValidationError('Please enter a valid API key');
      return;
    }

    setIsSubmitting(true);
    setValidationError('');
    
    try {
      await onSubmit(apiKey);
      console.log('API key submitted successfully. Closing dialog.');
      onClose();
    } catch (error) {
      setValidationError(error.message || 'Invalid API key. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
  };

  const getModelDisplayName = () => {
    const modelMap = {
      'gemini': 'Gemini 2.5 Pro',
      'claude': 'Claude 3.7 Sonnet',
      'o1': 'o1',
      'gpt': 'GPT-4.1'
    };
    return modelMap[modelName] || modelName;
  };

  return (
    <Modal show={show} onHide={onClose} centered>
      <Modal.Header closeButton>
        <Modal.Title>API Key Required</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p>
          Please enter your API key for <strong>{getModelDisplayName()}</strong> to continue.
        </p>
        
        <Form.Group className="mb-3">
          <Form.Label>API Key</Form.Label>
          <Form.Control 
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter the API key for your chosen model"
            autoFocus
          />
          <Form.Text className="text-muted">
            Your API key will only be used for this analysis session.
          </Form.Text>
        </Form.Group>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button 
          variant="primary" 
          onClick={handleSubmit}
          disabled={isSubmitting}
        >
          {'Submit'}
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default ApiKeyDialog;
