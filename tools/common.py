"""Small filesystem helpers. All writes stay inside the selected project."""
from __future__ import annotations
import hashlib, json, os, tempfile
from datetime import datetime
from pathlib import Path

def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")

def project_root(value=None):
    root = Path(value).expanduser().resolve() if value else Path(__file__).resolve().parents[1]
    if not (root / "config" / "project.json").is_file():
        raise ValueError(f"Not a scaffold directory: {root}")
    return root

def inside(root, relative):
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        raise ValueError(f"Path escapes project: {relative}") from None
    return path

def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))

def write_text(root, relative, content):
    path = inside(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    scratch = inside(root, "tmp")
    scratch.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="atomic_", dir=scratch)) / path.name
    with stage.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(stage, path)
    return path

def write_json(root, relative, value):
    return write_text(root, relative, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
