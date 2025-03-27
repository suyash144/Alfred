from flask import Flask, render_template, request, jsonify, send_file
import os
from utils import *
from data_loader import *
from flask_routes import *


if __name__ == '__main__':
    # Make sure to create 'static' and 'templates' directories
    os.makedirs('static', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
