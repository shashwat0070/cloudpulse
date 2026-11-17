FROM python:3.14-slim

WORKDIR /service

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN useradd --create-home --uid 10001 cloudpulse
RUN mkdir -p /service/.cloudpulse \
    && chown cloudpulse:cloudpulse /service/.cloudpulse

COPY app ./app

USER cloudpulse

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]