#!/usr/bin/env python3
"""Version-checked report locators for ordinary LaTeX labels, sections and equation environments."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from common import write_text as atomic_text

PARSER_SCOPE = "Literal section/chapter commands, label/tag commands, common equation environments, literal input/include relative to main source directory, ordinary newlabel aux records. No TeX macro expansion or proof of typeset correctness."
EQUATION_ENVS = {"equation", "equation*", "align", "align*", "gather", "gather*", "multline", "multline*", "eqnarray", "eqnarray*", "displaymath"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def within(root, path):
    value = (root / path).resolve()
    if not value.is_relative_to(root):
        raise ValueError("Report dependency leaves project: " + str(path))
    return value


def load(root):
    path = root / "catalog/report_locators.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()] if path.exists() else []


def save(root, records):
    path = root / "catalog/report_locators.jsonl"
    atomic_text(root, path, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records))


def group(text, start):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        return None, start
    depth, i = 1, start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return None, start


def normalize_grouped_value(value):
    """Remove only whole-value brace wrappers; never expand or simplify TeX tokens."""
    value = value.strip()
    while value.startswith("{"):
        inner, end = group(value, 0)
        if inner is None or end != len(value):
            break
        value = inner.strip()
    return value

def groups(text):
    result, cursor = [], 0
    while cursor < len(text):
        value, end = group(text, cursor)
        if value is None:
            break
        result.append(value)
        cursor = end
    return result


def no_comments(text):
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.search(r"(?<!\\)(?:\\\\)*%", line)
        if match:
            line = line[:match.start()] + ("\n" if line.endswith("\n") else "")
        lines.append(line)
    return "".join(lines)


def plain(value):
    return re.sub(r"\s+", " ", value).strip()


def dependencies(root, start, extension, warnings):
    found, visiting = [], set()
    def visit(path):
        path = within(root, path)
        if path.suffix.lower() != extension:
            raise ValueError("Unsupported report dependency type; no content read: " + path.name)
        if path in visiting:
            warnings.append("Repeated/cyclic include skipped: " + path.relative_to(root).as_posix())
            return
        if len(visiting) >= 100:
            raise ValueError("More than 100 report dependencies; explicit smaller report scope required")
        visiting.add(path)
        if not path.exists():
            raise ValueError("Missing report dependency: " + str(path))
        text = no_comments(path.read_text(encoding="utf-8-sig"))
        found.append((path, text))
        command = r"\\(?:input|include)\s*\{" if extension == ".tex" else r"\\@input\s*\{"
        for match in re.finditer(command, text):
            name, _ = group(text, match.end() - 1)
            if not name or any(char in name for char in "\\#$"):
                warnings.append("Dynamic include unsupported at " + path.relative_to(root).as_posix())
                continue
            included = Path(name)
            if not included.suffix:
                included = included.with_suffix(extension)
            visit(Path(start).parent / included)
    visit(start)
    return found


def parse_aux(files, warnings):
    labels = {}
    for path, text in files:
        for match in re.finditer(r"\\newlabel\s*\{", text):
            label, end = group(text, match.end() - 1)
            value, _ = group(text, end)
            fields = groups(value or "")
            if label is None or len(fields) < 2:
                warnings.append("Unsupported aux label record in " + path.name)
                continue
            if label.endswith("@cref"):
                continue
            if label in labels:
                warnings.append("Duplicate aux label: " + label)
            labels.setdefault(label, []).append({"printed_number": normalize_grouped_value(fields[0]), "printed_page": normalize_grouped_value(fields[1]), "aux": path.name})
    return labels


def parse_tex(root, files, labels, page_map, warnings):
    locators = []
    for path, text in files:
        rel = path.relative_to(root).as_posix()
        envs = []
        for match in re.finditer(r"\\begin\s*\{([^}]+)\}", text):
            env = match.group(1)
            if env not in EQUATION_ENVS:
                continue
            ending = re.search(r"\\end\s*\{" + re.escape(env) + r"\}", text[match.end():])
            if ending:
                end = match.end() + ending.end()
                envs.append((match.start(), end, text[match.start():end]))
            else:
                warnings.append("Unclosed equation environment at %s:%d" % (rel, text.count("\n", 0, match.start()) + 1))
        sections = []
        for match in re.finditer(r"\\(chapter|section|subsection|subsubsection|paragraph)(\*)?\s*(?:\[[^\]]*\])?\s*\{", text):
            title, end = group(text, match.end() - 1)
            if title is not None:
                entry = {"kind": "section", "level": match.group(1), "title": plain(title), "label": None,
                         "printed_number": None, "printed_page": None, "pdf_page": None,
                         "source": {"path": rel, "line": text.count("\n", 0, match.start()) + 1}, "text": text[match.start():end]}
                locators.append(entry)
                sections.append((match.start(), end, entry))
        for match in re.finditer(r"\\label\s*\{", text):
            label, end = group(text, match.end() - 1)
            if not label:
                continue
            containing = next((env for env in envs if env[0] <= match.start() < env[1]), None)
            prior = next((s for s in reversed(sections) if s[1] <= match.start()), None)
            # A section label is associated only across whitespace/comments; never guess across prose/math.
            is_section = prior is not None and not text[prior[1]:match.start()].strip()
            if containing:
                kind, snippet = "equation", containing[2]
                tags = list(re.finditer(r"\\tag\*?\s*\{", snippet))
                tag = group(snippet, tags[0].end() - 1)[0] if len(tags) == 1 and len(re.findall(r"\\label\s*\{", snippet)) == 1 else None
                if len(tags) > 1 and label not in labels:
                    warnings.append("Multiple tags in one environment need aux numbers: " + label)
            elif is_section:
                kind, snippet, tag = "section", prior[2]["text"], None
            else:
                kind, snippet, tag = "label", text[max(0, match.start() - 150):min(len(text), end + 250)], None
            values = labels.get(label, [None])
            for value in values:
                number = value["printed_number"] if value else normalize_grouped_value(tag) if tag is not None else None
                printed_page = value["printed_page"] if value else None
                entry = {"kind": kind, "label": label, "title": prior[2]["title"] if is_section else None,
                         "printed_number": number, "printed_page": printed_page, "pdf_page": page_map.get(str(printed_page)),
                         "source": {"path": rel, "line": text.count("\n", 0, match.start()) + 1}, "text": snippet[:6000],
                         "number_evidence": "aux" if value else "explicit_tag" if tag else "unknown"}
                if is_section and prior[2] in locators:
                    locators.remove(prior[2])
                locators.append(entry)
        # Unlabelled displayed equations with explicit tags are still resolvable by that tag.
        for start, end, snippet in envs:
            if re.search(r"\\label\s*\{", snippet):
                continue
            match = re.search(r"\\tag\*?\s*\{", snippet)
            tag = normalize_grouped_value(group(snippet, match.end() - 1)[0]) if match else None
            locators.append({"kind": "equation", "label": None, "title": None, "printed_number": tag,
                             "printed_page": None, "pdf_page": None, "source": {"path": rel, "line": text.count("\n", 0, start) + 1},
                             "text": snippet[:6000], "number_evidence": "explicit_tag" if tag else "unknown"})
    return locators


def register(root, report_id, tex, pdf=None, aux=None, aliases=(), page_map=None):
    records = load(root)
    previous = next((r for r in records if r["report_id"] == report_id), {})
    aliases = list(dict.fromkeys(previous.get("aliases", []) + list(aliases)))
    names = {report_id.casefold()} | {a.casefold() for a in aliases}
    for record in records:
        other = {record["report_id"].casefold()} | {a.casefold() for a in record.get("aliases", [])}
        if record["report_id"] != report_id and names & other:
            raise ValueError("Report ID/alias conflicts with existing report: " + record["report_id"])
    tex = within(root, tex)
    pdf = within(root, pdf) if pdf else tex.with_suffix(".pdf")
    aux = within(root, aux) if aux else tex.with_suffix(".aux")
    if pdf.suffix.lower() != ".pdf" or aux.suffix.lower() != ".aux":
        raise ValueError("PDF and aux arguments require .pdf and .aux files")
    warnings = []
    text_files = dependencies(root, tex, ".tex", warnings)
    aux_files = dependencies(root, aux, ".aux", warnings) if aux.exists() else []
    if not aux_files:
        warnings.append("No aux available: printed numbers/pages unknown except explicit tags")
    labels = parse_aux(aux_files, warnings)
    mapping = page_map or {}
    if any(not isinstance(value, int) or value < 1 for value in mapping.values()):
        raise ValueError("Physical PDF page mapping values must be positive integers")
    locators = parse_tex(root, text_files, labels, mapping, warnings)
    identities = {}
    for path, _ in text_files + aux_files:
        identities[path.relative_to(root).as_posix()] = digest(path)
    for path in (pdf, aux):
        identities[path.relative_to(root).as_posix()] = digest(path) if path.exists() else None
    main = tex.relative_to(root).as_posix()
    if not pdf.exists():
        warnings.append("PDF missing: no rendered report verified")
    else:
        try:
            from pypdf import PdfReader
            count = len(PdfReader(str(pdf)).pages)
            if any(p > count for p in mapping.values()):
                raise ValueError("Mapped physical page exceeds PDF page count")
        except ImportError:
            warnings.append("pypdf unavailable; physical page map not checked against PDF length")
        except ValueError:
            raise
        except Exception as exc:
            warnings.append("PDF page count unavailable: " + str(exc))
    if not mapping:
        warnings.append("Physical PDF pages are unknown; aux pages are printed page labels, not physical page indices")
    record = {"report_id": report_id, "aliases": list(dict.fromkeys(aliases)), "tex": main,
              "registered": now(), "identities": identities, "locators": locators,
              "parser_scope": PARSER_SCOPE, "warnings": warnings, "page_map": mapping,
              "revision": hashlib.sha256(json.dumps(identities, sort_keys=True).encode()).hexdigest()}
    previous = next((r for r in records if r["report_id"] == report_id), {})
    for key in ("notes", "judgments", "conventions", "originating_run", "supersedes"):
        if key in previous:
            record[key] = previous[key]
    save(root, [r for r in records if r["report_id"] != report_id] + [record])
    return {"report_id": report_id, "locators": len(locators), "revision": record["revision"], "warnings": warnings, "parser_scope": PARSER_SCOPE}


def lookup(root, report, label=None, equation=None, section=None):
    matches = [r for r in load(root) if report.casefold() in {r["report_id"].casefold(), *(a.casefold() for a in r.get("aliases", []))}]
    if len(matches) != 1:
        raise ValueError("Report identity is missing or ambiguous; use an explicit registered report ID")
    record = matches[0]
    changed = []
    for path, expected in record["identities"].items():
        p = within(root, path)
        actual = digest(p) if p.exists() else None
        if expected != actual:
            changed.append(path)
    if changed:
        raise ValueError("Stale report locators; re-register after review. Changed/missing: " + ", ".join(changed))
    matches = record["locators"]
    if label is not None:
        matches = [e for e in matches if e.get("label") == label]
    elif equation is not None:
        matches = [e for e in matches if e["kind"] == "equation" and e.get("printed_number") == equation]
    elif section is not None:
        matches = [e for e in matches if e["kind"] == "section" and section in (e.get("printed_number"), e.get("title"), e.get("label"))]
    if len(matches) != 1:
        raise ValueError("Locator missing or ambiguous (%d matches); use a unique label and check parser warnings" % len(matches))
    return {"report_id": record["report_id"], "revision": record["revision"], "locator": matches[0], "parser_scope": record["parser_scope"], "warnings": record["warnings"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("register", help="Register/refresh one explicit report version; does not compile or inspect scientific correctness")
    p.add_argument("--report-id", required=True)
    p.add_argument("--tex", required=True)
    p.add_argument("--pdf")
    p.add_argument("--aux")
    p.add_argument("--alias", action="append", default=[])
    p.add_argument("--page-map", type=Path, help="Project-relative JSON mapping printed labels to one-based physical PDF pages; absolute paths must remain inside project")
    p = sub.add_parser("lookup", help="Resolve a unique locator only if every registered input hash is current")
    p.add_argument("--report", required=True)
    group_ = p.add_mutually_exclusive_group(required=True)
    group_.add_argument("--label")
    group_.add_argument("--equation", help="Exact printed equation number/tag")
    group_.add_argument("--section", help="Exact section title, printed number, or label")
    sub.add_parser("list", help="List registered report identities and parser limits")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if not (root / "config/project.json").is_file():
            raise ValueError("Not a scaffold project root: missing config/project.json")
        if args.command == "register":
            map_path = within(root, args.page_map) if args.page_map else None
            if map_path and map_path.suffix.lower() != ".json":
                raise ValueError("--page-map requires a .json file")
            page_map = json.loads(map_path.read_text(encoding="utf-8-sig")) if map_path else None
            if page_map is not None and not isinstance(page_map, dict):
                raise ValueError("--page-map must contain a JSON object")
            result = register(root, args.report_id, args.tex, args.pdf, args.aux, args.alias, page_map)
        elif args.command == "lookup":
            result = lookup(root, args.report, args.label, args.equation, args.section)
        else:
            result = [{"report_id": r["report_id"], "aliases": r["aliases"], "tex": r["tex"], "revision": r["revision"], "warnings": r["warnings"]} for r in load(root)]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())






