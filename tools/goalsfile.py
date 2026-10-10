"""master/goals.md for CV Studio's Goals page: the AI proposal store, diff, the rule-1 check, backups,
save, restore and master/goals-log.md.

goals.md is the user's (CLAUDE.md rule 2). The goals-drafter agent writes only tools/goals-draft/proposal.md
(gitignored). save() and restore() are called only behind their click, the way Approve flips status: approved.
"""

import difflib
import hashlib
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = Path(__file__).resolve().parent / "goals-draft"
GOALS, LOG = "master/goals.md", "master/goals-log.md"
TRACKER_ENTRY = "(goals)"
KEEP_BACKUPS = 20
LOCK = threading.Lock()
LOG_HEADER = ("# Goals log\n\nWritten by CV Studio. One entry per change to master/goals.md: the date, how it was made, "
              "and the user's note word for word. Not read by any agent; the current direction is goals.md itself.\n")
BACKUP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}(-\d+)?\.md$")


class Conflict(Exception):
    """goals.md changed on disk since the page read it."""


# ---------- goals.md ----------

def read(root: Path = None) -> str:
    f = (root or ROOT) / GOALS
    return f.read_text() if f.exists() else ""  # a missing goals.md must not take three tabs down with it


def mtime(root: Path = None) -> str:
    f = (root or ROOT) / GOALS
    return str(f.stat().st_mtime_ns) if f.exists() else ""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def normalise(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"


def last_updated(text: str):
    m = re.search(r"^Last updated:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    return m.group(1) if m else None


def stamp(text: str, today: str) -> str:
    """Set the `Last updated:` line to today, adding it under the title if it is missing."""
    if re.search(r"^Last updated:.*$", text, re.M):
        return re.sub(r"^Last updated:.*$", f"Last updated: {today}", text, count=1, flags=re.M)
    lines = text.split("\n")
    at = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    lines[at:at] = ["", f"Last updated: {today}"] if at else [f"Last updated: {today}", ""]
    return "\n".join(lines)


def check(text: str):
    """Problems that make a version unsafe to save (the curator and extractor read these sections)."""
    if not text.strip():
        return ["goals.md can't be empty"]
    problems = []
    if not re.search(r"^# ", text, re.M):
        problems.append("the '# Career goals' title is missing")
    if not re.search(r"^## Target roles\s*$", text, re.M):
        problems.append("the '## Target roles' section is missing (the curator and extractor rank by it)")
    return problems


def diff(before: str, after: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                        "goals.md (before)", "goals.md (after)"))


def counts(before: str, after: str):
    lines = diff(before, after).splitlines()
    added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    return added, removed


def _words(text: str):
    text = re.sub(r"^\s*\d+\.\s", "", text, flags=re.M)  # list numbering is not a fact
    return re.findall(r"[A-Za-z][A-Za-z0-9&+'-]*|\d[\d.,]*%?", text)


def new_terms(base: str, notes, proposal: str):
    """Names and numbers in the proposal that neither goals.md nor the user's notes contain (CLAUDE.md rule 1).
    Advisory: a reworded sentence can trip it, so the page only warns."""
    known = {w.lower().strip(".,'") for w in _words(base + "\n" + "\n".join(notes))}
    out = []
    for w in _words(proposal):
        key = w.lower().strip(".,'")
        if (w[0].isupper() or w[0].isdigit()) and key and key not in known and w.strip(".,") not in out:
            out.append(w.strip(".,"))
    return out


# ---------- the AI proposal (tools/goals-draft/) ----------

def proposal_path() -> Path:
    return DIR / "proposal.md"


def _meta():
    try:
        return json.loads((DIR / "pending.json").read_text())
    except (OSError, ValueError):
        return None


def _write_meta(meta):
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "pending.json").write_text(json.dumps(meta, indent=1))


def start_proposal(note: str, date: str, base_sha: str):
    """A new draft: the user's note (word for word) and the goals.md version it is drafted from."""
    if proposal_path().exists():
        proposal_path().unlink()
    _write_meta({"notes": [{"text": note, "date": date}], "base_sha": base_sha, "sealed": False, "started": time.time()})


def add_note(note: str, date: str):
    """A revision: the proposal stays, so the drafter revises it. The base stays the goals.md version the
    first draft was made from, so a later outside edit still marks the draft stale."""
    meta = _meta()
    if not meta or not meta.get("sealed"):
        raise RuntimeError("there is no draft to revise")
    meta["notes"].append({"text": note, "date": date})
    meta.update(sealed=False, started=time.time())
    _write_meta(meta)


def undo_revision(previous: str):
    """A stopped or failed revise: the previous draft and its review come back, minus the new note."""
    meta = _meta()
    if not meta:
        return
    if len(meta["notes"]) > 1:
        meta["notes"].pop()
    meta["sealed"] = True
    proposal_path().write_text(previous)
    _write_meta(meta)


def notes():
    meta = _meta()
    return meta["notes"] if meta else []


