#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def next_run_time(now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_noon = now.replace(hour=12, minute=0, second=0, microsecond=0)

    candidates = [today_noon, today_midnight]
    future = [dt for dt in candidates if dt > now]
    if future:
        return min(future)
    return today_midnight + timedelta(days=1)


def sleep_to_next_run() -> tuple[int, datetime]:
    now = datetime.now()
    next_run = next_run_time(now)
    sleep_seconds = int((next_run - now).total_seconds())
    if sleep_seconds <= 0:
        sleep_seconds = 1
    return sleep_seconds, next_run


def run_once(args: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPT_DIR / "run_sync.py"), *args]
    try:
        subprocess.run(cmd, check=True)
        print("[ok] sync done")
        return 0
    except subprocess.CalledProcessError:
        print("[warn] sync failed, will retry at next scheduled time")
        return 1


def main() -> int:
    args = sys.argv[1:]
    print("[info] run immediately")
    run_once(args)

    while True:
        sleep_sec, next_run = sleep_to_next_run()
        next_label = next_run.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[info] next run at {next_label} (in {sleep_sec}s)")
        time.sleep(sleep_sec)
        print("[info] scheduled trigger")
        run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
