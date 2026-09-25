"""Explicit run lifecycle, compact handoff and optional audit cadence."""
from __future__ import annotations
import argparse, json, re, sys, os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from common import inside, now, project_root, read_json, write_text, write_json

AUDIT = re.compile(r"<!-- scaffold-audit (.*?) -->", re.S)
DEFAULT_AUDIT = {"anchor_closed_count": 0, "last_suggested_at": None, "last_completed_at": None}

def load_run(path):
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.S)
    if not match:
        raise ValueError(f"Missing managed frontmatter: {path}")
    data = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition(":")
        if not separator or not re.fullmatch(r"[a-z_]+", key):
            raise ValueError(f"Invalid run field: {line}")
        data[key] = json.loads(value.strip())
    if not isinstance(data.get("run_id"), str) or data.get("status") not in {"active", "closed"}:
        raise ValueError(f"Invalid run identity/status: {path}")
    return data, text[match.end():].lstrip("\r\n")

def save_run(root, path, data, body):
    text = "---\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in data.items()) + "\n---\n\n" + body.rstrip() + "\n"
    return write_text(root, path.relative_to(root), text)

def all_runs(root):
    records, seen = [], set()
    for path in sorted((root / "research" / "runs").glob("*/RUN.md")):
        inside(root, path.relative_to(root))
        data, body = load_run(path)
        if data["run_id"] in seen:
            raise ValueError(f"Duplicate run id: {data['run_id']}")
        if data["run_id"] != path.parent.name:
            raise ValueError(f"Run id/folder mismatch: {path}")
        seen.add(data["run_id"])
        records.append((path, data, body))
    return records

