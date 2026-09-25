#!/usr/bin/env python3
"""Discover local capabilities without installs, network calls or executable wrappers."""
from __future__ import annotations
import argparse
import ctypes
import datetime as dt
import hashlib
import importlib
import importlib.metadata as metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
from common import write_json

BASELINE = ("numpy", "scipy", "matplotlib", "sympy", "mpmath", "pandas", "psutil", "threadpoolctl")
TOOLS = {
    "wolframscript": ("wolframscript",), "wolfram_kernel": ("WolframKernel", "MathKernel"),
    "pdflatex": ("pdflatex",), "xelatex": ("xelatex",), "bibtex": ("bibtex",),
    "biber": ("biber",), "pdftoppm": ("pdftoppm",), "pdftotext": ("pdftotext",),
    "kpsewhich": ("kpsewhich",),
}
CHECK_STATES = {"passed", "failed", "inconclusive", "not_performed"}



REPORT_SKILLS = {
    "ars": {"name": "academic-research-suite", "purpose": "independent report review",
            "url": "https://github.com/Imbad0202/academic-research-skills-codex"},
    "tikz": {"name": "tikz-diagrams", "purpose": "useful report diagrams",
             "url": "https://github.com/Patrick-Healy/tikz-diagrams-skill"},
}


def skill_setup(root, profile, previous, discovery=None):
    """Evaluate explicit host/runtime evidence; inventory alone never proves activation."""
    discovery = discovery or {}
    if not isinstance(discovery, dict):
        raise ValueError("skill_discovery must be an object.")
    observations = discovery.get("capabilities", {})
    if not isinstance(observations, dict):
        raise ValueError("skill_discovery.capabilities must be an object.")
    checked = bool(discovery)
    hashes = evidence(root, discovery.get("evidence")) if checked else {}
    if type(discovery.get("complete", False)) is not bool:
        raise ValueError("skill_discovery.complete must be boolean.")
    records = {}
    same_host = profile["host_fingerprint"] == previous.get("host_fingerprint")
    for key, spec in REPORT_SKILLS.items():
        observed = observations.get(key, {})
        if not isinstance(observed, dict):
            raise ValueError("Skill observations must be objects.")
        for field in ("installed", "available"):
            if field in observed and type(observed[field]) is not bool:
                raise ValueError("installed/available observations must be booleans or omitted.")
        copies = [x["local_sha256"] for x in profile["extensions"]
                  if x["kind"] == "skill" and x["name"] == spec["name"]]
        installed, available = observed.get("installed"), observed.get("available")
        if installed is False and available is True:
            raise ValueError("A missing skill cannot simultaneously be available.")
        if available is True:
            status = "available"
        elif installed is True:
            status = "installed_but_unavailable" if available is False else "activation_unknown"
        elif installed is False or (discovery.get("complete") and not copies):
            status = "missing"
        else:
            status = "unknown"
        messages = {
            "available": "Available for " + spec["purpose"] + ".",
            "missing": "Offer to install " + spec["name"] + " for " + spec["purpose"] + "; ask for consent first.",
            "installed_but_unavailable": "Restore activation/discovery of " + spec["name"] + "; do not install a duplicate.",
            "activation_unknown": "Verify current-agent availability of " + spec["name"] + "; do not install a duplicate.",
            "unknown": "Check host installation and current-agent availability of " + spec["name"] +
                       "; if absent, offer installation for " + spec["purpose"] + " with consent.",
        }
        signature = digest({"status": status, "copies": sorted(copies), "spec": spec})
        old = previous.get("skill_setup", {}).get(key, {})
        decision = old.get("decision") if same_host and old.get("state_identity") == signature else None
        if decision:
            try:
                if evidence(root, list(decision["evidence_hashes"])) != decision["evidence_hashes"]:
                    decision = None
            except (OSError, ValueError, KeyError):
                decision = None
        suppressed = bool(decision and decision["choice"] in {"declined", "deferred", "accepted"})
        message = messages[status]
        if suppressed:
            message = "Previous setup choice: " + decision["choice"] + "; no repeated offer while state is unchanged."
        records[key] = {**spec, "status": status, "state_identity": signature,
                        "evidence_hashes": hashes, "decision": decision,
                        "recommendation": message, "offer_suppressed": suppressed}
    return records


