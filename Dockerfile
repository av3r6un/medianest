FROM python:3.14-slim

ARG INSTALL_FFMPEG=1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && \
    if [ "$INSTALL_FFMPEG" = "1" ]; then \
      apt-get install -y --no-install-recommends ffmpeg; \
    fi && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8090

ENTRYPOINT ["/app/entrypoint.sh"]
