from flask import Flask, render_template, request, jsonify, send_file
import os
import numpy as np
import pandas as pd
import json
import multiprocessing
import time
import threading
import datetime
import zipfile
from werkzeug.utils import secure_filename
from utils import *
from data_loader import *

###############################################################################
# Flask routes
###############################################################################
app = Flask(__name__)
app.state = AppState()

logger.info("Click here to run Alfred: http://localhost:5000")


@app.route('/')
def index():
    """Render the main index page"""
    # Format conversation history for display
    formatted_history = []
    for entry in app.state.conversation_history:
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

    conversation_history = app.state.conversation_history
    
    return render_template('index.html', 
                          conversation_history=formatted_history)

@app.route('/initialize', methods=['POST'])
def init_data():
    """Initialize dataset either with auto-generated data or user uploaded files"""

    app.state.conversation_history = []
    app.state.iteration_count = 0
    
    api_key = request.form.get('apiKey', '')
    model = request.form.get('model', 'gemini')

    if not api_key:
        api_key = get_api_key(model)
        if not api_key:
            logger.error("API key is required")
            return jsonify({"status": "error", "message": "API key is required"}), 400
    
    app.state.api_key = api_key
    app.state.model = model
    
    # Check which data source is being used
    data_source = request.form.get('dataSource', 'auto')
    logger.info(f"Initialising with data source: {data_source}")
    
    if data_source == 'auto':
        # Use the default auto-generated data
        data, data_inv = initialize_data()
        app.state.analysis_namespace['x'] = data
        app.state.conversation_history.append({
            "role": "assistant",
            "type": "text",
            "iteration": app.state.iteration_count,
            "content": data_inv
        })
        return jsonify({"status": "success", "message": "Data initialised successfully"})
    
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
                file_path = os.path.join('uploads', filename)
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
            app.state.conversation_history.append({
                "role": "user",
                "type": "text",
                "iteration": app.state.iteration_count,
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
    
    # Clear any existing 'x' data to avoid confusion
    if 'x' in app.state.analysis_namespace:
        del app.state.analysis_namespace['x']
    
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
                app.state.analysis_namespace[var_name] = df
                processed_files.append((var_name, f"DataFrame with shape {df.shape}"))
                logger.info(f"Loaded CSV file: {file_path} as {var_name}")
                
            elif file_type == 'npy':
                # Load NumPy array
                arr = np.load(file_path)
                var_name = f'arr_{base_name}'
                app.state.analysis_namespace[var_name] = arr
                processed_files.append((var_name, f"NumPy array with shape {arr.shape}"))
                logger.info(f"Loaded NumPy file: {file_path} as {var_name}")

            elif file_type == 'json':
                with open(file_path) as f:
                    jsonfile = json.load(f)
                var_name = f'json_{base_name}'
                app.state.analysis_namespace[var_name] = jsonfile
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
    app.state.conversation_history.append({
        "role": "assistant",
        "type": "text",
        "iteration": app.state.iteration_count,
        "content": data_inventory
    })
    
    logger.info(f"Processed {len(processed_files)} files successfully")
    return f"Successfully loaded {len(file_info)} file(s). Data inventory added to conversation."

@app.route('/get_analysis', methods=['GET'])
def get_analysis():
    """Get analysis from LLM based on conversation history"""
    logger.info(f"Getting analysis with conversation history length: {len(app.state.conversation_history)}")

    try:
        model_name = app.state.model
        client = get_client(model_name, app.state.api_key)
        if model_name == "o1":
            logger.info("Using model: o1 (Note: Better but slower than GPT-4o)")
            app.state.MODEL_NAME = "o1-2024-12-17"
        elif model_name == "claude":
            logger.info("Using model: Claude 3.7 Sonnet (Note: Best responses)")
            app.state.MODEL_NAME = "claude-3-7-sonnet-20250219"
        elif model_name == "gemini":
            logger.info("Using model: Gemini 2.5 Pro (Note: Free but limited token rate)")
            app.state.MODEL_NAME = "gemini-2.5-pro-exp-03-25"
        elif model_name == "4o":
            logger.info("Using model: GPT-4o (Note: Cheapest per token)")
            app.state.MODEL_NAME = "gpt-4o-2024-11-20"
        else:
            model_name = "gemini"
            app.state.MODEL_NAME = "gemini-2.5-pro-exp-03-25"
            logger.info("Using default model: Gemini 2.5 Pro")
        
        # Build prompt and call LLM
        prompt = build_llm_prompt(app.state.conversation_history, app.state.MODEL_NAME)
        llm_response = call_llm_and_parse(client, prompt, MODEL_NAME=app.state.MODEL_NAME)

        app.state.iteration_count += 1
        
        logger.info(f"Successfully got analysis from {model_name}")
        return jsonify({
            "status": "success",
            "summary": llm_response.text_summary,
            "code": llm_response.python_code,
            "conversation_length": len(app.state.conversation_history)
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
        elif model_name=="4o" or model_name=="o1":                                                                # OpenAI API Error codes
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
        else:
            if "Error code: 429" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "API rate limit exceeded. Please try again later."
                }), 429
            elif "Error code: 500" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "Error on Google's side. Could be because input context is too long."
                }), 500
            elif "Error code: 403" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "API key is incorrect or not authorised to access the Gemini API."
                }), 403
            elif "Error code: 503" in str(e):
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": "Gemini API is temporarily overloaded. Please try again later or switch to a different model."
                }), 503
            else:
                logger.error(f"Error getting analysis: {str(e)}")
                return jsonify({
                    "status": "error",
                    "message": str(e)
                })

