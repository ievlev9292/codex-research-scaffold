"""Small project-local filesystem helpers; no global permission changes."""
from __future__ import annotations
import hashlib, json, os, stat, time, uuid
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

def _native_path(path):
    text = str(path)
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        return "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text
    return text

def _windows_stage_permissions(path, stage):
    """Copy an existing destination DACL/protection before writing any content.

    Sibling staging shares the destination's parent, so inherited entries come
    from the correct directory. New files simply retain that inherited DACL.
    No permission mutation happens after rename.
    """
    import ctypes as c
    from ctypes import wintypes as w
    adv = c.WinDLL("advapi32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    adv.GetNamedSecurityInfoW.argtypes = [w.LPWSTR,w.DWORD,w.DWORD,c.c_void_p,c.c_void_p,c.POINTER(c.c_void_p),c.c_void_p,c.POINTER(c.c_void_p)]
    adv.GetNamedSecurityInfoW.restype = w.DWORD
    adv.GetSecurityDescriptorControl.argtypes = [c.c_void_p,c.POINTER(w.WORD),c.POINTER(w.DWORD)]
    adv.GetSecurityDescriptorControl.restype = w.BOOL
    adv.SetNamedSecurityInfoW.argtypes = [w.LPWSTR,w.DWORD,w.DWORD,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p]
    adv.SetNamedSecurityInfoW.restype = w.DWORD
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.LocalFree.restype = c.c_void_p
    descriptor, dacl = c.c_void_p(), c.c_void_p()
    error = adv.GetNamedSecurityInfoW(_native_path(path), 1, 4, None, None, c.byref(dacl), None, c.byref(descriptor))
    if error in (2, 3):  # New destination; sibling already inherits its parent.
        return
    if error:
        raise c.WinError(error)
    try:
        control, revision = w.WORD(), w.DWORD()
        if not adv.GetSecurityDescriptorControl(descriptor,c.byref(control),c.byref(revision)):
            raise c.WinError(c.get_last_error())
        protection = 0x80000000 if control.value & 0x1000 else 0x20000000
        error = adv.SetNamedSecurityInfoW(_native_path(stage),1,4|protection,None,None,dacl,None)
        if error:
            raise c.WinError(error)
    finally:
        kernel.LocalFree(descriptor)

def write_text(root, relative, content):
    """Complete-file replacement, not a read-modify-write lock or power-loss guarantee.

    Unique sibling stages inherit the right parent without creating directories.
    Apply existing destination permissions before content; retain failed stages.
    Concurrent successful saves are last-writer wins. Concurrent permission edits
    are outside this contract. Previously broken destination ACLs are not repaired.
    """
    path = inside(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    stage = path.parent / (".atomic-" + uuid.uuid4().hex + ".stage")
    try:
        fd = os.open(_native_path(stage), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            if os.name == "nt":
                _windows_stage_permissions(path, stage)
            else:
                os.chmod(stage, mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(6):
            try:
                os.replace(_native_path(stage), _native_path(path))
                break
            except PermissionError as exc:
                if os.name != "nt" or getattr(exc, "winerror", None) not in (5,32,33) or attempt == 5:
                    raise
                time.sleep(0.02 * (attempt + 1))
    except OSError as exc:
        raise OSError(f"Atomic save failed for {path}; retained stage if created: {stage}: {exc}") from exc
    return path

def write_json(root, relative, value):
    return write_text(root, relative, json.dumps(value, ensure_ascii=False, indent=2) + "\n")

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
