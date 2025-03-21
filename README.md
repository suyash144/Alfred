﻿# Alfred

A simple Python and Docker-based app for iterative data analysis using an LLM.

Alfred is Automatic LLM For Research and Exploring Data

### Usage

Install Docker and WSL.

Clone this repository and then navigate in the terminal to the directory where it is saved.

Use your personal API key by running

    set API_KEY=YOUR-API-KEY 

in the terminal. Optionally, you can also set the model to o1 or claude like this:

    set MODEL=o1

or

    set MODEL=claude

Otherwise, GPT-4o will be used. You can reset to 4o by setting MODEL=4o. Make sure you set the correct API key for the model you want to use. Then run
 
    docker-compose up --build

The application will run in localhost:5000.
