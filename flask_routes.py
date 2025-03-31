from flask import Flask, render_template, request, jsonify, send_file
import os
import numpy as np
import pandas as pd
import json
import multiprocessing
import time
import threading
from werkzeug.utils import secure_filename
from utils import *
from data_loader import *

###############################################################################
# Flask routes
###############################################################################
app = Flask(__name__)

logger.info("Click here to run Alfred: http://localhost:5000")

# Configure upload settings
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'npy', 'json'}

# Global variables
active_executions = {}
execution_results = {}
iteration_count = 0

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    """Check if a filename has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Render the main index page"""
    global conversation_history
    # Format conversation history for display
    formatted_history = []
    for entry in conversation_history:
        role = entry.get("role", "")
        content = entry.get("content", "")

        if role == "figure":
            # Handle figure entries differently
            if isinstance(content, dict) and "image_url" in content:
                logger.debug("Found figure with image_url in conversation history")
            else:
                logger.warning(f"Unexpected figure content structure: {content}")
                
            image_url = content.get("image_url", {}).get("url", "")
            formatted_history.append({
                "role": "figure",
                "type": "figure",
                "iteration": entry.get("iteration", 0),
                "content": image_url
            })
        else:
            # Handle text entries as before
            formatted_history.append({
                "role": role,
                "type": entry.get("type", "text"),
                "iteration": entry.get("iteration", 0),
                "content": content
            })
    
    return render_template('index.html', 
                          conversation_history=formatted_history)

@app.route('/initialize', methods=['POST'])
def init_data():
    """Initialize dataset either with auto-generated data or user uploaded files"""
    global conversation_history
    global iteration_count

    conversation_history = []
    iteration_count = 0
    
    if not os.getenv('API_KEY'):
        logger.error("API_KEY not found in environment variables")
        return jsonify({
            "status": "error", 
            "message": "API_KEY not found in environment variables. Please set this in order to use this tool."
        })
    
    # Check which data source is being used
    data_source = request.form.get('dataSource', 'auto')
    logger.info(f"Initialising with data source: {data_source}")
    
    if data_source == 'auto':
        # Use the default auto-generated data
        result, data_inv = initialize_data()
        conversation_history.append({
            "role": "assistant",
            "type": "text",
            "iteration": iteration_count,
            "content": data_inv
        })
        return jsonify({"status": "success", "message": result})
    
    elif data_source == 'custom':
        # Handle custom data upload
        file_count = int(request.form.get('fileCount', 0))
        
        if file_count == 0:
            logger.warning("No files were uploaded")
            return jsonify({"status": "error", "message": "No files were uploaded"})
        
        uploaded_files = []
        file_info = []
        
        # Process each uploaded file
        for i in range(file_count):
            file_key = f'dataFile_{i}'
            if file_key not in request.files:
                continue
            
            file = request.files[file_key]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                
                # Create a temporary file path
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                
                uploaded_files.append(file_path)
                file_info.append({
                    'name': filename,
                    'path': file_path,
                    'type': filename.rsplit('.', 1)[1].lower()
                })
        
        if not uploaded_files:
            logger.warning("No valid files were uploaded")
            return jsonify({
                "status": "error", 
                "message": "No valid files were uploaded. Please upload .csv, .json or .npy files."
            })
        
        # Process the uploaded files
        result = process_uploaded_files(file_info)
        
        # Check if a custom prompt was provided
        custom_prompt = request.form.get('customPrompt', '')
        if custom_prompt:
            logger.info("Custom prompt provided")
            # Add the custom prompt as the first user prompt.
            conversation_history.append({
                "role": "user",
                "type": "text",
                "iteration": iteration_count,
                "content": custom_prompt
            })
        
        return jsonify({
            "status": "success", 
            "message": f"Successfully processed {len(uploaded_files)} custom data file(s)"
        })
    
    else:
        logger.error(f"Invalid data source specified: {data_source}")
        return jsonify({"status": "error", "message": "Invalid data source specified"})

