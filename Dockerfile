FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.4
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app.py ./
COPY plan_ai.py ./
COPY scan.py ./
COPY worksheet_layout.py ./
COPY templates ./templates
COPY static ./static
ENV INSTANCE_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "app:create_app()"]
