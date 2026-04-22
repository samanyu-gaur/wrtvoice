FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (ffmpeg and build-essential for psycopg2)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY database.py .
COPY app_cloud.py .
COPY modules/ modules/

# Copy static frontend if deployed on the same server, though Vercel is used
# COPY static/ static/

# Expose port (Render automatically assigns PORT env variable, defaulting to 8000 here)
EXPOSE 8000

# Start FastAPI application (Render injects $PORT dynamically)
CMD uvicorn app_cloud:app --host 0.0.0.0 --port ${PORT:-8000}
