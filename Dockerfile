FROM python:3.12-alpine

# Install bash and required packages
RUN apk add --no-cache \
    bash \
    build-base \
    cargo \
    gcc \
    git \
    linux-headers \
    musl-dev \
    rust && \
    addgroup -S appgroup && adduser -S appuser -G appgroup

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production

# Copy pyproject.toml first for better Docker layer caching
COPY pyproject.toml ./pyproject.toml
COPY app ./app


# Install dependencies and set up permissions
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir . \
    && chown -R appuser:appgroup /app \
    && chmod 755 app/repos \
    && chown appuser:appgroup app/repos \
    && chmod +x app/main.py

# Switch to the non-root user (this should be LAST)
USER appuser

ENTRYPOINT ["python","-m", "app.main"]