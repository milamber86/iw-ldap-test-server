#!/usr/bin/env python3
"""WebClient login with the real user password via curl (getauthtoken, not impersonate)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.parse
from xml.sax.saxutils import escape as xml_escape

PHPSESSID_RE = re.compile(r"PHPSESSID_LOGIN=([^;]+)", re.I)
AUTHTOKEN_RE = re.compile(r"<authtoken>([^<]+)</authtoken>", re.I)
RESULT_RE = re.compile(r"<result>(.*?)</result>", re.I | re.S)
IQ_ERROR_RE = re.compile(r'type="error"', re.I)
WMSID_RE = re.compile(r'iq sid="([^"]+)"', re.I)
SID_RE = re.compile(r'sid="([^"]+)"', re.I)


class WcLoginError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def curl(args: list[str], timeout: int) -> tuple[int, str]:
    proc = subprocess.run(
        ["curl", "-sk", "--connect-timeout", "8", "-m", str(timeout), "-D", "-", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, out


def parse_authtoken(text: str) -> str:
    if IQ_ERROR_RE.search(text) or "auth_two_factor_required" in text:
        raise WcLoginError("getauthtoken", "error or two-factor required")
    match = AUTHTOKEN_RE.search(text)
    if match:
        token = match.group(1).strip()
        if token and token != "0":
            return token
    match = RESULT_RE.search(text)
    if not match:
        raise WcLoginError("getauthtoken", "no <result> in icewarpapi response")
    raw = match.group(1).strip()
    if not raw or raw == "0":
        raise WcLoginError("getauthtoken", "empty or zero result")
    inner = AUTHTOKEN_RE.search(raw)
    if inner:
        return inner.group(1).strip()
    if "atoken=" in raw:
        parsed = urllib.parse.urlparse(raw)
        qs = urllib.parse.parse_qs(parsed.query)
        if qs.get("atoken"):
            return qs["atoken"][0]
        return raw.rsplit("=", 1)[-1].strip()
    return raw


def strip_wm_prefix(value: str) -> str:
    if value.startswith("wm-"):
        return value[3:]
    if value.startswith("wm"):
        return value[2:]
    return value


def parse_phpsessid(blob: str) -> str:
    if "500 Internal Server Error" in blob:
        raise WcLoginError("phpsessid", "HTTP 500 opening /webmail/?atoken=")
    match = PHPSESSID_RE.search(blob)
    if not match:
        raise WcLoginError("phpsessid", "PHPSESSID_LOGIN missing")
    return strip_wm_prefix(match.group(1).strip())


def parse_wmsid(text: str) -> str:
    if "500 Internal Server Error" in text:
        raise WcLoginError("iq_auth", "webmail.php HTTP 500")
    match = WMSID_RE.search(text) or SID_RE.search(text)
    if not match:
        raise WcLoginError("iq_auth", "no webmail session sid")
    return strip_wm_prefix(match.group(1))


def login(email: str, password: str, base: str, timeout: int) -> dict:
    base = base.rstrip("/")
    payload = (
        '<iq uid="1" format="text/xml"><query xmlns="admin:iq:rpc">'
        "<commandname>getauthtoken</commandname><commandparams>"
        f"<email>{xml_escape(email)}</email>"
        f"<password>{xml_escape(password)}</password>"
        "<digest></digest><authtype>0</authtype><persistentlogin>0</persistentlogin>"
        "</commandparams></query></iq>"
    )
    rc, out = curl(
        ["--data-binary", payload, f"{base}/icewarpapi/"],
        timeout,
    )
    if rc != 0 and "HTTP/" not in out:
        raise WcLoginError("getauthtoken", f"curl rc={rc}")
    token = parse_authtoken(out)

    atoken_q = urllib.parse.urlencode({"atoken": token, "user_used_login": "1"})
    rc, out = curl(["-L", f"{base}/webmail/?{atoken_q}"], timeout)
    phpsessid = parse_phpsessid(out)
    sess = phpsessid if phpsessid.startswith("wm") else f"wm{phpsessid}"

    auth_xml = (
        f'<iq type="set"><query xmlns="webmail:iq:auth">'
        f"<session>{xml_escape(sess)}</session></query></iq>"
    )
    rc, out = curl(
        ["--data-binary", auth_xml, f"{base}/webmail/server/webmail.php"],
        timeout,
    )
    wmsid = parse_wmsid(out)

    logout = f'<iq sid="wm-{xml_escape(wmsid)}" type="set"><query xmlns="webmail:iq:auth"/></iq>'
    curl(
        ["--data-binary", logout, f"{base}/webmail/server/webmail.php"],
        min(15, timeout),
    )
    return {"ok": True, "stage": "ok", "error": ""}


def main() -> int:
    email = sys.argv[1] if len(sys.argv) > 1 else ""
    password = os.environ.get("IW_SMOKE_PASSWORD", "")
    base = sys.argv[2] if len(sys.argv) > 2 else "https://127.0.0.1"
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    if not email or not password:
        print(json.dumps({"ok": False, "stage": "args", "error": "usage: wc_login.py email [base] (password via IW_SMOKE_PASSWORD)"}))
        return 2
    try:
        print(json.dumps(login(email, password, base, timeout)))
        return 0
    except WcLoginError as exc:
        print(json.dumps({"ok": False, "stage": exc.stage, "error": str(exc)}))
        return 1
    except Exception as exc:
        print(json.dumps({"ok": False, "stage": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
