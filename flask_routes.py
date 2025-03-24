from flask import Flask, render_template, request, jsonify, send_file
import os
import numpy as np
import pandas as pd
import json
import tempfile
from werkzeug.utils import secure_filename
import logging
from utils import *
from data_loader import *

# Set up logging
logger = logging.getLogger('alfred.routes')

###############################################################################
# Flask routes
###############################################################################
app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'npy', 'json'}

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
                "content": image_url
            })
        else:
            # Handle text entries as before
            formatted_history.append({
                "role": role,
                "content": content.replace("\n", "<br>") if isinstance(content, str) else content
            })
    
    return render_template('index.html', 
                          conversation_history=formatted_history)

@app.route('/initialize', methods=['POST'])
def init_data():
    """Initialize dataset either with auto-generated data or user uploaded files"""
    global conversation_history
    conversation_history = []
    
    if not os.getenv('API_KEY'):
        logger.error("API_KEY not found in environment variables")
        return jsonify({
            "status": "error", 
            "message": "API_KEY not found in environment variables. Please set this in order to use this tool."
        })
    
    # Check which data source is being used
    data_source = request.form.get('dataSource', 'auto')
    logger.info(f"Initializing with data source: {data_source}")
    
    if data_source == 'auto':
        # Use the default auto-generated data
        result, data_inv = initialize_data()
        conversation_history.append({
            "role": "assistant",
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
                logger.info(f"Uploaded file: {filename}")
        
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
                processed_files.append((var_name, f"Json file"))
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
        "content": data_inventory
    })
    
    logger.info(f"Processed {len(processed_files)} files successfully")
    return f"Successfully loaded {len(file_info)} file(s). Data inventory added to conversation."

@app.route('/get_analysis', methods=['GET'])
def get_analysis():
    """Get analysis from LLM based on conversation history"""
    global conversation_history
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
            elif model_name == "4o":
                logger.info("Using model: GPT-4o (Note: Cheapest per token)")
        else:
            client = get_openai_client()
            logger.info("Using default model: GPT-4o")
        
        # Build prompt and call LLM
        prompt = build_llm_prompt(conversation_history)
        llm_response = call_llm_and_parse(client, prompt)
        
        logger.info("Successfully got analysis from LLM")
        return jsonify({
            "status": "success",
            "summary": llm_response.text_summary,
            "code": llm_response.python_code,
            "conversation_length": len(conversation_history)
        })
    except Exception as e:
        logger.error(f"Error getting analysis: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/execute_code', methods=['POST'])
def execute_code():
    """Execute Python code and capture outputs/figures"""
    global conversation_history
    code = request.json.get('code', '')
    summary = request.json.get('summary', '')
    
    logger.info(f"Executing code with conversation history length: {len(conversation_history)}")
    
    # First, add the summary and proposed code to conversation history
    conversation_history.append({
        "role": "assistant", 
        "content": summary
    })
    
    conversation_history.append({
        "role": "assistant",
        "content": "Proposed code:\n" + code
    })
    
    logger.debug(f"After adding summary and code: {len(conversation_history)}")
    
    # Now execute the code
    output_text, figures, had_error = run_and_capture_output(code)
    
    # Add execution record to history
    conversation_history.append({
        "role": "user",
        "content": "Execute code"
    })
    
    if had_error:
        logger.warning("Code execution resulted in error")
        conversation_history.append({
            "role": "assistant",
            "content": "Error while running code:\n" + output_text
        })
        return jsonify({
            "status": "error",
            "output": output_text,
            "figures": [],
            "history_length": len(conversation_history)
        })
    else:
        if output_text.strip():
            conversation_history.append({
                "role": "assistant",
                "content": "Code Output:\n" + output_text
            })
        
        # Save figures and add to conversation history
        figure_data = []
        for i, fig in enumerate(figures):
            img_str = fig_to_base64(fig)
            figure_data.append({
                "id": i,
                "data": img_str
            })
            
            # Create a description of the figure to add to conversation history
            # Get the title if it exists
            title = fig._suptitle.get_text() if fig._suptitle else f"Figure {i+1}"
            logger.info(f"Generated figure: {title}")
            
            # Add figure to conversation history
            conversation_history.append({
                "role": "figure",
                "content": {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_str}",
                    },
                }
            })
        
        logger.debug(f"Final conversation history length: {len(conversation_history)}")
        
        return jsonify({
            "status": "success",
            "output": output_text,
            "figures": figure_data,
            "history_length": len(conversation_history)
        })

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

        if role == "figure":
            # Handle figure entries differently
            if isinstance(content, dict) and "image_url" in content:
                logger.debug("Content has image_url")
            else:
                logger.warning(f"Unexpected content structure: {content}")
                
            image_url = content.get("image_url", {}).get("url", "")
            formatted_history.append({
                "role": "figure",
                "content": image_url
            })
        else:
            # Handle text entries as before
            formatted_history.append({
                "role": role,
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
    feedback = request.json.get('feedback', '')
    summary = request.json.get('summary', '')
    code = request.json.get('code', '')
    
    logger.info(f"Feedback route - Current history length: {len(conversation_history)}")
    
    # Add to conversation history
    conversation_history.append({
        "role": "assistant",
        "content": summary
    })
    conversation_history.append({
        "role": "assistant",
        "content": "Proposed code:\n" + code
    })
    conversation_history.append({
        "role": "user",
        "content": feedback
    })
    
    logger.debug(f"Feedback route - Updated history length: {len(conversation_history)}")
    
    # Now automatically get the next analysis
    try:
        if os.getenv('MODEL', default=None):
            client = get_client(os.environ.get('MODEL'))
        else:
            client = get_openai_client()
        
        prompt = build_llm_prompt(conversation_history)
        llm_response = call_llm_and_parse(client, prompt)
        
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
