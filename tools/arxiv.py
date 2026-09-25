"""Bounded arXiv PDF/source acquisition; downloaded content is never executed."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import uuid
import zlib
from common import inside, now, project_root, sha256, write_json

MAX_DOWNLOAD = 32 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_FILES = 1000
IDENTITY = re.compile(r"(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})v[1-9]\d*")
MARKER = re.compile(r"arXiv\s*:\s*((?:[a-z-]+(?:\.[A-Z]{2})?/\d{7}|\d{4}\.\d{4,5})v[1-9]\d*)")


def versioned(value):
    if not IDENTITY.fullmatch(value):
        raise ValueError("Use an explicit arXiv ID and version, e.g. hep-ph/0206123v1")
    return value


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "research-scaffold/3 (bounded paper retrieval)"}), timeout=30) as response:
        data = response.read(MAX_DOWNLOAD + 1)
        if len(data) > MAX_DOWNLOAD:
            raise ValueError("Download exceeds 32 MiB ceiling")
        return data, response.geturl()


def url_identity(url, role):
    parsed = urlparse(url)
    prefix = "/pdf/" if role == "pdf" else "/src/"
    if parsed.scheme != "https" or parsed.hostname not in {"arxiv.org", "export.arxiv.org"} or not parsed.path.startswith(prefix):
        return None
    value = parsed.path[len(prefix):].removesuffix(".pdf")
    return value if IDENTITY.fullmatch(value) else None


def pdf_identity(data, url, wanted):
    if not data.startswith(b"%PDF-"):
        raise ValueError("Response is not a PDF")
    text = ""
    try:
        from pypdf import PdfReader
        text = PdfReader(io.BytesIO(data)).pages[0].extract_text() or ""
    except Exception:
        pass  # Explicit version URL still provides transport evidence.
    markers = set(MARKER.findall(text))
    endpoint = url_identity(url, "pdf")
    if markers and markers != {wanted} or endpoint and endpoint != wanted:
        return "mismatch", "PDF first-page identifier or response URL conflicts with requested version"
    if markers == {wanted}:
        return "verified", "Embedded first-page arXiv identifier: " + wanted
    if endpoint == wanted:
        return "verified", "Official explicit-version response URL (embedded identity not available)"
    return "unknown", "Canonical/unrecognized PDF URL without verified embedded version"


def unpack(data):
    """Validate entire bounded payload before any extracted files are written."""
    if data.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            data = stream.read(MAX_EXPANDED + 1)
    if len(data) > MAX_EXPANDED:
        raise ValueError("Expanded source exceeds 64 MiB ceiling")
    try:
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
    except tarfile.ReadError:
        text = data.decode("utf-8", errors="replace")
        if "\\documentclass" not in text and "\\documentstyle" not in text:
            raise ValueError("Source is neither a tar archive nor recognizable single TeX")
        return {"paper.tex": data}
    files, paths, total = {}, {}, 0
    with archive:
        for count, member in enumerate(archive, 1):
            if count > MAX_FILES:
                raise ValueError("Source exceeds 1000 archive members")
            name = member.name
            if name in {'.', './'} and member.isdir():
                continue
            # Reject cross-platform aliases, drive/UNC names, reserved device names.
            parts = PurePosixPath(name).parts
            if not parts or name.startswith("/") or "\\" in name or any(p in {"..", "."} or p.endswith((".", " ")) or ":" in p or re.search(r'[<>"|?*\x00-\x1f]', p) or p.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *("COM"+str(i) for i in range(1,10)), *("LPT"+str(i) for i in range(1,10))} for p in parts):
                raise ValueError("Unsafe source path: " + name)
            normalized = "/".join(parts)
            folded = normalized.casefold()
            if folded in paths or any(folded.startswith(p + "/") and not directory or p.startswith(folded + "/") and not member.isdir() for p, directory in paths.items()):
                raise ValueError("Source path collision: " + name)
            if not member.isfile() and not member.isdir():
                raise ValueError("Links and special source members are not accepted")
            paths[folded] = member.isdir()
            if member.isfile():
                if PurePosixPath(normalized).suffix.lower() == ".nb":
                    raise ValueError("Notebook source member requires explicit user authorization; retained opaque archive only")
                total += member.size
                if member.size < 0 or total > MAX_EXPANDED:
                    raise ValueError("Expanded source exceeds 64 MiB ceiling")
                files[normalized] = archive.extractfile(member).read(member.size + 1)
                if len(files[normalized]) != member.size:
                    raise ValueError("Truncated source member")
    return files


def ingest(root, identity, pdf, pdf_url, source=None, source_url=None, source_error=None):
    identity = versioned(identity)
    if len(pdf) > MAX_DOWNLOAD or source is not None and len(source) > MAX_DOWNLOAD:
        raise ValueError("Download exceeds 32 MiB ceiling")
    status, evidence = pdf_identity(pdf, pdf_url, identity)
    # Each attempt has its own directory; previous originals are never overwritten.
    folder = inside(root, "sources/agentic_papers/arxiv/" + identity.replace("/", "_") + "/" + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    stamp = now().replace("-", "").replace(":", "")[:15].replace("T", "_")[:13]
    files = []
    def save(name, data, role, url=None):
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        files.append({"path": path.relative_to(root).as_posix(), "sha256": sha256(path), "role": role, "url": url})
        return files[-1]["path"]
    pdf_path = save(stamp + "_paper.pdf", pdf, "pdf", pdf_url)
    record = {"schema": 1, "paper_version": identity, "retrieved_at": now(), "pdf_status": status, "pdf_evidence": evidence,
              "source_status": "unavailable", "source_reason": source_error or "No source supplied", "files": files, "preferred": pdf_path if status == "verified" else None}
    if source is not None:
        save("original.source", source, "source_original", source_url)
        endpoint = url_identity(source_url or "", "source")
        record["source_status"] = "mismatch" if endpoint and endpoint != identity else "unknown"
        record["source_reason"] = "Source response must identify the same explicit version on the official endpoint"
        if endpoint == identity:
            try:
                extracted = unpack(source)
                texts = []
                for name, data in sorted(extracted.items()):
                    save("extracted/" + name, data, "source_member")
                    if Path(name).suffix.lower() in {".tex", ".sty", ".cls", ".bib", ".bbl"}:
                        texts.append("\n% FILE: " + name + "\n" + data.decode("utf-8", errors="replace"))
                usable = any(Path(name).suffix.lower() == ".tex" for name in extracted)
                record["source_status"] = "verified" if usable else "unusable"
                record["source_reason"] = "Official explicit-version response URL; source not compiled or compared in full to PDF"
                if usable:
                    body = save("reading.txt", "".join(texts).encode("utf-8"), "source_text")
                    if status == "verified":
                        record["preferred"] = body
            except (ValueError, OSError, EOFError, tarfile.TarError, zlib.error) as exc:
                record["source_status"], record["source_reason"] = "unusable", str(exc)
    record["pair_status"] = "matched" if status == record["source_status"] == "verified" else "not_matched"
    write_json(root, folder / "arxiv_manifest.json", record)
    return record


def acquire(root, identity):
    identity = versioned(identity)
    try:
        pdf, pdf_url = fetch("https://arxiv.org/pdf/" + identity)
    except Exception as original:
        pdf, pdf_url = fetch("https://arxiv.org/pdf/" + identity.rsplit("v", 1)[0])
        if pdf_identity(pdf, pdf_url, identity)[0] != "verified":
            raise ValueError("Versioned PDF failed; canonical fallback lacks matching embedded version") from original
    source, source_url, error = None, None, None
    try:
        source, source_url = fetch("https://arxiv.org/src/" + identity)
    except Exception as exc:
        error = str(exc)
    return ingest(root, identity, pdf, pdf_url, source, source_url, error)


def groups(root):
    """Only complete, hash-current acquisitions contribute preferred bodies."""
    result, choices = {}, {}
    base = root / "sources/agentic_papers/arxiv"
    if not base.exists():
        return result
    for member in base.rglob('*'):
        if member.is_file():
            result[member.relative_to(root).as_posix()] = {'preferred_body': None, 'representation_valid': False, 'provenance': 'Incomplete or unlisted acquisition'} 
    for path in sorted(base.glob("*/*/arxiv_manifest.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            versioned(record["paper_version"])
            valid = {}
            for item in record["files"]:
                target = inside(root, item["path"])
                if not target.is_relative_to(path.parent.resolve()):
                    raise ValueError("Representation leaves acquisition directory")
                if target.suffix.lower() == ".nb":
                    continue  # Notebook content and hashes require explicit authorization.
                if target.is_file() and sha256(target) == item["sha256"]:
                    valid[item["path"]] = item
            # A generated source body is usable only while all its inputs match.
            sources_ok = all(item["path"] in valid for item in record["files"] if item["role"] in {"source_original", "source_member", "source_text"})
            preferred = record.get("preferred")
            if preferred not in valid or not sources_ok or not any(item["role"] == "pdf" for item in valid.values()):
                preferred = next((p for p, item in valid.items() if item["role"] == "pdf" and record["pdf_status"] == "verified"), None)
            if preferred:
                rank = (valid[preferred]["role"] == "source_text", record.get("retrieved_at", ""), preferred)
                if rank > choices.get(record["paper_version"], (False, "", "")):
                    choices[record["paper_version"]] = rank
            for item in record["files"]:
                result[item["path"]] = {"paper_version": record["paper_version"], "representation": item["role"], "preferred_body": preferred,
                                        "representation_valid": item["path"] in valid, "provenance": path.relative_to(root).as_posix()}
        except (ValueError, KeyError, TypeError, OSError):
            # Malformed provenance is never a license to index unverified members.
            for member in path.parent.rglob("*"):
                if member.is_file():
                    result[member.relative_to(root).as_posix()] = {"preferred_body": None, "representation_valid": False, "provenance": path.relative_to(root).as_posix()}
    for representation in result.values():
        choice = choices.get(representation.get("paper_version"))
        representation["preferred_body"] = choice[2] if choice else None
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("command", choices=["acquire"])
    parser.add_argument("identity", help="Explicit IDvN; no unversioned/latest alias")
    args = parser.parse_args()
    try:
        print(json.dumps(acquire(project_root(args.root), args.identity), indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
