from flask import Flask, render_template, request, jsonify, send_file
import sys
import io
import os
import json
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pydantic import BaseModel
import openai
import base64
from datetime import datetime

app = Flask(__name__)

###############################################################################
# Constants: Model name and prompt text
###############################################################################
MODEL_NAME = "gpt-4o-2024-11-20"

SYSTEM_PROMPT = (
    "You are a helpful assistant designed to perform iterative exploratory data "
    "analysis on a 2D numpy array, stored in the variable 'x'. On each step, you must output valid JSON that "
    "follows the LLMResponse schema (two fields: 'text_summary' and 'python_code'). "
    "Do not output extra keys or any text outside the JSON. Your 'text_summary' "
    "should describe your current understanding of the data, your working hypotheses, "
    "and your next proposed analysis. Your 'python_code' should be a single Python "
    "analysis snippet that the user can run. It is crucial that your code outputs something as this is what"
    "you will receive as your next prompt."
)

# This is the fixed part of the user prompt appended at the end of conversation history
NOW_CONTINUE_TEXT = (
    "Now continue with a new step: Summarize what is known so far about the data, "
    "propose 5 or so working hypotheses, and suggest code for a single analysis step."
)

###############################################################################
# Pydantic model for the LLM's structured output
###############################################################################
class LLMResponse(BaseModel):
    text_summary: str
    python_code: str

###############################################################################
# Global analysis namespace for executed code (retains state across iterations)
###############################################################################
analysis_namespace = {}

###############################################################################
# Global conversation history
###############################################################################
conversation_history = []

###############################################################################
# Initialize example data
###############################################################################
def initialize_data():
    c1 = [[1, 0.8, 0],
          [0.8, 1, 0],
          [0, 0, 1]]
    c2 = [[1, 0, 0],
          [0, 1, -0.8],
          [0, -0.8, 1]]
    m1 = [0, 0, 0]
    m2 = [5, 0, 0]

    # Generate two sets of points from multivariate normals, then concatenate
    x = np.concatenate((
        np.random.multivariate_normal(m1, c1, 500),
        np.random.multivariate_normal(m2, c2, 500)
    ))
    
    analysis_namespace["x"] = x
    return "Data initialized successfully"

###############################################################################
# Build the prompt for the LLM
###############################################################################
def build_llm_prompt(conversation_history):
    """
    Build a prompt for the LLM, incorporating the current conversation history.
    We'll append the NOW_CONTINUE_TEXT at the end.
    """
    history_text = []
    for entry in conversation_history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        
        # Add special handling for figure entries
        if role == "figure":
            history_text.append(f"ASSISTANT SAYS: [Generated a figure: {content}]")
        else:
            history_text.append(f"{role.upper()} SAYS: {content}")

    history_text_str = "\n".join(history_text)

    prompt = (
        "Below is the conversation so far, including user feedback and "
        "assistant's previous analysis or error messages (if any). Then "
        "provide your new output:\n\n"
        f"{history_text_str}\n\n"
        f"{NOW_CONTINUE_TEXT}\n"
    )
    return prompt

###############################################################################
# Capture matplotlib figures
###############################################################################
def collect_matplotlib_figures():
    """
    Gather any currently open matplotlib figures. Returns them as a list.
    """
    figs = []
    for i in plt.get_fignums():
        fig = plt.figure(i)
        figs.append(fig)
    return figs

###############################################################################
# Execute code in shared namespace, capturing stdout, figures, and errors
###############################################################################
def run_and_capture_output(code):
    """
    Executes the given code string in the analysis_namespace context,
    capturing stdout and any matplotlib figures generated.
    Returns (output_text, figures, error_flag).
      - output_text is either the code's stdout or error message
      - figures is the list of created matplotlib figures
      - error_flag is True if an exception occurred
    """
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output

    # Close any existing figures so we only capture the new ones
    plt.close('all')

    figures = []
    error_flag = False
    try:
        exec(code, analysis_namespace)
        figures = collect_matplotlib_figures()
    except Exception as e:
        error_flag = True
        print(f"Execution Error: {e}")

    sys.stdout = old_stdout
    output_text = redirected_output.getvalue()

    if len(output_text) == 0:
        output_text = "Please make sure your code prints something to stdout. Otherwise you will not be able to see its results."

    return output_text, figures, error_flag

###############################################################################
# Actual LLM call to parse response
###############################################################################
def call_llm_and_parse(client, prompt):
    """
    Calls the new OpenAI client to parse the response into LLMResponse
    using the JSON schema automatically.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        response_format={"type": "json_object"},
        seed=42
    )
    
    # Parse the JSON response content manually
    response_content = completion.choices[0].message.content
    parsed_response = json.loads(response_content)
    
    # Convert to LLMResponse
    llm_response = LLMResponse(
        text_summary=parsed_response.get("text_summary", ""),
        python_code=parsed_response.get("python_code", "")
    )
    # Return the parsed LLMResponse object
    return llm_response

###############################################################################
# Function to get OpenAI client
###############################################################################
def get_openai_client():
    return openai.OpenAI(
        api_key=os.environ.get('API_KEY'),
    )

###############################################################################
# Function to convert matplotlib figure to base64 for web display
###############################################################################
def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode('utf-8')
    return img_str

###############################################################################
# Flask routes
###############################################################################

@app.route('/')
def index():
    global conversation_history
    # Format conversation history for display
    formatted_history = []
    for entry in conversation_history:
        formatted_history.append({
            "role": entry.get("role", ""),
            "content": entry.get("content", "").replace("\n", "<br>")
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
            
            # Add figure description to conversation history
            conversation_history.append({
                "role": "figure",
                "content": f"{title} - This figure shows a plot of the data."
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
        formatted_history.append({
            "role": entry.get("role", "unknown"),
            "content": entry.get("content", "")
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

if __name__ == '__main__':
    # Make sure to create 'static' and 'templates' directories
    os.makedirs('static', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Initialize data on startup
    initialize_data()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