def record_setup(root, receipt_path):
    path = inside(root, "config/host.local.json", must_exist=True)
    profile = read_json(path)
    if profile.get("host_fingerprint") != fingerprint() or profile.get("project_root") != str(root):
        raise ValueError("Host/project profile is stale; initialize this copy first.")
    receipt = read_json(inside(root, receipt_path, must_exist=True))
    key, choice = receipt.get("skill"), receipt.get("choice")
    if key not in profile.get("skill_setup", {}) or choice not in {"accepted", "declined", "deferred", "reconsider"}:
        raise ValueError("Setup receipt needs skill ars/tikz and choice accepted/declined/deferred/reconsider.")
    if not receipt.get("checked_at") or not receipt.get("user_instruction"):
        raise ValueError("Setup decisions need checked_at and the actual user_instruction.")
    receipt["evidence_hashes"] = evidence(root, receipt.get("evidence"))
    profile["skill_setup"][key]["decision"] = receipt
    write_json(root, path, profile)
    return {"recorded": key, "choice": choice, "scope": "Records user choice only; no installation or update performed."}
def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def read_json(path, default=None):
    # Type/extension checks precede reading; config options never authorize notebook work.
    path = Path(path)
    if path.suffix.lower() != ".json" or path.resolve().suffix.lower() != ".json":
        raise ValueError("Structured configuration and receipts must be .json files; notebooks are not read.")
    if not path.exists():
        return default
    if path.stat().st_size > 4 * 1024**2:
        raise ValueError("Structured JSON input exceeds the 4 MiB configuration limit.")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Structured JSON input must contain an object.")
    return value


def inside(root, value, must_exist=False):
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError("Project writes and evidence must resolve within --root.")
    if must_exist and not path.is_file():
        raise ValueError(f"Evidence file is missing: {value}")
    return path


def evidence_file(root, value):
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError("Evidence references must be project-relative strings.")
    path = inside(root, value, must_exist=True)
    if Path(value).suffix.lower() == ".nb" or path.suffix.lower() == ".nb":
        raise ValueError("Notebook content processing is explicit-only; use script/text evidence.")
    return path


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def fingerprint():
    # Store only an opaque machine identity, not the network name.
    return digest({"node": platform.node(), "system": platform.system(), "machine": platform.machine()})


def memory():
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total", ctypes.c_ulonglong), ("available", ctypes.c_ulonglong),
                        ("page_total", ctypes.c_ulonglong), ("page_available", ctypes.c_ulonglong),
                        ("virtual_total", ctypes.c_ulonglong), ("virtual_available", ctypes.c_ulonglong),
                        ("extended_available", ctypes.c_ulonglong)]
        state = MEMORYSTATUSEX()
        state.length = ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            return {"total_bytes": state.total, "available_bytes": state.available}
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        return {"total_bytes": page * os.sysconf("SC_PHYS_PAGES"),
                "available_bytes": page * os.sysconf("SC_AVPHYS_PAGES")}
    except (AttributeError, OSError, ValueError):
        return {"total_bytes": None, "available_bytes": None}


