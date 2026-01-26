# Use Python 3.12 slim image as base
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Update package lists
RUN apt-get update && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY web/ ./web/
COPY config/ ./config/

# Create logs directory
RUN mkdir -p logs

# Expose the web server port
EXPOSE 8000

# Set Python path to include src directory
ENV PYTHONPATH=/app/src

# Run the application from project root
# main.py adds src to sys.path, so this works correctly
# Using python directly since dependencies are already installed system-wide
CMD ["python", "src/main.py"]
