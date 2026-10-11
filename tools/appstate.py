"""Application folder state and the manager's non-LLM writes, shared by tools/ui.py and its tests.

Mirrors .claude/skills/apply/SKILL.md sections 2 (folder state) and 4a (answer lines). Change both together.
Nothing here writes CV content: it creates folders and jd.md, copies the user's answers word for word,
flips the status line on their Approve, and moves superseded files into drafts/.
"""

import re
import shutil
from datetime import date
from pathlib import Path

from render import split_sections

ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "applications"
SLUG_RE = re.compile(r"^\d{4}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")
APPROVED_RE = re.compile(r"(?m)^status:[ \t]*approved[ \t]*$")
DRAFT_RE = re.compile(r"(?m)^status:[ \t]*draft[ \t]*$")
QUESTIONS = "## Open questions"
ITEM_RE = re.compile(r"^- \[( |x|X)\] ?(.*)$")
UI_CHANGE = "Change requested in UI"


# ---------- folders ----------

def resolve_app(slug: str, apps: Path = APPS) -> Path:
    """applications/<slug> as an absolute path. ValueError for anything that is not a plain slug."""
    slug = slug.strip().strip("/")
    if slug.startswith("applications/"):
        slug = slug[len("applications/"):]
    if not SLUG_RE.match(slug):
        raise ValueError(f"not an application slug: {slug!r}")
    path = (apps / slug).resolve()
    if path.parent != apps.resolve():
        raise ValueError(f"outside applications/: {slug!r}")
    return path


def final_pdf(app: Path):
    pdfs = sorted(p for p in app.glob("*_CV_*.pdf") if not p.stem.endswith("_PREVIEW"))
    return pdfs[0] if pdfs else None


def preview_pdf(app: Path):
    pdfs = sorted(app.glob("*_CV_*_PREVIEW.pdf"))
    return pdfs[0] if pdfs else None


def preview_stale(app: Path) -> bool:
    """A preview PDF exists but is older than extraction.md (a revise or a hand edit since it was rendered)."""
    pdf, ext = preview_pdf(app), app / "extraction.md"
    return bool(pdf and ext.exists() and pdf.stat().st_mtime_ns < ext.stat().st_mtime_ns)


def folder_state(app: Path) -> str:
    """none | jd only | draft | approved | rendered (SKILL.md section 2)."""
    if not app.is_dir():
        return "none"
    if final_pdf(app):
        return "rendered"
    ext = app / "extraction.md"
    if not ext.exists():
        return "jd only" if (app / "jd.md").exists() else "none"
    return "approved" if APPROVED_RE.search(ext.read_text()) else "draft"


def list_apps(apps: Path = APPS):
    out = []
    for d in sorted((p for p in apps.iterdir() if p.is_dir() and SLUG_RE.match(p.name)), reverse=True):
        md = (d / "extraction.md").read_text() if (d / "extraction.md").exists() else ""
        out.append({"slug": d.name, "state": folder_state(d), "unticked": unticked(md),
                    "company": company_from(d, md), "role": role_from(d)})
    return out


def role_from(app: Path) -> str:
    """Role from jd.md's first line (`# Company: Role`), else from the slug."""
    jd = app / "jd.md"
    if jd.exists():
        first = jd.read_text().splitlines()[:1]
        if first and first[0].startswith("# ") and ":" in first[0]:
            return first[0].split(":", 1)[1].strip()
    return " ".join(app.name.split("-")[3:])


def company_from(app: Path, md: str = "") -> str:
    for line in split_sections(md).get("JD summary", []) if md else []:
        m = re.match(r"-\s*company:\s*(.+)", line)
        if m:
            return re.split(r"[,(]", m.group(1))[0].strip()
    jd = app / "jd.md"
    if jd.exists():
        first = jd.read_text().splitlines()[:1]
        if first and first[0].startswith("# "):
            return first[0][2:].split(":")[0].strip()
    return app.name.split("-", 2)[-1]


# ---------- open questions ----------

