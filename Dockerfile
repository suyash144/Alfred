# Stage 1: Build React frontend
FROM node:18 AS build-react

# Set the working directory for the frontend build
WORKDIR /app/frontend

# Copy package.json and lock file first to leverage Docker cache
COPY ./alfred-react-app/package.json ./alfred-react-app/package-lock.json* ./

# Install frontend dependencies
RUN npm install

# Copy the rest of the React app source code
COPY ./alfred-react-app/ ./

# Build the React app for production
RUN npm run build

# Stage 2: Build Python backend and serve React build
FROM python:3.11-slim

# Set working directory for the Flask app
WORKDIR /app

# Copy requirements file first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY utils.py .
COPY data_loader.py .
COPY prompts.py .
COPY flask_routes.py .
COPY gunicorn_config.py .

# Copy the built React app from the 'build-react' stage
COPY --from=build-react /app/frontend/dist ./build

# Make the necessary directories for the app to run
RUN mkdir -p uploads analyses figs

# Expose the port Flask runs on
EXPOSE 5000

# Set environment variables (DEBUG=True might be overridden by docker-compose)
# ENV DEBUG=True

CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