def process_uploaded_files(file_info):
    """Process uploaded files and store them in the analysis_namespace"""
    global conversation_history
    global analysis_namespace
    
    # Clear any existing 'x' data to avoid confusion
    if 'x' in analysis_namespace:
        del analysis_namespace['x']
    
    processed_files = []
    
    for file in file_info:
        file_path = file['path']
        file_type = file['type']
        base_name = os.path.basename(file_path).rsplit('.', 1)[0]
        
        try:
            if file_type == 'csv':
                # Load CSV file into a pandas DataFrame
                df = pd.read_csv(file_path)
                var_name = f'df_{base_name}'
                analysis_namespace[var_name] = df
                processed_files.append((var_name, f"DataFrame with shape {df.shape}"))
                logger.info(f"Loaded CSV file: {file_path} as {var_name}")
                
            elif file_type == 'npy':
                # Load NumPy array
                arr = np.load(file_path)
                var_name = f'arr_{base_name}'
                analysis_namespace[var_name] = arr
                processed_files.append((var_name, f"NumPy array with shape {arr.shape}"))
                logger.info(f"Loaded NumPy file: {file_path} as {var_name}")

            elif file_type == 'json':
                with open(file_path) as f:
                    jsonfile = json.load(f)
                var_name = f'json_{base_name}'
                analysis_namespace[var_name] = jsonfile
                if type(jsonfile) is list:
                    processed_files.append((var_name, f"List from JSON file"))
                elif type(jsonfile) is dict:
                    processed_files.append((var_name, f"Dictionary from JSON file"))
                else:
                    processed_files.append((var_name, f"Python object (not list or dict) loaded from a JSON file"))
                logger.info(f"Loaded JSON file: {file_path} as {var_name}")
                
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            continue
    
    # Create a data inventory message for the conversation history
    data_inventory = "Available data variables:\n"
    for var_name, description in processed_files:
        data_inventory += f"- {var_name}: {description}\n"
        
    # Add this inventory to the conversation history
    conversation_history.append({
        "role": "assistant",
        "type": "text",
        "iteration": iteration_count,
        "content": data_inventory
    })
    
    logger.info(f"Processed {len(processed_files)} files successfully")
    return f"Successfully loaded {len(file_info)} file(s). Data inventory added to conversation."

@app.route('/get_analysis', methods=['GET'])
def get_analysis():
    """Get analysis from LLM based on conversation history"""
    global conversation_history
    global iteration_count
    logger.info(f"Getting analysis with conversation history length: {len(conversation_history)}")

    try:
        # Get the appropriate client based on model specified in environment
        if os.getenv('MODEL', default=None):
            client = get_client(os.environ.get('MODEL'))
            model_name = os.environ.get('MODEL')
            if model_name == "o1":
                logger.info("Using model: o1 (Note: Better but slower than GPT-4o)")
            elif model_name == "claude":
                logger.info("Using model: Claude 3.7 Sonnet (Note: Best responses)")
            elif model_name == "gemini":
                logger.info("Using model: Gemini 2.5 Pro (Note: Free but limited token rate)")
            elif model_name == "4o":
                logger.info("Using model: GPT-4o (Note: Cheapest per token)")
        else:
            model_name = "gemini"
            client = get_client(model_name)
            logger.info("Using default model: Gemini 2.5 Pro")
        
        # Build prompt and call LLM
        prompt = build_llm_prompt(conversation_history)
        llm_response = call_llm_and_parse(client, prompt)

        iteration_count += 1
        
        logger.info(f"Successfully got analysis from {model_name}")
        return jsonify({
            "status": "success",
            "summary": llm_response.text_summary,
            "code": llm_response.python_code,
            "conversation_length": len(conversation_history)
        })
    
    except Exception as e:
        # Separately handle errors stemming from API providers.
        if model_name == "claude":                                          # Anthropic API Error codes 
            if "Error code: 429" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "API rate limit exceeded. Please try again later."
                }), 429
            elif "Error code: 529" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "Anthropic API is temporarily overloaded. Please try again later."
                }), 529
            else:
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
                })
        else:                                                                # OpenAI API Error codes
            if "429" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "API rate limit or token quota exceeded. Please try again later."
                }), 429
            elif "403" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "You are in an unsupported region to access the OpenAI API."
                }), 403
            elif "401" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "API authentication failed. Please check your API key."
                }), 401
            elif "500" in str(e) or "503" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "OpenAI servers are currently overloaded or experiencing issues. Please try again later."
                }), 500
            else:
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
                })

