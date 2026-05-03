FROM python:3.13-slim

# Install Node.js 20
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Build React frontend
COPY frontend/package*.json frontend/
RUN npm --prefix frontend install
COPY frontend/ frontend/
RUN npm --prefix frontend run build

# Copy app code
COPY api/ api/
COPY wsgi.py .

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT -w 2 --timeout 120 wsgi:app"]
