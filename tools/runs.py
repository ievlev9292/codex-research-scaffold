"""Explicit run lifecycle, compact handoff and optional audit cadence."""
from __future__ import annotations
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path
from common import inside, now, project_root, read_json, write_text

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

def start(root, title, objective, slug):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", slug):
        raise ValueError("Use a lowercase slug of letters, digits, hyphens or underscores")
    prefix = datetime.now().strftime("%Y%m%d_%H%M") + "_" + slug
    run_id, suffix = prefix, 2
    while (root / "research" / "runs" / run_id).exists():
        run_id = f"{prefix}_{suffix}"
        suffix += 1
    path = inside(root, f"research/runs/{run_id}/RUN.md")
    data = {"run_id": run_id, "title": title, "status": "active", "created_at": now(),
            "closed_at": None, "closed_once_at": None, "closure_stage": None}
    template = (root / "research" / "runs" / "RUN_TEMPLATE.md").read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", template, re.S)
    if not match:
        raise ValueError("Run template requires a frontmatter block and body")
    body = template[match.end():].lstrip("\r\n")
    values = {"title": title, "objective": objective,
              "next_action": "Begin the scoped investigation and retain its evidence."}
    body = re.sub(r"\{\{(title|objective|next_action)\}\}", lambda m: values[m[1]], body)
    save_run(root, path, data, body)
    rebuild_index(root)
    update_handoff(root, active=run_id)
    return {"run_id": run_id, "path": path.relative_to(root).as_posix(), "status": "active"}

def checkpoint(root, run_id, note, next_action):
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

def close(root, run_id, user_requested):
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

def audit_event(root, completed=False, user_requested=False, summary=None):
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

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start", help="Start an authorized research run")
    p.add_argument("--title", required=True); p.add_argument("--objective", required=True); p.add_argument("--slug", required=True)
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
        if args.command == "start": result = start(root, args.title, args.objective, args.slug)
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
