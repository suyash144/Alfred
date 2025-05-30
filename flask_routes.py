from flask import Flask, render_template, request, jsonify, send_from_directory, g
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
from app import app
from collections import defaultdict
import shutil

app.secret_key = os.environ.get('FLASK_SECRET', 'default_secret_key')

@app.before_request
def load_user_state():
    g.state = get_user_state()

logger.info("Click here to run Alfred: http://localhost:5000")

@app.route('/initialize', methods=['POST'])
def init_data():
    """Initialize dataset either with auto-generated data or user uploaded files"""

    g.state.conversation_history = []
    g.state.iteration_count = 0
    g.state.analysis_namespace = {}
    
    api_key = request.form.get('apiKey', '')
    model = request.form.get('model', 'gemini')

    if not api_key:
        api_key = get_api_key(model)
        if not api_key:
            logger.error("API key is required")
            return jsonify({"status": "error", "message": "API key is required"}), 400
    
    g.state.api_key = api_key
    g.state.model = model
    
    # Check which data source is being used
    data_source = request.form.get('dataSource', 'auto')
    logger.info(f"Initialising with data source: {data_source}")

    # Check if a custom prompt was provided
    custom_prompt = request.form.get('customPrompt', '')
    
    if data_source == 'auto':
        # Use the default auto-generated data
        data, data_inv = initialize_data()
        g.state.analysis_namespace['x'] = data
        g.state.conversation_history.append({
            "role": "assistant",
            "type": "text",
            "iteration": g.state.iteration_count,
            "content": data_inv
        })

        if custom_prompt:
            logger.info("Custom prompt provided")
            # Add the custom prompt as the first user prompt.
            g.state.conversation_history.append({
                "role": "user",
                "type": "text",
                "iteration": g.state.iteration_count,
                "content": custom_prompt
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
        process_uploaded_files(file_info)

        if custom_prompt:
            logger.info("Custom prompt provided")
            # Add the custom prompt as the first user prompt.
            g.state.conversation_history.append({
                "role": "user",
                "type": "text",
                "iteration": g.state.iteration_count,
                "content": custom_prompt
            })
        
        return jsonify({
            "status": "success", 
            "message": f"Successfully processed {len(uploaded_files)} custom data file(s)"
        })
    
    elif data_source == 'ibl':
        logger.info("Analysing IBL data. Loading default IBL prompt.")
        ibl_prompt_file_path = os.path.join(os.getcwd(), "ibl_prompt.md")

        try:
            with open(ibl_prompt_file_path, 'r', encoding='utf-8') as f:
                ibl_prompt = f.read()
            logger.info("Successfully loaded IBL prompt")
        except FileNotFoundError:
            logger.error(f"ibl_prompt.md not found at {ibl_prompt_file_path}")
            return jsonify({"status": "error", "message": "IBL prompt file not found."}), 500
        except Exception as e:
            logger.error(f"Error reading ibl_prompt.md: {e}")
            return jsonify({"status": "error", "message": f"Error reading IBL prompt file: {e}"}), 500
        
        g.state.conversation_history.append({
            "role": "user",
            "type": "text",
            "iteration": g.state.iteration_count,
            "content": ibl_prompt
        })

        if custom_prompt:
            logger.info("Custom prompt also provided")
            # Add the custom prompt as the first user prompt.
            g.state.conversation_history.append({
                "role": "user",
                "type": "text",
                "iteration": g.state.iteration_count,
                "content": custom_prompt
            })

        return jsonify({"status": "success", "message": "Ready to analyse IBL data."})

    else:
        if not custom_prompt:
            logger.warning("User is not uploading data and no custom prompt provided")
            return jsonify({
                "status": "error", 
                "message": "No data or prompt provided. Alfred needs data!"
            })
        else:
            logger.info(f"User is not uploading data files but there is a custom prompt.")

            g.state.conversation_history.append({
                "role": "user",
                "type": "text",
                "iteration": g.state.iteration_count,
                "content": custom_prompt
            })
            
            return jsonify({
                "status": "success", 
                "message": "Not uploading any data. Data access procedure should be specified in prompt."
            })

def process_uploaded_files(file_info):
    """Process uploaded files and store them in the analysis_namespace"""
    
    processed_files = []
    
    for file in file_info:
        file_path = file['path']
        file_type = file['type']
        base_name = os.path.basename(file_path).rsplit('.', 1)[0]
        base_name = re.sub('\W|^(?=\d)','_', base_name)                         # Clean up the base name for variable naming
        
        try:
            if file_type == 'csv':
                # Load CSV file into a pandas DataFrame
                df = pd.read_csv(file_path)
                var_name = f'df_{base_name}'
                g.state.analysis_namespace[var_name] = df
                processed_files.append((var_name, f"DataFrame with shape {df.shape}"))
                logger.info(f"Loaded CSV file: {file_path} as {var_name}")
                
            elif file_type == 'npy':
                # Load NumPy array
                try:
                    arr = np.load(file_path)
                except:
                    arr  = np.load(file_path, allow_pickle=True)
                var_name = f'arr_{base_name}'
                g.state.analysis_namespace[var_name] = arr
                processed_files.append((var_name, f"NumPy array with shape {arr.shape}"))
                logger.info(f"Loaded NumPy file: {file_path} as {var_name}")

            elif file_type == 'json':
                with open(file_path) as f:
                    jsonfile = json.load(f)
                var_name = f'json_{base_name}'
                g.state.analysis_namespace[var_name] = jsonfile
                if type(jsonfile) is list:
                    processed_files.append((var_name, f"List from JSON file"))
                elif type(jsonfile) is dict:
                    processed_files.append((var_name, f"Dictionary from JSON file"))
                else:
                    processed_files.append((var_name, f"Python object (not list or dict) loaded from a JSON file"))
                logger.info(f"Loaded JSON file: {file_path} as {var_name}")

            elif file_type == 'txt' or file_type == 'md':
                with open(file_path) as f:
                    txtfile = f.read()
                var_name = f'txt_{base_name}'
                g.state.analysis_namespace[var_name] = txtfile
                logger.info(f"Loaded text file: {file_path} as {var_name}")
                g.state.conversation_history.append({
                    "role": "assistant",
                    "type": "text",
                    "iteration": g.state.iteration_count,
                    "content": f"Text file loaded as string: \n{txtfile} \n\nAdded as variable {var_name}."
                })
                
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            continue
    
    # Create a data inventory message for the conversation history
    if processed_files:
        data_inventory = "Added the following variables:\n"
        for var_name, description in processed_files:
            data_inventory += f"- {var_name}: {description}\n"
            
        # Add this inventory to the conversation history
        g.state.conversation_history.append({
            "role": "assistant",
            "type": "text",
            "iteration": g.state.iteration_count,
            "content": data_inventory
        })
        
        logger.info(f"Processed {len(processed_files)} files successfully")
    return f"Successfully loaded {len(file_info)} file(s). Data inventory added to conversation."

@app.route('/get_analysis', methods=['GET'])
def get_analysis():
    """Get text from LLM based on conversation history"""
    logger.info(f"Getting analysis with conversation history length: {len(g.state.conversation_history)}")

    response_type = request.args.get('response_type', 'text')
    text_input = request.args.get('text_input', '')

    try:
        model_name = g.state.model
        client = get_client(model_name, g.state.api_key)
        g.state.MODEL_NAME = set_model_name(model_name)

        if response_type == "code":
            # Log the user command in conversation history
            if text_input:
                text = text_input
            else:
                text = "Analyse"
            g.state.conversation_history.append({
                "role": "user", 
                "type": "text",
                "iteration": g.state.iteration_count,
                "content": text
            })
        
        # Build prompt and call LLM
        prompt = build_llm_prompt(g.state.conversation_history, g.state.MODEL_NAME, response_type=response_type)
        llm_response = call_llm_and_parse(client, prompt, MODEL_NAME=g.state.MODEL_NAME, response_type=response_type)
        llm_response = process_llm_response(llm_response, response_type)

        # Increment the iteration if code was generated.
        if response_type == "code":
            g.state.iteration_count += 1
        
        if llm_response is None or len(llm_response) == 0:                  # try once again if LLM doesn't return anything
            llm_response = call_llm_and_parse(client, prompt, MODEL_NAME=g.state.MODEL_NAME, response_type=response_type)
            llm_response = process_llm_response(llm_response, response_type)
        
        if llm_response and len(llm_response) > 0:
            logger.info(f"Successfully got analysis from {model_name}")
            if response_type == "text":
                g.state.conversation_history.append({
                    "role": "assistant", 
                    "type": "text",
                    "iteration": g.state.iteration_count,
                    "content": llm_response
                })
            return jsonify({
                "status": "success",
                "response": llm_response,
                "conversation_length": len(g.state.conversation_history)
            })
        else:
            logger.info(f"No response from {model_name}")
            return jsonify({
                "status": "error",
                "message": f"No response from {model_name}. Please try again."
            })
    
    except Exception as e:
        # Separately handle errors stemming from API providers.
        error_msg, err_code = API_error_handler(e, model_name)
        return jsonify({
            "status": "error",
            "message": error_msg
        }), err_code

@app.route('/execute_code', methods=['POST'])
def execute_code():
    """Execute Python code in a separate process and capture outputs/figures"""
    
    code = request.json.get('code', '')
    execution_id = request.json.get('execution_id')
    
    if not execution_id:
        execution_id = str(time.time())  # Generate an ID if not provided
    
    logger.info(f"Starting code execution with ID: {execution_id}")
    
    # Initialize result storage
    g.state.execution_results[execution_id] = {
        'status': 'running',
        'output': '',
        'figures': [],
        'error': False,
        'complete': False
    }

    user_state = g.state
    
    # Create a pipe for communication
    parent_conn, child_conn = multiprocessing.Pipe()
    
    # Create and start the process
    process = multiprocessing.Process(
        target=run_code_in_process,
        args=(code, g.state.analysis_namespace, child_conn)
    )
    
    # Store the process and connection for potential cancellation
    user_state.active_executions[execution_id] = {
        'process': process,
        'connection': parent_conn,
        'start_time': time.time()
    }

    g.state.conversation_history.append({
        "role": "assistant",
        "type": "code",
        "iteration": user_state.iteration_count,
        "content": code
    })
    
    # Start the process
    process.start()
    
    # Set up a background thread to handle long-running code execution
    def process_execution_results(state, execution_id, parent_conn):
        with app.app_context():
            try:
                # Wait for results with a timeout
                if parent_conn.poll(600.0):  # 600 second timeout
                    output_text, figures, _, had_error, new_namespace = parent_conn.recv()

                    logger.info(f"Received execution results for {execution_id}")

                    # Update analysis namespace
                    state.analysis_namespace.update(dill.loads(new_namespace))

                    logger.info(f"Updated analysis namespace with new variables from execution {execution_id}")
                    
                    # Check if execution was terminated
                    if output_text == "TERMINATED":
                        logger.info(f"Execution {execution_id} was terminated")
                        state.execution_results[execution_id]['status'] = 'cancelled'
                        state.execution_results[execution_id]['output'] = "Execution was cancelled by user."
                        state.execution_results[execution_id]['complete'] = True
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
                        
                        state.conversation_history.append({
                            "role": "figure",
                            "type": "figure",
                            "iteration": state.iteration_count,
                            "content": {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_str}",
                                },
                            }
                        })
                    
                    logger.info(f"processed figures for execution {execution_id}")
                    
                    # Store the results for retrieval
                    state.execution_results[execution_id]['status'] = 'completed'
                    state.execution_results[execution_id]['output'] = output_text
                    state.execution_results[execution_id]['figures'] = figure_data
                    state.execution_results[execution_id]['error'] = had_error
                    state.execution_results[execution_id]['complete'] = True

                    logger.info(f"stored execution results for {execution_id}")
                    
                    # Add output to conversation history if it exists
                    if had_error:
                        logger.warning(f"Execution {execution_id} resulted in error")
                        state.conversation_history.append({
                            "role": "assistant",
                            "type": "output",
                            "iteration": state.iteration_count,
                            "content": "Error while running code:\n" + output_text
                        })
                    elif output_text.strip():
                        state.conversation_history.append({
                            "role": "assistant",
                            "type": "output",
                            "iteration": state.iteration_count,
                            "content": "Code Output:\n" + output_text
                        })

                    logger.info(f"Execution {execution_id} completed successfully")
                    
                else:
                    # Timeout occurred
                    logger.warning(f"Execution {execution_id} timed out")
                    output_text = "Execution timed out after 5 minutes. Consider optimizing your code or using smaller datasets."
                    
                    state.execution_results[execution_id]['status'] = 'timeout'
                    state.execution_results[execution_id]['output'] = output_text
                    state.execution_results[execution_id]['error'] = True
                    state.execution_results[execution_id]['complete'] = True
                    
                    state.conversation_history.append({
                        "role": "assistant",
                        "type": "output",
                        "iteration": state.iteration_count,
                        "content": "Execution timed out:\n" + output_text
                    })
            except Exception as e:
                logger.error(f"Error processing execution results: {str(e)}")
                output_text = f"Error during execution: {str(e)}"
                
                state.execution_results[execution_id]['status'] = 'error'
                state.execution_results[execution_id]['output'] = output_text
                state.execution_results[execution_id]['error'] = True
                state.execution_results[execution_id]['complete'] = True
                
                state.conversation_history.append({
                    "role": "assistant",
                    "type": "output",
                    "iteration": state.iteration_count,
                    "content": f"Execution error:\n{output_text}"
                })
            finally:
                # Clean up the process
                if execution_id in state.active_executions:
                    if state.active_executions[execution_id]['process'].is_alive():
                        state.active_executions[execution_id]['process'].terminate()
                    del state.active_executions[execution_id]
    
    # Start background thread for monitoring
    thread = threading.Thread(target=process_execution_results, 
                              args=(user_state, execution_id, parent_conn))
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
    
    if execution_id not in g.state.execution_results:
        return jsonify({
            "status": "not_found",
            "message": "No results found for this execution ID"
        }), 404
    
    result = g.state.execution_results[execution_id]
    
    # If execution is complete, we can clean up the results data after sending
    if result['complete'] and result['status'] != 'running':
        # Clone the result for response
        response_data = dict(result)
        
        # Clean up old results periodically (keep the last few)
        all_executions = list(g.state.execution_results.keys())
        if len(all_executions) > 10:  # Keep only last 10 results
            oldest = all_executions[0]
            if oldest != execution_id:  # Don't delete what we're returning
                del g.state.execution_results[oldest]
        
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
    
    if not execution_id or execution_id not in g.state.active_executions:
        logger.warning(f"Attempt to stop non-existent execution: {execution_id}")
        return jsonify({
            "status": "error",
            "message": "No such execution found. Wait for code to generate and then stop execution."
        }), 404
    
    logger.info(f"Stopping execution: {execution_id}")
    
    try:
        # Get the process
        execution = g.state.active_executions[execution_id]
        process = execution['process']
        
        # Update execution result status
        if execution_id in g.state.execution_results:
            g.state.execution_results[execution_id]['status'] = 'cancelled'
            g.state.execution_results[execution_id]['output'] = "Execution was cancelled by user."
            g.state.execution_results[execution_id]['complete'] = True
        
        # Terminate the process if it's still running
        if process.is_alive():
            process.terminate()
            process.join(timeout=2.0)
            
            # If it didn't terminate, try to kill it
            if process.is_alive():
                logger.warning(f"Process {execution_id} did not terminate gracefully, forcing kill")
                os.kill(process.pid, signal.SIGKILL)
        
        # Add to conversation history
        g.state.conversation_history.append({
            "role": "assistant",
            "type": "output",
            "iteration": g.state.iteration_count,
            "content": "Code execution was cancelled by user."
        })
        
        # Clean up
        del g.state.active_executions[execution_id]
        
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
    
    logger.debug(f"Debug History Endpoint - History length: {len(g.state.conversation_history)}")
    
    # Format conversation history for JSON response
    formatted_history = []
    for entry in g.state.conversation_history:
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
        "history_length": len(g.state.conversation_history),
        "history": formatted_history
    })

