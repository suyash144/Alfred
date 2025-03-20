from flask import Flask, render_template, request, jsonify, send_file
import os
import numpy as np
import pandas as pd
import tempfile
from werkzeug.utils import secure_filename
from utils import *
from data_loader import *
###############################################################################
# Flask routes
###############################################################################
app = Flask(__name__)

# Configure upload settings
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'npy'}

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    global conversation_history
    # Format conversation history for display
    formatted_history = []
    for entry in conversation_history:

        role = entry.get("role", "")
        content = entry.get("content", "")

        if role == "figure":
            # Handle figure entries differently
            if isinstance(content, dict) and "image_url" in content:
                print("Content has image_url")
            else:
                print(f"   Unexpected content structure: {content}")
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
    global conversation_history
    conversation_history = []
    
    if not os.getenv('API_KEY'):
        raise ValueError("API_KEY not found in environment variables. Please set this in order to use this tool.")
    
    # Check which data source is being used
    data_source = request.form.get('dataSource', 'auto')
    
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
            return jsonify({
                "status": "error", 
                "message": "No valid files were uploaded. Please upload .csv or .npy files."
            })
        
        # Process the uploaded files
        result = process_uploaded_files(file_info)
        
        # Check if a custom prompt was provided
        custom_prompt = request.form.get('customPrompt', '')
        if custom_prompt:
            # Store the custom prompt in the analysis namespace for later use
            analysis_namespace['custom_prompt'] = custom_prompt
        
        return jsonify({
            "status": "success", 
            "message": f"Successfully processed {len(uploaded_files)} custom data file(s)"
        })
    
    else:
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
                
            elif file_type == 'npy':
                # Load NumPy array
                arr = np.load(file_path)
                var_name = f'arr_{base_name}'
                analysis_namespace[var_name] = arr
                processed_files.append((var_name, f"NumPy array with shape {arr.shape}"))
                
        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")
            continue
    
    # If only one file was processed, also set it as 'x' for backwards compatibility
    if len(processed_files) == 1:
        var_name, _ = processed_files[0]
        analysis_namespace['x'] = analysis_namespace[var_name]
        processed_files.append(('x', f"Reference to {var_name}"))
    
    # Create a data inventory message for the conversation history
    data_inventory = "Available data variables:\n"
    for var_name, description in processed_files:
        data_inventory += f"- {var_name}: {description}\n"
        
    # Add this inventory to the conversation history
    conversation_history.append({
        "role": "assistant",
        "content": data_inventory
    })
    
    return f"Successfully loaded {len(file_info)} file(s). Data inventory added to conversation."

@app.route('/get_analysis', methods=['GET'])
def get_analysis():
    # Get the full conversation history from session
    global conversation_history

    if os.getenv('MODEL', default=None):
        client = get_client(os.environ.get('MODEL'))
        if os.environ.get('MODEL') == "o1":
            print("Using model: o1. This is better but much slower than GPT-4o.")
        elif os.environ.get('MODEL') == "claude":
            print("Using model: Claude 3.7 Sonnet.")
        elif os.environ.get('MODEL') == "4o":
            print("Using model: GPT-4o. This is the cheapest model to use per token.")
    else:
        client = get_openai_client()
        print("Using default model: GPT-4o")
    
    # Check if custom prompt exists and use it instead of the default prompt
    if 'custom_prompt' in analysis_namespace:
        custom_system_prompt = analysis_namespace['custom_prompt']
        prompt = build_llm_prompt(conversation_history, custom_system_prompt)
    else:
        prompt = build_llm_prompt(conversation_history)
    
    try:
        llm_response = call_llm_and_parse(client, prompt)
        
        # Store the model's response in conversation_history only if the user accepts/runs it
        # (this will be done in the execute_code or send_feedback routes)
        
        return jsonify({
            "status": "success",
            "summary": llm_response.text_summary,
            "code": llm_response.python_code,
            "conversation_length": len(conversation_history)  # Add this to help debug
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.route('/execute_code', methods=['POST'])
def execute_code():
    global conversation_history
    code = request.json.get('code', '')
    summary = request.json.get('summary', '')
    
    print(f"Current conversation history length: {len(conversation_history)}")
    
    # First, add the summary and proposed code to conversation history
    conversation_history.append({
        "role": "assistant", 
        "content": summary
    })
    
    conversation_history.append({
        "role": "assistant",
        "content": "Proposed code:\n" + code
    })
    
    print(f"After adding summary and code: {len(conversation_history)}")
    
    # Now execute the code
    output_text, figures, had_error = run_and_capture_output(code)
    
    # Add execution record to history
    conversation_history.append({
        "role": "user",
        "content": "Execute code"
    })
    
    if had_error:
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
            
            # Add figure to conversation history
            conversation_history.append({
                "role": "figure",
                "content":                 {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_str}",
                    },
                }
            })
            
        print(f"Final conversation history length: {len(conversation_history)}")
        
        return jsonify({
            "status": "success",
            "output": output_text,
            "figures": figure_data,
            "history_length": len(conversation_history)
        })

@app.route('/debug/history', methods=['GET'])
def debug_history():
    """
    Debug endpoint to get the full conversation history
    """
    global conversation_history
    
    # Print to server console for debugging
    print(f"Debug History Endpoint - History length: {len(conversation_history)}")
    
    # Format conversation history for JSON response
    formatted_history = []
    for entry in conversation_history:
        role = entry.get("role", "")
        content = entry.get("content", "")

        if role == "figure":
            # Handle figure entries differently
            if isinstance(content, dict) and "image_url" in content:
                print("Content has image_url")
            else:
                print(f"   Unexpected content structure: {content}")
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
    global conversation_history
    feedback = request.json.get('feedback', '')
    summary = request.json.get('summary', '')
    code = request.json.get('code', '')
    
    print(f"Feedback route - Current history length: {len(conversation_history)}")
    
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
    
    print(f"Feedback route - Updated history length: {len(conversation_history)}")
    
    # Now automatically get the next analysis
    if os.getenv('MODEL', default=None):
        client = get_client(os.environ.get('MODEL'))
    else:
        client = get_openai_client()
    
    # Check if custom prompt exists and use it
    if 'custom_prompt' in analysis_namespace:
        custom_system_prompt = analysis_namespace['custom_prompt']
        prompt = build_llm_prompt(conversation_history, custom_system_prompt)
    else:
        prompt = build_llm_prompt(conversation_history)
    
    try:
        llm_response = call_llm_and_parse(client, prompt)
        
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
        print(f"Error getting next analysis after feedback: {str(e)}")
        # If there's an error getting the next analysis, still return success for the feedback
        return jsonify({
            "status": "success", 
            "history_length": len(conversation_history),
            "error": str(e)
        })