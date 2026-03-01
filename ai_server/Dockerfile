# Use NVIDIA CUDA base image for GPU support
FROM pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime

# Set working directory
WORKDIR /app

# Install system dependencies
# ffmpeg is required for audio processing
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
# Upgrade pip first to avoid build errors
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy application code
COPY app.py .

# Create directories
RUN mkdir -p uploads generated

# Expose port
EXPOSE 5000

# Run the application
CMD ["python", "app.py"]