@app.route('/execute_code', methods=['POST'])
def execute_code():
    """Execute Python code in a separate process and capture outputs/figures"""
    global conversation_history
    global active_executions
    global execution_results
    global analysis_namespace
    
    code = request.json.get('code', '')
    summary = request.json.get('summary', '')
    execution_id = request.json.get('execution_id')
    
    if not execution_id:
        execution_id = str(time.time())  # Generate an ID if not provided
    
    logger.info(f"Starting code execution with ID: {execution_id}")
    
    # First, add the summary and proposed code to conversation history
    conversation_history.append({
        "role": "assistant", 
        "type": "text",
        "iteration": iteration_count,
        "content": summary
    })
    
    conversation_history.append({
        "role": "assistant",
        "type": "code",
        "iteration": iteration_count,
        "content": "Proposed code:\n" + code
    })
    
    # Add execution record to history
    conversation_history.append({
        "role": "user",
        "type": "text",
        "iteration": iteration_count,
        "content": "Execute code"
    })
    
    # Initialize result storage
    execution_results[execution_id] = {
        'status': 'running',
        'output': '',
        'figures': [],
        'error': False,
        'complete': False
    }
    
    # Create a pipe for communication
    parent_conn, child_conn = multiprocessing.Pipe()
    
    # Create and start the process
    process = multiprocessing.Process(
        target=run_code_in_process,
        args=(code, analysis_namespace, child_conn)
    )
    
    # Store the process and connection for potential cancellation
    active_executions[execution_id] = {
        'process': process,
        'connection': parent_conn,
        'start_time': time.time()
    }
    
    # Start the process
    process.start()
    
    # Set up a background thread to handle long-running code execution
    def process_execution_results():
        try:
            # Wait for results with a timeout
            if parent_conn.poll(600.0):  # 600 second timeout
                output_text, figures, _, had_error, new_namespace = parent_conn.recv()

                # Update analysis namespace
                analysis_namespace.update(dill.loads(new_namespace))
                
                # Check if execution was terminated
                if output_text == "TERMINATED":
                    logger.info(f"Execution {execution_id} was terminated")
                    execution_results[execution_id]['status'] = 'cancelled'
                    execution_results[execution_id]['output'] = "Execution was cancelled by user."
                    execution_results[execution_id]['complete'] = True
                    return
                
                # Process figures if any
                figure_data = []
                for i, fig in enumerate(figures or []):
                    img_str = fig_to_base64(fig)
                    figure_data.append({
                        "id": i,
                        "data": img_str
                    })
                    
                    # Add figure to conversation history
                    title = fig._suptitle.get_text() if hasattr(fig, '_suptitle') and fig._suptitle else f"Figure {i+1}"
                    logger.info(f"Generated figure: {title}")
                    
                    conversation_history.append({
                        "role": "figure",
                        "type": "figure",
                        "iteration": iteration_count,
                        "content": {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_str}",
                            },
                        }
                    })
                
                # Store the results for retrieval
                execution_results[execution_id]['status'] = 'completed'
                execution_results[execution_id]['output'] = output_text
                execution_results[execution_id]['figures'] = figure_data
                execution_results[execution_id]['error'] = had_error
                execution_results[execution_id]['complete'] = True
                
                # Add output to conversation history if it exists
                if had_error:
                    logger.warning(f"Execution {execution_id} resulted in error")
                    conversation_history.append({
                        "role": "assistant",
                        "type": "output",
                        "iteration": iteration_count,
                        "content": "Error while running code:\n" + output_text
                    })
                elif output_text.strip():
                    conversation_history.append({
                        "role": "assistant",
                        "type": "output",
                        "iteration": iteration_count,
                        "content": "Code Output:\n" + output_text
                    })
                
            else:
                # Timeout occurred
                logger.warning(f"Execution {execution_id} timed out")
                output_text = "Execution timed out after 5 minutes. Consider optimizing your code or using smaller datasets."
                
                execution_results[execution_id]['status'] = 'timeout'
                execution_results[execution_id]['output'] = output_text
                execution_results[execution_id]['error'] = True
                execution_results[execution_id]['complete'] = True
                
                conversation_history.append({
                    "role": "assistant",
                    "type": "output",
                    "iteration": iteration_count,
                    "content": "Execution timed out:\n" + output_text
                })
        except Exception as e:
            logger.error(f"Error processing execution results: {str(e)}")
            output_text = f"Error during execution: {str(e)}"
            
            execution_results[execution_id]['status'] = 'error'
            execution_results[execution_id]['output'] = output_text
            execution_results[execution_id]['error'] = True
            execution_results[execution_id]['complete'] = True
            
            conversation_history.append({
                "role": "assistant",
                "type": "output",
                "iteration": iteration_count,
                "content": f"Execution error:\n{output_text}"
            })
        finally:
            # Clean up the process
            if execution_id in active_executions:
                if active_executions[execution_id]['process'].is_alive():
                    active_executions[execution_id]['process'].terminate()
                del active_executions[execution_id]
    
    # Start background thread for monitoring
    thread = threading.Thread(target=process_execution_results)
    thread.daemon = True
    thread.start()
    
    # Return immediately with a status that execution has started
    return jsonify({
        "status": "executing",
        "message": "Code execution started",
        "execution_id": execution_id
    })

