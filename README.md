# Alfred
![image](https://github.com/user-attachments/assets/28cc3f43-9ad9-466e-bf63-ba1242296da1)



A simple Python and Docker-based app for iterative data analysis using an LLM.

### Usage

Install Docker and WSL.

Clone this repository and then navigate in the terminal to the directory where it is saved. Then run

    docker-compose up --build

When you open the application, make sure to use the correct API key for the model you select.

### Setting API keys as environment variables (optional)

If you don't want to keep pasting your API key for each analysis, you can set API keys as environment variables and just select the model at runtime. 
There are currently 4 supported LLMs from 3 different providers: 
 - GPT-4o and o1 from OpenAI
 - Claude 3.7 Sonnet from Anthropic
 - Gemini 2.5 Pro from Google

Each provider will give you an API key to use their models. To set your Gemini API key, run this:

    set API_KEY_GEM=YOUR-GEMINI-API-KEY

To set your API key for Claude, run this:

    set API_KEY_ANT=YOUR-ANTHROPIC-API-KEY

And to set your API key for either of the OpenAI models, run this:

    set API_KEY_OAI=YOUR-OPENAI-API-KEY

You can set all of these at the beginning and then use a different model each time you restart, without ever having to paste your API key into the GUI.


The application will run in localhost:5000.
