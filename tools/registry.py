#!/usr/bin/env python3
"""Maintain an evidence-based Wolfram package registry; never load or install packages."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import platform
import os
from common import write_json
import json
from pathlib import Path
import re
import sys

ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
STATES = {"not_performed", "passed", "failed", "inconclusive"}


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def inside(root, value, *, must_exist=False):
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError("Evidence and project files must resolve inside the project.")
    if must_exist and not path.is_file():
        raise ValueError(f"Missing evidence: {value}")
    return path


def read_json(path):
    path = Path(path)
    if path.suffix.lower() != ".json" or path.resolve().suffix.lower() != ".json":
        raise ValueError("Registry configuration and entries must be .json files; notebooks are not read.")
    if path.stat().st_size > 4 * 1024**2:
        raise ValueError("Structured JSON input exceeds the 4 MiB configuration limit.")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Registry JSON input must contain an object.")
    return value


def binding_identity(binding):
    """Fingerprint the selected binding, without loading code or reading notebooks.

    Files are hashed directly. Directory bindings cover a bounded, explicit file list
    (identity_files) or the default executable-code extensions listed below. This is
    change detection for the stated scope, not a package audit or security sandbox.
    """
    if not isinstance(binding, dict) or not isinstance(binding.get("path"), str):
        raise ValueError("Binding needs an absolute package path.")
    supplied = Path(binding["path"])
    if not supplied.is_absolute():
        raise ValueError("Local package binding paths must be absolute.")
    base = supplied.resolve()
    if supplied.suffix.lower() == ".nb" or base.suffix.lower() == ".nb":
        raise ValueError("Notebook bindings are not processed; select script/package code.")
    if not base.exists():
        raise ValueError("Selected package binding is unavailable.")
    code_suffixes = {".m", ".wl", ".mx", ".wxf", ".dll", ".so", ".dylib", ".exe"}
    files = []
    scope = "bound-file"
    if base.is_file():
        files = [base]
    elif base.is_dir():
        selected = binding.get("identity_files")
        if selected is not None:
            if not isinstance(selected, list) or not selected or not all(isinstance(x, str) for x in selected):
                raise ValueError("identity_files must be a nonempty list of relative package files.")
            scope = "explicit-package-files"
            for value in selected:
                candidate = (base / value).resolve()
                if Path(value).is_absolute() or not candidate.is_relative_to(base):
                    raise ValueError("Identity file escapes the selected package directory.")
                if Path(value).suffix.lower() == ".nb" or candidate.suffix.lower() == ".nb":
                    raise ValueError("Notebook contents cannot be package identity input.")
                if not candidate.is_file():
                    raise ValueError("Selected package identity file is unavailable.")
                files.append(candidate)
        else:
            scope = "package-code-files"
            inspected = 0
            for directory, children, names in os.walk(base, followlinks=False):
                children[:] = sorted(c for c in children if c not in {".git", "__pycache__", "tmp"})
                for name in sorted(names):
                    inspected += 1
                    if inspected > 5000:
                        raise ValueError("Package tree exceeds the bounded scan; select identity_files explicitly.")
                    candidate = Path(directory) / name
                    if candidate.suffix.lower() not in code_suffixes:
                        continue
                    resolved = candidate.resolve()
                    if not resolved.is_relative_to(base):
                        raise ValueError("Package code resolves outside the selected directory.")
                    if resolved.suffix.lower() == ".nb":
                        raise ValueError("Package code resolves to a notebook; it was not read.")
                    files.append(resolved)
            if not files:
                raise ValueError("No package code found; provide explicit non-notebook identity_files.")
    else:
        raise ValueError("Binding must identify a regular file or package directory.")
    files = sorted(set(files))
    if len(files) > 500:
        raise ValueError("Identity scope exceeds 500 files; select a bounded explicit scope.")
    rows, total = [], 0
    for candidate in files:
        size = candidate.stat().st_size
        total += size
        if total > 100 * 1024**2:
            raise ValueError("Identity scope exceeds 100 MiB; select a bounded explicit scope.")
        code_hash = hashlib.sha256()
        with candidate.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                code_hash.update(block)
        rows.append({"file": candidate.relative_to(base).as_posix() if base.is_dir() else candidate.name,
                     "sha256": code_hash.hexdigest()})
    payload = {"path": str(base), "version": binding.get("version"), "scope": scope, "files": rows}
    return {"identity": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            "scope": scope, "file_count": len(rows), "bytes": total}


def evidence_errors(root, values, label):
    errors = []
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        return [f"{label}: evidence must be a list of project-relative paths"]
    for value in values:
        try:
            path = inside(root, value, must_exist=True)
            if Path(value).is_absolute():
                errors.append(f"{label}: portable evidence path must be relative: {value}")
            if path.suffix.lower() == ".nb":
                errors.append(f"{label}: use script/text evidence; notebook processing is explicit-only")
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
    return errors


def review(root, document):
    """Return errors, warnings and per-environment readiness. No package code is run."""
    errors, warnings, readiness = [], [], []
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        return {"errors": ["Registry schema_version must be 1"], "warnings": [], "readiness": []}
    packages = document.get("packages")
    if not isinstance(packages, list):
        return {"errors": ["packages must be an array"], "warnings": [], "readiness": []}
    host_path = inside(root, "config/host.local.json")
    host = read_json(host_path) if host_path.exists() else {}
    actual_host = hashlib.sha256(json.dumps({"node": platform.node(), "system": platform.system(), "machine": platform.machine()}, sort_keys=True).encode()).hexdigest()
    host_id = host.get("host_fingerprint") if host.get("host_fingerprint") == actual_host and host.get("project_root") == str(root) else None
    if host and not host_id:
        warnings.append("Host/project profile is stale; initialize this copy before treating any package as ready.")
    ids, entries = {}, {}
    for i, package in enumerate(packages):
        label = f"entry {i}"
        if not isinstance(package, dict):
            errors.append(f"{label}: entry must be an object")
            continue
        known = {"id", "name", "source", "version", "entry_points", "dependencies", "environments", "installation", "validation", "authorization", "capabilities", "limitations"}
        if set(package) - known:
            errors.append(f"{label}: unrecognized fields: {', '.join(sorted(set(package) - known))}")
        pid = package.get("id", "")
        label = pid or label
        if not isinstance(pid, str) or not ID.fullmatch(pid):
            errors.append(f"{label}: invalid id")
            continue
        if pid in ids:
            errors.append(f"{pid}: duplicate id")
        ids[pid] = package
        for field in ("name", "version"):
            if field not in package or not (isinstance(package[field], str) or (field == "version" and package[field] is None)):
                errors.append(f"{pid}: {field} must be a string (version may be null)")
        source = package.get("source", {})
        if not isinstance(source, dict) or not isinstance(source.get("url"), str) or not source["url"].startswith(("https://", "http://")):
            errors.append(f"{pid}: source.url must identify documentation or upstream")
        for field in ("entry_points", "dependencies", "environments", "capabilities", "limitations"):
            values = package.get(field)
            if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
                errors.append(f"{pid}: {field} must be a string array")
            elif len(set(values)) != len(values):
                errors.append(f"{pid}: {field} contains duplicates")
        if any(not isinstance(package.get(f), list) or not all(isinstance(x, str) for x in package[f]) for f in ("entry_points", "dependencies", "environments", "capabilities", "limitations")):
            continue
        envs = package.get("environments", [])
        if not isinstance(envs, list):
            envs = []
        elif not envs or any(not isinstance(e, str) or not ID.fullmatch(e) for e in envs):
            errors.append(f"{pid}: at least one valid environment is required")
        points = package.get("entry_points", [])
        if not isinstance(points, list):
            points = []
        for env in envs:
            for point in points:
                if isinstance(env, str) and isinstance(point, str):
                    entries.setdefault((env, point), []).append(pid)
        installation = package.get("installation", {})
        validation = package.get("validation", {})
        authorization = package.get("authorization", {})
        if not isinstance(installation, dict) or installation.get("status") not in {"unknown", "absent", "present"}:
            errors.append(f"{pid}: invalid installation status")
            installation = {}
        if not isinstance(validation, dict) or validation.get("status") not in STATES:
            errors.append(f"{pid}: invalid validation status")
            validation = {}
        if not isinstance(authorization, dict) or authorization.get("status") not in {"unrequested", "authorized", "denied"}:
            errors.append(f"{pid}: invalid authorization status")
            authorization = {}
        for section, value in (("installation", installation), ("validation", validation), ("authorization", authorization)):
            errors.extend(evidence_errors(root, value.get("evidence", []), f"{pid}/{section}"))
        scopes = authorization.get("scope", [])
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            errors.append(f"{pid}: authorization scope must be a string array")
            scopes = []
        current_binding = None
        binding = host.get("wolfram_bindings", {}).get(installation.get("binding_key"), {})
        if binding:
            try:
                current_binding = binding_identity(binding)
            except (OSError, ValueError) as exc:
                warnings.append(f"{pid}: binding identity unavailable: {exc}")
        if installation.get("status") == "present":
            if not installation.get("binding_key") or not installation.get("host_fingerprint") or not installation.get("evidence"):
                errors.append(f"{pid}: present installation needs a local binding, host identity and evidence")
            binding = host.get("wolfram_bindings", {}).get(installation.get("binding_key"), {})
            if not isinstance(binding, dict) or not binding.get("path") or not Path(binding["path"]).exists():
                warnings.append(f"{pid}: installation local binding is unavailable on this host")
        if validation.get("status") == "passed":
            required = ("host_fingerprint", "environment", "version", "checked_at", "basis", "evidence", "binding_identity")
            if any(not validation.get(f) for f in required):
                errors.append(f"{pid}: passed validation needs host, environment, version, date, basis, evidence and binding_identity")
            if validation.get("version") != package.get("version"):
                warnings.append(f"{pid}: validation is stale for the registered version")
            if validation.get("environment") not in envs:
                errors.append(f"{pid}: validation refers to an undeclared environment")
            if not current_binding or validation.get("binding_identity") != current_binding["identity"]:
                warnings.append(f"{pid}: validation is stale for the selected binding or covered package code")
        if authorization.get("status") == "authorized" and (not scopes or not authorization.get("evidence")):
            errors.append(f"{pid}: authorized scope needs explicit evidence")
        capabilities = package.get("capabilities", [])
        if isinstance(capabilities, list) and any(c.startswith("external:") and c not in scopes for c in capabilities if isinstance(c, str)):
            warnings.append(f"{pid}: an external capability is outside the authorized scope")
        for env in envs:
            binding = host.get("wolfram_bindings", {}).get(installation.get("binding_key"), {})
            ready = bool(
                installation.get("status") == "present" and host_id
                and installation.get("host_fingerprint") == host_id and isinstance(binding, dict)
                and binding.get("path") and Path(binding["path"]).exists()
                and binding.get("version") == package.get("version")
                and validation.get("status") == "passed"
                and validation.get("host_fingerprint") == host_id
                and validation.get("environment") == env
                and validation.get("version") == package.get("version")
                and current_binding and validation.get("binding_identity") == current_binding["identity"]
                and authorization.get("status") == "authorized"
                and {"load", "evaluate"}.issubset(scopes)
            )
            readiness.append({"id": pid, "environment": env, "ready": ready})
    for (env, point), members in entries.items():
        if len(set(members)) > 1:
            errors.append(f"{env}: shadowed entry point {point}: {', '.join(members)}")
    for pid, package in ids.items():
        dependencies = package.get("dependencies", [])
        if not isinstance(dependencies, list) or not all(isinstance(x, str) for x in dependencies):
            continue
        for dependency in dependencies:
            if dependency not in ids:
                errors.append(f"{pid}: unknown dependency {dependency}")
                continue
            own_envs = package.get("environments", [])
            dep_envs = ids[dependency].get("environments", [])
            if isinstance(own_envs, list) and isinstance(dep_envs, list):
                missing = set(own_envs) - set(dep_envs)
                if missing:
                    errors.append(f"{pid}: dependency {dependency} is unavailable in {', '.join(sorted(missing))}")
    visited, active = set(), set()
    def visit(pid):
        if pid in active:
            errors.append(f"{pid}: dependency cycle")
            return
        if pid in visited or pid not in ids:
            return
        active.add(pid)
        dependencies = ids[pid].get("dependencies", [])
        if isinstance(dependencies, list):
            for dependency in dependencies:
                if isinstance(dependency, str):
                    visit(dependency)
        active.remove(pid)
        visited.add(pid)
    for pid in ids:
        visit(pid)
    # A validated package cannot be ready if one of its declared dependencies is not ready.
    for _ in range(len(readiness)):
        state = {(x["id"], x["environment"]): x["ready"] for x in readiness}
        for item in readiness:
            dependencies = ids.get(item["id"], {}).get("dependencies", [])
            if isinstance(dependencies, list):
                item["ready"] = item["ready"] and all(state.get((d, item["environment"]), False) for d in dependencies)
    if errors:
        for item in readiness:
            item["ready"] = False
    return {"errors": errors, "warnings": warnings, "readiness": readiness}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("review")
    identity_command = commands.add_parser("binding-identity", help="Read-only identity for the selected binding; retain it with validation evidence")
    identity_command.add_argument("binding_key")
    add = commands.add_parser("add", help="Add a pending or evidenced package, then review the whole registry")
    add.add_argument("entry", type=Path)
    add.add_argument("--replace", action="store_true", help="Explicitly replace the same package id")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        path = inside(root, "config/wolfram_packages.json", must_exist=True)
        document = read_json(path)
        if args.command == "binding-identity":
            host = read_json(inside(root, "config/host.local.json", must_exist=True))
            binding = host.get("wolfram_bindings", {}).get(args.binding_key)
            print(json.dumps(binding_identity(binding), indent=2))
            return 0
        if args.command == "add":
            entry = read_json(inside(root, args.entry, must_exist=True))
            if not isinstance(document.get("packages"), list):
                raise ValueError("Existing registry is malformed.")
            previous = [x for x in document["packages"] if x.get("id") == entry.get("id")]
            if previous and not args.replace:
                raise ValueError("That id already exists; inspect it before an explicit --replace.")
            document["packages"] = [x for x in document["packages"] if x.get("id") != entry.get("id")] + [entry]
        result = review(root, document)
        if args.command == "add" and not result["errors"]:
            write_json(root, path, document)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result["errors"] else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
