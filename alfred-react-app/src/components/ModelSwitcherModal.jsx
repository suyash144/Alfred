import React, {useState, useEffect} from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Card from 'react-bootstrap/Card';
import Row from 'react-bootstrap/Row';
import Col from 'react-bootstrap/Col';
import Badge from 'react-bootstrap/Badge';

const ModelSwitcherModal = ({ show, onClose, onSelectModel, currentModel }) => {

  const [selectedModelInModal, setSelectedModelInModal] = useState(currentModel);
  
  // Reset the selection when the modal opens
  useEffect(() => {
    if (show) {
      setSelectedModelInModal(currentModel);
    }
  }, [show, currentModel]);

  const models = [
    { id: 'gemini', name: 'Gemini 2.5 Pro', description: 'Google\'s advanced multimodal model' },
    { id: 'claude', name: 'Claude 3.7 Sonnet', description: 'Anthropic\'s balanced reasoning model' },
    { id: 'o1', name: 'o1', description: 'OpenAI\'s cutting-edge reasoning model' },
    { id: 'gpt', name: 'GPT-4.1', description: 'OpenAI\'s multimodal foundation model' }
  ];


  // Helper to get clean name for display
  const getCleanName = (modelId) => {
    const model = models.find(m => m.id === modelId);
    return model ? model.name : modelId;
  };

  const handleConfirm = () => {
    onSelectModel(selectedModelInModal);
  };
  
  // Check if the selected model is different from current
  const hasChanged = selectedModelInModal !== currentModel;

  return (
    <Modal show={show} onHide={onClose} size="lg" centered>
      <Modal.Header closeButton>
        <Modal.Title>Switch Model</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="mb-4">Select a model to continue your analysis</p>
        <Row className="g-4">
          {models.map((model) => (
            <Col md={6} key={model.id}>
              <Card 
                className={`h-100 ${selectedModelInModal === model.id ? 'border-primary' : ''}`}
                style={{  
                  cursor: 'pointer',
                  transition: 'all 0.2s ease-in-out',
                  transform: selectedModelInModal === model.id ? 'translateY(-5px)' : 'none',
                  boxShadow: selectedModelInModal === model.id ? '0 4px 8px rgba(0,0,0,0.1)' : 'none'
                }}
                onClick={() => setSelectedModelInModal(model.id)}
              >
                <Card.Body className="d-flex flex-column">
                  <div className="d-flex justify-content-between align-items-start mb-2">
                    {currentModel === model.id && (
                      <Badge bg="success" pill>Current</Badge>
                    )}
                  </div>
                  <div className="mt-auto">
                    <Button 
                      variant={selectedModelInModal === model.id ? "primary" : "outline-primary"} 
                      className="w-100"
                      onClick={() => setSelectedModelInModal(model.id)}
                    >
                      {model.name}
                    </Button>
                  </div>
                </Card.Body>
              </Card>
            </Col>
          ))}
        </Row>
      </Modal.Body>
      <Modal.Footer className="d-flex justify-content-between">
        <div>
          {hasChanged && (
            <p className="text-success mb-0">
              <i className="bi bi-check-circle me-2"></i>
              Switching to {getCleanName(selectedModelInModal)}
            </p>
          )}
        </div>
        <div>
          <Button variant="secondary" onClick={onClose} className="me-2">
            Cancel
          </Button>
          <Button 
            variant="warning" 
            onClick={handleConfirm} 
            disabled={!hasChanged}
            style={{ 
              opacity: hasChanged ? 1 : 0.5,
              transition: 'opacity 0.3s ease'
            }}
          >
            Select
          </Button>
        </div>
      </Modal.Footer>
    </Modal>
  );
};

export default ModelSwitcherModal;