@app.route('/execute_code', methods=['POST'])
def execute_code():
    """Execute Python code in a separate process and capture outputs/figures"""
    
    code = request.json.get('code', '')
    summary = request.json.get('summary', '')
    execution_id = request.json.get('execution_id')
    
    if not execution_id:
        execution_id = str(time.time())  # Generate an ID if not provided
    
    logger.info(f"Starting code execution with ID: {execution_id}")
    
    # First, add the summary and proposed code to conversation history
    app.state.conversation_history.append({
        "role": "assistant", 
        "type": "text",
        "iteration": app.state.iteration_count,
        "content": summary
    })
    
    app.state.conversation_history.append({
        "role": "assistant",
        "type": "code",
        "iteration": app.state.iteration_count,
        "content": "Proposed code:\n" + code
    })
    
    # Add execution record to history
    app.state.conversation_history.append({
        "role": "user",
        "type": "text",
        "iteration": app.state.iteration_count,
        "content": "Execute code"
    })
    
    # Initialize result storage
    app.state.execution_results[execution_id] = {
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
        args=(code, app.state.analysis_namespace, child_conn)
    )
    
    # Store the process and connection for potential cancellation
    app.state.active_executions[execution_id] = {
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
                app.state.analysis_namespace.update(dill.loads(new_namespace))
                
                # Check if execution was terminated
                if output_text == "TERMINATED":
                    logger.info(f"Execution {execution_id} was terminated")
                    app.state.execution_results[execution_id]['status'] = 'cancelled'
                    app.state.execution_results[execution_id]['output'] = "Execution was cancelled by user."
                    app.state.execution_results[execution_id]['complete'] = True
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
                    
                    app.state.conversation_history.append({
                        "role": "figure",
                        "type": "figure",
                        "iteration": app.state.iteration_count,
                        "content": {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_str}",
                            },
                        }
                    })
                
                # Store the results for retrieval
                app.state.execution_results[execution_id]['status'] = 'completed'
                app.state.execution_results[execution_id]['output'] = output_text
                app.state.execution_results[execution_id]['figures'] = figure_data
                app.state.execution_results[execution_id]['error'] = had_error
                app.state.execution_results[execution_id]['complete'] = True
                
                # Add output to conversation history if it exists
                if had_error:
                    logger.warning(f"Execution {execution_id} resulted in error")
                    app.state.conversation_history.append({
                        "role": "assistant",
                        "type": "output",
                        "iteration": app.state.iteration_count,
                        "content": "Error while running code:\n" + output_text
                    })
                elif output_text.strip():
                    app.state.conversation_history.append({
                        "role": "assistant",
                        "type": "output",
                        "iteration": app.state.iteration_count,
                        "content": "Code Output:\n" + output_text
                    })
                
            else:
                # Timeout occurred
                logger.warning(f"Execution {execution_id} timed out")
                output_text = "Execution timed out after 5 minutes. Consider optimizing your code or using smaller datasets."
                
                app.state.execution_results[execution_id]['status'] = 'timeout'
                app.state.execution_results[execution_id]['output'] = output_text
                app.state.execution_results[execution_id]['error'] = True
                app.state.execution_results[execution_id]['complete'] = True
                
                app.state.conversation_history.append({
                    "role": "assistant",
                    "type": "output",
                    "iteration": app.state.iteration_count,
                    "content": "Execution timed out:\n" + output_text
                })
        except Exception as e:
            logger.error(f"Error processing execution results: {str(e)}")
            output_text = f"Error during execution: {str(e)}"
            
            app.state.execution_results[execution_id]['status'] = 'error'
            app.state.execution_results[execution_id]['output'] = output_text
            app.state.execution_results[execution_id]['error'] = True
            app.state.execution_results[execution_id]['complete'] = True
            
            app.state.conversation_history.append({
                "role": "assistant",
                "type": "output",
                "iteration": app.state.iteration_count,
                "content": f"Execution error:\n{output_text}"
            })
        finally:
            # Clean up the process
            if execution_id in app.state.active_executions:
                if app.state.active_executions[execution_id]['process'].is_alive():
                    app.state.active_executions[execution_id]['process'].terminate()
                del app.state.active_executions[execution_id]
    
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
    
    if execution_id not in app.state.execution_results:
        return jsonify({
            "status": "not_found",
            "message": "No results found for this execution ID"
        }), 404
    
    result = app.state.execution_results[execution_id]
    
    # If execution is complete, we can clean up the results data after sending
    if result['complete'] and result['status'] != 'running':
        # Clone the result for response
        response_data = dict(result)
        
        # Clean up old results periodically (keep the last few)
        all_executions = list(app.state.execution_results.keys())
        if len(all_executions) > 10:  # Keep only last 10 results
            oldest = all_executions[0]
            if oldest != execution_id:  # Don't delete what we're returning
                del app.state.execution_results[oldest]
        
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
    
    execution_id = request.json.get('execution_id')
    
    if not execution_id or execution_id not in app.state.active_executions:
        logger.warning(f"Attempt to stop non-existent execution: {execution_id}")
        return jsonify({
            "status": "error",
            "message": "No such execution found"
        }), 404
    
    logger.info(f"Stopping execution: {execution_id}")
    
    try:
        # Get the process
        execution = app.state.active_executions[execution_id]
        process = execution['process']
        
        # Update execution result status
        if execution_id in app.state.execution_results:
            app.state.execution_results[execution_id]['status'] = 'cancelled'
            app.state.execution_results[execution_id]['output'] = "Execution was cancelled by user."
            app.state.execution_results[execution_id]['complete'] = True
        
        # Terminate the process if it's still running
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
            
            # If it didn't terminate, try to kill it
            if process.is_alive():
                logger.warning(f"Process {execution_id} did not terminate gracefully, forcing kill")
                os.kill(process.pid, signal.SIGKILL)
        
        # Add to conversation history
        app.state.conversation_history.append({
            "role": "assistant",
            "type": "output",
            "iteration": app.state.iteration_count,
            "content": "Code execution was cancelled by user."
        })
        
        # Clean up
        del app.state.active_executions[execution_id]
        
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
    
    logger.debug(f"Debug History Endpoint - History length: {len(app.state.conversation_history)}")
    
    # Format conversation history for JSON response
    formatted_history = []
    for entry in app.state.conversation_history:
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
        "history_length": len(app.state.conversation_history),
        "history": formatted_history
    })

