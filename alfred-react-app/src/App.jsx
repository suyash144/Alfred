// src/App.js
import React, { useState, useEffect, useCallback, useRef } from 'react';
import Container from 'react-bootstrap/Container';
import Row from 'react-bootstrap/Row';
import Col from 'react-bootstrap/Col';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import Collapse from 'react-bootstrap/Collapse';
import Alert from 'react-bootstrap/Alert'; // For save status
import './index.css'; // Your custom styles

// Import API functions
import {
    initializeApi, getAnalysisApi, executeCodeApi, pollExecutionResultsApi,
    stopExecutionApi, sendFeedbackApi, getHistoryApi, saveAnalysisApi
} from './api';

// Import Components
import ApiConfig from './components/ApiConfig';
import DataSourceSelector from './components/DataSourceSelector';
import HistoryPanel from './components/HistoryPanel';
import CurrentAnalysis from './components/CurrentAnalysis';
import ExecutionOutput from './components/ExecutionOutput';
import FiguresDisplay from './components/FiguresDisplay';
import ImageModal from './components/ImageModal';

// Import CSS
import './App.css'; // If you have custom App-specific styles

function App() {
    // --- State Variables ---
    const [apiKey, setApiKey] = useState('');
    const [selectedModel, setSelectedModel] = useState('gemini');
    const [dataSource, setDataSource] = useState('auto');
    const [selectedFiles, setSelectedFiles] = useState([]);
    const [useCustomPrompt, setUseCustomPrompt] = useState(false);
    const [customPromptText, setCustomPromptText] = useState('');
    const [promptFile, setPromptFile] = useState(null); // Store the File object

    const [isInitialized, setIsInitialized] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [processingStatus, setProcessingStatus] = useState('');

    const [history, setHistory] = useState([]); // Combined history
    const [currentSummary, setCurrentSummary] = useState('');
    // const [currentCode, setCurrentCode] = useState(''); // Maybe not needed if code is just in history? Re-add if needed.
    const [feedbackInput, setFeedbackInput] = useState('');
    const [executionOutput, setExecutionOutput] = useState('');
    const [currentFigures, setCurrentFigures] = useState([]); // Array of { data: base64string }

    const [buttonState, setButtonState] = useState('analyse'); // 'analyse', 'stop'
    const [executionId, setExecutionId] = useState(null);
    const [codeExecutionInProgress, setCodeExecutionInProgress] = useState(false);

    const [showImageModal, setShowImageModal] = useState(false);
    const [modalImageSrc, setModalImageSrc] = useState('');

    const [expandedCodeBlocks, setExpandedCodeBlocks] = useState(new Set());

    const [saveStatus, setSaveStatus] = useState({ message: '', type: '' }); // For save analysis feedback

    // Refs for intervals
    const pollIntervalRef = useRef(null);
    const historyIntervalRef = useRef(null);

    // --- Helper Functions ---
    const clearExecutionState = () => {
        setCodeExecutionInProgress(false);
        setExecutionId(null);
        setExecutionOutput('');
        setCurrentFigures([]);
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    };

    const resetUIState = () => {
        setIsInitialized(false);
        setIsLoading(false);
        setProcessingStatus('');
        setHistory([]);
        setCurrentSummary('');
        setFeedbackInput('');
        clearExecutionState();
        setButtonState('analyse');
        setExpandedCodeBlocks(new Set());
        setSaveStatus({ message: '', type: '' });
        // Keep API config, but reset data source/files
        // setDataSource('auto');
        // setSelectedFiles([]);
        // setUseCustomPrompt(false);
        // setCustomPromptText('');
        // setPromptFile(null);
    };

    const updateLoading = (loading, status = '') => {
        setIsLoading(loading);
        setProcessingStatus(status);
    };

     const fetchHistory = useCallback(async () => {
        if (isLoading || codeExecutionInProgress) return; // Don't refresh during critical ops
        const response = await getHistoryApi();
        if (response.status === 'success' && response.data?.history) {
            // Only update if content differs to avoid unnecessary re-renders
            if (JSON.stringify(history) !== JSON.stringify(response.data.history)) {
                 setHistory(response.data.history);
            }
        }
    }, [isLoading, codeExecutionInProgress, history]); // Add history to dependencies

    // --- Effects ---

    // History polling
    useEffect(() => {
        if (isInitialized) {
            // Initial fetch
            fetchHistory();

            // Set interval
            historyIntervalRef.current = setInterval(fetchHistory, 5000); // Poll every 5 seconds

            // Cleanup interval on component unmount or when isInitialized becomes false
            return () => {
                if (historyIntervalRef.current) {
                    clearInterval(historyIntervalRef.current);
                     historyIntervalRef.current = null;
                }
            };
        } else {
             // Clear interval if not initialized
             if (historyIntervalRef.current) {
                 clearInterval(historyIntervalRef.current);
                 historyIntervalRef.current = null;
             }
        }
    }, [isInitialized, fetchHistory]); // Re-run if isInitialized changes

     // Code execution polling
    useEffect(() => {
        if (codeExecutionInProgress && executionId) {
            pollIntervalRef.current = setInterval(async () => {
                console.log(`Polling for execution ID: ${executionId}`);
                const response = await pollExecutionResultsApi(executionId);

                 if (response.status === 'success' && response.data) {
                     const { complete, output, figures } = response.data;

                     if (complete) {
                         console.log(`Execution ${executionId} complete.`);
                         clearInterval(pollIntervalRef.current);
                         pollIntervalRef.current = null;
                         setCodeExecutionInProgress(false);
                         // Update output and figures *before* getting next analysis
                         setExecutionOutput(output || '');
                         setCurrentFigures(figures || []);
                         // Fetch history immediately to include output/figures
                         await fetchHistory();

                         // Now get the next text analysis
                         updateLoading(true, 'Analysing results...');
                         const analysisResponse = await getAnalysisApi('text');
                         if (analysisResponse.status === 'success' && analysisResponse.data.response) {
                            setCurrentSummary(analysisResponse.data.response);
                            setButtonState('analyse'); // Ready for next execution
                         } else {
                            // Handle error getting next analysis
                            setCurrentSummary(currentSummary + "\n\n(Error getting next analysis step)");
                            setButtonState('analyse'); // Allow retry
                         }
                         updateLoading(false);
                     } else {
                         // Still running, maybe update status?
                         setProcessingStatus('Executing code...'); // Keep status updated
                     }
                } else if (response.status === 'pending') {
                    // Still waiting, do nothing
                } else {
                     // Polling error or backend issue
                     console.error(`Polling error or invalid state for ${executionId}. Stopping poll.`);
                     alert('Error checking execution status. Please check the console.');
                     clearInterval(pollIntervalRef.current);
                     pollIntervalRef.current = null;
                     setCodeExecutionInProgress(false);
                     setButtonState('analyse'); // Allow user to retry
                     updateLoading(false);
                }
            }, 2000); // Poll every 2 seconds
        }

        // Cleanup function
        return () => {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
                pollIntervalRef.current = null;
            }
        };
    }, [codeExecutionInProgress, executionId, fetchHistory, currentSummary]); // Add dependencies

    // --- Event Handlers ---

    const handleInitialize = async () => {
        if (isInitialized) {
            if (!window.confirm("Are you sure you want to restart? This will clear the current analysis session.")) {
                return;
            }
            resetUIState(); // Reset everything before starting new init
            return;
        }

        if (dataSource === 'custom' && selectedFiles.length === 0) {
            alert('Please select files for custom data source.');
            return;
        }

        updateLoading(true, 'Initializing...');

        const formData = new FormData();
        formData.append('apiKey', apiKey); // Send API key securely if needed (consider backend env var first)
        formData.append('model', selectedModel);
        formData.append('dataSource', dataSource);

        if (dataSource === 'custom') {
            selectedFiles.forEach((file, index) => {
                formData.append(`dataFile_${index}`, file);
            });
            formData.append('fileCount', selectedFiles.length);
        }

        if (useCustomPrompt) {
            let finalCustomPrompt = customPromptText;
            if (promptFile) {
                // Prioritize file content if available (read it here)
                try {
                    finalCustomPrompt = await promptFile.text();
                } catch (e) {
                    alert('Error reading prompt file. Using typed prompt instead.');
                }
            }
             if (finalCustomPrompt) {
                 formData.append('customPrompt', finalCustomPrompt.trim());
            }
        }

        // 1. Initialize
        const initResponse = await initializeApi(formData);
        if (initResponse.status !== 'success') {
            updateLoading(false);
            // Error already alerted in api.js
            return;
        }

        // 2. Get first analysis
        updateLoading(true, 'Getting initial analysis...');
        const analysisResponse = await getAnalysisApi('text');
        if (analysisResponse.status === 'success' && analysisResponse.data?.response) {
            setCurrentSummary(analysisResponse.data.response);
            setIsInitialized(true);
            setButtonState('analyse'); // Ready for first execution
            await fetchHistory(); // Fetch initial history
        } else {
            // Handle error in getting first analysis
            resetUIState(); // Go back to uninitialized state on failure
            alert('Initialization succeeded, but failed to get initial analysis.');
        }
        updateLoading(false);
    };

    const handleActionClick = async () => {
        if (buttonState === 'stop') {
            // --- Stop Execution ---
            if (!codeExecutionInProgress || !executionId) return;
            updateLoading(true, 'Stopping execution...');
            const stopResponse = await stopExecutionApi(executionId);
            if (stopResponse.status === 'success') {
                 setExecutionOutput((prev) => prev + "\n\nExecution stopped by user.");
            }
            // Clear polling and reset state regardless of success/failure stopping
            clearExecutionState();
            setButtonState('analyse'); // Ready to try again
            updateLoading(false);
            await fetchHistory(); // Refresh history after stopping
        } else if (buttonState === 'analyse') {
            // --- Execute Code ---
            updateLoading(true, 'Generating code...');
            setExecutionOutput(''); // Clear previous output
            setCurrentFigures([]); // Clear previous figures

            const analysisResponse = await getAnalysisApi('code');
            if (analysisResponse.status === 'success' && analysisResponse.data?.response) {
                const codeToExecute = analysisResponse.data.response;
                // setCurrentCode(codeToExecute); // Store if needed

                const newExecutionId = Date.now().toString();
                setExecutionId(newExecutionId);

                updateLoading(true, 'Executing code...');
                const executeResponse = await executeCodeApi(codeToExecute, currentSummary, newExecutionId);

                if (executeResponse.status === 'success') {
                    setCodeExecutionInProgress(true); // Start polling
                    setButtonState('stop'); // Change button to Stop
                    // Loading state will be managed by polling effect
                } else {
                    // Failed to start execution
                    clearExecutionState();
                    setButtonState('analyse');
                    updateLoading(false);
                    // Error already alerted
                    await fetchHistory(); // Update history even on failure
                }
            } else {
                // Failed to get code
                updateLoading(false);
                // Error already alerted
            }
        }
    };

    const handleSendFeedback = async () => {
        if (!feedbackInput.trim()) {
            alert('Please enter feedback.');
            return;
        }
        updateLoading(true, 'Sending feedback...');
        setExecutionOutput(''); // Clear output/figures when feedback is sent
        setCurrentFigures([]);

        const response = await sendFeedbackApi(feedbackInput, currentSummary /*, currentCode */); // Pass code if needed

        if (response.status === 'success' && response.data?.response) {
            setCurrentSummary(response.data.response);
            setFeedbackInput(''); // Clear input
            setButtonState('analyse'); // Ready for next execution
        } else if (response.status === 'success') {
            // Feedback sent, but no next analysis?
             alert('Feedback sent, but no next analysis received.');
             setFeedbackInput('');
             setButtonState('analyse');
        } else {
             // Error sending feedback (already alerted)
             // Keep feedback text so user doesn't lose it
        }
        updateLoading(false);
        await fetchHistory(); // Refresh history
    };

    const handleImageClick = (src) => {
        setModalImageSrc(src);
        setShowImageModal(true);
    };

    const handleToggleCodeExpand = (blockId) => {
        setExpandedCodeBlocks(prev => {
            const newSet = new Set(prev);
            if (newSet.has(blockId)) {
                newSet.delete(blockId);
            } else {
                newSet.add(blockId);
            }
            return newSet;
        });
    };

    const handleSaveAnalysis = async () => {
        setSaveStatus({ message: 'Preparing data...', type: 'info' });
        // Use the current history state
        const historyData = {
            // Structure according to backend expectation
             // Example: Reformat if backend needs { text: [], code: [], ... }
             text: history.filter(e => e.type === 'text'),
             code: history.filter(e => e.type === 'code'),
             output: history.filter(e => e.type === 'output'),
             figures: history.filter(e => e.type === 'figure').map(e => ({ iteration: e.iteration, src: e.content })) // Adjust based on backend
        };

        const response = await saveAnalysisApi({ history: history }); // Send the raw history if backend processes it

         if (response.status === 'success' && response.data?.download_url) {
            setSaveStatus({ message: 'Success! Starting download...', type: 'success' });
            window.location.href = response.data.download_url; // Trigger download
            setTimeout(() => setSaveStatus({ message: '', type: '' }), 5000); // Clear after 5s
        } else {
            setSaveStatus({ message: response.message || 'Error saving analysis.', type: 'danger' });
        }
    };


    return (
        <Container fluid className="mt-4">
            <h1 className="mb-4">Alfred</h1>

            {/* Configuration and Initialization */}
            <Row className="mb-4">
                <Col>
                    {/* Show config only if not initialized */}
                     <Collapse in={!isInitialized}>
                         <div> {/* Required for Collapse */}
                            <ApiConfig
                                apiKey={apiKey}
                                selectedModel={selectedModel}
                                onApiKeyChange={setApiKey}
                                onModelChange={setSelectedModel}
                                isDisabled={isLoading}
                            />
                            <DataSourceSelector
                                dataSource={dataSource}
                                selectedFiles={selectedFiles}
                                useCustomPrompt={useCustomPrompt}
                                customPromptText={customPromptText}
                                onDataSourceChange={setDataSource}
                                onFilesChange={setSelectedFiles}
                                onUseCustomPromptChange={setUseCustomPrompt}
                                onCustomPromptTextChange={setCustomPromptText}
                                onPromptFileChange={setPromptFile}
                                isDisabled={isLoading}
                             />
                        </div>
                    </Collapse>

                    <Button
                        variant={isInitialized ? "danger" : "primary"}
                        onClick={handleInitialize}
                        disabled={isLoading}
                        className="mt-3"
                    >
                        {isLoading && processingStatus.toLowerCase().includes('init') ? (
                           <> <Spinner animation="border" size="sm" /> Initialising... </>
                        ) : (
                           isInitialized ? 'Restart Analysis' : 'Initialise Dataset'
                        )}
                    </Button>
                </Col>
            </Row>

            {/* Main Content Area */}
            <Row>
                {/* History Columns */}
                <Col md={6}>
                     <HistoryPanel
                        title="Conversation History"
                        history={history}
                        type="text"
                    />
                     <HistoryPanel
                        title="Code History"
                        history={history}
                        type="code"
                        expandedCodeBlocks={expandedCodeBlocks}
                        onToggleCodeExpand={handleToggleCodeExpand}
                    />
                     <HistoryPanel
                        title="Code Output History"
                        history={history}
                        type="output"
                    />
                     <HistoryPanel
                        title="Figure History"
                        history={history}
                        type="figure"
                        onImageClick={handleImageClick}
                    />
                </Col>

                {/* Current Analysis and Output */}
                <Col md={6}>
                    <CurrentAnalysis
                        summary={currentSummary}
                        buttonState={buttonState}
                        onActionClick={handleActionClick}
                        feedbackInput={feedbackInput}
                        onFeedbackChange={setFeedbackInput}
                        onSendFeedback={handleSendFeedback}
                        isLoading={isLoading}
                        processingStatus={processingStatus}
                        isInitialized={isInitialized}
                    />
                     <ExecutionOutput output={executionOutput} />
                     <FiguresDisplay figures={currentFigures} onImageClick={handleImageClick} />
                </Col>
            </Row>

             {/* Save Button */}
            <Row className="mt-5 mb-4">
                <Col className="text-center">
                    <Button
                        variant="primary"
                        size="lg"
                        onClick={handleSaveAnalysis}
                        disabled={isLoading || !isInitialized || saveStatus.type === 'info'}
                        id="save-analysis-btn"
                    >
                        {saveStatus.type === 'info' ? (
                           <Spinner animation="border" size="sm" className="me-2" />
                        ) : (
                           <i className="bi bi-download me-2"></i>
                        )}
                        Save Complete Analysis
                    </Button>
                     {saveStatus.message && (
                        <Alert variant={saveStatus.type === 'info' ? 'secondary' : saveStatus.type} className="mt-2 d-inline-block py-1 px-3" id="save-status">
                            {saveStatus.message}
                        </Alert>
                    )}
                </Col>
            </Row>


            {/* Image Modal */}
            <ImageModal
                show={showImageModal}
                src={modalImageSrc}
                onClose={() => setShowImageModal(false)}
            />
        </Container>
    );
}

export default App;