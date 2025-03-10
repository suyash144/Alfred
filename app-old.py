"""
Example Python program for iterative exploratory data analysis (EDA)
with an LLM using structured outputs via client.beta.chat.completions.parse.

This file demonstrates:
1. A Pydantic model (LLMResponse) to parse the LLM's response using the new SDK.
2. An iterative loop that:
   - Gathers conversation context,
   - Calls the LLM with a prompt,
   - Receives a text summary & code proposal,
   - Accepts user feedback or executes the code,
   - Records analysis steps and results in the conversation history,
   - Exits if the user types 'q'.

"""

import sys
import io
import os
import json
import matplotlib.pyplot as plt
import numpy as np
from pydantic import BaseModel
import openai

# We'll use IPython display utilities to render text in Markdown form:
from IPython.display import display, Markdown


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
    "analysis snippet that the user can run."
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
# Conversation history data structure
###############################################################################
conversation_history = []

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
        history_text.append(f"{role.upper()} SAYS: {content}")

    history_text_str = "\n".join(history_text)

    prompt = (
        "Below is the conversation so far, including user feedback and "
        "assistant’s previous analysis or error messages (if any). Then "
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
    completion = client.beta.chat.completions.parse(
        model=MODEL_NAME,
        messages=messages,
        response_format=LLMResponse
    )
    # Return the parsed LLMResponse object from the first choice
    return completion.choices[0].message.parsed

###############################################################################
# Main iterative analysis loop
###############################################################################
def analysis_loop(x):
    """
    Main loop that:
    - Repeatedly asks the LLM for an analysis proposal,
    - Lets the user provide feedback or accept,
    - Runs the code in a shared namespace,
    - Logs the steps in conversation_history,
    - Exits if user types 'q'.
    """
    # Make sure the dataset is available in the analysis namespace
    analysis_namespace["x"] = x

    # For demonstration, we retrieve the API key from a Colab "secrets" approach:
    client = openai.OpenAI(
        api_key=os.environ.get('API_KEY'),  # or set your openai.api_key another way
    )

    while True:
        # 1. Build prompt from conversation history
        prompt = build_llm_prompt(conversation_history)

        # 2. Call LLM to parse response into LLMResponse
        llm_response = call_llm_and_parse(client, prompt)

        # 3. Show the LLM's proposal (in Markdown)
        print("\n===== LLM's Summary and Proposal =====\n")
        display(Markdown(llm_response.text_summary))

        print("\n===== Proposed Code =====\n")
        # We'll also show the code as Markdown for nicer formatting:
        display(Markdown(f"python\n{llm_response.python_code}\n"))
        print("======================================\n")

        # 4. Get user feedback
        user_feedback = input("Enter feedback for the LLM, press return to accept and run code, or type 'q' to quit:\n")

        # If user typed 'q', break from the loop
        if user_feedback.strip().lower() == 'q':
            print("Exiting analysis loop.")
            break

        # If user just presses return, accept & execute the code
        if user_feedback.strip() == "":
            # Execute the code
            output_text, figures, had_error = run_and_capture_output(llm_response.python_code)

            if had_error:
                # Log the error
                conversation_history.append({
                    "role": "assistant",
                    "content": "Executed code"
                })
                conversation_history.append({
                    "role": "assistant",
                    "content": "Error while running code:\n" + output_text
                })
                print("----- Error Output -----")
                print(output_text)
            else:
                # Log successful execution
                conversation_history.append({
                    "role": "assistant",
                    "content": "Executed code"
                })
                # Display any text output
                if output_text.strip():
                    conversation_history.append({
                        "role": "assistant",
                        "content": "Code Output:\n" + output_text
                    })
                    print("----- Code Output -----")
                    print(output_text)
                # Display figures inline
                for fig in figures:
                    fig.show()

        else:
            # The user typed feedback (non-empty, non-q). Code is NOT executed.
            # So we log the LLM summary, proposed code, and user feedback.
            conversation_history.append({
                "role": "assistant",
                "content": llm_response.text_summary
            })
            conversation_history.append({
                "role": "assistant",
                "content": "Proposed code:\n" + llm_response.python_code
            })
            conversation_history.append({
                "role": "user",
                "content": user_feedback
            })

def main():
    """
    Example main function.
    Generates a 2D numpy array from specified distributions,
    then starts the interactive EDA loop.
    """
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

    # Start the analysis loop
    analysis_loop(x)


