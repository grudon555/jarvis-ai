FROM python:3.11-slim

WORKDIR /app

# System deps for faster-whisper / sounddevice
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist skills and DB across restarts
VOLUME ["/app/skills", "/app/.jarvis_db"]

EXPOSE 8000

CMD ["python", "server.py"]