def get_run(root, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Run id must be a local folder identifier")
    path = inside(root, f"research/runs/{run_id}/RUN.md")
    if not path.is_file():
        raise ValueError(f"Unknown run: {run_id}")
    data, body = load_run(path)
    if data["run_id"] != run_id:
        raise ValueError("Run identity mismatch")
    return path, data, body

def handoff(root):
    path = root / "PROJECT_HANDOFF.md"
    text = path.read_text(encoding="utf-8-sig") if path.exists() else "# Project handoff\n\n"
    markers = AUDIT.findall(text)
    if len(markers) > 1:
        raise ValueError("Ambiguous audit markers in handoff")
    state = dict(DEFAULT_AUDIT)
    if markers:
        state.update(json.loads(markers[0]))
    anchor = state["anchor_closed_count"]
    if isinstance(anchor, bool) or not isinstance(anchor, int) or anchor < 0:
        raise ValueError("Invalid audit cadence marker")
    return text, state

def update_handoff(root, active=None, audit_state=None):
    text, previous = handoff(root)
    if active is not None:
        line = "Active run: " + (f"[{active}](research/runs/{active}/RUN.md)" if active else "none.")
        if re.search(r"(?m)^Active run:.*$", text):
            text = re.sub(r"(?m)^Active run:.*$", lambda _: line, text)
        else:
            text += "\n" + line + "\n"
        next_line = "Next: read the active RUN.md for the next action." if active else "Next: follow the next authorized research request."
        text = re.sub(r"(?m)^Next:.*$", lambda _: next_line, text) if re.search(r"(?m)^Next:", text) else text + next_line + "\n"
        text = re.sub(r"(?m)^Project state: uninitialized\.$", "Project state: research records present; consult the host audit for initialization status.", text)
    marker = "<!-- scaffold-audit " + json.dumps(audit_state if audit_state is not None else previous, ensure_ascii=False, separators=(",", ":")) + " -->"
    text = AUDIT.sub(lambda _: marker, text) if AUDIT.search(text) else text.rstrip() + "\n\n" + marker + "\n"
    write_text(root, "PROJECT_HANDOFF.md", text)

def rebuild_index(root):
    records = all_runs(root)
    rows = ["# Research runs", "", "| Run | Status | Title |", "|---|---|---|"]
    for path, data, _ in records:
        title = str(data.get("title") or "").replace("|", r"\|").replace("\n", " ")
        rows.append(f"| [{data['run_id']}]({data['run_id']}/RUN.md) | {data['status']} | {title} |")
    if not records:
        rows = ["# Research runs", "", "No research runs yet."]
    write_text(root, "research/runs/INDEX.md", "\n".join(rows) + "\n")
    return records

def audit_status(root):
    records = all_runs(root)
    closed = sum(bool(data.get("closed_once_at")) for _, data, _ in records)
    _, state = handoff(root)
    config = read_json(root / "config" / "project.json", {})
    interval = config.get("maintenance", {}).get("audit_every_closed_runs", 5)
    if isinstance(interval, bool) or not isinstance(interval, int) or interval < 1:
        raise ValueError("audit_every_closed_runs must be a positive integer")
    anchor = state["anchor_closed_count"]
    return {"closed_runs": closed, "interval": interval, "anchor_closed_count": anchor,
            "audit_due": closed >= anchor + interval,
            "warning": "Closed-run history is incomplete relative to audit marker" if closed < anchor else None}

def _create_run(root, title, objective, slug, reserved_id=None, context=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        raise ValueError("Use a lowercase slug of letters, digits, hyphens or underscores")
    prefix = datetime.now().strftime("%Y%m%d_%H%M") + "_" + slug
    run_id, suffix = prefix, 2
    while (root / "research" / "runs" / run_id).exists():
        run_id = f"{prefix}_{suffix}"
        suffix += 1
    if reserved_id:
        run_id = reserved_id
    path = inside(root, f"research/runs/{run_id}/RUN.md")
    data = {"run_id": run_id, "title": title, "status": "active", "created_at": now(),
            "closed_at": None, "closed_once_at": None, "closure_stage": None}
    if context:
        data.update(context)
    template = (root / "research" / "runs" / "RUN_TEMPLATE.md").read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", template, re.S)
    if not match:
        raise ValueError("Run template requires a frontmatter block and body")
    body = template[match.end():].lstrip("\r\n")
    values = {"title": title, "objective": objective,
              "next_action": "Audit relevant prior literature before substantial investigation; retain the evidence."}
    body = re.sub(r"\{\{(title|objective|next_action)\}\}", lambda m: values[m[1]], body)
    save_run(root, path, data, body)
    rebuild_index(root)
    update_handoff(root, active=run_id)
    return {"run_id": run_id, "path": path.relative_to(root).as_posix(), "status": "active"}

def _checkpoint(root, run_id, note, next_action):
    path, data, body = get_run(root, run_id)
    if data["status"] != "active":
        raise ValueError("A closed run cannot receive a research checkpoint")
    addition = f"\n### Checkpoint {now()}\n\n{note}\n"
    marker = "\n## Coverage and remaining work"
    body = body.replace(marker, addition + marker, 1) if marker in body else body + addition
    if next_action is not None:
        section = "\n## Next action\n"
        start_at = body.find(section)
        if start_at >= 0:
            tail_at = body.find("\n## ", start_at + len(section))
            tail = body[tail_at:] if tail_at >= 0 else ""
            body = body[:start_at] + section + "\n" + next_action + "\n" + tail
        else:
            body += section + "\n" + next_action + "\n"
    save_run(root, path, data, body)
    return {"run_id": run_id, "status": "active", "checkpoint_saved": True}

def _close(root, run_id, user_requested):
    if not user_requested:
        raise ValueError("Closing requires the user's explicit request; do not infer it from task completion")
    path, data, body = get_run(root, run_id)
    already_closed = data["status"] == "closed" and data.get("closure_stage") == "complete"
    data["closure_stage"] = "reconciling"
    save_run(root, path, data, body)
    data["status"] = "closed"
    data["closed_at"] = data.get("closed_at") or now()
    data["closed_once_at"] = data.get("closed_once_at") or data["closed_at"]
    save_run(root, path, data, body)
    records = rebuild_index(root)
    active = [d["run_id"] for _, d, _ in records if d["status"] == "active"]
    update_handoff(root, active=active[-1] if active else "")
    data["closure_stage"] = "complete"
    save_run(root, path, data, body)
    return {"run_id": run_id, "status": "closed", "already_closed": already_closed, **audit_status(root)}

def _audit_event(root, completed=False, user_requested=False, summary=None):
    if completed and not user_requested:
        raise ValueError("Only record an actually user-requested and completed audit")
    status = audit_status(root)
    if not completed and not status["audit_due"]:
        return {**status, "recorded": False}
    _, state = handoff(root)
    state["anchor_closed_count"] = status["closed_runs"]
    state["last_completed_at" if completed else "last_suggested_at"] = now()
    if completed and summary is not None:
        state["latest_summary"] = summary
    update_handoff(root, audit_state=state)
    return {**audit_status(root), "recorded": True}

# One compact registry per project. Run records retain historical chat/request IDs.
CHATS = "research/runs/chat_state.json"

def _chat_key(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label} must be a nonempty, stable identifier of at most 200 characters")
    return value

@contextmanager
def lifecycle_lock(root):
    """Serialize lifecycle updates; OS releases the lock even after interruption."""
    path = inside(root, "research/runs/.lifecycle.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"0"); stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError("Another lifecycle operation is active; retry after it finishes") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

def chat_state(root):
    state = read_json(inside(root, CHATS), {"schema_version": 1, "chats": {}})
    if not isinstance(state, dict) or state.get("schema_version") != 1 or not isinstance(state.get("chats"), dict):
        raise ValueError("Invalid chat state; preserve it and resolve before starting a run")
    for key, entry in state["chats"].items():
        _chat_key(key, "chat_id")
        if not isinstance(entry, dict):
            raise ValueError("Invalid chat entry")
    return state

def _chat_result(root, chat_id, entry, action):
    run_id = entry.get("run_id")
    status = get_run(root, run_id)[1]["status"] if run_id else None
    return {"chat_id": chat_id, "run_id": run_id, "status": status,
            "decision": entry.get("decision"), "action": action,
            "pending": bool(entry.get("pending"))}

def chat_status(root, chat_id):
    _chat_key(chat_id, "chat_id")
    entry = chat_state(root)["chats"].get(chat_id)
    return _chat_result(root, chat_id, entry, "existing_chat") if entry else {
        "chat_id": chat_id, "action": "unregistered", "run_id": None,
        "warning": "Unregistered is not evidence of a new chat. Check conversation context."}

def _finish_chat_start(root, state, chat_id):
    entry = state["chats"][chat_id]
    pending = entry.get("pending")
    if not pending:
        return
    run_id = pending["run_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid reserved run id")
    path = inside(root, f"research/runs/{run_id}/RUN.md")
    context = {"chat_id": chat_id, "start_reason": pending["reason"],
               "start_request_id": pending["request_id"]}
    if path.exists():
        data = get_run(root, run_id)[1]
        if any(data.get(key) != value for key, value in context.items()):
            raise ValueError("Reserved run identity conflicts with retained evidence")
        rebuild_index(root)
        update_handoff(root, active=run_id if data["status"] == "active" else None)
    else:
        _create_run(root, pending["title"], pending["objective"], pending["slug"],
                    reserved_id=run_id, context=context)
    entry.update(run_id=run_id, decision=pending["reason"])
    del entry["pending"]
    write_json(root, CHATS, state)

def _schedule_chat_start(root, state, chat_id, title, objective, slug, reason, request_id):
    if not all(isinstance(v, str) and v.strip() for v in (title, objective, slug)):
        raise ValueError("A new run needs title, objective and slug")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        raise ValueError("Use a lowercase slug of letters, digits, hyphens or underscores")
    prefix = datetime.now().strftime("%Y%m%d_%H%M") + "_" + slug
    run_id, suffix = prefix, 2
    reserved = {e.get("pending", {}).get("run_id") for e in state["chats"].values()}
    while (root / "research/runs" / run_id).exists() or run_id in reserved:
        run_id = f"{prefix}_{suffix}"; suffix += 1
    entry = state["chats"].setdefault(chat_id, {"opened_at": now(), "run_id": None})
    entry["pending"] = {"run_id": run_id, "title": title, "objective": objective,
                        "slug": slug, "reason": reason, "request_id": request_id}
    write_json(root, CHATS, state)  # Recovery intent precedes creation.
    _finish_chat_start(root, state, chat_id)
    return _chat_result(root, chat_id, entry, "started")

def enter_chat(root, chat_id, title=None, objective=None, slug=None, opt_out=False, continue_run=None):
    """Caller attests a real opening. Replays never start a second run."""
    _chat_key(chat_id, "chat_id")
    if opt_out and continue_run:
        raise ValueError("Choose opt-out or continue-run")
    with lifecycle_lock(root):
        state = chat_state(root)
        if chat_id in state["chats"]:
            _finish_chat_start(root, state, chat_id)
            return _chat_result(root, chat_id, state["chats"][chat_id], "existing_chat")
        if opt_out or continue_run:
            if continue_run:
                get_run(root, continue_run)
            entry = {"opened_at": now(), "run_id": continue_run,
                     "decision": "continue_existing" if continue_run else "opt_out"}
            state["chats"][chat_id] = entry
            write_json(root, CHATS, state)
            return _chat_result(root, chat_id, entry, "registered")
        return _schedule_chat_start(root, state, chat_id, title, objective, slug, "new_chat", "opening")

def start(root, title, objective, slug, user_requested=False, chat_id=None, request_id=None):
    """Explicit mid-chat start. Intent flags are records, not an authorization system."""
    if not user_requested:
        raise ValueError("Mid-chat starts require an explicit user request; use enter-chat only at a real chat opening")
    _chat_key(chat_id, "chat_id"); _chat_key(request_id, "request_id")
    if request_id == "opening":
        raise ValueError("opening is reserved for enter-chat; choose a distinct request_id")
    with lifecycle_lock(root):
        state = chat_state(root)
        if chat_id in state["chats"]:
            _finish_chat_start(root, state, chat_id)
        matching = [(path, data) for path, data, _ in all_runs(root)
                    if data.get("chat_id") == chat_id and data.get("start_request_id") == request_id]
        if matching:
            if len(matching) != 1:
                raise ValueError("Ambiguous retained start request")
            data = matching[0][1]
            return {"chat_id": chat_id, "run_id": data["run_id"], "status": data["status"],
                    "action": "existing_request"}
        return _schedule_chat_start(root, state, chat_id, title, objective, slug, "user_requested", request_id)

def close(root, run_id, user_requested):
    with lifecycle_lock(root):
        return _close(root, run_id, user_requested)

def checkpoint(root, run_id, note, next_action):
    with lifecycle_lock(root):
        return _checkpoint(root, run_id, note, next_action)

def audit_event(root, completed=False, user_requested=False, summary=None):
    with lifecycle_lock(root):
        return _audit_event(root, completed, user_requested, summary)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start", help="Start an authorized research run")
    p.add_argument("--title", required=True); p.add_argument("--objective", required=True); p.add_argument("--slug", required=True)
    p.add_argument("--user-requested", action="store_true")
    p.add_argument("--chat-id", required=True); p.add_argument("--request-id", required=True)
    p = sub.add_parser("enter-chat", help="Register a real chat opening once; otherwise consult chat-status")
    p.add_argument("--chat-id", required=True)
    p.add_argument("--title"); p.add_argument("--objective"); p.add_argument("--slug")
    modes = p.add_mutually_exclusive_group()
    modes.add_argument("--opt-out", action="store_true")
    modes.add_argument("--continue-run")
    p = sub.add_parser("chat-status", help="Read the current chat association without creating anything")
    p.add_argument("--chat-id", required=True)
    p = sub.add_parser("checkpoint", help="Save meaningful progress in an active run")
    p.add_argument("run_id"); p.add_argument("--note", required=True); p.add_argument("--next", dest="next_action")
    p = sub.add_parser("close", help="Reconcile lifecycle state only after explicit user closure instruction")
    p.add_argument("run_id"); p.add_argument("--user-requested", action="store_true")
    sub.add_parser("list"); sub.add_parser("audit-status")
    sub.add_parser("audit-offered", help="Record that the due suggestion is being delivered, avoiding repeated reminders")
    p = sub.add_parser("audit-completed", help="Record a completed user-requested maintenance audit")
    p.add_argument("--user-requested", action="store_true"); p.add_argument("--summary")
    args = parser.parse_args(argv)
    try:
        root = project_root(args.root)
        if args.command == "start": result = start(root, args.title, args.objective, args.slug, args.user_requested, args.chat_id, args.request_id)
        elif args.command == "enter-chat": result = enter_chat(root, args.chat_id, args.title, args.objective, args.slug, args.opt_out, args.continue_run)
        elif args.command == "chat-status": result = chat_status(root, args.chat_id)
        elif args.command == "checkpoint": result = checkpoint(root, args.run_id, args.note, args.next_action)
        elif args.command == "close": result = close(root, args.run_id, args.user_requested)
        elif args.command == "list": result = [{"path": p.relative_to(root).as_posix(), **d} for p, d, _ in all_runs(root)]
        elif args.command == "audit-status": result = audit_status(root)
        else: result = audit_event(root, args.command == "audit-completed", getattr(args, "user_requested", False), getattr(args, "summary", None))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
