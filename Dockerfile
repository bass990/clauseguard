# ClauseGuard: one image serves the API and the built React UI.
#
#   docker build -t clauseguard .
#   docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... clauseguard          # live analysis
#   docker run -p 8000:8000 -e CLAUSEGUARD_DEMO=1 clauseguard                     # replay demo, no key needed
#
# Stage 1 builds the frontend; stage 2 is a slim Python runtime with
# Tesseract available for the optional OCR path.

FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ENV VITE_API_BASE=""
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt pytesseract Pillow
COPY config.py ./
COPY backend/ backend/
COPY sample_contracts/ sample_contracts/
COPY demo/ demo/
COPY --from=ui /ui/dist frontend/dist
RUN useradd -m app && mkdir -p uploads logs && chown -R app:app /app
USER app
EXPOSE 8000
ENV CLAUSEGUARD_CORS_ORIGINS="*" PORT=8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
