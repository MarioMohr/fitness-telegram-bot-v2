FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app/app

ENV PYTHONPATH=/app/app

EXPOSE 8888

CMD ["sh", "-c", "uvicorn app.webhook:app --host 0.0.0.0 --port 8888 & python app/frontend.py"]

