"""Experience folders, interview records and master-CV lookups for CV Studio's experience side.

Mirrors .claude/skills/curate/SKILL.md (index.md template, statuses) the way appstate.py mirrors
.claude/skills/apply/SKILL.md. Change both together. Nothing here writes CV content: it creates folders
from the template, copies the user's answers word for word into interview.md, flips status lines on
their Finish, saves files they drop in, and checks that agents did not drop any of their notes.
"""

import re
from collections import Counter
from datetime import date
from pathlib import Path

from appstate import DATE_RE, ITEM_RE, MONTHS, answer_lines, SLUG_RE as APP_SLUG_RE, _one_line, _versioned, slugify

ROOT = Path(__file__).resolve().parent.parent
EXPS = ROOT / "experiences"
MASTER = ROOT / "master" / "master-cv.md"
EXP_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TYPES = ["work", "internship", "project", "leadership", "education", "self-study", "sport"]
ALLOWED_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".html", ".htm", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_UPLOAD = 25 * 1024 * 1024
MAX_ROUNDS = 3
SECTIONS = ["Context", "What I did", "Numbers", "Tools", "What went wrong and what I changed", "Interview story",
            "Target role angle", "Shareability", "Artifact notes", "From seed", "Open questions"]
INTERVIEW_HEADER = ("# Interview record: {slug}\n\n"
                    "Written by CV Studio. Questions come from the interviewer agent; `answer:` lines are the user's words, "
                    "copied exactly. Not a CV source: the facts live in index.md.\n")
UI_NOTE = "Also noted in CV Studio"
STATUS_LINE = re.compile(r"(?m)^status:[ \t]*(\S+)[ \t]*$")


# ---------- folders ----------

def resolve_exp(slug: str, exps: Path = EXPS) -> Path:
    slug = slug.strip().strip("/")
    if slug.startswith("experiences/"):
        slug = slug[len("experiences/"):]
    if not EXP_SLUG_RE.match(slug) or APP_SLUG_RE.match(slug):
        raise ValueError(f"not an experience slug: {slug!r}")
    path = (exps / slug).resolve()
    if path.parent != exps.resolve():
        raise ValueError(f"outside experiences/: {slug!r}")
    return path


def template(slug, title, organisation, dates, typ) -> str:
    """index.md for a new experience: the SKILL.md template with a blank line between sections."""
    body = "\n\n".join(f"## {s}" for s in SECTIONS)
    return (f"---\nslug: {slug}\ntitle: {title}\norganisation: {organisation}\ndates: {dates}\ntype: {typ}\nstatus: stub\n---\n\n"
            f"# {title}, {organisation}\n\n{body}\n")


def create_experience(title, organisation, dates, typ, slug=None, exps: Path = EXPS) -> Path:
    title, organisation, dates = (_one_line(x or "") for x in (title, organisation, dates))
    if not (title and organisation and dates):
        raise ValueError("title, organisation and dates are all needed")
    if typ not in TYPES:
        raise ValueError(f"type must be one of: {', '.join(TYPES)}")
    slug = slug or slugify(title)
    exp = resolve_exp(slug, exps)
    if exp.exists():
        raise FileExistsError(f"experiences/{slug}/ already exists")
    exp.mkdir()
    (exp / "artifacts").mkdir()
    (exp / "artifacts" / ".gitkeep").write_text("")
    (exp / "index.md").write_text(template(slug, title, organisation, dates, typ))
    return exp


