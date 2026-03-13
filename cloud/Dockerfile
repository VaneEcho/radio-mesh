FROM python:3.11-slim

WORKDIR /app

COPY cloud/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole project so `cloud` is a package importable as `cloud.*`
COPY . /app

CMD ["uvicorn", "cloud.main:app", "--host", "0.0.0.0", "--port", "8000"]
