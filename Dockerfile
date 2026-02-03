FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .


ENV PYTHONUNBUFFERED=1

# 默认执行主仓库同步入口；Zeabur Cron 可直接复�?

CMD ["python", "./run_sync.py"]
