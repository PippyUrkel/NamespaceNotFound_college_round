# CrisisGrid Reproducible ML Execution Environment
# Base container image: crisisgrid-ml-base:latest
#
# Build with:
#   docker build -t crisisgrid-ml-base:latest .

FROM python:3.11-slim

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TORCH_HOME=/cache/torch \
    HF_HOME=/cache/huggingface \
    PIP_CACHE_DIR=/cache/pip

# Install necessary system build tools and libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create execution workspace and shared caches with permissive permissions for container workers
RUN mkdir -p /workspace /workspace/data /workspace/output /cache /cache/pip /cache/torch /cache/huggingface /cache/data && \
    chmod -R 777 /workspace /cache

WORKDIR /workspace

# Install PyTorch CPU wheels
RUN pip install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install standard core scientific and ML packages
RUN pip install --no-cache-dir \
    numpy \
    scipy \
    scikit-learn \
    pandas \
    pillow \
    psutil \
    sympy \
    networkx \
    jinja2 \
    requests \
    tqdm \
    fsspec \
    filelock

# Ensure permissions remain permissive for container runtime mounts
RUN chmod -R 777 /workspace /cache

CMD ["python3", "-c", "import torch, torchvision, numpy, sklearn, scipy, pandas, psutil; print('CrisisGrid ML Base container image is ready and verified!')"]