@app.route('/execution_results/<execution_id>', methods=['GET'])
def get_execution_results(execution_id):
    """Get the results of a code execution"""
    global execution_results
    
    if execution_id not in execution_results:
        return jsonify({
            "status": "not_found",
            "message": "No results found for this execution ID"
        }), 404
    
    result = execution_results[execution_id]
    
    # If execution is complete, we can clean up the results data after sending
    if result['complete'] and result['status'] != 'running':
        # Clone the result for response
        response_data = dict(result)
        
        # Clean up old results periodically (keep the last few)
        all_executions = list(execution_results.keys())
        if len(all_executions) > 10:  # Keep only last 10 results
            oldest = all_executions[0]
            if oldest != execution_id:  # Don't delete what we're returning
                del execution_results[oldest]
        
        return jsonify({
            "status": result['status'],
            "output": result['output'],
            "figures": result['figures'],
            "error": result['error'],
            "complete": True
        })
    
    return jsonify({
        "status": result['status'],
        "complete": result['complete']
    })

@app.route('/stop_execution', methods=['POST'])
def stop_execution():
    """Stop a running code execution"""
    global active_executions
    global execution_results
    
    execution_id = request.json.get('execution_id')
    
    if not execution_id or execution_id not in active_executions:
        logger.warning(f"Attempt to stop non-existent execution: {execution_id}")
        return jsonify({
            "status": "error",
            "message": "No such execution found"
        }), 404
    
    logger.info(f"Stopping execution: {execution_id}")
    
    try:
        # Get the process
        execution = active_executions[execution_id]
        process = execution['process']
        
        # Update execution result status
        if execution_id in execution_results:
            execution_results[execution_id]['status'] = 'cancelled'
            execution_results[execution_id]['output'] = "Execution was cancelled by user."
            execution_results[execution_id]['complete'] = True
        
        # Terminate the process if it's still running
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
            
            # If it didn't terminate, try to kill it
            if process.is_alive():
                logger.warning(f"Process {execution_id} did not terminate gracefully, forcing kill")
                os.kill(process.pid, signal.SIGKILL)
        
        # Add to conversation history
        conversation_history.append({
            "role": "assistant",
            "type": "output",
            "iteration": iteration_count,
            "content": "Code execution was cancelled by user."
        })
        
        # Clean up
        del active_executions[execution_id]
        
        return jsonify({
            "status": "cancelled",
            "message": "Execution cancelled successfully"
        })
        
    except Exception as e:
        logger.error(f"Error stopping execution {execution_id}: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error stopping execution: {str(e)}"
        }), 500