def _question_bounds(lines):
    """(start, end) line indexes of the open questions section body. end is exclusive."""
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == QUESTIONS) + 1
    except StopIteration:
        return None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def parse_questions(md: str):
    """Questions in file order: {index, line, ticked, text, answers, decisions}."""
    lines = md.splitlines()
    bounds = _question_bounds(lines)
    if not bounds:
        return []
    out = []
    for i in range(*bounds):
        line = lines[i]
        m = ITEM_RE.match(line)
        if m:
            out.append({"index": len(out), "line": i, "last": i, "ticked": m.group(1) != " ",
                        "text": m.group(2).strip(), "answers": [], "decisions": []})
        elif out and line[:1] in (" ", "\t") and line.strip():
            q = out[-1]
            q["last"] = i
            body = line.strip()
            if body.startswith("answer:"):
                q["answers"].append(body[7:].strip())
            elif body.startswith("decision:"):
                q["decisions"].append(body[9:].strip())
            else:
                q["text"] += " " + body
    return out


def unticked(md: str) -> int:
    return sum(1 for q in parse_questions(md) if not q["ticked"])


def pending_answers(md: str) -> int:
    """Unticked questions that already carry an answer: the revise run has not applied them yet."""
    return sum(1 for q in parse_questions(md) if not q["ticked"] and q["answers"])


def _one_line(text: str) -> str:
    return " ".join(text.split())


def answer_lines(text: str) -> list:
    """The user's answer as `  answer:` lines, one per paragraph, so the breaks they meant survive.
    A single line break inside a sentence still joins (a textarea wraps, people paste)."""
    return [f"  answer: {_one_line(p)}" for p in re.split(r"\n\s*\n", str(text)) if p.strip()]


def write_answers(md: str, answers: dict, other: str = "", skipped: list = None) -> str:
    """Insert `  answer: <text>` under each answered unticked question, verbatim except that line
    breaks become spaces. A free-form request becomes `- [ ] Change requested in UI` at the section end.
    Answers to questions that are already ticked (or no longer exist) are skipped and listed in `skipped`."""
    skipped = skipped if skipped is not None else []
    lines = md.splitlines()
    bounds = _question_bounds(lines)
    if not bounds:
        raise ValueError("extraction.md has no open questions section")
    questions = parse_questions(md)
    inserts = []  # (after_line_index, new_lines)
    for key, text in answers.items():
        text = text if (text or "").strip() else ""
        if not text:
            continue
        idx = int(key)
        if idx < 0 or idx >= len(questions) or questions[idx]["ticked"]:
            skipped.append(idx)
            continue
        inserts.append((questions[idx]["last"], answer_lines(text), 0))
    other = _one_line(other or "")
    if other:
        last = bounds[1] - 1
        while last >= bounds[0] and not lines[last].strip():
            last -= 1
        inserts.append((max(last, bounds[0] - 1), [f"- [ ] {UI_CHANGE}", f"  answer: {other}"], 1))
    if not inserts:
        raise ValueError("those questions are already answered; nothing new to apply" if skipped else "no answers given")
    # bottom-up so earlier indexes stay valid. At the same spot the free-text item goes in first so it ends up last
    for after, new, _ in sorted(inserts, key=lambda x: (x[0], x[2]), reverse=True):
        lines[after + 1:after + 1] = new
    return "\n".join(lines) + ("\n" if md.endswith("\n") else "")


def approve(md: str) -> str:
    """The user's Approve: flip the one status line. Refuses while any question is unticked."""
    n = unticked(md)
    if n:
        raise ValueError(f"{n} open question(s) are still unticked")
    if not DRAFT_RE.search(md):
        raise ValueError("extraction.md has no `status: draft` line")
    return DRAFT_RE.sub("status: approved", md, count=1)


def unmatched(md: str):
    for line in split_sections(md).get("JD summary", []):
        m = re.match(r"-\s*unmatched:\s*\[(.*)\]\s*$", line)
        if m:
            return [s.strip() for s in re.split(r",\s*(?![^()]*\))", m.group(1)) if s.strip()]
    return []


