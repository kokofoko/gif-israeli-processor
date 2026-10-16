FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir 'yt-dlp[default]==2026.08.19'
ENV PATH="/opt/venv/bin:$PATH" PORT=8080
WORKDIR /app
COPY server.py /app/server.py
RUN useradd --create-home processor
USER processor
EXPOSE 8080
CMD ["python3", "server.py"]