@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    """Send user feedback and get next analysis"""

    feedback = request.json.get('feedback', '')
    files_data = request.json.get('files', [])
    iter = g.state.iteration_count
    
    logger.info(f"Feedback route - Current history length: {len(g.state.conversation_history)}")
    
    # Add to conversation history
    g.state.conversation_history.append({
        "role": "user",
        "type": "text",
        "iteration": iter,
        "content": feedback
    })
    
    if files_data:
        file_info = process_fdbk_files(files_data)
        process_uploaded_files(file_info)
    
    logger.debug(f"Feedback route - Updated history length: {len(g.state.conversation_history)}")
    
    # Now automatically get the next analysis
    try:
        model_name = g.state.model
        client = get_client(model_name, g.state.api_key)
        g.state.MODEL_NAME = set_model_name(model_name)
    
        prompt = build_llm_prompt(g.state.conversation_history, g.state.MODEL_NAME, response_type="feedback")
        llm_response = call_llm_and_parse(client, prompt, MODEL_NAME=g.state.MODEL_NAME, response_type="feedback")
        llm_response = process_llm_response(llm_response, response_type="feedback")
        
        logger.info("Successfully got next analysis after feedback")

        g.state.conversation_history.append({
            "role": "assistant",
            "type": "text",
            "iteration": iter,
            "content": llm_response
        })
        
        # Return both the success status and the new analysis
        return jsonify({
            "status": "success", 
            "history_length": len(g.state.conversation_history),
            "response": llm_response
        })
    except Exception as e:
        logger.error(f"Error getting next analysis after feedback: {str(e)}")
        # If there's an error getting the next analysis, still return success for the feedback
        return jsonify({
            "status": "success", 
            "history_length": len(g.state.conversation_history),
            "error": str(e)
        })

