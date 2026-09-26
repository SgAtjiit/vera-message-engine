# =============================================================================
# Dockerfile for vera-bot FastAPI Application (Render Free Tier Ready)
# =============================================================================

# 1. Base Image: Lightweight Python 3.11 slim image
FROM python:3.11-slim

# 2. Environment settings:
# - PYTHONDONTWRITEBYTECODE: Disables creation of .pyc files
# - PYTHONUNBUFFERED: Ensures real-time stdout/stderr log streaming
# - PORT: Default fallback port (Render overrides this with dynamic $PORT)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# 3. Set container working directory
WORKDIR /app

# 4. Install system utilities (curl for container health probes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. Copy dependencies first for Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy application code and dataset contexts
COPY app/ ./app/
COPY dataset/ ./dataset/
COPY expanded/ ./expanded/
COPY config.py .
COPY bot.py .

# 7. Expose dynamic port variable
EXPOSE ${PORT}

# 8. Start uvicorn binding to 0.0.0.0:$PORT
# Uses shell exec form so $PORT is evaluated at runtime and uvicorn handles signals as PID 1
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
