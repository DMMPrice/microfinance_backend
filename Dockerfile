# Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    default-libmysqlclient-dev \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose FastAPI port (inside container)
EXPOSE 5050

# Run FastAPI (PROD mode → no --reload)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5050", "--workers", "4"]
