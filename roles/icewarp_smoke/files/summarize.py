#!/usr/bin/env python3
"""Build IceWarp smoke listing JSON from tool.sh exports and login helper stdout."""
from __future__ import annotations

import json
import re
import sys


def parse_account_export(text: str) -> dict:
    result = {"u_name": "", "u_type": "", "u_authmode": "", "u_alias": ""}
    if not text:
        return result
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return result
    last = lines[-1]
    if "," in last and not last.lower().startswith("u_"):
        parts = last.split(",")
        # email, u_name, u_type, u_authmode [, u_alias]
        if len(parts) >= 4:
            result["u_name"] = parts[1].strip()
            result["u_type"] = parts[2].strip()
            result["u_authmode"] = parts[3].strip()
            if len(parts) >= 5:
                result["u_alias"] = parts[4].strip()
            return result
    kv = {}
    for line in lines:
        match = re.match(r"^(u_\w+)\s*[:=,]\s*(.*)$", line, re.I)
        if match:
            kv[match.group(1).lower()] = match.group(2).strip().strip(",")
    for key in result:
        if key in kv:
            result[key] = kv[key]
    return result


def as_int(value, default: int = 1) -> int:
    if value is None or value == "":
        return default
    return int(value)


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")


def parse_json_blob(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid helper JSON"}


def main() -> int:
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as handle:
            raw = json.load(handle)
    else:
        raw = json.load(sys.stdin)
    domain = raw["domain"]
    expected_users = raw["expected_users"]
    expected_groups = raw["expected_groups"]
    exports = raw.get("exports") or []
    export_rcs = raw.get("export_rcs") or []
    imap_blobs = raw.get("imap") or []
    wc_blobs = raw.get("wc") or []

    users = []
    groups = []
    for idx, name in enumerate(expected_users):
        export_text = exports[idx] if idx < len(exports) else ""
        parsed = parse_account_export(export_text)
        present = int(export_rcs[idx] if idx < len(export_rcs) else 1) == 0
        imapj = parse_json_blob(imap_blobs[idx] if idx < len(imap_blobs) else "")
        wcj = parse_json_blob(wc_blobs[idx] if idx < len(wc_blobs) else "")
        u_type = str(parsed.get("u_type", ""))
        u_auth = str(parsed.get("u_authmode", ""))
        users.append(
            {
                "email": f"{name}@{domain}",
                "export_ok": present,
                "u_name": parsed.get("u_name", ""),
                "u_type": u_type,
                "u_authmode": u_auth,
                "u_alias": parsed.get("u_alias", ""),
                "type_ok": u_type == "0",
                "authmode_ok": u_auth == "2",
                "imap_ok": bool(imapj.get("ok")),
                "imap_error": imapj.get("error", ""),
                "webclient_ok": bool(wcj.get("ok")),
                "webclient_stage": wcj.get("stage", ""),
                "webclient_error": wcj.get("error", ""),
            }
        )

    group_offset = len(expected_users)
    for gidx, name in enumerate(expected_groups):
        idx = group_offset + gidx
        export_text = exports[idx] if idx < len(exports) else ""
        parsed = parse_account_export(export_text)
        present = int(export_rcs[idx] if idx < len(export_rcs) else 1) == 0
        u_type = str(parsed.get("u_type", ""))
        groups.append(
            {
                "email": f"{name}@{domain}",
                "export_ok": present,
                "u_name": parsed.get("u_name", ""),
                "u_type": u_type,
                "u_authmode": str(parsed.get("u_authmode", "")),
                "u_alias": parsed.get("u_alias", ""),
                "type_ok": u_type == "7",
            }
        )

    missing_users = [u["email"] for u in users if not u["export_ok"]]
    missing_groups = [g["email"] for g in groups if not g["export_ok"]]
    users_ok = all(
        u["export_ok"] and u["type_ok"] and u["authmode_ok"] and u["imap_ok"] and u["webclient_ok"]
        for u in users
    )
    groups_ok = all(g["export_ok"] and g["type_ok"] for g in groups)
    domain_out = (raw.get("export_domain_stdout") or "").strip()
    domain_rc = as_int(raw.get("export_domain_rc"), 1)
    domain_ok = domain_rc == 0 or (
        domain.lower() in domain_out.lower() and "not found" not in domain_out.lower()
    )
    sync_ok = as_bool(raw.get("sync_ok"))
    ok = sync_ok and domain_ok and users_ok and groups_ok and not missing_users and not missing_groups
    errors = []
    if not sync_ok:
        errors.append("ADSync did not finish")
    if not domain_ok:
        errors.append("domain export failed")
    if missing_users:
        errors.append("missing users: " + ",".join(missing_users))
    if missing_groups:
        errors.append("missing groups: " + ",".join(missing_groups))
    if not users_ok:
        bad = [
            u["email"]
            for u in users
            if not (u["export_ok"] and u["type_ok"] and u["authmode_ok"] and u["imap_ok"] and u["webclient_ok"])
        ]
        errors.append("user checks failed: " + ",".join(bad))
    if not groups_ok:
        bad = [g["email"] for g in groups if not (g["export_ok"] and g["type_ok"])]
        errors.append("group checks failed: " + ",".join(bad))

    print(
        json.dumps(
            {
                "ok": ok,
                "domain_export_ok": domain_ok,
                "users": users,
                "groups": groups,
                "missing_users": missing_users,
                "missing_groups": missing_groups,
                "accounts_listing": raw.get("export_all", ""),
                "domain_export": domain_out,
                "error": "; ".join(errors),
            }
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
