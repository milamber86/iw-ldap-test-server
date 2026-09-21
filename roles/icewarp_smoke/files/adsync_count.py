#!/usr/bin/env python3
"""Count ADSync 'Synchronizing domain <name> finished' lines in today's/yesterday's logs."""
from __future__ import annotations

import glob
import os
import sys
from datetime import datetime, timedelta


def log_files(log_dir: str, prefix: str, today: str, yesterday: str) -> list[str]:
    names = []
    if prefix:
        names.extend(glob.glob(os.path.join(log_dir, f"{prefix}{today}-*.log")))
        names.extend(glob.glob(os.path.join(log_dir, f"{prefix}{yesterday}-*.log")))
    else:
        names.extend(glob.glob(os.path.join(log_dir, f"*{today}-*.log")))
        names.extend(glob.glob(os.path.join(log_dir, f"*{yesterday}-*.log")))
    return sorted(set(names))


def count_and_last(files: list[str], needle: str) -> tuple[int, str, str]:
    count = 0
    last = ""
    last_path = ""
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if needle in line:
                        count += 1
                        last = line.rstrip("\n")
                        last_path = path
        except OSError:
            continue
    return count, last, last_path


def main() -> int:
    if len(sys.argv) < 3:
        print("0\t\t")
        return 2
    log_dir = sys.argv[1]
    domain = sys.argv[2]
    prefix = sys.argv[3] if len(sys.argv) > 3 else ""
    now = datetime.now()
    today = now.strftime("%Y%m%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y%m%d")
    needle = f"Synchronizing domain {domain} finished"
    files = log_files(log_dir, prefix, today, yesterday)
    count, last, last_path = count_and_last(files, needle)
    # stdout: count<TAB>path<TAB>line  (no secrets)
    print(f"{count}\t{last_path}\t{last}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