@app.route('/api/switch_model', methods=['POST'])
def switch_model():

    model = request.json.get('model')
    if not model:
        return jsonify({'status': 'error', 'message': 'No model specified'}), 400

    if not get_api_key(model):
        logger.info(f"API key for {model} not found")
        return jsonify({"status": "error", "message": "API key is required"}), 401
    else:
        g.state.model = model
        g.state.api_key = get_api_key(model)
        return jsonify({"status": "success", "message": f"Switched to model: {model}"}), 200

@app.route('/api/store_api_key', methods=['POST'])
def store_api_key():
    data = request.json
    model = data.get('model')
    api_key = data.get('apiKey')
    
    if not model or not api_key:
        return jsonify({
            'status': 'error',
            'message': 'Model and API key are required'
        }), 400
    
    # Store the API key as an environment variable
    if model == 'gemini':
        os.environ['API_KEY_GEM'] = api_key
    elif model == 'claude':
        os.environ['API_KEY_ANT'] = api_key
    else:
        os.environ['API_KEY_OAI'] = api_key
    
    g.state.model = model
    return jsonify({
        'status': 'success',
        'message': f'API key for {model} stored successfully'
    }), 200

@app.route('/save_analysis', methods=['POST'])
def save_analysis():
    """Save all analysis history from g.state to files in a structured ZIP."""
    if not hasattr(g, 'state') or not hasattr(g.state, 'conversation_history'):
        logger.error("Attempted to save analysis, but no state or history found in g.")
        return jsonify({"status": "error", "message": "No analysis state found to save."}), 400

    logger.info("API route: /save_analysis called")
    temp_dir = None # Initialize to None for finally block
    try:
        # --- 1. Setup Folders ---
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        analysis_name = f"analysis_{timestamp}" # Base name for folder and zip
        # Create a temporary directory for staging files before zipping
        # Place it inside 'analyses' which should exist (created by Dockerfile)
        temp_dir = os.path.join("analyses", analysis_name)
        os.makedirs(temp_dir, exist_ok=True)

        code_dir = os.path.join(temp_dir, "code")
        figures_dir = os.path.join(temp_dir, "figures")
        os.makedirs(code_dir, exist_ok=True)
        os.makedirs(figures_dir, exist_ok=True)
        logger.debug(f"Created temporary directory structure in: {temp_dir}")

        # --- 2. Process History from g.state ---
        history = g.state.conversation_history
        figure_counter = defaultdict(int) # To count figures per iteration: figure_counter[iteration] -> count

        # Open main markdown files
        conversation_file_path = os.path.join(temp_dir, "conversation.md")
        output_file_path = os.path.join(temp_dir, "output.md")

        with open(conversation_file_path, 'w', encoding='utf-8') as f_conv, \
             open(output_file_path, 'w', encoding='utf-8') as f_out:

            f_conv.write(f"# Conversation History - {timestamp}\n\n")
            f_out.write(f"# Code Output History - {timestamp}\n\n")

            for entry in history:
                role = entry.get("role", "unknown")
                content = entry.get("content", "")
                entry_type = entry.get("type", "text") # Default to text
                iteration = entry.get("iteration", 0)

                if role == "figure" and entry_type != "figure": entry_type = "figure"
                elif role == "tool_code" and entry_type != "code": entry_type = "code"
                elif role == "tool_output" and entry_type != "output": entry_type = "output"

                if entry_type == 'text':
                    f_conv.write(f"## Iteration {iteration} - {role.upper()}\n\n")
                    # Perform necessary cleaning
                    cleaned_content = content.replace('<br>', '\n') # Basic newline conversion
                    cleaned_content = re.sub(r'<.*?>', '', cleaned_content) # Strip potential HTML tags
                    f_conv.write(f"{cleaned_content}\n\n")

                elif entry_type == 'code':
                    # Clean up code block markers if content includes them
                    # (adjust regex if needed based on actual content format)
                    code_content = re.sub(r'^```(?:python)?\s*|```\s*$', '', content, flags=re.MULTILINE).strip()
                    if code_content.startswith("Proposed code:"):
                        code_content = code_content[14:]
                    filename = f"code_iteration_{iteration}.py" # Assuming one code block per iteration entry
                    code_file_path = os.path.join(code_dir, filename)
                    with open(code_file_path, 'w', encoding='utf-8') as f_code:
                        f_code.write(f"# Code from Iteration {iteration}\n")
                        f_code.write(f"# Generated by Alfred\n\n")
                        f_code.write(code_content)

                elif entry_type == 'output':
                    f_out.write(f"## Iteration {iteration} - {role.upper()}\n\n")
                     # Perform necessary cleaning (similar to original)
                    cleaned_content = content.replace('<br>', '\n')
                    cleaned_content = re.sub(r'<.*?>', '', cleaned_content) # Strip potential HTML tags
                    f_out.write(f"```\n{cleaned_content}\n```\n\n")

                elif entry_type == 'figure':
                    img = content.get("image_url", {}).get("url", "")
                    if isinstance(img, str) and img.startswith('data:image/png;base64,'):
                        try:
                            base64_data = img.split(',', 1)[1]
                            image_data = base64.b64decode(base64_data)

                            figure_counter[iteration] += 1 # Increment counter for this iteration
                            fig_num = figure_counter[iteration]
                            filename = f"iteration_{iteration}_figure_{fig_num}.png"
                            figure_file_path = os.path.join(figures_dir, filename)

                            with open(figure_file_path, 'wb') as f_fig:
                                f_fig.write(image_data)
                        except (IndexError, base64.binascii.Error, IOError) as img_err:
                            logger.warning(f"Could not process/save figure data for iteration {iteration}: {img_err}. Content: {img[:100]}...")
                    else:
                        logger.warning(f"Skipping figure for iteration {iteration}: Image is not a valid base64 PNG data URI. Content: {str(img)[:100]}...")


        # --- 3. Save Metadata ---
        metadata_file_path = os.path.join(temp_dir, "metadata.json")
        metadata = {
            "timestamp": timestamp,
            "model": getattr(g.state, 'MODEL_NAME', 'unknown'), # Safely access model
            # Provide data keys if available in g.state, otherwise empty list
            "data_keys": list(getattr(g.state, 'analysis_namespace', {}).keys())
        }
        with open(metadata_file_path, 'w', encoding='utf-8') as f_meta:
            json.dump(metadata, f_meta, indent=4) # Use indent=4 for readability

        logger.debug("Finished processing history, metadata saved.")

        # --- 4. Create Zip File ---
        zip_filename = f"{analysis_name}.zip"
        # Save ZIP file directly into the 'analyses' directory
        zip_filepath = os.path.join("analyses", zip_filename)

        memory_file = io.BytesIO() # Create zip in memory first
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            base_dir = os.path.dirname(temp_dir) # e.g., 'analyses'
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Arcname is the path inside the zip file, relative to the analysis folder
                    arcname = os.path.relpath(file_path, base_dir)
                    zf.write(file_path, arcname)
        memory_file.seek(0)

        # Write the in-memory zip to the final file path
        with open(zip_filepath, 'wb') as f_zip:
            f_zip.write(memory_file.read())

        logger.info(f"Analysis successfully zipped to: {zip_filepath}")

        # --- 5. Return Download URL ---
        # Use the secure filename for the download route URL component
        safe_zip_filename = secure_filename(zip_filename)
        download_url = f"/download_analysis/{safe_zip_filename}" # Use the dedicated download route

        return jsonify({
            "status": "success",
            "message": "Analysis saved successfully",
            "download_url": download_url
        })

    except Exception as e:
        logger.error(f"Error during save_analysis: {e}", exc_info=True) # Log full traceback
        return jsonify({
            "status": "error",
            "message": f"An internal error occurred while saving the analysis: {e}"
        }), 500

    finally:
        # --- 6. Cleanup Temporary Directory ---
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Successfully removed temporary directory: {temp_dir}")
            except Exception as cleanup_err:
                logger.error(f"Error removing temporary directory {temp_dir}: {cleanup_err}")
    
@app.route('/download_analysis/<filename>', methods=['GET'])
def download_analysis_file(filename):
    """Serves the saved analysis file for download."""
    # Important: filename received here MUST be validated/sanitized
    # Using secure_filename helps, but ensure it matches expected pattern too.
    safe_filename = secure_filename(filename)
    if safe_filename != filename or not filename.startswith("analysis_") or not filename.endswith(".zip"):
         logger.warning(f"Attempt to download invalid filename: {filename}")
         return jsonify({"status": "error", "message": "Invalid filename."}), 400

    analyses_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'analyses')
    file_path = os.path.join(analyses_dir, safe_filename)

    # Check if file exists *after* constructing path from safe filename
    if not os.path.isfile(file_path):
         logger.error(f"Download request for non-existent file: {file_path}")
         return jsonify({"status": "error", "message": "File not found."}), 404

    try:
        logger.info(f"Downloading analysis file: {safe_filename}")
        return send_from_directory(analyses_dir, safe_filename, as_attachment=True)
    except Exception as e:
        logger.error(f"Error sending analysis file {safe_filename}: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Could not download file."}), 500

