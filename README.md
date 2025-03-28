# Alfred

A simple Python and Docker-based app for iterative data analysis using an LLM.

Alfred is Automatic LLM For Research and Exploring Data

### Usage

Install Docker and WSL.

Clone this repository and then navigate in the terminal to the directory where it is saved.

Use your personal API key by running

    set API_KEY=YOUR-API-KEY 

in the terminal. The options for the LLM backbone of Alfred are GPT-4o, o1, Gemini 2.5 or Claude 3.7 Sonnet. The codes for to use these are (respectively) ```4o```, ```o1```, ```gemini``` and ```claude```.
Set the model as follows:

    set MODEL=MODEL-NAME

Otherwise, GPT-4o will be used. You can reset to 4o by setting MODEL=4o. Make sure you set the correct API key for the model you want to use. Then run
 
    docker-compose up --build

The application will run in localhost:5000.
