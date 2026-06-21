FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# The platform provides $PORT (Railway/Render/Fly). Default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn baseline.api.app:create_app --factory --host 0.0.0.0 --port ${PORT}"]