@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    """Send user feedback and get next analysis"""

    feedback = request.json.get('feedback', '')
    summary = request.json.get('summary', '')
    code = request.json.get('code', '')
    iter = app.state.iteration_count
    
    logger.info(f"Feedback route - Current history length: {len(app.state.conversation_history)}")
    
    # Add to conversation history
    app.state.conversation_history.append({
        "role": "assistant",
        "type": "text",
        "iteration": iter,
        "content": summary
    })
    app.state.conversation_history.append({
        "role": "assistant",
        "type": "code",
        "iteration": iter,
        "content": "Proposed code:\n" + code
    })
    app.state.conversation_history.append({
        "role": "user",
        "type": "text",
        "iteration": iter,
        "content": feedback
    })
    
    logger.debug(f"Feedback route - Updated history length: {len(app.state.conversation_history)}")
    
    # Now automatically get the next analysis
    try:
        model_name = app.state.model
        client = get_client(model_name, app.state.api_key)
    
        prompt = build_llm_prompt(app.state.conversation_history, app.state.MODEL_NAME)
        llm_response = call_llm_and_parse(client, prompt, model_name=app.state.MODEL_NAME)

        app.state.iteration_count += 1
        
        logger.info("Successfully got next analysis after feedback")
        
        # Return both the success status and the new analysis
        return jsonify({
            "status": "success", 
            "history_length": len(app.state.conversation_history),
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
            "history_length": len(app.state.conversation_history),
            "error": str(e)
        })

