#!/usr/bin/env python3
"""List LDAP domain, users, and groups as JSON. Password is never printed."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def search(uri: str, bind_dn: str, password: str, base: str, scope: str, filt: str, attrs: list[str]) -> tuple[int, str, str]:
    cmd = [
        "ldapsearch",
        "-LLL",
        "-o",
        "ldif-wrap=no",
        "-x",
        "-H",
        uri,
        "-D",
        bind_dn,
        "-w",
        password,
        "-b",
        base,
        "-s",
        scope,
        filt,
        *attrs,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def parse_ldif(text: str) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("#") or line.startswith("version:"):
            continue
        if not line.strip():
            if current:
                entries.append(current)
                current = None
            continue
        if line.startswith("dn:") or line.startswith("dn::"):
            if current:
                entries.append(current)
            dn = line.split(":", 1)[1].lstrip()
            if line.startswith("dn::"):
                dn = dn  # keep encoded; listing still has uid/cn attrs
            current = {"dn": dn.strip(), "attrs": {}}
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.endswith(":"):
            continue
        key = key.strip()
        value = value.strip()
        current["attrs"].setdefault(key, []).append(value)
    if current:
        entries.append(current)
    return entries


def first_attr(entry: dict, name: str) -> str:
    values = entry.get("attrs", {}).get(name, [])
    return values[0] if values else ""


def main() -> int:
    if len(sys.argv) < 8:
        print(json.dumps({"ok": False, "error": "usage: ldap_list.py uri bind base people groups users_csv groups_csv"}))
        return 2
    uri, bind_dn, base, people, groups, users_csv, groups_csv = sys.argv[1:8]
    password = os.environ.get("LDAP_BIND_PASSWORD", "")
    if not password:
        print(json.dumps({"ok": False, "error": "LDAP_BIND_PASSWORD env is empty"}))
        return 2
    expected_users = [u for u in users_csv.split(",") if u]
    expected_groups = [g for g in groups_csv.split(",") if g]

    result = {
        "ok": True,
        "error": "",
        "domain": {"dn": base, "dc": "", "o": ""},
        "users": [],
        "groups": [],
        "missing_users": [],
        "missing_groups": [],
    }

    rc, out, err = search(uri, bind_dn, password, base, "base", "(objectClass=*)", ["dc", "o"])
    if rc != 0:
        result["ok"] = False
        result["error"] = "domain search failed"
        print(json.dumps(result))
        return 1
    domain_entries = parse_ldif(out)
    if domain_entries:
        result["domain"]["dc"] = first_attr(domain_entries[0], "dc")
        result["domain"]["o"] = first_attr(domain_entries[0], "o")
        result["domain"]["dn"] = domain_entries[0].get("dn", base)

    rc, out, err = search(
        uri,
        bind_dn,
        password,
        people,
        "sub",
        "(objectClass=inetOrgPerson)",
        ["uid", "mail", "cn"],
    )
    if rc != 0:
        result["ok"] = False
        result["error"] = "people search failed"
        print(json.dumps(result))
        return 1
    found_uids = set()
    for entry in parse_ldif(out):
        uid = first_attr(entry, "uid")
        found_uids.add(uid)
        result["users"].append(
            {
                "uid": uid,
                "cn": first_attr(entry, "cn"),
                "mail": first_attr(entry, "mail"),
                "dn": entry.get("dn", ""),
            }
        )
    result["users"].sort(key=lambda u: u["uid"])
    result["missing_users"] = [u for u in expected_users if u not in found_uids]

    rc, out, err = search(
        uri,
        bind_dn,
        password,
        groups,
        "sub",
        "(objectClass=groupOfNames)",
        ["cn", "mail", "member"],
    )
    if rc != 0:
        result["ok"] = False
        result["error"] = "group search failed"
        print(json.dumps(result))
        return 1
    found_cns = set()
    for entry in parse_ldif(out):
        cn = first_attr(entry, "cn")
        found_cns.add(cn)
        result["groups"].append(
            {
                "cn": cn,
                "mail": first_attr(entry, "mail"),
                "members": entry.get("attrs", {}).get("member", []),
                "dn": entry.get("dn", ""),
            }
        )
    result["groups"].sort(key=lambda g: g["cn"])
    result["missing_groups"] = [g for g in expected_groups if g not in found_cns]

    if result["missing_users"] or result["missing_groups"]:
        result["ok"] = False
        parts = []
        if result["missing_users"]:
            parts.append("missing users: " + ",".join(result["missing_users"]))
        if result["missing_groups"]:
            parts.append("missing groups: " + ",".join(result["missing_groups"]))
        result["error"] = "; ".join(parts)
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
