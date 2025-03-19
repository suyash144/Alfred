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
        result = initialize_data()
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
    """
    Process uploaded files and store them in the analysis_namespace
    
    Args:
        file_info: List of dictionaries containing file metadata
        
    Returns:
        str: Status message
    """
    # Reset any existing data in the namespace
    if 'x' in analysis_namespace:
        del analysis_namespace['x']
    
    # Process each file based on its type
    data_frames = []
    numpy_arrays = []
    
    for file in file_info:
        file_path = file['path']
        file_type = file['type']
        
        try:
            if file_type == 'csv':
                # Load CSV file into a pandas DataFrame
                df = pd.read_csv(file_path)
                data_frames.append(df)
                
                # Store the individual DataFrame in namespace with its filename as key
                base_name = os.path.basename(file_path).rsplit('.', 1)[0]
                analysis_namespace[f'df_{base_name}'] = df
                
            elif file_type == 'npy':
                # Load NumPy array
                arr = np.load(file_path)
                numpy_arrays.append(arr)
                
                # Store the individual array in namespace with its filename as key
                base_name = os.path.basename(file_path).rsplit('.', 1)[0]
                analysis_namespace[f'arr_{base_name}'] = arr
        except Exception as e:
            print(f"Error processing file {file_path}: {str(e)}")
            continue
    
    # If we have data frames, combine them or use the first one
    if data_frames:
        if len(data_frames) == 1:
            # If only one DataFrame, use it directly
            df = data_frames[0]
        else:
            # If multiple DataFrames, try to combine them intelligently
            # This is a simplified approach - in practice, you might need more sophisticated merging
            df = pd.concat(data_frames, ignore_index=True)
        
        # Convert DataFrame to numpy array for compatibility with existing code
        analysis_namespace['x'] = df.select_dtypes(include=[np.number]).to_numpy()
        analysis_namespace['df'] = df  # Also store the full DataFrame for reference
    
    # If we have NumPy arrays, combine them or use the first one
    elif numpy_arrays:
        if len(numpy_arrays) == 1:
            # If only one array, use it directly
            analysis_namespace['x'] = numpy_arrays[0]
        else:
            # If multiple arrays, try to combine them
            # Attempt to concatenate along first axis (assuming they have compatible shapes)
            try:
                analysis_namespace['x'] = np.concatenate(numpy_arrays, axis=0)
            except:
                # If concatenation fails, just use the first array
                analysis_namespace['x'] = numpy_arrays[0]
    
    # Log the shape of the data
    if 'x' in analysis_namespace:
        x_shape = analysis_namespace['x'].shape
        return f"Data loaded successfully with shape {x_shape}"
    else:
        return "Warning: Could not process any of the uploaded files into usable data"

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