@app.route('/save_analysis', methods=['POST'])
def save_analysis():
    """Save all analysis history to files in a structured folder"""
    try:
        # Get the data from the request
        data = request.json
        
        # Create timestamp for folder name
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        parent_folder = f"analysis_{timestamp}"
        
        # Create temporary directory structure
        temp_dir = os.path.join("analyses", parent_folder)
        os.makedirs(temp_dir, exist_ok=True)
        
        # Create subfolders
        code_dir = os.path.join(temp_dir, "code")
        figures_dir = os.path.join(temp_dir, "figures")
        
        os.makedirs(code_dir, exist_ok=True)
        os.makedirs(figures_dir, exist_ok=True)
        
        # Save conversation history as markdown
        if data.get('text'):
            with open(os.path.join(temp_dir, "conversation.md"), 'w') as f:
                f.write(f"# Conversation History - {timestamp}\n\n")
                for item in data['text']:
                    f.write(f"## Iteration {item['iteration']} - {item['role']}\n\n")
                    content = item['content'].replace('<br>', '\n')
                    # Strip HTML tags
                    content = re.sub(r'<.*?>', '', content)
                    f.write(f"{content}\n\n")
        
        # Save code history as Python files
        if data.get('code'):
            for i, item in enumerate(data['code']):
                content = item['content']
                # Clean up any HTML or markdown code block syntax
                content = re.sub(r'```python|```', '', content)
                
                filename = f"code_iteration_{item['iteration']}.py"
                with open(os.path.join(code_dir, filename), 'w') as f:
                    f.write(f"# Code from Iteration {item['iteration']}\n")
                    f.write(f"# Generated by Alfred\n\n")
                    f.write(content)
        
        # Save output history as markdown
        if data.get('output'):
            with open(os.path.join(temp_dir, "output.md"), 'w') as f:
                f.write(f"# Code Output History - {timestamp}\n\n")
                for item in data['output']:
                    f.write(f"## Iteration {item['iteration']} - {item['role']}\n\n")
                    content = item['content'].replace('<br>', '\n')
                    # Strip HTML tags
                    content = re.sub(r'<.*?>', '', content)
                    f.write(f"```\n{content}\n```\n\n")
        
        # Save figures as PNG files
        if data.get('figures'):
            last_iter = 1
            last_fignum = 0
            for i, figure in enumerate(data['figures']):
                src = figure['src']
                iter = figure['iteration']
                fignum = last_fignum + 1 if iter == last_iter else 1
                if src.startswith('data:image/png;base64,'):
                    # Extract the base64 data
                    base64_data = src.split(',')[1]
                    image_data = base64.b64decode(base64_data)
                    
                    filename = f"iteration_{iter}_figure_{fignum}.png"
                    with open(os.path.join(figures_dir, filename), 'wb') as f:
                        f.write(image_data)
                    
                    last_fignum = fignum
                    last_iter = iter
        
        # Save metadata as JSON
        metadata_file = open(os.path.join(temp_dir, "metadata.json"), 'w')
        metadata = {
            "model": app.state.model,
            "data": list(app.state.analysis_namespace.keys())
        }
        json.dump(metadata, metadata_file, indent=6)

        # Create a zip file containing all folders
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Walk through the directory and add all files to the zip
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(temp_dir))
                    zf.write(file_path, arcname)
        
        # Reset the file pointer to the beginning
        memory_file.seek(0)
        
        # Save the zip file
        zip_path = os.path.join("static", f"{parent_folder}.zip")
        with open(zip_path, 'wb') as f:
            f.write(memory_file.read())
        
        # Return the URL for downloading the zip file
        return jsonify({
            "status": "success",
            "message": "Analysis saved successfully",
            "download_url": f"/{zip_path}"
        })
        
    except Exception as e:
        logger.error(f"Error saving analysis: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
@app.route('/static/<path:filename>', methods=['GET'])
def serve_static(filename):
    """Serve static files like the generated zip"""
    return send_file(os.path.join("static", filename), as_attachment=True)