@app.route('/debug/history', methods=['GET'])
def debug_history():
    """Debug endpoint to get the full conversation history"""
    global conversation_history
    
    logger.debug(f"Debug History Endpoint - History length: {len(conversation_history)}")
    
    # Format conversation history for JSON response
    formatted_history = []
    for entry in conversation_history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        type = entry.get("type", "text")

        if role == "figure":
            # Handle figure entries differently
            if isinstance(content, dict) and "image_url" in content:
                pass
            else:
                logger.warning(f"Unexpected content structure: {content}")
                
            image_url = content.get("image_url", {}).get("url", "")
            formatted_history.append({
                "role": "figure",
                "type": "figure",
                "iteration": entry.get("iteration", 0),
                "content": image_url
            })
        elif type == "code":
            formatted_history.append({
                "role": role,
                "type": entry.get("type", "code"),
                "iteration": entry.get("iteration", 0),
                "content": content
            })
        elif type == "output":
            if content.startswith("Code Output:"):
                content = content.replace("\n", "<br>")
            formatted_history.append({
                "role": role,
                "type": entry.get("type", "output"),
                "iteration": entry.get("iteration", 0),
                "content": content
            })
        else:
            # Handle text entries as before
            formatted_history.append({
                "role": role,
                "type": entry.get("type", "text"),
                "iteration": entry.get("iteration", 0),
                "content": content.replace("\n", "<br>") if isinstance(content, str) else content
            })
    
    return jsonify({
        "history_length": len(conversation_history),
        "history": formatted_history
    })

@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    """Send user feedback and get next analysis"""
    global conversation_history
    global iteration_count

    feedback = request.json.get('feedback', '')
    summary = request.json.get('summary', '')
    code = request.json.get('code', '')
    iter = request.json.get('iteration', 0)
    
    logger.info(f"Feedback route - Current history length: {len(conversation_history)}")
    
    # Add to conversation history
    conversation_history.append({
        "role": "assistant",
        "type": "text",
        "iteration": iter,
        "content": summary
    })
    conversation_history.append({
        "role": "assistant",
        "type": "code",
        "iteration": iter,
        "content": "Proposed code:\n" + code
    })
    conversation_history.append({
        "role": "user",
        "type": "text",
        "iteration": iter,
        "content": feedback
    })
    
    logger.debug(f"Feedback route - Updated history length: {len(conversation_history)}")
    
    # Now automatically get the next analysis
    try:
        if os.getenv('MODEL', default=None):
            client = get_client(os.environ.get('MODEL'))
        else:
            client = get_client("gemini")
        
        prompt = build_llm_prompt(conversation_history)
        llm_response = call_llm_and_parse(client, prompt)

        iteration_count += 1
        
        logger.info("Successfully got next analysis after feedback")
        
        # Return both the success status and the new analysis
        return jsonify({
            "status": "success", 
            "history_length": len(conversation_history),
            "next_analysis": {
                "summary": llm_response.text_summary,
                "code": llm_response.python_code
            }
        })
    except Exception as e:
        logger.error(f"Error getting next analysis after feedback: {str(e)}")
        # If there's an error getting the next analysis, still return success for the feedback
        return jsonify({
            "status": "success", 
            "history_length": len(conversation_history),
            "error": str(e)
        })
