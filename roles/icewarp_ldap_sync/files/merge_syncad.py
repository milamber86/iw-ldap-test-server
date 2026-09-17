#!/usr/bin/env python3
"""Merge one IceWarp <DOMAIN> fragment into config/syncad.dat without dropping other domains."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _local(tag):
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def _domain_name(node):
    for child in list(node):
        if _local(child.tag).upper() == "DOMAIN":
            return (child.text or "").strip()
    return None


def main():
    if len(sys.argv) != 4:
        sys.stderr.write("usage: merge_syncad.py SYNCAD_PATH FRAGMENT_PATH DOMAIN_NAME\n")
        return 2

    syncad_path = Path(sys.argv[1])
    fragment_path = Path(sys.argv[2])
    domain_name = sys.argv[3]

    fragment = ET.fromstring(fragment_path.read_bytes())
    if _local(fragment.tag).upper() != "DOMAIN":
        sys.stderr.write("fragment root must be <DOMAIN>\n")
        return 2

    if syncad_path.exists() and syncad_path.read_bytes().strip():
        try:
            tree = ET.parse(str(syncad_path))
            root = tree.getroot()
        except ET.ParseError:
            root = ET.Element("DOMAINS")
            tree = ET.ElementTree(root)
    else:
        root = ET.Element("DOMAINS")
        tree = ET.ElementTree(root)

    if _local(root.tag).upper() != "DOMAINS":
        wrapper = ET.Element("DOMAINS")
        wrapper.append(root)
        root = wrapper
        tree = ET.ElementTree(root)

    for child in list(root):
        if _local(child.tag).upper() != "DOMAIN":
            continue
        if _domain_name(child) == domain_name:
            root.remove(child)

    root.append(fragment)
    tree.write(str(syncad_path), encoding="utf-8", xml_declaration=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
