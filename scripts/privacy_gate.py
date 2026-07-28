#!/usr/bin/env python3
"""Fail a build when tracked files or named artifacts contain common private data."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

MAX_TEXT_BYTES = 8 * 1024 * 1024
DENIED_NAMES = {
    ".env",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
DENIED_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
PATTERNS = [
    (
        "email address",
        re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ),
    ("phone number", re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")),
    ("Windows absolute path", re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")),
    ("home-directory path", re.compile(r"/(?:home|Users)/[^\s\"']+")),
    ("UNC path", re.compile(r"\\\\[A-Za-z0-9][^\s\"']*")),
    ("file URI", re.compile("file:" + "///", re.IGNORECASE)),
    ("private IPv4 address", re.compile(r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b")),
    ("replacement character", re.compile(chr(0xFFFD))),
    (
        "credential prefix",
        re.compile(
            "(?:"
            + "gh"
            + "p_|github_" + "pat_|s" + "k-"
            + "|AKIA[0-9A-Z]{12,}"
            + ")"
        ),
    ),
    ("private-key marker", re.compile("BEGIN " + "PRIVATE KEY")),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--extra", type=Path, action="append", default=[])
    return parser.parse_args()


def tracked_files(root: Path) -> list[Path]:
    output = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [root / item.decode("utf-8") for item in output.split(b"\0") if item]


def unsafe_name(path: Path) -> str | None:
    lower_name = path.name.lower()
    if lower_name in DENIED_NAMES or lower_name.startswith(".env."):
        return "credential-like filename"
    if path.suffix.lower() in DENIED_SUFFIXES:
        return "credential-like file suffix"
    return None


def scan_text(path: Path, text: str) -> list[tuple[str, int]]:
    findings: list[tuple[str, int]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for label, pattern in PATTERNS:
            if pattern.search(line):
                findings.append((label, line_number))
    return findings


def scan_file(path: Path) -> list[tuple[str, int]]:
    name_finding = unsafe_name(path)
    if name_finding:
        return [(name_finding, 0)]
    data = path.read_bytes()
    if len(data) > MAX_TEXT_BYTES:
        return [("file exceeds privacy-gate text limit", 0)]
    if b"\0" in data:
        return [("binary file is outside the public text-only boundary", 0)]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [("file is not valid UTF-8", 0)]
    return scan_text(path, text)


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    candidates = tracked_files(root)
    candidates.extend(path.resolve() for path in args.extra)

    findings: list[tuple[Path, str, int]] = []
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            findings.append((path, "expected scan target is not a regular file", 0))
            continue
        for label, line_number in scan_file(path):
            findings.append((path, label, line_number))

    if findings:
        for path, label, line_number in findings:
            try:
                display = path.relative_to(root)
            except ValueError:
                display = Path(path.name)
            location = f":{line_number}" if line_number else ""
            print(f"privacy-gate: {display}{location}: {label}")
        return 1
    print(f"privacy-gate: passed ({len(seen)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
