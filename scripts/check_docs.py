#!/usr/bin/env python3
"""Check local Markdown links without traversing node_modules or build output."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"node_modules", ".venv", "venv", "dist", "build", "out", "cache", ".git"}
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

def markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)

def main() -> int:
    broken: list[tuple[Path, str]] = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                broken.append((path.relative_to(ROOT), target))
    if broken:
        print(f"{len(broken)} broken link(s):")
        for path, target in broken:
            print(f"  {path}: {target}")
        return 1
    print(f"OK: {len(markdown_files())} Markdown files, no broken local links.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
