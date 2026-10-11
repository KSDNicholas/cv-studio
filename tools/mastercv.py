"""Changes to master/master-cv.md that the user makes in CV Studio (CLAUDE.md rule 2).

Code, not an agent, makes them, and each goes through the same Keep or Undo review as a curator run. Every edit
leaves a `pin:` line on the entry so later curator runs keep what the user set.
"""

import re
from datetime import date

PIN_RE = re.compile(r"^pin:\s*(.*?)\s*(\(([^()]*)\))?\s*$")
ARCHIVE_LINE = re.compile(r"^- Archived (because|by) ")


def _parse(lines):
    """(section headings with their line index, entry blocks). A block runs from its ### line to the line before
    the next ### or ## heading, without trailing blank lines."""
    sections, blocks, section = [], [], None
    for i, line in enumerate(lines):
        if line.startswith("## "):
            section = line[3:].strip()
            sections.append((section, i))
        elif line.startswith("### "):
            blocks.append({"section": section, "start": i})
    for b in blocks:
        end = next((j for j in range(b["start"] + 1, len(lines)) if lines[j].startswith(("## ", "### "))), len(lines))
        while end > b["start"] + 1 and not lines[end - 1].strip():
            end -= 1
        b["end"] = end
        retrieve = next((l for l in lines[b["start"]:end] if l.startswith("retrieve:")), "")
        first = re.search(r"experiences/([a-z0-9-]+)/index\.md", retrieve)
        b["owner"] = first.group(1) if first else None
    return sections, blocks


def sections(md: str):
    """Section names an entry can live in (Header and Skills hold no entries)."""
    return [s for s, _ in _parse(md.splitlines())[0] if s not in ("Header", "Skills")]


def owned_block(md: str, slug: str):
    """The entry this experience owns (its own index.md comes first on the retrieve: line), or None."""
    _, blocks = _parse(md.splitlines())
    return next((b for b in blocks if b["owner"] == slug and b["section"] != "Skills"), None)


def with_pin(block, field: str, who: str, today: date):
    """Add `field` to the entry's pin: line, keeping fields pinned before."""
    fields, out = [], []
    for line in block:
        m = PIN_RE.match(line)
        if m:
            fields = [f.strip() for f in m.group(1).split(",") if f.strip()]
        else:
            out.append(line)
    if field not in fields:
        fields.append(field)
    return out + [f"pin: {', '.join(fields)} ({who}, {today:%Y-%m-%d})"]


def move_entry(md: str, slug: str, to: str, who: str, reason: str = "", today: date = None) -> str:
    """Move an experience's entry to another section. Into Archive it gains the user's reason as its first line.
    Out of Archive it loses the archive reason lines. Either way the section is pinned."""
    today = today or date.today()
    lines = md.splitlines()
    sects, _ = _parse(lines)
    if to not in [s for s, _ in sects] or to in ("Header", "Skills"):
        raise ValueError(f"the master CV has no '{to}' section for entries")
    b = owned_block(md, slug)
    if not b:
        raise ValueError("this experience has no entry of its own in the master CV")
    if b["section"] == to:
        raise ValueError(f"it is already in {to}")
    block = lines[b["start"]:b["end"]]
    if to == "Archive":
        reason = " ".join((reason or "").split()).rstrip(".")
        if not reason:
            raise ValueError("say why, in a few words. The reason stays with the entry")
        block = [block[0], f"- Archived by {who} on {today:%Y-%m-%d} because {reason[0].lower() + reason[1:]}."] + block[1:]
    else:
        block = [l for l in block if not ARCHIVE_LINE.match(l)]
    block = with_pin(block, "section", who, today)
    rest = lines[:b["start"]] + lines[b["end"]:]
    # drop the blank line the block leaves behind, so sections keep one blank line between entries
    if b["start"] < len(rest) and b["start"] > 0 and not rest[b["start"] - 1].strip() and not rest[b["start"]].strip():
        del rest[b["start"]]
    head = next(i for i, l in enumerate(rest) if l.strip() == f"## {to}")
    end = next((j for j in range(head + 1, len(rest)) if rest[j].startswith("## ")), len(rest))
    while end > head + 1 and not rest[end - 1].strip():
        end -= 1
    rest[end:end] = [""] + block + ([""] if end < len(rest) and rest[end].strip() else [])
    return "\n".join(rest).rstrip("\n") + "\n"
