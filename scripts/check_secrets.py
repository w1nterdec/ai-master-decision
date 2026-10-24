#!/usr/bin/env python3
"""Inspect tracked and non-ignored new text; report locations, never secret values."""

from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"
    ),
    "aws-access-id": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "openai-key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{25,}\b"),
    "google-key": re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    "slack-token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "credential-url": re.compile(
        r"\b(?:https?|postgres(?:ql)?|mysql)://[^\s/:]+:[^\s/@]+@", re.I
    ),
    "internal-domain": re.compile(
        r"https?://[a-z0-9.-]+\.(?:internal|corp|local)(?:[/:\s]|$)", re.I
    ),
}
EXTENSIONS = {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".example"}
MAX_BLOB_BYTES = 10_000_000
MAX_XML_BYTES = 20_000_000


def is_private_file(name: str) -> bool:
    path = Path(name)
    base = path.name.lower()
    return (
        ((base == ".env" or base.startswith(".env.")) and base != ".env.example")
        or base in ("decision_profile.json", "id_rsa", "id_ed25519")
        or path.suffix.lower() in (".db", ".sqlite", ".sqlite3")
    )


def findings(text: str) -> list[tuple[int, str]]:
    return [
        (line_no, name)
        for line_no, line in enumerate(text.splitlines(), 1)
        for name, pattern in RULES.items()
        if pattern.search(line)
    ]


def inspect_blob(raw: bytes, name: str) -> tuple[list[str], bool]:
    """Return redacted locations and whether content was outside the scan scope."""
    hits = []
    if raw.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = [
                    item
                    for item in archive.infolist()
                    if item.filename.endswith((".xml", ".rels"))
                ]
                if sum(item.file_size for item in entries) > MAX_XML_BYTES:
                    return [], True
                for entry in entries:
                    text = archive.read(entry).decode("utf-8", errors="replace")
                    hits.extend(
                        f"{name}!{entry.filename}:{line}: {rule}"
                        for line, rule in findings(text)
                    )
                return hits, not bool(entries)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
            return [], True
    if b"\0" in raw[:8192] or Path(name).suffix.lower() in (".jpg", ".jpeg", ".png"):
        return [], True
    return [
        f"{name}:{line}: {rule}"
        for line, rule in findings(raw.decode("utf-8", errors="replace"))
    ], False


def scan_history(root: Path) -> tuple[list[str], int, int]:
    """Scan branch/tag/remote history, excluding local application capture refs."""
    objects = (
        subprocess.check_output(
            ["git", "rev-list", "--objects", "--branches", "--tags", "--remotes"],
            cwd=root,
        )
        .decode("utf-8")
        .splitlines()
    )
    names = {}
    for entry in objects:
        oid, _, name = entry.partition(" ")
        names.setdefault(oid, name or oid)
    if not names:
        return [], 0, 0
    check = (
        subprocess.check_output(
            [
                "git",
                "cat-file",
                "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            ],
            input=("\n".join(names) + "\n").encode(),
            cwd=root,
        )
        .decode()
        .splitlines()
    )
    blobs = [
        line.split()
        for line in check
        if len(line.split()) == 3 and line.split()[1] == "blob"
    ]
    eligible = [row[0] for row in blobs if int(row[2]) <= MAX_BLOB_BYTES]
    skipped = len(blobs) - len(eligible)
    if not eligible:
        return [], 0, skipped
    stream = io.BytesIO(
        subprocess.check_output(
            ["git", "cat-file", "--batch"],
            input=("\n".join(eligible) + "\n").encode(),
            cwd=root,
        )
    )
    hits = []
    for _ in eligible:
        oid, kind, size = stream.readline().decode().strip().split()
        raw = stream.read(int(size))
        stream.read(1)
        if kind != "blob":
            raise RuntimeError("Unexpected Git object type")
        if is_private_file(names[oid]):
            hits.append(f"{names[oid]}@{oid[:12]}: sensitive-file")
        found, outside_scope = inspect_blob(raw, f"{names[oid]}@{oid[:12]}")
        hits.extend(found)
        skipped += int(outside_scope)
    return hits, len(eligible), skipped


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history", action="store_true", help="另外扫描分支、标签及远端引用的可达历史"
    )
    args = parser.parse_args(argv)
    names = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
        )
        .decode("utf-8")
        .split("\0")
    )
    hits = []
    for name in names:
        path = ROOT / name
        if name and path.is_file() and is_private_file(name):
            hits.append(f"{name}: sensitive-file")
        if (
            not name
            or not path.is_file()
            or path.suffix not in EXTENSIONS
            or path.stat().st_size > 2_000_000
        ):
            continue
        for line, rule in findings(path.read_text(encoding="utf-8", errors="replace")):
            hits.append(f"{name}:{line}: {rule}")
    if args.history:
        historical, count, skipped = scan_history(ROOT)
        hits.extend(historical)
        print(
            f"[INFO] History: {count} eligible blobs; {skipped} oversized/binary/unreadable objects outside full text scan scope"
        )
    for hit in hits:
        print(hit)
    if hits:
        return 1
    print(
        "[OK] No configured secret or internal-domain patterns found in versionable text"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
