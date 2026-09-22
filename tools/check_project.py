"""Bounded mechanical link/figure checks and project documentation statistics."""
from __future__ import annotations
import argparse, json, os, re, sys
from pathlib import Path
from urllib.parse import unquote
from common import project_root

LINK = re.compile(r"(?<!!)\[[^\]]*\]\((<[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)")
SKIP = {"tmp", ".git", "__pycache__"}

def walk(root):
    root = root.resolve()
    for folder, directories, filenames in os.walk(root, followlinks=False):
        parent = Path(folder)
        directories[:] = [name for name in directories
                          if name not in SKIP and not (parent / name).is_symlink()
                          and (parent / name).resolve().is_relative_to(root)]
        for name in filenames:
            path = parent / name
            if not path.is_symlink() and path.resolve().is_relative_to(root):
                yield path


def check_links(root):
    findings = []
    paths = [p for p in walk(root) if p.suffix.lower() == ".md" and "sources" not in p.relative_to(root).parts]
    for path in paths:
        text = path.read_text(encoding="utf-8-sig")
        text = re.sub(r"(?ms)^\x60{3}.*?^\x60{3}[^\n]*", "", text)
        for match in LINK.finditer(text):
            target = unquote(match.group(1).strip("<>")).split("#", 1)[0]
            if not target or "{{" in target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            candidate = (path.parent / target).resolve()
            line = text[:match.start()].count("\n") + 1
            if not candidate.is_relative_to(root):
                findings.append({"kind": "external_local_link", "file": path.relative_to(root).as_posix(), "line": line, "target": target})
            elif not candidate.exists():
                findings.append({"kind": "broken_link", "file": path.relative_to(root).as_posix(), "line": line, "target": target})
    return {"checked_documents": len(paths), "findings": findings}

def check_figures(root):
    findings, checked = [], 0
    for report in sorted((root / "reports_tex").iterdir()):
        if not report.is_dir() or report.is_symlink():
            continue
        used, visited = set(), set()
        pending = list(report.glob("*.tex"))
        while pending:
            tex = pending.pop().resolve()
            if tex in visited:
                continue
            visited.add(tex)
            body = re.sub(r"(?m)(?<!\\)%.*$", "", tex.read_text(encoding="utf-8-sig"))
            for raw in re.findall(r"\\(?:input|include)\s*\{([^}]+)\}", body):
                if "\\" in raw or "#" in raw:
                    findings.append({"kind": "unresolved_include_macro", "file": tex.relative_to(root).as_posix(), "target": raw})
                    continue
                include = report / raw
                if not include.suffix:
                    include = include.with_suffix(".tex")
                include = include.resolve()
                if include.suffix.lower() != ".tex" or not include.is_relative_to(report.resolve()):
                    findings.append({"kind": "unsupported_include", "file": tex.relative_to(root).as_posix(), "target": raw})
                elif not include.is_file():
                    findings.append({"kind": "missing_include", "file": tex.relative_to(root).as_posix(), "target": raw})
                else:
                    pending.append(include)
            for raw in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body):
                checked += 1
                if "\\" in raw or "#" in raw:
                    findings.append({"kind": "unresolved_graphics_macro", "file": tex.relative_to(root).as_posix(), "target": raw})
                    continue
                candidates = [report / raw, report / "figures" / raw]
                expanded = []
                for candidate in candidates:
                    expanded.extend([candidate] if candidate.suffix else [candidate.with_suffix(ext) for ext in (".pdf", ".png", ".jpg", ".jpeg", ".eps")])
                existing = [p.resolve() for p in expanded if p.is_file() and p.resolve().is_relative_to(root)]
                if not existing:
                    findings.append({"kind": "missing_figure", "file": tex.relative_to(root).as_posix(), "target": raw})
                else:
                    used.add(existing[0])
        figures = report / "figures"
        index = figures / "INDEX.md"
        if figures.is_dir() and not index.is_file():
            findings.append({"kind": "missing_figure_index", "file": figures.relative_to(root).as_posix()})
        content = index.read_text(encoding="utf-8-sig") if index.is_file() else ""
        for path in sorted(used):
            if not path.is_relative_to(figures.resolve()):
                findings.append({"kind": "figure_not_preserved_in_report", "file": path.relative_to(root).as_posix()})
            elif path.name not in content:
                findings.append({"kind": "unindexed_figure", "file": path.relative_to(root).as_posix()})
    return {"checked_inclusions": checked, "findings": findings,
            "limits": "Literal includegraphics and input/include paths relative to the report directory; no TeX macro expansion. Inspect graphics search-path macros, inline diagrams and scientific provenance separately."}


def audit(root):
    files = list(walk(root))
    docs = [{"path": p.relative_to(root).as_posix(), "bytes": p.stat().st_size} for p in files if p.suffix.lower() == ".md"]
    docs.sort(key=lambda item: item["bytes"], reverse=True)
    cache = [p for p in files if p.relative_to(root).parts[0] == "catalog" and (p.suffix in {".sqlite", ".db", ".txt"} or "extracted" in p.parts)]
    runs = list((root / "research" / "runs").glob("*/RUN.md"))
    return {"documentation_files": len(docs), "documentation_bytes": sum(d["bytes"] for d in docs),
            "largest_documents": docs[:8], "derived_cache_bytes": sum(p.stat().st_size for p in cache),
            "recent_runs_for_sampling": [p.relative_to(root).as_posix() for p in sorted(runs)[-5:]],
            "mechanical_links": check_links(root), "mechanical_figures": check_figures(root),
            "limits": "Statistics and mechanical checks only. Inspect selected documents for duplication, usefulness and scientific context; no files changed."}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root")
    parser.add_argument("command", choices=["links", "figures", "audit", "all"])
    args = parser.parse_args(argv)
    try:
        root = project_root(args.root)
        if args.command == "links": result = check_links(root)
        elif args.command == "figures": result = check_figures(root)
        elif args.command == "audit": result = audit(root)
        else: result = {"links": check_links(root), "figures": check_figures(root)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "audit": return 0
        values = result.values() if args.command == "all" else [result]
        return 1 if any(item.get("findings") for item in values) else 0
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
