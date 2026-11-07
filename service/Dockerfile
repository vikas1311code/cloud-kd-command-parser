FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir --retries 10 --timeout 120 torch==2.5.1+cpu --extra-index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 10 --timeout 120 -r requirements.txt
COPY app.py schema.json ./
ENV HF_HOME=/tmp/hf
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
