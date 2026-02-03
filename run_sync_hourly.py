#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def sleep_to_next_hour() -> int:
    now = datetime.now()
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    sleep_seconds = int((next_hour - now).total_seconds())
    if sleep_seconds <= 0:
        sleep_seconds = 1
    return sleep_seconds


def run_once(args: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPT_DIR / "run_sync.py"), *args]
    try:
        subprocess.run(cmd, check=True)
        print("[ok] sync done")
        return 0
    except subprocess.CalledProcessError:
        print("[warn] sync failed, will retry next hour")
        return 1


def main() -> int:
    args = sys.argv[1:]
    print("[info] run immediately")
    run_once(args)

    while True:
        sleep_sec = sleep_to_next_hour()
        print(f"[info] next run in {sleep_sec}s")
        time.sleep(sleep_sec)
        print("[info] hourly trigger")
        run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
