FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml MANIFEST.in ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY db ./db
COPY evals ./evals
COPY scripts/init_demo_data.py scripts/docker-entrypoint.sh ./scripts/
RUN chmod +x /app/scripts/docker-entrypoint.sh && mkdir -p data/artifacts data/logs data/evaluation
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["uvicorn","finance_insight.api:app","--host","0.0.0.0","--port","8000"]
