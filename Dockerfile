FROM python:3.12-alpine

RUN apk add --no-cache git ca-certificates

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# 默认常驻定时同步入口（每日 00:00/12:00）；也可在 Zeabur Start Command 覆盖
CMD ["python", "./scripts/run_sync_hourly.py"]
