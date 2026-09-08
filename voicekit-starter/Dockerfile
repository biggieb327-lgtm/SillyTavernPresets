FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source
COPY src/ src/

# Expose port
EXPOSE 8000

# Run server
CMD ["python", "-m", "voicekit.api", "--host", "0.0.0.0", "--port", "8000"]
