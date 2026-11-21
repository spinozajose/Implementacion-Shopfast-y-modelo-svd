FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/app.py api/openapi.py ./
EXPOSE 8000
# 1 worker + hilos: las métricas en memoria reflejan todo el servicio (ver README)
CMD ["gunicorn", "-w", "1", "--threads", "4", "-b", "0.0.0.0:8000", "--timeout", "30", "app:create_app()"]
