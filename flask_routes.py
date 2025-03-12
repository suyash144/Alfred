from flask import Flask, render_template, request, jsonify, send_file
from utils import *
from data_loader import *
###############################################################################
# Flask routes
###############################################################################
app = Flask(__name__)

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
    result = initialize_data()
    return jsonify({"status": "success", "message": result})

@app.route('/get_analysis', methods=['GET'])
def get_analysis():
    # Get the full conversation history from session
    global conversation_history
    
    client = get_openai_client()
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
    
    return jsonify({"status": "success", "history_length": len(conversation_history)})