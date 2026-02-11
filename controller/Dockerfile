FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY controller/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY controller /app/controller
COPY shared /app/shared

# Create data and scenarios directories
RUN mkdir -p /app/data /app/scenarios

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:///./data/wipi.db
ENV SCENARIO_DIR=/app/scenarios

# Run the application
CMD ["python", "-m", "uvicorn", "controller.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
