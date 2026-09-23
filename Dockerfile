FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN useradd --system --uid 10001 --create-home proofflow \
    && mkdir -p /app/private_data \
    && chown -R proofflow:proofflow /app/private_data
USER proofflow
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