def resource_policy(hardware, override=None):
    cores = max(1, hardware.get("logical_cpus") or 1)
    total = hardware.get("total_bytes")
    cpu_budget = max(1, cores // 2)
    # Initial ceilings reserve at least half the machine for interactive use.
    jobs = max(1, min(4, cpu_budget // 4, int(total / (16 * 1024**3)) if total else 1))
    result = {
        "origin": "recommended", "max_numerical_jobs": jobs,
        "threads_per_job": max(1, min(4, cpu_budget // jobs)),
        "max_memory_fraction": 0.5,
        "reason": "Initial ceilings reserve half of logical CPUs/memory; use a pilot and current free memory before substantial work.",
    }
    if override:
        for key in ("max_numerical_jobs", "threads_per_job"):
            value = override.get(key)
            if type(value) is not int or value < 1:
                raise ValueError(f"Policy {key} must be a positive integer.")
        fraction = override.get("max_memory_fraction")
        if isinstance(fraction, bool) or not isinstance(fraction, (int, float)) or not 0 < fraction <= 0.8:
            raise ValueError("Policy max_memory_fraction must be in (0, 0.8].")
        if not isinstance(override.get("reason"), str) or not override["reason"].strip():
            raise ValueError("An explicit resource policy needs a reason.")
        if override["max_numerical_jobs"] * override["threads_per_job"] > cores:
            raise ValueError("Combined jobs and threads exceed detected logical CPUs.")
        result.update({key: override[key] for key in ("max_numerical_jobs", "threads_per_job", "max_memory_fraction", "reason")})
        result["origin"] = "user"
    result["max_total_memory_bytes"] = int(total * result["max_memory_fraction"]) if total else None
    return result


def package_metadata(names):
    packages = {}
    for name in names:
        record = {"installed": False, "version": None, "location": None, "capability": "not_performed"}
        try:
            distribution = metadata.distribution(name)
            record.update(installed=True, version=distribution.version, location=str(distribution.locate_file("").resolve()))
        except metadata.PackageNotFoundError:
            pass
        packages[name] = record
    return packages


def discover_tools(bindings):
    found = {}
    for name, aliases in TOOLS.items():
        configured = bindings.get(name)
        if configured:
            path = Path(configured).expanduser()
            if not path.is_absolute():
                raise ValueError(f"Tool binding {name} must be an exact absolute path.")
            selected = str(path)
            origin = "configured"
        else:
            selected = next((p for alias in aliases if (p := shutil.which(alias))), None)
            origin = "PATH discovery" if selected else "unavailable"
        exists = bool(selected and Path(selected).is_file())
        found[name] = {"path": selected, "exists": exists, "origin": origin,
                       "capability": "not_performed" if exists else "unavailable",
                       "version": None,
                       "file_identity": {"size": Path(selected).stat().st_size, "mtime_ns": Path(selected).stat().st_mtime_ns} if exists else None}
    return found


def inventory(roots, kind, limit=250):
    """Bounded metadata inventory; a directory is never treated as proof of activation."""
    results, warnings = [], []
    for root_value in roots:
        origin = Path(root_value).expanduser().resolve()
        if not origin.is_dir():
            warnings.append(f"{kind} root unavailable: {origin}")
            continue
        for directory, children, files in os.walk(origin):
            current = Path(directory)
            depth = len(current.relative_to(origin).parts)
            children[:] = [c for c in sorted(children) if c not in {".git", "node_modules", "__pycache__", "tmp"}]
            if depth >= (6 if kind == "plugin" else 3):
                children[:] = []
            match = (kind == "skill" and "SKILL.md" in files) or (kind == "plugin" and current.name == ".codex-plugin" and "plugin.json" in files)
            if not match:
                continue
            if len(results) >= limit:
                warnings.append(f"{kind} inventory capped at {limit} entries; remaining locations uninspected")
                return results, warnings
            path = current / ("SKILL.md" if kind == "skill" else "plugin.json")
            try:
                if path.resolve().suffix.lower() == ".nb":
                    warnings.append(f"Skipped notebook target for {kind} metadata: {path}")
                    continue
                if path.stat().st_size > 512000:
                    warnings.append(f"Skipped oversized {kind} metadata: {path}")
                    continue
                raw = path.read_bytes()
                source = None
                version = None
                if kind == "plugin":
                    data = json.loads(raw.decode("utf-8-sig"))
                    name = str(data.get("name") or current.parent.name)
                    version = data.get("version")
                    candidate = data.get("repository") or data.get("homepage")
                    if isinstance(candidate, dict):
                        candidate = candidate.get("url")
                    if isinstance(candidate, str) and candidate.startswith(("https://", "http://")) and "@" not in candidate.split("://", 1)[-1].split("/", 1)[0]:
                        source = candidate.split("?", 1)[0]
                else:
                    text = raw.decode("utf-8-sig")
                    front = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
                    name_match = re.search(r"(?m)^name:\s*(.+?)\s*$", front)
                    version_match = re.search(r"(?m)^version:\s*(.+?)\s*$", front)
                    name = name_match.group(1).strip("'\"") if name_match else current.name
                    version = version_match.group(1).strip("'\"") if version_match else None
                results.append({"kind": kind, "name": name, "version": version, "location": str(path),
                                "local_sha256": hashlib.sha256(raw).hexdigest(), "source_url": source,
                                "states": {"present_on_disk": True, "installed": "unknown", "enabled": "unknown", "exposed": "unknown", "usable": "not_performed"},
                                "release_status": "unchecked"})
            except (OSError, UnicodeError, ValueError) as exc:
                warnings.append(f"Unreadable {kind} metadata at {path}: {type(exc).__name__}")
    groups = {}
    for item in results:
        groups.setdefault(item["name"], []).append(item["location"])
    for name, locations in groups.items():
        if len(locations) > 1:
            warnings.append(f"Multiple {kind} copies of {name}; active copy must be identified from runtime evidence.")
    return results, warnings


def python_probes(root, policy, packages):
    scratch = Path(tempfile.mkdtemp(prefix="environment_", dir=inside(root, "tmp")))
    os.environ["MPLCONFIGDIR"] = str(scratch / "matplotlib")
    os.environ["XDG_CACHE_HOME"] = str(scratch / "cache")
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[variable] = str(policy["threads_per_job"])
    checks = {}
    def run(name, expected, check):
        try:
            actual = check()
            checks[name] = {"status": "passed", "expected": expected, "actual": actual}
        except ImportError as exc:
            checks[name] = {"status": "not_performed", "expected": expected, "reason": str(exc)}
        except Exception as exc:
            checks[name] = {"status": "failed", "expected": expected, "reason": f"{type(exc).__name__}: {exc}"}
        if name in packages:
            packages[name]["capability"] = checks[name]["status"]
    def linear():
        import numpy as np
        matrix = np.array([[3., 1.], [1., 2.]])
        rhs = np.array([9., 8.])
        answer = np.linalg.solve(matrix, rhs)
        residual = float(np.linalg.norm(matrix @ answer - rhs, ord=np.inf))
        assert residual < 1e-12 and np.allclose(answer, [2., 3.]), (answer, residual)
        return {"solution": answer.tolist(), "residual": residual}
    def integral():
        from scipy.integrate import quad
        value, error = quad(lambda x: x*x, 0., 1.)
        assert abs(value - 1/3) < 1e-12
        return {"integral": value, "estimated_error": error}
    def symbolic():
        import sympy as sp
        x = sp.symbols("x", real=True)
        value = sp.simplify(sp.sin(x)**2 + sp.cos(x)**2 - 1)
        assert value == 0
        return {"residual": str(value)}
    def precision():
        import mpmath as mp
        with mp.workdps(50):
            residual = abs(mp.sqrt(2)**2 - 2)
            assert residual < mp.mpf("1e-45")
            return {"digits": 50, "residual": str(residual)}
    def table():
        import pandas as pd
        frame = pd.DataFrame({"x": [1, 2], "y": [0.25, 0.5]})
        destination = scratch / "roundtrip.csv"
        frame.to_csv(destination, index=False)
        restored = pd.read_csv(destination)
        assert frame.equals(restored)
        return {"rows": len(restored), "path": destination.relative_to(root).as_posix()}
    def plot():
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        destination = scratch / "plot.png"
        figure, ax = plt.subplots(figsize=(2, 2))
        ax.plot([0, 1], [0, 1])
        figure.tight_layout()
        figure.savefig(destination, dpi=60)
        plt.close(figure)
        assert destination.stat().st_size > 100
        assert destination.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        return {"backend": matplotlib.get_backend(), "path": destination.relative_to(root).as_posix(), "limitation": "PNG signature checked; no visual scientific validation."}
    def resources():
        import psutil
        return {"logical_cpus": psutil.cpu_count(), "physical_cpus": psutil.cpu_count(logical=False),
                "available_bytes": psutil.virtual_memory().available}
    def threads():
        from threadpoolctl import threadpool_info, threadpool_limits
        with threadpool_limits(limits=policy["threads_per_job"]):
            records = [{k: item.get(k) for k in ("user_api", "internal_api", "num_threads", "version")} for item in threadpool_info()]
            assert all(item.get("num_threads", 0) <= policy["threads_per_job"] for item in records if isinstance(item.get("num_threads"), int))
        return {"backends": records, "limitation": "Only backends visible to threadpoolctl are covered."}
    for name, expected, check in (
        ("numpy", "A*x=b gives x=(2,3), residual <1e-12", linear),
        ("scipy", "Integral of x^2 on [0,1] is 1/3", integral),
        ("sympy", "sin(x)^2+cos(x)^2-1 simplifies to zero for real x", symbolic),
        ("mpmath", "50-digit sqrt(2)^2 residual <1e-45", precision),
        ("pandas", "Two-row CSV roundtrip preserves values", table),
        ("matplotlib", "Headless PNG export exists with PNG signature", plot),
        ("psutil", "Read resource counters", resources),
        ("threadpoolctl", "Visible backends respect requested thread limit inside context", threads),
    ):
        if name in packages:
            run(name, expected, check)
    receipt = {"checked_at": now(), "python": sys.executable, "policy": policy,
               "checks": checks, "scope": "Small capability checks, not broad scientific validation."}
    destination = scratch / "python_checks.json"
    write_json(root, destination, receipt)
    return {"evidence": destination.relative_to(root).as_posix(), **receipt}


def identity(profile, component):
    family, _, name = component.partition(":")
    if family == "python":
        item = profile.get("python", {}).get("packages", {}).get(name)
        if name == "interpreter":
            item = {k: profile.get("python", {}).get(k) for k in ("executable", "version", "prefix")}
    elif family == "tool":
        item = profile.get("tools", {}).get(name)
    elif family in {"plugin", "skill"}:
        matches = [x for x in profile.get("extensions", []) if x["kind"] == family and x["name"] == name]
        if len(matches) != 1:
            raise ValueError("Extension identity is missing or ambiguous; use distinct recorded names.")
        item = matches[0]
    else:
        item = None
    if item is None:
        raise ValueError(f"Unknown component: {component}")
    # Mutable audit state must not change component identity.
    stable = {k: v for k, v in item.items() if k not in {"capability", "states", "release_status"} and not (family == "tool" and k == "version")}
    return digest(stable)


def evidence(root, paths):
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise ValueError("A receipt needs a nonempty evidence list of project-relative files.")
    result = {}
    for value in paths:
        if Path(value).is_absolute():
            raise ValueError("Evidence paths must be project-relative.")
        path = evidence_file(root, value)
        result[value] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def record(root, kind, receipt_path):
    path = inside(root, "config/host.local.json", must_exist=True)
    profile = read_json(path)
    if profile.get("host_fingerprint") != fingerprint() or profile.get("project_root") != str(root):
        raise ValueError("Host/project profile is stale; initialize this copy first.")
    receipt = read_json(inside(root, receipt_path, must_exist=True))
    component = receipt.get("component", "")
    key = identity(profile, component)
    for field in ("checked_at", "method", "recommendation"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            raise ValueError(f"A receipt needs {field}.")
    if kind == "capability_checks":
        if receipt.get("status") not in CHECK_STATES or not receipt.get("capability"):
            raise ValueError("A capability receipt needs capability and a valid status.")
        if receipt["status"] == "passed" and ("expected" not in receipt or "actual" not in receipt):
            raise ValueError("Passed checks need expected and actual outcomes.")
        receipt["evidence_hashes"] = evidence(root, receipt.get("evidence"))
        key_name = component + "/" + receipt["capability"]
    else:
        if receipt.get("status") not in {"verified", "unknown", "unchecked"}:
            raise ValueError("Release status must be verified, unknown or unchecked.")
        if receipt["status"] == "verified":
            if not receipt.get("latest_stable") or not receipt.get("source_url", "").startswith("https://"):
                raise ValueError("Verified release information needs latest_stable and an authoritative HTTPS source.")
            if receipt.get("compatible_target") and not receipt.get("compatibility_basis"):
                raise ValueError("A compatible target needs a compatibility_basis.")
        receipt["evidence_hashes"] = evidence(root, receipt.get("evidence"))
        key_name = component
    if kind == "capability_checks":
        family, _, component_name = component.partition(":")
        if family == "tool" and receipt.get("observed_version"):
            profile["tools"][component_name]["version"] = receipt["observed_version"]
        if family in {"plugin", "skill"} and receipt.get("observed_states"):
            supplied = receipt["observed_states"]
            if not isinstance(supplied, dict) or any(k not in {"installed", "enabled", "exposed", "usable"} for k in supplied):
                raise ValueError("Unsupported extension observation.")
            for item in profile["extensions"]:
                if item["kind"] == family and item["name"] == component_name:
                    item["states"].update(supplied)
    receipt["component_identity"] = key
    receipt["host_fingerprint"] = profile["host_fingerprint"]
    receipt["stale"] = False
    profile.setdefault(kind, {})[key_name] = receipt
    write_json(root, path, profile)
    return {"recorded": key_name, "kind": kind, "status": receipt["status"], "scope": "Stores caller-supplied evidence; acceptance does not independently verify an upstream release or scientific claim."}


def state(root):
    profile = read_json(inside(root, "config/host.local.json"))
    if not profile:
        return {"initialized": False, "needs_audit": True, "reasons": ["No host profile."]}
    reasons = []
    if profile.get("project_root") != str(root):
        reasons.append("Project location changed; rebind project-local absolute paths before use.")
    if profile.get("host_fingerprint") != fingerprint():
        reasons.append("Host fingerprint changed; local bindings, validation and policy need reassessment.")
    current_python = str(Path(sys.executable).resolve())
    if profile.get("python", {}).get("executable") != current_python:
        reasons.append("Selected Python differs from this process; do not silently switch interpreters.")
    if profile.get("python", {}).get("version") != platform.python_version():
        reasons.append("Python version changed.")
    for name, tool in profile.get("tools", {}).items():
        target = Path(tool["path"]) if tool.get("path") else None
        exists = bool(target and target.is_file())
        current = {"size": target.stat().st_size, "mtime_ns": target.stat().st_mtime_ns} if exists else None
        if current != tool.get("file_identity"):
            reasons.append(f"Tool file changed or became unavailable: {name}")
    for extension in profile.get("extensions", []):
        try:
            target = Path(extension["location"])
            if target.suffix.lower() == ".nb" or target.resolve().suffix.lower() == ".nb":
                raise ValueError("Notebook target is not eligible extension metadata.")
            if hashlib.sha256(target.read_bytes()).hexdigest() != extension["local_sha256"]:
                reasons.append(f"Extension instructions/manifest changed: {extension['name']}")
        except (OSError, ValueError):
            reasons.append(f"Extension instructions/manifest unavailable: {extension['name']}")
    previous_packages = profile.get("python", {}).get("packages", {})
    current_packages = package_metadata(previous_packages)
    changed = [n for n, p in previous_packages.items() if current_packages[n]["version"] != p.get("version") or current_packages[n]["location"] != p.get("location")]
    if changed:
        reasons.append("Python package identity changed: " + ", ".join(changed))
    for group in ("capability_checks", "release_checks"):
        for key, receipt in profile.get(group, {}).items():
            for value, saved_hash in receipt.get("evidence_hashes", {}).items():
                try:
                    target = evidence_file(root, value)
                    actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                    if actual_hash != saved_hash:
                        reasons.append(f"Changed audit evidence: {key}")
                        break
                except (OSError, ValueError):
                    reasons.append(f"Missing audit evidence: {key}")
                    break
    return {"initialized": True, "needs_audit": bool(reasons), "reasons": reasons,
            "current_memory": memory(), "resource_policy": profile.get("resource_policy")}


def audit(root, args):
    inside(root, "tmp").mkdir(parents=True, exist_ok=True)
    config = read_json(inside(root, "config/project.json"), {}) or {}
    settings = config.get("environment", {})
    bindings = read_json(inside(root, args.bindings, must_exist=True)) if args.bindings else {}
    previous = read_json(inside(root, "config/host.local.json"), {}) or {}
    same_host = previous.get("host_fingerprint") == fingerprint()
    old_root = Path(previous["project_root"]) if previous.get("project_root") else None
    moved_project = bool(old_root and old_root != root)
    configured_python = bindings.get("selected_python") or (previous.get("python", {}).get("executable") if same_host else None)
    selected_python = str(Path(sys.executable).resolve())
    if configured_python and Path(configured_python).resolve() != Path(selected_python):
        raise ValueError("This process is not the configured Python. Invoke the selected interpreter directly.")
    hardware = {"logical_cpus": os.cpu_count(), **memory()}
    override = read_json(inside(root, args.policy, must_exist=True)) if args.policy else None
    if override is None and same_host and previous.get("resource_policy", {}).get("origin") == "user":
        override = previous["resource_policy"]
    policy = resource_policy(hardware, override)
    local_tools = {n: x["path"] for n, x in previous.get("tools", {}).items() if x.get("origin") == "configured" and x.get("path")} if same_host else {}
    if moved_project:
        local_tools = {n: p for n, p in local_tools.items() if not Path(p).is_relative_to(old_root)}
    local_tools.update(settings.get("tools", {}))
    local_tools.update(bindings.get("tools", {}))
    packages = package_metadata(settings.get("baseline_python_packages", BASELINE))
    extensions, warnings = [], []
    for kind in ("skill", "plugin"):
        roots = [str(inside(root, p)) for p in settings.get(kind + "_roots", [])]
        roots += bindings.get(kind + "_roots", [])
        roots += getattr(args, kind + "_root", [])
        found, issues = inventory(roots, kind)
        extensions += found
        warnings += issues
    if not extensions:
        warnings.append("No extension inventory locations supplied; installed/enabled/exposed plugin and skill states remain unknown.")
    wolfram_bindings = previous.get("wolfram_bindings", {}) if same_host else {}
    if moved_project:
        wolfram_bindings = {n: b for n, b in wolfram_bindings.items() if not isinstance(b, dict) or not b.get("path") or not Path(b["path"]).is_relative_to(old_root)}
    wolfram_bindings = bindings.get("wolfram_bindings", wolfram_bindings)
    profile = {
        "schema_version": 1, "audited_at": now(), "host_fingerprint": fingerprint(), "project_root": str(root),
        "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "hardware": hardware, "resource_policy": policy,
        "python": {"executable": selected_python, "version": platform.python_version(),
                   "prefix": sys.prefix, "packages": packages},
        "tools": discover_tools(local_tools), "extensions": extensions,
        "wolfram_bindings": wolfram_bindings,
        "capability_checks": {}, "release_checks": {},
        "warnings": warnings,
        "pending": [
            "Record runtime evidence for installed, enabled, exposed and usable extension states; directory discovery alone cannot establish them.",
            "Check official stable releases and compatibility, then record release receipts; this helper never fetches or installs updates.",
            "Invoke configured TeX/PDF tools directly with the required workdir and noninstalling options; record actual artifact checks.",
            "Invoke the headless .wl check directly with the configured Wolfram launcher/kernel; record version, license and known-result outcome.",
        ],
    }
    if moved_project:
        profile["warnings"].append("Project moved: old project-local absolute tool/package bindings were discarded; rebind explicitly if needed.")
    if previous and not same_host:
        profile["warnings"].append("Host changed: old absolute bindings and user resource policy were not reused.")
    for group in ("capability_checks", "release_checks"):
        for key, receipt in previous.get(group, {}).items():
            try:
                unchanged = same_host and receipt.get("component_identity") == identity(profile, receipt["component"])
                for value, saved_hash in receipt.get("evidence_hashes", {}).items():
                    target = evidence_file(root, value)
                    unchanged = unchanged and hashlib.sha256(target.read_bytes()).hexdigest() == saved_hash
            except (KeyError, ValueError, OSError):
                unchanged = False
            profile[group][key] = {**receipt, "stale": not unchanged}
    if args.probe_python:
        profile["python_probe"] = python_probes(root, policy, packages)
        profile["python_probe"]["host_fingerprint"] = profile["host_fingerprint"]
        profile["python_probe"]["package_identity"] = digest(packages)
        profile["python_probe"]["stale"] = False
    elif previous.get("python_probe"):
        prior_probe = previous["python_probe"]
        old_packages = previous.get("python", {}).get("packages", {})
        unchanged = same_host and policy == previous.get("resource_policy") and set(packages) == set(old_packages)
        unchanged = unchanged and all(p["version"] == old_packages.get(n, {}).get("version") and p["location"] == old_packages.get(n, {}).get("location") for n, p in packages.items())
        try:
            inside(root, prior_probe["evidence"], must_exist=True)
        except (KeyError, ValueError):
            unchanged = False
        profile["python_probe"] = {**prior_probe, "stale": not unchanged}
        if unchanged:
            for n in packages:
                packages[n]["capability"] = old_packages[n].get("capability", "not_performed")
    profile["skill_setup"] = skill_setup(root, profile, previous, bindings.get("skill_discovery"))
    write_json(root, "config/host.local.json", profile)
    return {
        "profile": "config/host.local.json",
        "python": selected_python, "resource_policy": policy,
        "python_packages": {n: {"version": p["version"], "check": p["capability"]} for n, p in packages.items()},
        "skill_setup": profile["skill_setup"],
        "extensions_found": len(extensions), "warnings": profile["warnings"], "pending": profile["pending"],
        "scope": "Local inventory plus requested bounded Python checks; other capability/release checks require evidence.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("audit")
    init.add_argument("--probe-python", action="store_true")
    init.add_argument("--bindings", help="Project-local JSON with selected_python, tools, optional extension roots and Wolfram bindings")
    init.add_argument("--policy", help="Project-local JSON with explicit job/thread/memory policy and reason")
    init.add_argument("--skill-root", action="append", default=[])
    init.add_argument("--plugin-root", action="append", default=[])
    commands.add_parser("status")
    for command in ("record-check", "record-release", "record-setup"):
        sub = commands.add_parser(command)
        sub.add_argument("receipt")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if not (root / "config/project.json").is_file():
            raise ValueError("Not an initialized scaffold layout: config/project.json is missing.")
        if args.command == "audit":
            result = audit(root, args)
        elif args.command == "record-setup":
            result = record_setup(root, args.receipt)
        elif args.command == "status":
            result = state(root)
        else:
            result = record(root, "capability_checks" if args.command == "record-check" else "release_checks", args.receipt)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
