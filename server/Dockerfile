FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

# OPENAI_API_KEY is passed at runtime (docker run --env-file .env), never baked in.
EXPOSE 9999
CMD ["python", "main.py"]
