FROM python:3.11-slim

WORKDIR /app

COPY services/ui/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/ui /app/services/ui

ENV PYTHONPATH=/app

CMD ["streamlit", "run", "/app/services/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
