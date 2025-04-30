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
    stopExecutionApi, sendFeedbackApi, getHistoryApi, saveAnalysisApi, switchModelApi
} from './api';

// Import Components
import ApiConfig from './components/ApiConfig';
import DataSourceSelector from './components/DataSourceSelector';
import ChatLog from './components/Chatlog.jsx';
import ChatInputArea from './components/ChatInputArea';
import ModelSwitcherModal from './components/ModelSwitcherModal';
// import CurrentAnalysis from './components/CurrentAnalysis';
// import ExecutionOutput from './components/ExecutionOutput';
// import FiguresDisplay from './components/FiguresDisplay';
import ImageModal from './components/ImageModal';

// Import CSS
import './App.css';
import './components/ChatLog.css';

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

    const [buttonState, setButtonState] = useState('analyse'); // 'analyse', 'stop'
    const [executionId, setExecutionId] = useState(null);
    const [codeExecutionInProgress, setCodeExecutionInProgress] = useState(false);

    const [showImageModal, setShowImageModal] = useState(false);
    const [modalImageSrc, setModalImageSrc] = useState('');

    const [expandedCodeBlocks, setExpandedCodeBlocks] = useState(new Set());

    const [showModelSwitcher, setShowModelSwitcher] = useState(false);

    const [saveStatus, setSaveStatus] = useState({ message: '', type: '' }); // For save analysis feedback

    // Refs for intervals
    const pollIntervalRef = useRef(null);
    const historyIntervalRef = useRef(null);

    // --- Helper Functions ---
    const clearExecutionState = () => {
        setCodeExecutionInProgress(false);
        setExecutionId(null);
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    };

    const resetUIState = useCallback(() => {
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
    }, [clearExecutionState]);

    const updateLoading = (loading, status = '') => {
        setIsLoading(loading);
        setProcessingStatus(status);
    };

     const fetchHistory = useCallback(async () => {
        const response = await getHistoryApi();
        if (response.status === 'success' && response.data?.history) {
            // Only update if content differs to avoid unnecessary re-renders
            if (history.length !== response.data.history.length || JSON.stringify(history) !== JSON.stringify(response.data.history)) {
                setHistory(response.data.history);
            }
        }
    }, [isLoading, history]);

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
                         await fetchHistory();

                         console.log(`Execution output: ${output}`);
                         console.log("History after execution:", history);

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
    }, [codeExecutionInProgress, executionId, fetchHistory]);

    // --- Event Handlers ---

    const handleInitialize = useCallback(async () => {
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

        updateLoading(true, 'Initialising...');

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
            alert('Initialisation succeeded, but failed to get AI analysis. Please try a different model.');
        }
        updateLoading(false);
    }, [isInitialized, resetUIState, dataSource, selectedFiles, apiKey, selectedModel, useCustomPrompt, customPromptText, promptFile, fetchHistory]);

    const handleActionClick = useCallback(async () => {
        if (buttonState === 'stop') {
            // --- Stop Execution ---
            if (!codeExecutionInProgress || !executionId) return;
            updateLoading(true, 'Stopping execution...');
            const stopResponse = await stopExecutionApi(executionId);
            // Clear polling and reset state regardless of success/failure stopping
            clearExecutionState();
            setButtonState('analyse'); // Ready to try again
            updateLoading(false);
            await fetchHistory(); // Refresh history after stopping
        } else if (buttonState === 'analyse') {
            // 1. Get the Code first
            updateLoading(true, 'Generating code...');
            const codeAnalysisResponse = await getAnalysisApi('code');

            // Fetch history immediately to show the code bubble
            await fetchHistory();

            if (codeAnalysisResponse.status === 'success' && codeAnalysisResponse.data?.response) {
                const codeToExecute = codeAnalysisResponse.data.response;
                const newExecutionId = Date.now().toString();
                setExecutionId(newExecutionId);

                // 2. Execute the Code (Execution results/output/figures added later via polling/history)
                updateLoading(true, 'Executing code...');
                const executeResponse = await executeCodeApi(codeToExecute, newExecutionId); // Pass summary if needed

                if (executeResponse.status === 'success') {
                    setCodeExecutionInProgress(true); // Start polling for results
                    setButtonState('stop');
                } else {
                    // Failed to start execution
                    clearExecutionState();
                    setButtonState('analyse');
                    updateLoading(false);
                    // Fetch history again in case backend added an error message during failed exec start
                    await fetchHistory();
                }
            } else {
                // Failed to get code
                updateLoading(false);
                setButtonState('analyse'); // Allow retry
                // Fetch history in case backend added an error message
                await fetchHistory();
            }
            await fetchHistory();
        }
    }, [buttonState, codeExecutionInProgress, executionId, clearExecutionState, fetchHistory, currentSummary]);

    const handleSendFeedback = useCallback(async () => {
        if (!feedbackInput.trim()) { alert('Please enter feedback.'); return; }
        updateLoading(true, 'Loading...');
        // Backend adds feedback to history
        const response = await sendFeedbackApi(feedbackInput, currentSummary);

        if (response.status === 'success') {
            // The response might contain the next text analysis, but we rely on fetchHistory
            setFeedbackInput('');
            setButtonState('analyse'); // Ready for next code gen/execution step
        } else {
            setFeedbackInput(currentInput);
        }
        updateLoading(false);
        await fetchHistory(); // Refresh history to show feedback and the new text analysis
    }, [feedbackInput, currentSummary, fetchHistory]);

    const handleSwitchModel = useCallback(() => {
        setShowModelSwitcher(true);
    }, []);

    const handleSelectModel = useCallback(async (modelId) => {
        if (modelId === selectedModel) {
            setShowModelSwitcher(false);
            return; // No change needed
        }

        let cleanName = '';
        let backendName = '';

        if (modelId === 'o1'){
            cleanName = 'o1';
            backendName = 'o1';
        } else if (modelId === 'gpt4o'){
            cleanName = 'GPT-4o';
            backendName = '4o';
        } else if (modelId === 'claude'){
            cleanName = 'Claude 3.7 Sonnet';
            backendName = 'claude';
        } else if (modelId === 'gemini'){
            cleanName = 'Gemini 2.5 Pro';
            backendName = 'gemini';
        }
        
        updateLoading(true, 'Switching model...');
        setShowModelSwitcher(false);
        
        // Update the selected model
        setSelectedModel(modelId);
        
        try {
            await switchModelApi(backendName); // Call the API to switch model
            updateLoading(false);
        } catch (error) {
            console.error('Error switching model:', error);
            alert('Failed to switch model. Please try again.');
            updateLoading(false);
        }
    }, [selectedModel]);

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

    const handleSaveAnalysis = useCallback(async () => {
        setSaveStatus({ message: 'Preparing data...', type: 'info' });
        const response = await saveAnalysisApi({ history: history }); // Send the raw history

         if (response.status === 'success' && response.data?.download_url) {
            setSaveStatus({ message: 'Success! Starting download...', type: 'success' });
            window.location.href = response.data.download_url; // Trigger download
            setTimeout(() => setSaveStatus({ message: '', type: '' }), 5000); // Clear after 5s
        } else {
            setSaveStatus({ message: response.message || 'Error saving analysis.', type: 'danger' });
        }
    }, [history]);


    return (
        <Container className="mt-4">
            <h1 className="mb-4">Alfred</h1>
            <Row className="mb-4">
                <Col>
                     <Collapse in={!isInitialized}>
                         <div>
                            <ApiConfig apiKey={apiKey} selectedModel={selectedModel} onApiKeyChange={setApiKey} onModelChange={setSelectedModel} isDisabled={isLoading} />
                            <DataSourceSelector dataSource={dataSource} selectedFiles={selectedFiles} useCustomPrompt={useCustomPrompt} customPromptText={customPromptText} onDataSourceChange={setDataSource} onFilesChange={setSelectedFiles} onUseCustomPromptChange={setUseCustomPrompt} onCustomPromptTextChange={setCustomPromptText} onPromptFileChange={setPromptFile} isDisabled={isLoading} />
                        </div>
                    </Collapse>

                    <div className="d-flex align-items-center mt-3">
                        <Button 
                            variant={isInitialized ? "danger" : "primary"} 
                            onClick={handleInitialize} 
                            disabled={isLoading}
                            className="me-3" // Add right margin for spacing
                        >
                            {isLoading && processingStatus.toLowerCase().includes('init') ? 
                                (<> <Spinner animation="border" size="sm" /> Initialising... </>) : 
                                (isInitialized ? 'Restart Analysis' : 'Initialise Dataset')}
                        </Button>
                        
                        {isInitialized && (
                            <Button 
                                variant="warning"
                                onClick={handleSwitchModel} 
                                disabled={isLoading}
                            >
                                Switch Model
                            </Button>
                        )}
                    </div>
                </Col>
            </Row>

            {/* Main Content Area*/}
            <Row>
                <Col> {/* Use full width */}
                    {/* Container for Chat Log and Input */}
                    {isInitialized && (
                        <div className="main-chat-container bg-white shadow-sm"> {/* Added classes */}
                            <ChatLog
                                // Pass the raw history array
                                history={history}
                                expandedCodeBlocks={expandedCodeBlocks}
                                onToggleCodeExpand={handleToggleCodeExpand}
                                onImageClick={handleImageClick}
                            />
                            <ChatInputArea
                                feedbackInput={feedbackInput}
                                onFeedbackChange={(e) => setFeedbackInput(e.target.value)} // Pass simple handler
                                onSendFeedback={handleSendFeedback}
                                buttonState={buttonState}
                                onActionClick={handleActionClick}
                                isLoading={isLoading}
                                isInitialized={isInitialized} // Pass for conditional render inside
                                processingStatus={processingStatus}
                            />
                        </div>
                    )}
                </Col>
            </Row>

            <Row className="mt-5 mb-4">
                <Col className="text-center">
                    <Button variant="primary" size="lg" onClick={handleSaveAnalysis} disabled={isLoading || !isInitialized || saveStatus.type === 'info'} id="save-analysis-btn">
                        {saveStatus.type === 'info' ? (<Spinner animation="border" size="sm" className="me-2" />) : (<i className="bi bi-download me-2"></i>)}
                        Save Analysis
                    </Button>
                     {saveStatus.message && (<Alert variant={saveStatus.type === 'info' ? 'secondary' : saveStatus.type} className="mt-2 d-inline-block py-1 px-3">{saveStatus.message}</Alert>)}
                </Col>
            </Row>

            <ModelSwitcherModal 
                show={showModelSwitcher}
                onClose={() => setShowModelSwitcher(false)}
                onSelectModel={handleSelectModel}
                currentModel={selectedModel}
            />
            <ImageModal show={showImageModal} src={modalImageSrc} onClose={() => setShowImageModal(false)} />
        </Container>
    );
}

export default App;