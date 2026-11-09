FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY . .
RUN uv sync --frozen --no-dev
ENV DATABASE_URL=postgresql://recovery:recovery_local@db:5432/recovery
EXPOSE 8000
CMD ["sh", "-c", "uv run recovery demo && uv run uvicorn cart_recovery.api:app --host 0.0.0.0 --port 8000"]
