FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/goldtrader-pro-core
WORKDIR /app
COPY GoldTraderProCloud/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip && python -m pip install --no-cache-dir -r /app/requirements.txt
COPY GoldTraderProDesktop/core /opt/goldtrader-pro-core/core
COPY GoldTraderProCloud/app /app/app
RUN mkdir -p /data && useradd --system --uid 10001 --home-dir /app appuser && chown -R appuser:appuser /app /data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
