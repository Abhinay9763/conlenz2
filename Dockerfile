FROM python:3.11-slim

# Install system dependencies required for OpenCV and EasyOCR
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
# We can remove PySide6 from the docker install since this is headless CLI only,
# but to be safe and avoid missing imports, we'll keep it or filter it out.
# Let's just install everything to ensure compatibility.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the obfuscated app folder
COPY app /app/app

# The entrypoint script for GitHub Actions
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