def front_matter(md: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def set_status(md: str, new: str) -> str:
    """Change the status line inside the front matter only."""
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    if not m or not STATUS_LINE.search(m.group(1)):
        raise ValueError("index.md has no status line in its front matter")
    block = STATUS_LINE.sub(f"status: {new}", m.group(1), count=1)
    return f"---\n{block}\n---\n" + md[m.end():]


AY_RE = re.compile(r"\bAY\s?(\d{2})/(\d{2})\b")
PLANNED_RE = re.compile(r"(?i)\bplanned\b")


def timeline(text: str, today: date = None) -> dict:
    """Where an experience sits in time, for the Experiences filter: phase is "ended", "ongoing", "planned" or
    "undated", with its first and last month as "yyyy-mm" ("present" for an open end). "Present" or an end still
    ahead is ongoing. "Planned" or a start still ahead is planned. AY24/25 reads as Aug 2024 to May 2025."""
    today = today or date.today()
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", text or "")  # the date on a note like "(Robin, 2026-10-06: ...)"
    text = AY_RE.sub(lambda m: f"Aug 20{m.group(1)} - May 20{m.group(2)}", text)
    found, present = [], False
    for m in DATE_RE.finditer(text):
        if m.group("present"):
            present = True
            continue
        mon = MONTHS.get((m.group("mon") or "").lower())
        found.append((int(m.group("year")), mon))
    if not found:
        phase = "planned" if PLANNED_RE.search(text) else "ongoing" if present else "undated"
        return {"phase": phase, "start": None, "end": "present" if present else None}
    start = min((y, mon or 1) for y, mon in found)
    end = max((y, mon or 12) for y, mon in found)
    now = (today.year, today.month)
    if PLANNED_RE.search(text) or start > now:
        phase = "planned"
    elif present or end >= now:
        phase = "ongoing"
    else:
        phase = "ended"
    return {"phase": phase, "start": "%d-%02d" % start, "end": "present" if present else "%d-%02d" % end}


def _has_date(text: str) -> bool:
    return bool(DATE_RE.search(text or "") or AY_RE.search(text or "") or PLANNED_RE.search(text or ""))


def list_experiences(exps: Path = EXPS, master_md: str = None):
    master_md = master_md if master_md is not None else (MASTER.read_text() if MASTER.exists() else "")
    out = []
    for d in sorted(p for p in exps.iterdir() if p.is_dir() and EXP_SLUG_RE.match(p.name)):
        idx = d / "index.md"
        fm = front_matter(idx.read_text()) if idx.exists() else {}
        iv = (d / "interview.md").read_text() if (d / "interview.md").exists() else ""
        entry = master_entry(master_md, d.name)
        dates = fm.get("dates", "")  # a TODO in the notes falls back to the dates in the master CV heading
        when = timeline(dates if _has_date(dates) or not entry else entry["heading"])
        part_of = entry["owner"] if entry and entry["owner"] != d.name and entry["section"] != "Skills" else None
        out.append({"slug": d.name, "part_of": part_of, "title": fm.get("title", d.name), "organisation": fm.get("organisation", ""),
                    "dates": fm.get("dates", ""), "type": fm.get("type", ""), "status": fm.get("status", "stub"),
                    "interviewing": open_session_of(parse_interview(iv)) is not None,
                    "in_master": bool(entry), "archived": bool(entry and entry["archived"]),
                    "section": entry["section"] if entry else None, "artifacts": len(list_artifacts(d)), **when})
    return out


# ---------- master CV ----------

def master_entry(master_md: str, slug: str):
    """The `### ` block whose retrieve: line points at experiences/<slug>/index.md."""
    section, block = None, None
    blocks = []
    for line in master_md.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            block = None
        elif line.startswith("### "):
            block = {"heading": line[4:].strip(), "section": section, "lines": []}
            blocks.append(block)
        elif block is not None:
            block["lines"].append(line)
    for b in blocks:
        retrieve = next((l for l in b["lines"] if l.startswith("retrieve:")), "")
        if f"experiences/{slug}/index.md" in retrieve:
            tags_line = next((l for l in b["lines"] if l.startswith("tags:")), "")
            tags = [t.strip() for t in tags_line[5:].strip().strip("[]").split(",") if t.strip()]
            first = re.search(r"experiences/([a-z0-9-]+)/index\.md", retrieve)  # the entry's own experience
            return {"heading": b["heading"], "section": b["section"], "archived": b["section"] == "Archive",
                    "bullets": [l[2:] for l in b["lines"] if l.startswith("- ")], "tags": tags,
                    "owner": first.group(1) if first else slug}
    return None


def tag_vocabulary(claude_md: str):
    out, inside = [], False
    for line in claude_md.splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Tag vocabulary"
            continue
        m = inside and re.match(r"^- \*\*(.+?):\*\*\s*(.*)$", line)
        if m:
            out.append({"group": m.group(1), "tags": re.findall(r"`([^`]+)`", m.group(2))})
    return out


def section_text(md: str, heading: str) -> str:
    """Body of `## heading` (without the heading line), or '' if absent."""
    m = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", md)
    return m.group(1) if m else ""


# ---------- artifacts ----------

def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name.strip().replace(" ", "-")
    name = re.sub(r"[^A-Za-z0-9_.-]", "", name).lstrip(".")
    stem, suffix = Path(name).stem[:100], Path(name).suffix.lower()
    if not stem:
        raise ValueError("that file name has no usable characters")
    return stem + suffix


def save_artifact(exp: Path, name: str, data: bytes) -> str:
    name = safe_name(name)
    suffix = Path(name).suffix
    if suffix not in ALLOWED_EXT:
        hint = " Export it to PDF first." if suffix in (".docx", ".doc", ".pptx", ".ppt", ".key", ".pages", ".xlsx", ".numbers") else ""
        raise ValueError(f"{suffix or 'files without an extension'} can't be read by the interviewer.{hint}")
    if len(data) > MAX_UPLOAD:
        raise ValueError(f"too large: {len(data) / 1048576:.0f} MB, limit {MAX_UPLOAD // 1048576} MB")
    folder = exp / "artifacts"
    folder.mkdir(exist_ok=True)
    dest = folder / name
    if dest.exists():
        dest = _versioned(folder, name)
    dest.write_bytes(data)
    return dest.name


def list_artifacts(exp: Path):
    folder = exp / "artifacts"
    if not folder.is_dir():
        return []
    return [{"name": f.name, "size": f.stat().st_size} for f in sorted(folder.iterdir())
            if f.is_file() and not f.name.startswith(".")]


# ---------- interview.md ----------

def parse_interview(md: str):
    """[{date, kind, note, status, rounds: [{n, questions: [...]}]}], with questions as in appstate.parse_questions."""
    sessions, cur, rnd = [], None, None
    for i, line in enumerate(md.splitlines()):
        m = re.match(r"^## Session (\S+) \((\w+)\)\s*$", line)
        if m:
            cur = {"date": m.group(1), "kind": m.group(2), "note": "", "status": "open", "line": i, "rounds": []}
            sessions.append(cur)
            rnd = None
            continue
        if cur is None:
            continue
        r = re.match(r"^### Round (\d+)\s*$", line)
        if r:
            rnd = {"n": int(r.group(1)), "line": i, "last": i, "questions": []}
            cur["rounds"].append(rnd)
            continue
        if rnd is None:
            if line.startswith("note:"):
                cur["note"] = line[5:].strip()
            elif line.startswith("status:"):
                cur["status"] = line[7:].strip()
            continue
        item = ITEM_RE.match(line)
        if item:
            rnd["questions"].append({"index": len(rnd["questions"]), "line": i, "last": i, "ticked": item.group(1) != " ",
                                     "text": item.group(2).strip(), "answers": [], "outcomes": []})
            rnd["last"] = i
        elif rnd["questions"] and line[:1] in (" ", "\t") and line.strip():
            q = rnd["questions"][-1]
            q["last"] = rnd["last"] = i
            body = line.strip()
            if body.startswith("answer:"):
                q["answers"].append(body[7:].strip())
            elif body.startswith("outcome:"):
                q["outcomes"].append(body[8:].strip())
            else:
                q["text"] += " " + body
    return sessions


def open_session_of(sessions):
    return next((s for s in reversed(sessions) if s["status"] == "open"), None)


def open_session(md: str, slug: str, kind: str, note: str = "", today: date = None) -> str:
    today = today or date.today()
    if open_session_of(parse_interview(md)):
        raise ValueError("an interview is already open for this experience; finish it first")
    if kind not in ("add", "update"):
        raise ValueError("kind must be add or update")
    md = md.rstrip("\n") + "\n" if md.strip() else INTERVIEW_HEADER.format(slug=slug)
    note = _one_line(note or "")
    return md + f"\n## Session {today:%Y-%m-%d} ({kind})\n" + (f"note: {note}\n" if note else "") + "status: open\n"


def current_round(md: str):
    s = open_session_of(parse_interview(md))
    return s["rounds"][-1] if s and s["rounds"] else None


def round_count(md: str) -> int:
    s = open_session_of(parse_interview(md))
    return len(s["rounds"]) if s else 0


def write_round_answers(md: str, answers: dict, other: str = "", skipped: list = None) -> str:
    """`  answer:` lines under the current round's unticked questions, verbatim except line breaks;
    the free-text box becomes `- [ ] Also noted in CV Studio` at the end of the round."""
    skipped = skipped if skipped is not None else []
    rnd = current_round(md)
    if not rnd:
        raise ValueError("there is no open interview round")
    lines = md.splitlines()
    inserts = []
    for key, text in (answers or {}).items():
        text = text if (text or "").strip() else ""
        if not text:
            continue
        idx = int(key)
        if idx < 0 or idx >= len(rnd["questions"]) or rnd["questions"][idx]["ticked"]:
            skipped.append(idx)
            continue
        inserts.append((rnd["questions"][idx]["last"], answer_lines(text), 0))
    other = _one_line(other or "")
    if other:
        inserts.append((rnd["last"], [f"- [ ] {UI_NOTE}", f"  answer: {other}"], 1))
    if not inserts:
        return md
    # bottom-up so earlier indexes stay valid. At the same spot the free-text item goes in first so it ends up last
    for after, new, _ in sorted(inserts, key=lambda x: (x[0], x[2]), reverse=True):
        lines[after + 1:after + 1] = new
    return "\n".join(lines) + ("\n" if md.endswith("\n") else "")


def pending_round_answers(md: str) -> int:
    rnd = current_round(md)
    return sum(1 for q in rnd["questions"] if not q["ticked"] and q["answers"]) if rnd else 0


def close_session(md: str) -> str:
    s = open_session_of(parse_interview(md))
    if not s:
        raise ValueError("no open interview session")
    lines = md.splitlines()
    for i in range(s["line"] + 1, len(lines)):
        if lines[i].startswith("## ") or lines[i].startswith("### "):
            break
        if lines[i].strip() == "status: open":
            lines[i] = "status: closed"
            return "\n".join(lines) + ("\n" if md.endswith("\n") else "")
    raise ValueError("open session has no status line")


# ---------- guards ----------

def _outside_open_questions(md: str):
    out, inside = [], False
    for line in md.splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Open questions"
        if not inside and line.strip():
            out.append(line.rstrip())
    return Counter(out)


def index_guard(before: str, after: str):
    """Problems if an agent dropped a line of the user's notes (outside ## Open questions) or touched the front matter."""
    problems = []
    fm = lambda md: (re.match(r"^---\n.*?\n---\n", md, re.S) or [""])[0]
    if fm(before) != fm(after):
        problems.append("the front matter (title, dates, status) was changed")
    lost = _outside_open_questions(before) - _outside_open_questions(after)
    for line, n in lost.items():
        problems.append(f"a line of your notes went missing: {line[:100]}")
    return problems


def status_only_change(before: str, after: str) -> bool:
    strip = lambda md: STATUS_LINE.sub("status: _", md, count=1)
    return strip(before) == strip(after)


def outside_section_equal(before: str, after: str, heading: str) -> bool:
    """True if everything outside `## heading` is unchanged (used for CLAUDE.md's Tag vocabulary)."""
    cut = lambda md: re.sub(rf"(?ms)^## {re.escape(heading)}\s*\n.*?(?=^## |\Z)", f"## {heading}\n", md)
    return cut(before) == cut(after)
