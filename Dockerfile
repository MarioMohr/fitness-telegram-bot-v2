FROM python:3.11-slim

# System Pakete installieren
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python Abhängigkeiten
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

CMD ["python", "app/main.py"]