# ---------- selected entries and their scores ----------

SCORE_RE = re.compile(r"\s*\[score\s+(\d+)\s*/\s*10\]\s*$")
BREAKDOWN_RE = re.compile(r"(tags|relevance|goals|recency)\s*([+\-−]?\d+)")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(r"(?:(?P<mon>[A-Za-z]{3})[a-z]*\s+)?(?P<year>(?:19|20)\d{2})\b|(?P<present>\bPresent\b)")
JD_DATE_RE = re.compile(r"(?m)^Source:.*?(\d{4}-\d{2}-\d{2})")


def parse_entries(md: str):
    """The `### ` blocks under "Selected experiences": {heading, score, section, why, breakdown, bullets}.
    `score` is the `[score n/10]` suffix (None if missing). `breakdown` is the `score:` line as
    {tags, relevance, goals, recency}, or None for a draft written before the extractor broke scores down."""
    lines = next((v for k, v in split_sections(md).items() if k.startswith("Selected experiences")), [])
    out = []
    for line in lines:
        if line.startswith("### "):
            raw = line[4:].strip()
            m = SCORE_RE.search(raw)
            out.append({"heading": SCORE_RE.sub("", raw).strip(), "score": int(m.group(1)) if m else None,
                        "section": "", "why": "", "breakdown": None, "bullets": []})
        elif not out:
            continue
        elif line.startswith("section:"):
            out[-1]["section"] = line[8:].strip()
        elif line.startswith("why:"):
            out[-1]["why"] = line[4:].strip()
        elif line.startswith("score:"):
            parts = {k: int(v.replace("−", "-")) for k, v in BREAKDOWN_RE.findall(line[6:])}
            if parts:
                out[-1]["breakdown"] = {k: parts.get(k, 0) for k in ("tags", "relevance", "goals", "recency")}
        elif line.startswith("- "):
            out[-1]["bullets"].append(line[2:].strip())
    return out


def end_date(heading: str):
    """When the entry ended, from the latest date range in its heading: the first day of that month
    (December for a bare year), date.max for "Present", None when the heading carries no date.
    Handles "May 2026 - Aug 2026", "Nov 2024", "Sep 2026 - Present" and "2024 - 2028 (Expected)"."""
    latest = None
    for m in DATE_RE.finditer(heading):
        if m.group("present"):
            return date.max
        mon = MONTHS.get((m.group("mon") or "").lower())  # any other word before the year is not a month
        d = date(int(m.group("year")), mon or 12, 1)
        if latest is None or d > latest:
            latest = d
    return latest


def recency(heading: str, on: date) -> int:
    """The extractor's recency term: +1 if ongoing or ended 12 months ago or less, 0 if it ended 13 to 36
    months ago or carries no date, -1 if older. Counted in calendar months against `on`."""
    end = end_date(heading)
    if end is None:
        return 0
    if end == date.max:
        return 1
    months = (on.year - end.year) * 12 + on.month - end.month
    return 1 if months <= 12 else 0 if months <= 36 else -1


def jd_date(app: Path, today: date = None) -> date:
    """The date in jd.md's `Source: ..., yyyy-mm-dd` line, else today. Recency is measured against it."""
    jd = app / "jd.md"
    m = JD_DATE_RE.search(jd.read_text()) if jd.exists() else None
    if m:
        try:
            return date.fromisoformat(m.group(1))
        except ValueError:
            pass
    return today or date.today()


# ---------- new applications ----------

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_slug(company: str, role: str, today: date = None) -> str:
    today = today or date.today()
    slug = f"{today:%Y-%m}-{slugify(company)}-{slugify(role)}"
    if not SLUG_RE.match(slug):
        raise ValueError("company and role must contain letters or digits")
    return slug


