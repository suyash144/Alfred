import sys, os, io
import matplotlib.pyplot as plt
from pydantic import BaseModel
import json
import openai
import base64


# MODEL_NAME = "gpt-4o-2024-11-20"
if os.environ.get('MODEL')=="4o":
    MODEL_NAME = "gpt-4o-2024-11-20"
elif os.environ.get('MODEL')=="o1":
    MODEL_NAME = "o1-2024-12-17"
elif os.environ.get('MODEL')=="claude":
    MODEL_NAME = "claude-3-7-sonnet-20250219"
else:
    MODEL_NAME = "gpt-4o-2024-11-20"

SYSTEM_PROMPT = (
    "You are a helpful assistant designed to perform iterative exploratory data "
    "analysis on a 2D numpy array, stored in the variable 'x'. On each step, you must output valid JSON that "
    "follows the LLMResponse schema (two fields: 'text_summary' and 'python_code'). "
    "Do not output extra keys or any text outside the JSON. Your 'text_summary' "
    "should describe your current understanding of the data, your working hypotheses, "
    "and your next proposed analysis. Your 'python_code' should be a single Python "
    "analysis snippet that the user can run. It is crucial that your code outputs something as this is what"
    "you will receive as your next prompt. The Python snippet must also include any required import statements."
)

# This is the fixed part of the user prompt appended at the end of conversation history
NOW_CONTINUE_TEXT = (
    "Now continue with a new step: Summarize what is known so far about the data, "
    "propose 5 or so working hypotheses, and suggest code for a single analysis step."
)

###############################################################################
# Global analysis namespace for executed code (retains state across iterations)
###############################################################################
analysis_namespace = {}

###############################################################################
# Global conversation history
###############################################################################
conversation_history = []

###############################################################################
# Pydantic model for the LLM's structured output
###############################################################################
class LLMResponse(BaseModel):
    text_summary: str
    python_code: str

###############################################################################
# Build the prompt for the LLM
###############################################################################
def build_llm_prompt(conversation_history):
    """
    Build a prompt for the LLM, incorporating the current conversation history.
    For text entries, we maintain the existing format.
    For figure entries, we now handle them specially to be passed as images.
    """
    # We'll store content parts for the final user message
    content_parts = []
    # And normal text history for context as before
    history_text = []
    
    # First build the text history as before for context
    for entry in conversation_history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        
        # Add special handling for figure entries in the text representation
        if role == "figure":
            history_text.append(f"ASSISTANT SAYS: [Generated a figure]")
        else:
            history_text.append(f"{role.upper()} SAYS: {content}")

    history_text_str = "\n".join(history_text)

    # Create the text prompt
    text_prompt = (
        "Below is the conversation so far, including user feedback and "
        "assistant's previous analysis or error messages (if any). Then "
        "provide your new output:\n\n"
        f"{history_text_str}\n\n"
        f"{NOW_CONTINUE_TEXT}\n"
    )
    
    # Add the text as the first content part
    content_parts.append({
        "type": "text",
        "text": text_prompt
    })
    
    # Now add any figures from the most recent part of the conversation
    for entry in conversation_history:
        if entry.get("role") == "figure":
            fig_content = entry.get("content")          # this is a dictionary
            url_dict = fig_content["image_url"]
            fig_content = url_dict["url"]
            
            # If the content is already a matplotlib figure
            if isinstance(fig_content, plt.Figure):
                base64_img = fig_to_base64(fig_content)
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_img}"
                    }
                })
            # If the content is a base64 string already
            elif isinstance(fig_content, str) and fig_content.startswith("data:image"):
                content_parts.append({
                    "type": "image_url",
                    "image_url": {
                        "url": fig_content
                    }
                })
    
    return content_parts

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

    if len(output_text) == 0 and len(figures) == 0:
        output_text = "Please make sure your code prints something to stdout or generates some figures. Otherwise you will not receive any information."

    return output_text, figures, error_flag

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
# Functions to get LLM clients
###############################################################################
def get_openai_client():
    return openai.OpenAI(
        api_key=os.environ.get('API_KEY'),
    )

def get_client(model_name):
    if model_name=="4o" or model_name=="o1":
        return get_openai_client()
    elif model_name=="claude":
        client = openai.OpenAI(
            api_key=os.environ.get('API_KEY'),
            base_url="https://api.anthropic.com/v1/"
        )
        return client

###############################################################################
# Function to convert matplotlib figure to base64 for web display
###############################################################################
def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode('utf-8')
    return img_str
