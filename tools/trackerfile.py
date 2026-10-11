"""tracker.md edits the UI makes after each state change (CLAUDE.md "Tracker", SKILL.md section 6).

Pure text functions plus update(), which applies them to the file under a lock.
"""

import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "tracker.md"
LOCK = threading.Lock()


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "/")


def _section(lines, heading):
    """(start, end) indexes of the lines under `## heading`. end is exclusive."""
    start = next((i + 1 for i, l in enumerate(lines) if l.strip() == f"## {heading}"), None)
    if start is None:
        raise ValueError(f"tracker.md has no '## {heading}' section")
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def _append_row(lines, heading, row):
    start, end = _section(lines, heading)
    last = max((i for i in range(start, end) if lines[i].startswith("|")), default=None)
    if last is None:
        raise ValueError(f"'## {heading}' has no table")
    lines.insert(last + 1, row)


def upsert_application(text: str, slug: str, status: str, closes: str) -> str:
    lines = text.split("\n")
    row = f"| {slug} | {_cell(status)} | {_cell(closes)} |"
    start, end = _section(lines, "Applications")
    for i in range(start, end):
        if lines[i].startswith(f"| {slug} |"):
            lines[i] = row
            return "\n".join(lines)
    _append_row(lines, "Applications", row)
    return "\n".join(lines)


def _key(*cells) -> str:
    """A row's identity for spotting repeats: no trailing "(who, date)" stamp, case, spacing or punctuation.
    A curator or interviewer run that raises the same question on another day then matches the first row."""
    def one(c):
        c = re.sub(r"\s*\([^()]*\b\d{4}-\d{2}-\d{2}\)\s*\.?\s*$", "", _cell(c))
        return re.sub(r"[^a-z0-9]+", " ", c.lower()).strip()
    return " | ".join(one(c) for c in cells)


def _has_row(lines, heading, *cells) -> bool:
    start, end = _section(lines, heading)
    want = _key(*cells)
    for i in range(start, end):
        if lines[i].startswith("|") and not lines[i].startswith("| ---"):
            have = [c for c in lines[i].strip().strip("|").split("|")]
            if _key(*have) == want:
                return True
    return False


def add_waiting_item(text: str, entry: str, item: str) -> str:
    lines = text.split("\n")
    if _has_row(lines, "Waiting on you (no deadline)", entry, item):
        return text
    _append_row(lines, "Waiting on you (no deadline)", f"| {_cell(entry)} | {_cell(item)} |")
    return "\n".join(lines)


def replace_waiting_item(text: str, entry: str, prefix: str, item: str) -> str:
    """Drop the entry's rows that start with `prefix`, then add `item`. For counts that each run restates."""
    lines = text.split("\n")
    start, end = _section(lines, "Waiting on you (no deadline)")
    head = f"| {_cell(entry)} | {_cell(prefix)}"
    lines = [l for i, l in enumerate(lines) if not (start <= i < end and l.startswith(head))]
    return add_waiting_item("\n".join(lines), entry, item)


def merge_skill_gap(text: str, company: str, items, when: str) -> str:
    """One line per company: append items it does not already mention, or add a new line."""
    items = [_cell(i) for i in items if i.strip()]
    if not items:
        return text
    lines = text.split("\n")
    start, end = _section(lines, "Skill gaps surfaced by applications")
    for i in range(start, end):
        label = lines[i][2:].split(":", 1)[0] if lines[i].startswith("- ") else ""
        if label and company.lower() in label.lower():
            new = [x for x in items if x.lower() not in lines[i].lower()]
            if new:
                lines[i] = lines[i].rstrip() + f" Also ({when}): {', '.join(new)}."
            return "\n".join(lines)
    last = max((i for i in range(start, end) if lines[i].startswith("- ")), default=start)
    lines.insert(last + 1, f"- {company}: {', '.join(items)}.")
    return "\n".join(lines)


def set_last_updated(text: str, when: str, note: str) -> str:
    return re.sub(r"(?m)^Last updated: .*$", f"Last updated: {when} ({_cell(note)})", text, count=1)


def update(*edits, path: Path = TRACKER):
    """Apply edits (functions text -> text) to tracker.md atomically with respect to other UI jobs."""
    with LOCK:
        text = path.read_text()
        for edit in edits:
            text = edit(text)
        path.write_text(text)


def add_dated_item(text: str, when: str, entry: str, what: str) -> str:
    lines = text.split("\n")
    if _has_row(lines, "Waiting on a date or event", when, entry, what):
        return text
    _append_row(lines, "Waiting on a date or event", f"| {_cell(when)} | {_cell(entry)} | {_cell(what)} |")
    return "\n".join(lines)


def rows_mentioning(text: str, slug: str):
    """Tracker rows and bullets that name `slug` (both Waiting tables and Interview prep only)."""
    lines = text.split("\n")
    out = []
    for heading in ("Waiting on a date or event", "Waiting on you (no deadline)", "Interview prep only (never on a CV)"):
        try:
            start, end = _section(lines, heading)
        except ValueError:
            continue
        for i in range(start, end):
            line = lines[i]
            if line.startswith("| ---") or not line.strip():
                continue
            if re.search(rf"(?<![a-z0-9-]){re.escape(slug)}(?![a-z0-9-])", line):
                cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.startswith("|") else [line[2:].strip()]
                out.append({"section": heading, "line": line, "cells": cells})
    return out


def delete_rows_mentioning(text: str, slug: str) -> str:
    for row in rows_mentioning(text, slug):
        text = delete_row(text, row["line"])
    return text


def delete_row(text: str, line: str) -> str:
    lines = text.split("\n")
    if line not in lines:
        raise ValueError("that tracker row is no longer there (it may have changed)")
    lines.remove(line)
    return "\n".join(lines)


WAITING = "Waiting on you (no deadline)"
VIEW_SECTIONS = ("Waiting on a date or event", WAITING, "Applications", "Skill gaps surfaced by applications",
                 "Interview prep only (never on a CV)")


def all_items(text: str):
    """Every row and bullet in the sections CV Studio's tracker page shows, with its header cells."""
    lines = text.split("\n")
    out = []
    for heading in VIEW_SECTIONS:
        try:
            start, end = _section(lines, heading)
        except ValueError:
            continue
        header = None
        for i in range(start, end):
            line = lines[i]
            if line.startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if i + 1 < end and lines[i + 1].startswith("| ---"):
                    header = cells
                elif not line.startswith("| ---"):
                    out.append({"section": heading, "line": line, "cells": cells, "header": header, "kind": "row"})
            elif line.startswith("- "):
                out.append({"section": heading, "line": line, "cells": [line[2:].strip()], "header": None, "kind": "bullet"})
    return out


def replace_item(text: str, old: str, cells) -> str:
    """Rewrite one row (or bullet) by its exact current text, keeping its kind."""
    lines = text.split("\n")
    if old not in lines:
        raise ValueError("that row changed or is gone. Reload the page")
    new = f"- {_cell(cells[0])}" if old.startswith("- ") else "| " + " | ".join(_cell(c) for c in cells) + " |"
    lines[lines.index(old)] = new
    return "\n".join(lines)

