#!/usr/bin/env python3
"""IMAP LOGIN with the real user password via curl (143 then 993)."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def curl_imap(url: str, email: str, password: str, extra: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "--max-time",
            "15",
            *extra,
            "--url",
            url,
            "--user",
            f"{email}:{password}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out


def looks_ok(rc: int, text: str) -> bool:
    upper = text.upper()
    if "NO LOGIN" in upper or "AUTHENTICATIONFAILED" in upper:
        return False
    return rc == 0


def imaplib_login(email: str, password: str) -> dict:
    import imaplib
    import ssl

    try:
        client = imaplib.IMAP4("127.0.0.1", 143, timeout=15)
        typ, _data = client.login(email, password)
        try:
            client.logout()
        except Exception:
            pass
        if typ == "OK":
            return {"ok": True, "port": 143, "error": ""}
    except Exception as exc:
        err_plain = str(exc)
    else:
        err_plain = "LOGIN not OK"
    try:
        ctx = ssl._create_unverified_context()
        client = imaplib.IMAP4_SSL("127.0.0.1", 993, ssl_context=ctx, timeout=15)
        typ, _data = client.login(email, password)
        try:
            client.logout()
        except Exception:
            pass
        if typ == "OK":
            return {"ok": True, "port": 993, "error": ""}
        return {"ok": False, "port": 0, "error": f"993 {typ}"}
    except Exception as exc:
        return {"ok": False, "port": 0, "error": f"{err_plain}; 993 {exc}"[:500]}


def try_login(email: str, password: str) -> dict:
    rc, out = curl_imap("imap://127.0.0.1:143/INBOX", email, password, [])
    if looks_ok(rc, out):
        return {"ok": True, "port": 143, "error": ""}
    err_143 = f"143 rc={rc} {out.strip()[:200]}"

    rc, out = curl_imap("imaps://127.0.0.1:993/INBOX", email, password, ["-k"])
    if looks_ok(rc, out):
        return {"ok": True, "port": 993, "error": ""}
    err_993 = f"993 rc={rc} {out.strip()[:200]}"
    fallback = imaplib_login(email, password)
    if fallback["ok"]:
        return fallback
    extra = fallback.get("error", "")
    return {"ok": False, "port": 0, "error": f"{err_143}; {err_993}; {extra}"[:500]}


def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else ""
    password = os.environ.get("IW_SMOKE_PASSWORD", "")
    if not email or not password:
        print(json.dumps({"ok": False, "port": 0, "error": "usage: imap_login.py email (password via IW_SMOKE_PASSWORD)"}))
        return 2
    result = try_login(email, password)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