def find_existing(company: str, role: str, apps: Path = APPS):
    """(exact, similar): folders for the same company and role in any month, and same company other role."""
    c, r = slugify(company), slugify(role)
    exact, similar = [], []
    for d in sorted(apps.glob(f"*-{c}-*")):
        if not d.is_dir() or not SLUG_RE.match(d.name):
            continue
        rest = d.name[8:]  # strip yyyy-mm-
        if rest == f"{c}-{r}":
            exact.append(d.name)
        elif rest.startswith(f"{c}-"):
            similar.append(d.name)
    return exact, similar


def write_jd(app: Path, company: str, role: str, jd: str, today: date = None) -> Path:
    """jd.md in the manager's format (SKILL.md section 3, first row)."""
    today = today or date.today()
    app.mkdir(parents=False, exist_ok=False)
    body = jd.replace("\r\n", "\n").replace("\r", "\n").strip()
    path = app / "jd.md"
    path.write_text(f"# {company.strip()}: {role.strip()}\n\nSource: pasted in CV Studio, {today:%Y-%m-%d}.\n\n{body}\n")
    return path


# ---------- moves into drafts/ ----------

def _versioned(drafts: Path, name: str) -> Path:
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while (drafts / f"{stem}-v{n}{suffix}").exists():
        n += 1
    return drafts / f"{stem}-v{n}{suffix}"


def archive_previews(app: Path):
    """After a final render: preview files go to drafts/ (versioned if a copy is already there)."""
    drafts = app / "drafts"
    moved = []
    for f in list(app.glob("*_PREVIEW.pdf")) + list(app.glob("cv-preview.html")):
        drafts.mkdir(exist_ok=True)
        dest = drafts / f.name
        if dest.exists():
            dest = _versioned(drafts, f.name)
        shutil.move(str(f), dest)
        moved.append(dest.name)
    return moved


def archive_final(app: Path):
    """Before a re-render: the final PDF and cv.html go to drafts/ with a -v<n> suffix."""
    drafts = app / "drafts"
    moved = []
    for f in [final_pdf(app), app / "cv.html"]:
        if f and f.exists():
            drafts.mkdir(exist_ok=True)
            dest = _versioned(drafts, f.name)
            shutil.move(str(f), dest)
            moved.append(dest.name)
    return moved


# ---------- the user's own edits to an application (CV Studio code, never an agent) ----------

SRC_RE = re.compile(r"\s*\(source:\s*([^)]*)\)\s*$")


def draft_for_editing(md: str) -> dict:
    """What the Edit draft page needs: each selected entry with its bullets split into text and citation,
    plus the education lines and the skills line."""
    sections = split_sections(md)
    entries = []
    for line in next((v for k, v in sections.items() if k.startswith("Selected experiences")), []):
        if line.startswith("### "):
            entries.append({"line": line, "heading": SCORE_RE.sub("", line[4:]).strip(), "section": "", "bullets": []})
        elif entries and line.startswith("section:"):
            entries[-1]["section"] = line[8:].strip()
        elif entries and line.startswith("- "):
            m = SRC_RE.search(line[2:])
            entries[-1]["bullets"].append({"text": SRC_RE.sub("", line[2:]).strip(), "source": m.group(1).strip() if m else ""})
    return {"entries": entries,
            "education": [l[2:].strip() for l in sections.get("Education", []) if l.startswith("- ")],
            "skills": " ".join(l.strip() for l in sections.get("Suggested skills line", []) if l.strip())}


