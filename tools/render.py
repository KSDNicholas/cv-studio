"""Render an approved extraction.md into cv.html and a one-page PDF.

Usage:
    .venv/bin/python tools/render.py applications/<slug> [--pages N] [--max-trims 3]

Content comes only from extraction.md. The name and contact line come from master/profile.md.
Nothing is reworded. If the PDF runs past N pages, the last bullet of the lowest-scored
entry (lowest on the page when scores tie) is dropped and the page re-rendered, at most
--max-trims times. Every drop is reported. Output: JSON summary on stdout.
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "master" / "profile.md"
SOURCE_RE = re.compile(r"\s*\(source:[^)]*\)")
SCORE_RE = re.compile(r"\s*\[score\s+(\d+)\s*/\s*10\]\s*$")
SECTION_ORDER = ["Experience", "Projects", "Hackathons and case competitions", "Leadership & Co-Curricular Activities"]
SECTION_ALIASES = {"Leadership": "Leadership & Co-Curricular Activities"}


def clean(text: str) -> str:
    return SOURCE_RE.sub("", text).strip()


def split_sections(md: str) -> dict:
    """Map each '## Heading' to the lines under it."""
    sections, current = {}, None
    for line in md.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def split_heading(heading: str):
    """'Title, Org (dates)' -> (title, org, dates). Org and dates may be empty."""
    dates = ""
    if heading.endswith(")"):
        depth = 0
        for i in range(len(heading) - 1, -1, -1):
            if heading[i] == ")":
                depth += 1
            elif heading[i] == "(":
                depth -= 1
                if depth == 0:
                    dates = heading[i + 1:-1].strip()
                    heading = heading[:i].strip()
                    break
    depth, cut = 0, -1
    for i, ch in enumerate(heading):  # first ", " outside parentheses
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0 and heading[i + 1:i + 2] == " ":
            cut = i
            break
    if cut < 0:
        return heading, "", dates
    return heading[:cut].strip(), heading[cut + 2:].strip(), dates


def parse_entries(lines):
    entries = []
    for line in lines:
        if line.startswith("### "):
            raw = line[4:].strip()
            m = SCORE_RE.search(raw)
            score = int(m.group(1)) if m else 0
            title, org, dates = split_heading(SCORE_RE.sub("", raw))
            entries.append({"title": title, "org": org, "dates": dates, "score": score,
                            "section": "Experience", "bullets": []})
        elif entries and line.startswith("section:"):
            sec = line.split(":", 1)[1].strip()
            entries[-1]["section"] = SECTION_ALIASES.get(sec, sec)
        elif entries and line.startswith("- "):
            entries[-1]["bullets"].append(clean(line[2:]))
    return entries


def read_profile(path: Path = PROFILE) -> dict:
    """master/profile.md as {field: value}, keys lowercased with spaces kept ("short name")."""
    fields = {}
    if path.exists():
        for line in path.read_text().splitlines():
            m = re.match(r"-\s*([A-Za-z][A-Za-z ]*?):\s*(.+)", line)
            if m:
                fields[m.group(1).strip().lower()] = m.group(2).strip()
    return fields


def short_name(profile: dict = None) -> str:
    """How agents and the page refer to the user. Falls back to the first word of Name, then "the user"."""
    profile = read_profile() if profile is None else profile
    return profile.get("short name") or (profile.get("name", "").split() or ["the user"])[0]


def pdf_stem(profile: dict = None) -> str:
    """"Robin Tay" -> "Robin_Tay_CV". Final PDFs are <stem>_<Company>.pdf."""
    profile = read_profile() if profile is None else profile
    name = re.sub(r"[^A-Za-z0-9]+", "_", profile.get("name", "")).strip("_")
    return f"{name}_CV" if name else "CV"


def parse_header(profile: dict = None):
    fields = read_profile() if profile is None else profile
    short = lambda url: re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    contact = [fields.get("phone"), fields.get("email"),
               short(fields["linkedin"]) if "linkedin" in fields else None,
               short(fields["github"]) if "github" in fields else None]
    return fields.get("name", ""), " • ".join(c for c in contact if c)


def entry_html(e):
    head = (f'<div class="entry-head"><span class="title">{html.escape(e["title"])}</span>'
            f'<span class="dates">{html.escape(e["dates"])}</span></div>')
    org = f'<div class="org">{html.escape(e["org"])}</div>' if e["org"] else ""
    items = "".join(f"<li>{html.escape(b)}</li>" for b in e["bullets"])
    return f'<div class="entry">{head}{org}<ul>{items}</ul></div>' if items else f'<div class="entry">{head}{org}</div>'


def build_body(entries, education_lines, skills, interests=""):
    parts = []
    if education_lines:
        title, org, dates = split_heading(education_lines[0])
        rest = list(education_lines[1:])
        parts.append('<section class="cv-section"><h2>Education</h2>'
                     + entry_html({"title": title, "org": org, "dates": dates, "bullets": rest})
                     + "</section>")
    known = SECTION_ORDER + sorted({e["section"] for e in entries} - set(SECTION_ORDER))
    for name in known:
        group = [e for e in entries if e["section"] == name]
        if group:
            parts.append(f'<section class="cv-section"><h2>{html.escape(name)}</h2>'
                         + "".join(entry_html(e) for e in group) + "</section>")
    if skills or interests:
        rows = f"<p><strong>Technical:</strong> {html.escape(skills)}</p>" if skills else ""
        rows += f"<p><strong>Interests:</strong> {html.escape(interests)}</p>" if interests else ""
        parts.append(f'<section class="cv-section skills"><h2>Skills</h2>{rows}</section>')
    return "\n".join(parts)


BANNED = {"\u2014": "em dash", "\u2013": "en dash", ";": "semicolon"}
COURSEWORK = "Relevant coursework: "  # the one colon allowed (CLAUDE.md style rule 4)


def style_problems(entries, education, availability, skills, interests=""):
    """CLAUDE.md 'CV writing style' rule 4, checked mechanically on everything that reaches the page."""
    problems = []
    lines = [("availability", availability), ("skills", skills), ("interests", interests)]
    lines += [("education", l) for l in education]
    for e in entries:
        lines.append((e["title"], f'{e["title"]} {e["org"]} {e["dates"]}'))
        lines += [(e["title"], b) for b in e["bullets"]]
    for where, text in lines:
        for ch, label in BANNED.items():
            if ch in text:
                problems.append(f"{label} in {where}: {text[:90]}")
    for e in entries:
        for b in e["bullets"]:
            if ":" in b:
                problems.append(f"colon inside a bullet in {e['title']}: {b[:90]}")
    for l in education[1:]:
        if ":" in l.removeprefix(COURSEWORK):
            problems.append(f"colon inside an education line: {l[:90]}")
    return problems


def md_problems(md: str, jd_text: str = "") -> list:
    """Everything the final render would refuse in an extraction.md, so Approve can refuse it first."""
    sections = split_sections(md)
    entries = parse_entries(sections.get("Selected experiences (ordered)", []))
    education = [clean(l[2:]) for l in sections.get("Education", []) if l.startswith("- ")]
    availability = " ".join(clean(l[2:] if l.startswith("- ") else l) for l in sections.get("Availability", []) if l.strip())
    skills = " ".join(clean(l) for l in sections.get("Suggested skills line", []) if l.strip())
    interests = " ".join(clean(l) for l in sections.get("Interests", []) if l.strip())
    problems = style_problems(entries, education, availability, skills, interests)
    if "availability" in jd_text.lower() and not availability:
        problems.append("JD asks for availability but extraction.md has no Availability section")
    return problems


def company_name(jd_lines):
    for line in jd_lines:
        m = re.match(r"-\s*company:\s*(.+)", line)
        if m:
            name = re.split(r"[,(]", m.group(1))[0].strip()
            return re.sub(r"[^A-Za-z0-9]+", "", name) or "Company"
    return "Company"


def render_pdf(html_path: Path, pdf_path: Path) -> int:
    from playwright.sync_api import sync_playwright
    from pypdf import PdfReader
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome")
        except Exception:
            browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.as_uri())
        page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
        browser.close()
    return len(PdfReader(str(pdf_path)).pages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("app_dir")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--max-trims", type=int, default=3)
    ap.add_argument("--preview", action="store_true", help="render a draft extraction to *_PREVIEW files for vetting")
    args = ap.parse_args()

    app = (ROOT / args.app_dir).resolve() if not Path(args.app_dir).is_absolute() else Path(args.app_dir)
    md = (app / "extraction.md").read_text()
    if not args.preview and not re.search(r"(?m)^status:\s*approved\s*$", md):
        sys.exit("refused: extraction.md is not status: approved (use --preview to vet a draft)")

    sections = split_sections(md)
    entries = parse_entries(sections.get("Selected experiences (ordered)", []))
    education = [clean(l[2:]) for l in sections.get("Education", []) if l.startswith("- ")]
    availability = " ".join(clean(l[2:] if l.startswith("- ") else l) for l in sections.get("Availability", []) if l.strip())
    skills = " ".join(clean(l) for l in sections.get("Suggested skills line", []) if l.strip())
    interests = " ".join(clean(l) for l in sections.get("Interests", []) if l.strip())
    problems = style_problems(entries, education, availability, skills, interests)
    jd_text = (app / "jd.md").read_text().lower() if (app / "jd.md").exists() else ""
    if "availability" in jd_text and not availability:
        problems.append("JD asks for availability but extraction.md has no Availability section")
    if problems:
        print(json.dumps({"refused": "extraction.md breaks CLAUDE.md CV writing style rule 4", "problems": problems}, indent=2))
        sys.exit(2)
    profile = read_profile()
    if not profile.get("name"):
        sys.exit("refused: master/profile.md has no Name line (see docs/SETUP.md)")
    name, contact = parse_header(profile)
    company = company_name(sections.get("JD summary", []))
    template = (ROOT / "templates" / "cv.html").read_text()

    suffix = "_PREVIEW" if args.preview else ""
    html_path = app / f"cv{suffix.lower().replace('_', '-')}.html"
    pdf_path = app / f"{pdf_stem(profile)}_{company}{suffix}.pdf"
    dropped = []
    for attempt in range(args.max_trims + 1):
        page_html = (template.replace("{{name}}", html.escape(name))
                     .replace("{{contact}}", html.escape(contact))
                     .replace("{{availability}}", html.escape(availability))
                     .replace("{{body}}", build_body(entries, education, skills, interests)))
        html_path.write_text(page_html)
        pages = render_pdf(html_path, pdf_path)
        if pages <= args.pages or attempt == args.max_trims:
            break
        candidates = [(e["score"], -i, e) for i, e in enumerate(entries) if len(e["bullets"]) > 1]
        if not candidates:
            break
        _, _, victim = min(candidates, key=lambda c: (c[0], c[1]))
        dropped.append({"entry": victim["title"], "bullet": victim["bullets"].pop()})

    print(json.dumps({"pdf": str(pdf_path.relative_to(ROOT)), "html": str(html_path.relative_to(ROOT)),
                      "pages": pages, "target_pages": args.pages, "dropped": dropped}, indent=2))


if __name__ == "__main__":
    main()
