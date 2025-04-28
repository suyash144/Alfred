// src/api.js
import axios from 'axios';

const API_BASE_URL = ''; // Your Flask backend URL, often '/' if served together

// Utility to handle errors
const handleApiError = (error, defaultMessage) => {
    console.error(`${defaultMessage}:`, error);
    const message = error.response?.data?.message || error.message || defaultMessage;
    alert(`${defaultMessage}: ${message}`);
    return { status: 'error', message };
};

export const initializeApi = async (formData) => {
    try {
        const response = await axios.post(`${API_BASE_URL}/initialize`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        });
        return { status: 'success', data: response.data };
    } catch (error) {
        return handleApiError(error, 'Error initialising data');
    }
};

export const getAnalysisApi = async (responseType) => {
    try {
        const response = await axios.get(`${API_BASE_URL}/get_analysis`, {
            params: { response_type: responseType },
        });
        return { status: 'success', data: response.data };
    } catch (error) {
        return handleApiError(error, 'Error getting analysis');
    }
};

export const executeCodeApi = async (code, summary, executionId) => {
     try {
        const response = await axios.post(`${API_BASE_URL}/execute_code`, {
            code,
            summary,
            execution_id: executionId
        });
        return { status: 'success', data: response.data };
    } catch (error) {
        return handleApiError(error, 'Error starting code execution');
    }
};

export const pollExecutionResultsApi = async (executionId) => {
    try {
        const response = await axios.get(`${API_BASE_URL}/execution_results/${executionId}`);
        // Don't pop alert on normal polling errors (e.g., 404 before ready)
        if (response.status >= 400) {
            console.warn(`Polling error for ${executionId}: ${response.status}`);
             return { status: 'pending' }; // Indicate still pending or error
        }
        return { status: 'success', data: response.data };
    } catch (error) {
         // Only log polling errors, don't alert
         console.warn(`Polling failed for ${executionId}:`, error.message);
         return { status: 'pending' }; // Treat errors as potentially temporary
    }
};


export const stopExecutionApi = async (executionId) => {
    try {
        const response = await axios.post(`${API_BASE_URL}/stop_execution`, { execution_id: executionId });
        return { status: 'success', data: response.data };
    } catch (error) {
        return handleApiError(error, 'Error stopping execution');
    }
};

export const sendFeedbackApi = async (feedback, summary, code) => {
    try {
        const response = await axios.post(`${API_BASE_URL}/send_feedback`, { feedback, summary, code });
        return { status: 'success', data: response.data };
    } catch (error) {
        return handleApiError(error, 'Error sending feedback');
    }
};

export const getHistoryApi = async () => {
    try {
        const response = await axios.get(`${API_BASE_URL}/debug/history`);
        return { status: 'success', data: response.data };
    } catch (error) {
        // Don't alert on history refresh errors, just log
        console.error("Error refreshing history:", error);
        return { status: 'error', message: 'Failed to fetch history' };
    }
};

export const saveAnalysisApi = async (historyData) => {
    try {
        const response = await axios.post(`${API_BASE_URL}/save_analysis`, historyData);
        return { status: 'success', data: response.data };
    } catch (error) {
        return handleApiError(error, 'Error saving analysis');
    }
};