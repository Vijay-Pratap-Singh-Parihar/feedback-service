FROM python:3.10-slim

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

COPY . /app/

RUN apt-get update \
    && apt-get install -y libpq-dev gcc \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 8001

CMD ["/bin/bash", "-c", "sleep 10 && uvicorn main:app --host 0.0.0.0 --port 8001"]