def _section_span(lines, pred):
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and pred(l[3:].strip())), None)
    if start is None:
        return None
    end = next((j for j in range(start + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
    return start, end


def edit_draft(md: str, entries, removed, education, skills, who: str) -> str:
    """Rewrite the selected entries (order, section, bullets), the education lines and the skills line.
    Each bullet keeps a citation: a new bullet must bring one. Removed entries are listed under ## Dropped."""
    lines = md.splitlines()
    span = _section_span(lines, lambda h: h.startswith("Selected experiences"))
    if not span:
        raise ValueError("this draft has no Selected experiences section")
    blocks, cur = {}, None
    for line in lines[span[0] + 1:span[1]]:
        if line.startswith("### "):
            cur = line
            blocks[cur] = []
        elif cur:
            blocks[cur].append(line)
    out = [lines[span[0]], ""]
    for e in entries:
        if e["line"] not in blocks:
            raise ValueError("the draft changed since you opened it. Reload first")
        meta = [l for l in blocks[e["line"]] if l.strip() and not l.startswith("- ") and not l.startswith("section:")]
        out += [e["line"], f"section: {_one_line(e.get('section') or '')}"] + meta
        for k, b in enumerate(e.get("bullets") or [], 1):
            text, source = _one_line(b.get("text") or ""), _one_line(b.get("source") or "")
            if not text:
                continue
            if not re.match(r"experiences/[a-z0-9-]+/index\.md L\d", source):
                raise ValueError(f"{SCORE_RE.sub('', e['line'][4:]).strip()}, bullet {k}: give its source, like experiences/<slug>/index.md L12")
            out.append(f"- {text} (source: {source})")
        out.append("")
    for line in removed or []:
        if line not in blocks:
            raise ValueError("the draft changed since you opened it. Reload first")
    new = lines[:span[0]] + out + lines[span[1]:]
    if removed:
        drop = [f"- {SCORE_RE.sub('', l[4:]).strip()}: removed by {who} in CV Studio" for l in removed]
        d = _section_span(new, lambda h: h == "Dropped")
        if d:
            new[d[1]:d[1]] = drop + [""]
        else:
            q = _section_span(new, lambda h: h.startswith("Open questions")) or (len(new), len(new))
            new[q[0]:q[0]] = ["## Dropped", ""] + drop + [""]
    for heading, body in (("Education", [f"- {_one_line(x)}" for x in education or [] if x.strip()]),
                          ("Suggested skills line", [_one_line(skills or "")] if (skills or "").strip() else [])):
        sp = _section_span(new, lambda h, heading=heading: h == heading)
        if sp:
            new[sp[0] + 1:sp[1]] = body + [""]
    return "\n".join(new).rstrip("\n") + "\n"


def dismiss_question(md: str, index: int, who: str) -> str:
    """Dismiss: tick a question without asking the extractor for anything. The draft stays as it is."""
    qs = parse_questions(md)
    if not 0 <= index < len(qs) or qs[index]["ticked"]:
        raise ValueError("that question is already settled")
    lines = md.splitlines()
    q = qs[index]
    lines[q["line"]] = re.sub(r"^- \[ \]", "- [x]", lines[q["line"]], count=1)
    lines.insert(q["last"] + 1, f"  decision: dismissed by {who} in CV Studio, no change")
    return "\n".join(lines) + ("\n" if md.endswith("\n") else "")


def reopen(app: Path) -> list:
    """Reopen an approved or rendered draft for editing: status back to draft, the final PDF into drafts/."""
    ext = app / "extraction.md"
    md = ext.read_text()
    if not APPROVED_RE.search(md):
        raise ValueError("only an approved draft can be reopened")
    moved = archive_final(app)
    ext.write_text(APPROVED_RE.sub("status: draft", md, count=1))
    return moved


def edit_jd(app: Path, body: str):
    """Replace the job description text, keeping its title and Source lines."""
    body = body.replace("\r\n", "\n").strip()
    if not body:
        raise ValueError("the job description can't be empty")
    jd = app / "jd.md"
    head = jd.read_text().split("\n\n", 2)[:2] if jd.exists() else []
    jd.write_text("\n\n".join(head + [body]) + "\n")


def set_aside_draft(app: Path) -> list:
    """Re-extract: the current draft and its previews go to drafts/, so the extractor starts over from the job description."""
    drafts, moved = app / "drafts", archive_previews(app)
    ext = app / "extraction.md"
    if ext.exists():
        drafts.mkdir(exist_ok=True)
        dest = _versioned(drafts, ext.name)
        shutil.move(str(ext), dest)
        moved.append(dest.name)
    return moved
