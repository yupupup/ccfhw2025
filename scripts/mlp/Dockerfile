FROM pytorch/pytorch:2.1.2-cuda12.1-cudnn8-runtime

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# PyTorch is already installed in the base image, but we need pandas/scikit-learn
RUN pip install --no-cache-dir \
    pandas \
    numpy \
    scikit-learn

# Set the entrypoint to python
ENTRYPOINT ["python3"]
