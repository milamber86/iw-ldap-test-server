#!/usr/bin/env python3
"""IMAP LOGIN with the real user password on localhost (UTF-8 LOGIN like telnet)."""
from __future__ import annotations

import json
import os
import re
import socket
import ssl
import sys


def imap_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def tagged_login(host: str, port: int, email: str, password: str, use_ssl: bool, timeout: float = 15.0) -> tuple[bool, str]:
    last_err = ""
    for mode in ("raw", "quoted", "literal"):
        if mode == "raw" and ("\r" in password or "\n" in password):
            continue
        ok, err = _login_once(host, port, email, password, use_ssl, timeout, mode)
        if ok:
            return True, ""
        last_err = err
    return False, last_err


def _login_once(
    host: str, port: int, email: str, password: str, use_ssl: bool, timeout: float, mode: str
) -> tuple[bool, str]:
    raw = socket.create_connection((host, port), timeout=timeout)
    sock: socket.socket
    if use_ssl:
        ctx = ssl._create_unverified_context()
        sock = ctx.wrap_socket(raw, server_hostname=host)
    else:
        sock = raw
    try:
        greeting = _recv_line(sock, timeout)
        if not greeting.upper().startswith("* OK"):
            return False, f"{port} greeting {greeting[:120]}"
        pwd_bytes = password.encode("utf-8")
        if mode == "raw":
            sock.sendall(f"A1 LOGIN {email} {password}\r\n".encode("utf-8"))
        elif mode == "quoted":
            sock.sendall(f"A1 LOGIN {imap_quote(email)} {imap_quote(password)}\r\n".encode("utf-8"))
        else:
            sock.sendall(f"A1 LOGIN {email} {{{len(pwd_bytes)}}}\r\n".encode("ascii"))
            cont = _recv_line(sock, timeout)
            if not cont.startswith("+"):
                return False, f"{port} literal {cont[:120]}"
            sock.sendall(pwd_bytes + b"\r\n")
        replies: list[str] = []
        while True:
            line = _recv_line(sock, timeout)
            replies.append(line)
            if line.startswith("A1 ") or line.upper().startswith("A1 "):
                break
        try:
            sock.sendall(b"A2 LOGOUT\r\n")
        except OSError:
            pass
        tagged = next((ln for ln in replies if ln.startswith("A1 ")), "")
        blob = "\n".join(replies)
        if re.match(r"A1 OK\b", tagged, re.I) or "OK LOGIN" in tagged.upper():
            return True, ""
        if re.match(r"A1 NO\b", tagged, re.I) or "NO LOGIN" in blob.upper():
            return False, f"{port} NO LOGIN {mode}"
        return False, f"{port} {mode} {tagged or blob}"[:200]
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _recv_line(sock: socket.socket, timeout: float) -> str:
    sock.settimeout(timeout)
    buf = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            break
        buf.extend(chunk)
        if buf.endswith(b"\n"):
            break
        if len(buf) > 8192:
            break
    return buf.decode("utf-8", errors="replace").rstrip("\r\n")


def try_login(email: str, password: str) -> dict:
    try:
        ok, err = tagged_login("127.0.0.1", 143, email, password, use_ssl=False)
        if ok:
            return {"ok": True, "port": 143, "error": ""}
        err_143 = err or "143 login failed"
    except Exception as exc:
        err_143 = f"143 {exc}"

    try:
        ok, err = tagged_login("127.0.0.1", 993, email, password, use_ssl=True)
        if ok:
            return {"ok": True, "port": 993, "error": ""}
        err_993 = err or "993 login failed"
    except Exception as exc:
        err_993 = f"993 {exc}"
    return {"ok": False, "port": 0, "error": f"{err_143}; {err_993}"[:500]}


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
