# Base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .
COPY templates/ templates/

# Create directories for templates and static files
RUN mkdir -p templates static

# Expose port
EXPOSE 5000

# Command to run the application
CMD ["python", "-u", "app.py"]
