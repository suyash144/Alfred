import sys, os, io
import matplotlib.pyplot as plt
from pydantic import BaseModel
import uuid
from flask import session
import json
import openai
import anthropic
from google import genai
from google.genai import types
import re
import base64
import logging
import signal
import dill
from prompts import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Log to stderr
    ]
)
logger = logging.getLogger('alfred')
logging.getLogger('werkzeug').setLevel(logging.WARNING)

ALLOWED_EXTENSIONS = {'csv', 'npy', 'json'}
user_states = {}


###############################################################################
# Class to contain the state of the application
###############################################################################
class AppState:
    """
    Centralized container for application state.
    This contains variables that are needed throughout the application but
    are specific to an instance.
    """
    def __init__(self):
        # State variables that were previously globals
        self.conversation_history = []
        self.active_executions = {}
        self.execution_results = {}
        self.iteration_count = 0
        self.analysis_namespace = {}
        self.api_key = None
        self.model = "gemini"           # default model
        self.MODEL_NAME = "gemini-2.5-pro-exp-03-25"

###############################################################################
# Pydantic model for the LLM's structured output
###############################################################################
def get_user_state():
    """Fetch or create a new state for the current user."""
    # Ensure the user has a unique session ID
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    session_id = session['session_id']
    
    # If this session does not have a state yet, create one
    if session_id not in user_states:
        user_states[session_id] = AppState()  # Assuming AppState is your Alfred state container
    return user_states[session_id]

###############################################################################
# Pydantic model for the LLM's structured output
###############################################################################
class LLMResponse(BaseModel):
    text_summary: str
    python_code: str

###############################################################################
# Extract the actual base64 data from the data URL format
###############################################################################
def extract_base64_from_data_url(data_url):
    # Find where the actual base64 data begins after the prefix
    base64_start = data_url.find("base64,") + len("base64,")
    # Return only the base64 part
    return data_url[base64_start:]

