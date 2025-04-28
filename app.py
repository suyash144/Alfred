# --- Keep your existing imports ---
from flask import Flask, request, jsonify, send_file, send_from_directory # Added send_from_directory
import os
from utils import *
from data_loader import *

# --- Configuration for serving React build ---
BUILD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build')
STATIC_FOLDER = os.path.join(BUILD_FOLDER, 'assets') # React build usually puts js/css in 'static'

# --- Initialize Flask App ---
app = Flask(__name__,
            static_folder=STATIC_FOLDER,
            template_folder=BUILD_FOLDER,
            static_url_path='/assets' # URL path for static files from React build
           )

from flask_routes import *

# --- Catch-All Route to Serve React App ---
# It serves the main index.html file for any path not handled by API routes.
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react_app(path):
    """Serves the React app's index.html for routing."""

    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        pass

    return send_from_directory(app.template_folder, 'index.html')


# --- Main Execution Block (for local development mainly) ---
if __name__ == '__main__':

    # Get debug flag from environment variable or default
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    # Start Flask app using development server (Gunicorn/Waitress used in Docker CMD)
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)