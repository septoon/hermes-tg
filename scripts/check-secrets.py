#!/usr/bin/env python3
"""Reject credentials and private runtime files before commit or push."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


patterns = [
    rb"sk-aitunnel-[A-Za-z0-9_-]{16,}",
    rb"sk-(?:proj-|ant-)?[A-Za-z0-9_-]{24,}",
    rb"gh[pousr]_[A-Za-z0-9_]{30,}",
    rb"github_pat_[A-Za-z0-9_]{30,}",
    rb"\b[0-9]{8,12}:[A-Za-z0-9_-]{30,}",
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
]
secrets = []
env = ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            value = line.split("=", 1)[1].strip().strip("\"'")
            if len(value) >= 12:
                secrets.append(value.encode())


def check(name, data):
    parts = Path(name).parts
    private = any(p in {".hermes", ".runtime", ".artifacts", "venv", ".venv"} for p in parts)
    private |= any(p.startswith(".env") and p != ".env.example" for p in parts)
    private |= Path(name).suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
    if private or any(re.search(p, data) for p in patterns) or any(s in data for s in secrets):
        raise SystemExit(f"BLOCKED: possible secret or private file: {name}")


for record in git("ls-files", "--stage", "-z").split(b"\0"):
    if not record:
        continue
    meta, name = record.split(b"\t", 1)
    mode, object_id, stage = meta.split()
    if stage != b"0":
        raise SystemExit("BLOCKED: unresolved Git index")
    if mode == b"160000":
        continue  # A submodule stores a public upstream commit, not its local files.
    check(name.decode(), git("cat-file", "blob", object_id.decode()))

if "--history" in sys.argv:
    for line in git("rev-list", "--objects", "--all").splitlines():
        object_id, _, name = line.partition(b" ")
        if name and git("cat-file", "-t", object_id.decode()).strip() == b"blob":
            check(name.decode(), git("cat-file", "blob", object_id.decode()))
print("Secret check passed: Git index" + (" and full history" if "--history" in sys.argv else ""))