###############################################################################
# Build the prompt for the LLM
###############################################################################
def build_llm_prompt(conversation_history, MODEL_NAME, response_type):
    """
    Build a prompt for the LLM, incorporating the current conversation history.
    For text entries, we maintain the existing format.
    For figure entries, we handle them specially to be passed as images.
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

    if response_type == "code":
        now_cont = NOW_CONTINUE_CODE
    elif response_type == "feedback":
        now_cont = NOW_CONTINUE_FDBK
    elif response_type == "both":
        now_cont = NOW_CONTINUE_BOTH
    else:
        now_cont = NOW_CONTINUE_TEXT
    
    # Create the text prompt
    text_prompt = (
        "Below is the conversation so far, including user feedback and "
        "assistant's previous analysis or error messages (if any). Then "
        "provide your new output:\n\n"
        f"{history_text_str}\n\n"
        f"{now_cont}\n"
    )
    
    # Add the text as the first content part
    content_parts.append({
        "type": "text",
        "text": text_prompt
    })
    
    # Now add any figures from the conversation
    for entry in conversation_history:
        if entry.get("role") == "figure":
            fig_content = entry.get("content")          # this is a dictionary
            url_dict = fig_content["image_url"]
            fig_content = url_dict["url"]
            
            # If the content is a matplotlib figure
            if isinstance(fig_content, plt.Figure):
                base64_img = fig_to_base64(fig_content)
            
            # If the content is a base64 string already
            elif isinstance(fig_content, str) and fig_content.startswith("data:image"):
                base64_img = fig_content
            
            if MODEL_NAME.startswith('claude'):
                if base64_img.startswith("data:image"):
                    content_parts.append({
                        "type": "image",
                        "source":{
                            "type": "base64",
                            "media_type":"image/png",
                            "data": extract_base64_from_data_url(base64_img)
                        }
                    })
                else:
                    content_parts.append({
                        "type": "image",
                        "source":{
                            "type": "base64",
                            "media_type":"image/png",
                            "data": base64_img
                        }
                    })

            elif MODEL_NAME.startswith('gemini'):
                content_parts.append(types.Part.from_bytes(
                        mime_type = 'image/png',
                        data = base64.b64decode(extract_base64_from_data_url(base64_img))
                    )
                )

            else:
                if base64_img.startswith("data:image"):
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": fig_content
                        }
                    })
                else:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_img}"
                        }
                    })
    
    return content_parts

###############################################################################
# Execute code in shared namespace, capturing stdout, figures, and errors
###############################################################################
def run_code_in_process(code, analysis_namespace, pipe_conn):
    """
    Run code in a separate process.
    
    Args:
        code (str): The code to execute
        analysis_namespace (dict): Shared namespace for analysis
        pipe_conn (multiprocessing.Connection): Pipe connection to send results back
    """
    # We need to redirect stdout to capture output
    import sys, io
    import matplotlib.pyplot as plt
    
    # Configure signal handling for graceful termination
    def handle_terminate(signum, frame):
        pipe_conn.send(("TERMINATED", None, None, True))
        pipe_conn.close()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, handle_terminate)
    
    # Redirect stdout
    old_stdout = sys.stdout
    redirected_output = io.StringIO()
    sys.stdout = redirected_output
    
    # Close any existing figures
    plt.close('all')
    
    figures = []
    error_flag = False
    
    try:
        # Execute the code
        exec(code, analysis_namespace)
        
        # Collect figures
        for i in plt.get_fignums():
            fig = plt.figure(i)
            figures.append(fig)
    
    except Exception as e:
        error_flag = True
        print(f"Execution Error: {str(e)}")
    
    finally:
        # Get the captured output
        sys.stdout = old_stdout
        output_text = redirected_output.getvalue()
        
        # If no output was generated, provide a helpful message
        if len(output_text) == 0 and len(figures) == 0:
            output_text = "Please make sure your code prints something to stdout or generates some figures."
    
    # Send results back through the pipe
    pipe_conn.send((output_text, figures, None, error_flag, dill.dumps(analysis_namespace)))
    pipe_conn.close()

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
    
    logger.debug(f"Collected {len(figs)} matplotlib figures")
    return figs

###############################################################################
# Functions to safely load JSON from LLM output
###############################################################################
def extract_json_dict(text):
    """
    Extract a potential JSON dictionary by removing any text before the first '{' and after the last '}'.
    
    Args:
        text (str): Input string that may contain a JSON dictionary.
        
    Returns:
        tuple: (is_valid, result)
            is_valid (bool): True if a valid JSON dictionary was extracted
            result (dict or str): Extracted dictionary if valid, original extracted string if not
    """
    # Find the first opening brace
    start_index = text.find('{')
    if start_index == -1:
        logger.warning("No JSON dictionary found in LLM response")
        return {"text_summary":"No JSON dictionary found - please ensure your response is a valid JSON dictionary."}
    
    # Find the last closing brace
    end_index = text.rfind('}')
    if end_index == -1:
        logger.warning("No JSON dictionary found in LLM response")
        return {"text_summary":"No JSON dictionary found - please ensure your response is a valid JSON dictionary."}
    
    # Extract the potential dictionary
    potential_dict = text[start_index:end_index+1]
    
    return potential_dict

# Fix the invalid escape sequences in JSON strings
def fix_json_escapes(json_str):
    """
    Finds and removes invalid escape characters and control characters in JSON strings.
    
    Args:
        json_str (str): JSON string that may contain invalid escape sequences
                        or unescaped control characters
        
    Returns:
        str: Fixed JSON string with invalid sequences removed
    """
    if not json_str:
        return json_str
        
    # JSON only allows these escape sequences
    valid_json_escapes = {
        '"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'
    }
    
    result = []
    i = 0
    in_string = False

    json_str = json_str.replace('\import', '\nimport')
    
    while i < len(json_str):
        char = json_str[i]
        
        # Track when we're inside a JSON string (which must be double-quoted)
        if char == '"' and (i == 0 or json_str[i-1] != '\\'):
            in_string = not in_string
        
        # Handle control characters (ASCII 0-31)
        if in_string and ord(char) < 32:
            # Control character in string - replace with appropriate escape or remove
            if char == '\b':
                result.append('\\b')
            elif char == '\f':
                result.append('\\f')
            elif char == '\n':
                result.append('\\n')
            elif char == '\r':
                result.append('\\r')
            elif char == '\t':
                result.append('\\t')
            else:
                # Other control chars should be escaped as \uXXXX
                hex_value = format(ord(char), '04x')
                result.append(f'\\u{hex_value}')
        # Handle invalid escapes
        elif in_string and char == '\\' and i + 1 < len(json_str):
            next_char = json_str[i+1]
            
            # Check if it's a valid JSON escape
            if next_char in valid_json_escapes:
                # Special handling for unicode escapes \uXXXX
                if next_char == 'u':
                    if i + 5 < len(json_str) and all(c.lower() in '0123456789abcdef' for c in json_str[i+2:i+6]):
                        # Valid unicode escape, keep it
                        result.append(char)
                    else:
                        # Invalid unicode escape, remove backslash
                        pass
                else:
                    # Valid standard escape, keep it
                    result.append(char)
            else:
                # Invalid escape, omit the backslash
                pass
        else:
            # Regular character or backslash at the end of string, keep it
            result.append(char)
        
        i += 1
    
    return ''.join(result)

# Add a function to safely parse JSON
def safe_json_loads(json_str):
    """
    Safely parses JSON by first fixing invalid escape sequences and control characters.
    
    Args:
        json_str (str): JSON string that may contain invalid escape sequences
                        or unescaped control characters
        
    Returns:
        dict/list: Parsed JSON object
        
    Raises:
        ValueError: If JSON cannot be parsed even after fixing problematic sequences
    """

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        error_message = str(e)
        logger.warning(f"Initial JSON parsing failed: {error_message}")
        
        # Check for common JSON parsing errors we can fix
        needs_fixing = any([
            "Invalid \\escape" in error_message,
            "Invalid escape" in error_message,
            "Invalid control character" in error_message,
            "control character" in error_message,
            "character U+" in error_message and "is not allowed" in error_message
        ])
        
        if needs_fixing:
            # Fix invalid escapes and control characters, then try again
            logger.info("Attempting to fix JSON escape sequences")
            fixed_json = fix_json_escapes(json_str)
            try:
                return json.loads(fixed_json)
            except json.JSONDecodeError as e2:
                logger.warning(f"JSON parsing still failed after fixing escapes: {str(e2)}")
                # If still failing, try a more aggressive approach - strip all control chars
                try:
                    import re
                    logger.info("Attempting aggressive JSON fix - stripping control characters")
                    # Strip all control characters outside of strings
                    aggressive_fix = re.sub(r'[\x00-\x1F]', '', fixed_json)
                    return json.loads(aggressive_fix)
                except json.JSONDecodeError as e3:
                    error_pos = e3.pos
                    context = aggressive_fix[max(0, error_pos-20):min(len(aggressive_fix), error_pos+20)]
                    logger.error(f"All JSON parsing attempts failed: {str(e3)}")
                    raise ValueError(f"Could not parse JSON even after fixes: {str(e3)}\nError near: {context}")
        
        elif "Unterminated string" in error_message:
            # Attempt to fix by adding a closing quote at the end
            logger.info("Attempting to fix JSON by adding a closing quote")
            fixed_json = json_str + r'"'
            try:
                return json.loads(fixed_json)
            except json.JSONDecodeError as e2:
                logger.error(f"Adding closing quote did not fix JSON parsing: {str(e2)}")
                raise ValueError(f"JSON parsing error: {error_message}")
        else:
            # Some other JSON parsing error
            logger.error(f"JSON parsing failed with error: {error_message}")
            raise ValueError(f"JSON parsing error: {error_message}")

###############################################################################
# Actual LLM call to parse response
###############################################################################
def call_llm_and_parse(client, prompt, MODEL_NAME, response_type):
    """
    Calls the LLM client to parse the response into LLMResponse
    using the JSON schema automatically.
    
    Args:
        client: LLM client (OpenAI, Google or Anthropic)
        prompt: List of content parts for the prompt
        MODEL_NAME: Name of the model to use
        response_type: Type of response to expect (text, code, feedback, both)
    
    Returns:
        LLMResponse: Parsed response from the LLM
        or just the response content if we don't need the JSON structured response
    """
    
    if MODEL_NAME.startswith('claude'):
        messages = [
            {"role": "user", "content": prompt}
        ]
        completion = client.messages.create(
            model=MODEL_NAME,
            system=SYSTEM_PROMPT,
            messages=messages,
            max_tokens=5000
        )
        response_content = completion.content[0].text
        if response_type == "both":
            response_content = re.sub(r'^```json\s*|\s*```$', '', response_content, flags=re.MULTILINE)
            response_content = extract_json_dict(response_content)

    elif MODEL_NAME.startswith('gemini'):
        text = prompt[0]["text"]
        parts = [types.Part.from_text(text=text)]
        for msg in prompt[1:]:
            parts.append(msg)

        contents = types.Content(
            role = "user",
            parts = parts
        )

        if response_type == "both":
            gen_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                system_instruction=[
                    types.Part.from_text(text=SYSTEM_PROMPT),
                ],
            )
        else:
            gen_config = types.GenerateContentConfig(
                system_instruction=[
                    types.Part.from_text(text=SYSTEM_PROMPT),
                ],
            )
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=gen_config
        )
        response_content = response.text

    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        if response_type == "both":
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                response_format={"type": "json_object"}
            )

        else:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages = messages
            )
        
        response_content = completion.choices[0].message.content
    
    if response_type == "both":
        try:
            parsed_response = safe_json_loads(response_content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            if "Invalid \escape" in str(e):
                parsed_response = {"text_summary":"Invalid escape sequence found in JSON response. Please correct this."}
            else:
                parsed_response = {"text_summary":"JSONDecodeError. Please correct this."}
                logger.error(f"Raw response: {response_content}")
        
        # Convert to LLMResponse
        llm_response = LLMResponse(
            text_summary=parsed_response.get("text_summary", ""),
            python_code=parsed_response.get("python_code", "")
        )
        # Return the parsed LLMResponse object
        return llm_response

    elif response_type == "code":
        if "```python" in response_content:
            response_content = response_content[response_content.find("```python")+10:]
        if response_content.endswith("```"):
            response_content = response_content.rsplit("```", 1)[0]
    
    else:
        return response_content

###############################################################################
# Functions to get LLM clients
###############################################################################
def get_client(model_name, api_key=None):
    """Returns the appropriate client based on the model name"""

    if not api_key:
        api_key = get_api_key(model_name)
        if not api_key:
            logger.error("No API key provided")
            raise ValueError("API_KEY is required")
    
    if model_name=="4o" or model_name=="o1":
        return openai.OpenAI(api_key=api_key)
    elif model_name=="claude":
        client = anthropic.Anthropic(api_key=api_key)
        return client
    elif model_name=="gemini":
        client = genai.Client(api_key=api_key)
        return client
    else:
        logger.error(f"Invalid model name: {model_name}")
        raise ValueError("Invalid model name - choose 4o, o1, gemini or claude")

###############################################################################
# Function to get API key from environment variables
###############################################################################
def get_api_key(model):
    if model == "claude":
        return os.environ.get('API_KEY_ANT', None)
    elif model == "gemini":
        return os.environ.get('API_KEY_GEM', None)
    elif model == "4o" or model == "o1":
        return os.environ.get('API_KEY_OAI', None)
    else:
        return None

###############################################################################
# Function to convert matplotlib figure to base64 for web display
###############################################################################
def fig_to_base64(fig):
    """Convert matplotlib figure to base64 string for web display"""
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode('utf-8')
    return img_str

###############################################################################
# Check if filename is allowed
###############################################################################
def allowed_file(filename):
    """Check if a filename has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