def seal_proposal(message: str, fields: dict, terms):
    meta = _meta() or {}
    meta.update(sealed=True, when=time.time(), message=message, new_terms=list(terms),
                **{k: fields.get(k, "") for k in ("changed", "kept", "not done", "open")})
    _write_meta(meta)


def pending(root: Path = None):
    """The proposal awaiting review, with a live diff against the current goals.md, or None."""
    root = root or ROOT
    meta = _meta()
    if not meta or not meta.get("sealed") or not proposal_path().exists():
        return None
    text, current = proposal_path().read_text(), read(root)
    return {"notes": meta["notes"], "when": meta.get("when"), "message": meta.get("message", ""),
            "changed": meta.get("changed", ""), "kept": meta.get("kept", ""), "not_done": meta.get("not done", ""),
            "open": meta.get("open", ""), "new_terms": meta.get("new_terms", []), "text": text,
            "diff": diff(current, text), "stale": sha(current) != meta.get("base_sha")}


def unsealed():
    """Notes saved for a draft whose run did not finish (the page offers Retry)."""
    meta = _meta()
    return bool(meta) and not meta.get("sealed")


def discard():
    for f in (proposal_path(), DIR / "pending.json"):
        if f.exists():
            f.unlink()


# ---------- backups and the log ----------

def _backups_dir() -> Path:
    return DIR / "backups"


def _order(name: str):
    """Oldest first: by timestamp, then the -2, -3 suffix of backups made in the same second."""
    return name[:19], int(name[20:-3]) if len(name) > 22 else 1


def backup(text: str) -> str:
    d = _backups_dir()
    d.mkdir(parents=True, exist_ok=True)
    base = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    taken = [_order(p.name)[1] for p in d.iterdir() if BACKUP_RE.match(p.name) and p.name.startswith(base)]
    name = f"{base}-{max(taken) + 1}.md" if taken else f"{base}.md"  # never reuse a pruned name: it would sort as oldest
    (d / name).write_text(text)
    for old in sorted((p.name for p in d.iterdir() if BACKUP_RE.match(p.name)), key=_order)[:-KEEP_BACKUPS]:
        (d / old).unlink()
    return name


def _when(name: str) -> str:
    return f"{name[:10]} {name[11:13]}:{name[14:16]}"


def list_backups():
    d = _backups_dir()
    if not d.is_dir():
        return []
    names = sorted((p.name for p in d.iterdir() if BACKUP_RE.match(p.name)), key=_order, reverse=True)
    return [{"name": x, "when": _when(x), "size": (d / x).stat().st_size} for x in names]


def read_backup(name: str) -> str:
    f = _backups_dir() / name
    if not BACKUP_RE.match(name) or not f.is_file():
        raise ValueError("that saved version is not there any more")
    return f.read_text()


def log_entry(date: str, kind: str, notes, changed: str) -> str:
    lines = [f"## {date} ({kind})"]
    for i, n in enumerate(notes):
        label = "note" if i == 0 else f"revision {i}"
        body = [x.rstrip() for x in n["text"].strip().split("\n") if x.strip()]
        if len(body) > 1:  # a long note keeps its lines, as a quote block
            lines.append(f"- {label}:")
            lines += [f"> {x}" for x in body]
        else:
            lines.append(f"- {label}: {' '.join(n['text'].split())}")
    if not notes:
        lines.append("- note: (none given)")
    lines.append(f"- changed: {' '.join(changed.split()) or '(no summary)'}")
    return "\n".join(lines) + "\n"


def append_log(log: str, entry: str) -> str:
    return (log.rstrip("\n") + "\n\n" if log.strip() else LOG_HEADER + "\n") + entry


def save(text: str, today: str, kind: str, notes, changed: str = "", expect_mtime: str = None, root: Path = None):
    """The user's Save: back up the current file, write the new one with today's date, log it.
    Refuses (Conflict) if goals.md changed since the page read it."""
    root = root or ROOT
    text = normalise(text)
    problems = check(text)
    if problems:
        raise ValueError("; ".join(problems))
    with LOCK:
        if expect_mtime is not None and expect_mtime != mtime(root):
            raise Conflict("goals.md changed since you opened it (maybe in VS Code or chat). Reload first.")
        current = read(root)
        name = backup(current)
        new = stamp(text, today)
        added, removed = counts(current, new)
        (root / GOALS).write_text(new)
        log = root / LOG
        log.write_text(append_log(log.read_text() if log.exists() else "", log_entry(
            today, kind, notes, changed or f"{added} line{'s' if added != 1 else ''} added, {removed} removed")))
    return {"backup": name, "added": added, "removed": removed}


def restore(name: str, today: str, expect_mtime: str = None, root: Path = None):
    """Put a saved version back (the current file is backed up first, so a restore can be undone too)."""
    return save(read_backup(name), today, f"restored version from {_when(name)}", [], "", expect_mtime, root)
