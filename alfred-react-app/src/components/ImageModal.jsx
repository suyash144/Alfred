// src/components/ImageModal.js
import React, { useState } from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import { saveAs } from 'file-saver'; // npm install file-saver

const ImageModal = ({ show, src, onClose }) => {
    const [isDownloading, setIsDownloading] = useState(false);

    const handleDownload = async () => {
        if (!src || isDownloading) return;

        setIsDownloading(true);
        try {
            const filename = `figure_${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
            if (src.startsWith('data:image')) {
                 // Convert base64 to blob and save
                 const response = await fetch(src);
                 const blob = await response.blob();
                 saveAs(blob, filename);
            } else {
                 // Assume it's a direct URL (might have CORS issues if external)
                 saveAs(src, filename);
            }
        } catch (error) {
            console.error('Error downloading image:', error);
            alert('Failed to download image.');
        } finally {
            // Add a small delay so user sees the spinner
            setTimeout(() => setIsDownloading(false), 500);
        }
    };

    return (
        <Modal show={show} onHide={onClose} size="xl" centered dialogClassName="image-modal-dialog">
            <Modal.Header closeButton>
                <Modal.Title>Image Viewer</Modal.Title>
            </Modal.Header>
            <Modal.Body className="text-center p-0 bg-light">
                {src && <img id="modalImage" src={src} alt="Expanded figure" className="img-fluid" style={{ maxHeight: '85vh', objectFit: 'contain' }} />}
            </Modal.Body>
            <Modal.Footer className="justify-content-between">
                 <Button
                    variant="primary"
                    onClick={handleDownload}
                    disabled={isDownloading}
                    id="downloadImageBtn"
                 >
                    {isDownloading ? (
                        <>
                            <Spinner as="span" animation="border" size="sm" role="status" aria-hidden="true" className="me-1" />
                            Saving...
                        </>
                    ) : (
                         <>
                             <i className="bi bi-download me-1"></i> Save Image
                         </>
                    )}
                 </Button>
                <span className="image-info text-muted small me-auto ms-2">Click Save or Close</span>
                <Button variant="secondary" onClick={onClose}>
                    Close
                </Button>
            </Modal.Footer>
        </Modal>
    );
};

export default ImageModal;

// Add some CSS in index.css if needed for .image-modal-dialog
// .image-modal-dialog { max-width: 90vw !important; }