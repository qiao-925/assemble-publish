FROM python:3.12-alpine

RUN apk add --no-cache git ca-certificates

WORKDIR /app

# 将临时目录指向可挂载的大空间卷；容器启动时可用 -v /host/bigdisk:/data 覆盖
ENV TMPDIR=/data/assemble-tmp
RUN mkdir -p "$TMPDIR" && chmod 777 "$TMPDIR"

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# 默认常驻定时同步入口（每日 00:00/12:00）；也可在 Zeabur Start Command 覆盖
CMD ["python", "./scripts/run_sync_hourly.py"]
