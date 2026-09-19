#!/usr/bin/env python3
from __future__ import annotations
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8")) or {}
interval = CFG.get("schedule", {}).get("interval", "30m").lower().strip()

m = re.fullmatch(r"(\d+)(m|h|d)", interval)
if not m:
    raise SystemExit(f"Invalid schedule.interval: {interval}")

n = int(m.group(1))
unit = m.group(2)

if unit == "m":
    if n < 5 or n > 59:
        raise SystemExit("Minute interval must be between 5m and 59m for GitHub Actions.")
    cron = f"*/{n} * * * *"
elif unit == "h":
    if n < 1 or n > 23:
        raise SystemExit("Hour interval must be between 1h and 23h.")
    cron = f"0 */{n} * * *"
else:
    if n < 1 or n > 7:
        raise SystemExit("Day interval must be between 1d and 7d.")
    cron = f"0 0 */{n} * *"

print(cron)
