# CV System: harness

This repo builds tailored CVs from one source of truth. The user pastes a job description, an extractor proposes content, the user vets it, and a renderer produces a one-page PDF. These rules apply to every session and every subagent in this repo. docs/ARCHITECTURE.md explains why each part exists.

"The user" below is the person whose CV this is. Their name, contact details and short name are in `master/profile.md`. Nothing else stores who they are.

## Paths

| Path | What it is | Who writes it |
| --- | --- | --- |
| `master/profile.md` | Name, short name, contact details, availability. The renderer prints the header from it; agents tag facts with the short name | The user only |
| `master/master-cv.md` | Source of truth: short entries with `tags` and `retrieve` pointers | Curator, or the user through CV Studio's edits (code writes them, Keep or Undo, `pin:` lines) |
| `tracker.md` | Outstanding items: facts waiting on the user, entries to revisit on a date or event, applications in flight | Any skill or agent, per "Tracker" below |
| `master/goals.md` | Career direction; used to rank and demote entries | The user only: by hand, or with Save in CV Studio's Goals tab, whose code writes the file after they see the diff. The goals-drafter agent only writes a proposal in gitignored `tools/goals-draft/` |
| `master/goals-log.md` | CV Studio's record of goals changes: date, how it was made (manual edit, AI draft, restore) and the user's note word for word. Not read by any agent | CV Studio code |
| `experiences/<slug>/index.md` | Long-form notes per experience, with a `status` field (stub, interviewed, condensed) | `/curate` skill or the interviewer agent in CV Studio (from the user's answers), or the user themselves (by hand, or Edit notes, Edit details and Answer in CV Studio, written by code); curator agent may only change `status` |
| `experiences/<slug>/interview.md` | CV Studio's interview record: questions per round and the user's answers word for word. Not a CV source (the facts live in `index.md`) | CV Studio code (sessions, `answer:` lines); interviewer agent (questions, ticks, `outcome:` lines) |
| `experiences/<slug>/artifacts/` | Journals, slides, READMEs dropped in as source material | The user only (directly or by upload in CV Studio) |
| `applications/<yyyy-mm>-<company>-<role>/jd.md` | The pasted job description | Manager or CV Studio |
| `applications/<...>/extraction.md` | Proposed content for vetting | Extractor, then the user |
| `applications/<...>/cv.html`, `<Name>_CV_<Company>.pdf` | Rendered output | `tools/render.py` (via the generator or CV Studio) |
| `seed/` | Raw input for `/curate backfill` (an existing CV, a LinkedIn export). Read by the curate skill only, never cited by the master CV | The user only |
| `examples/robin/` | A fictional example persona with the same layout as the live folders. Loaded by `tools/example.py load`, read by the tests | Claude, on request |
| `templates/blank/` | Empty profile, goals, master CV and tracker for `tools/example.py fresh` | Claude, on request |
| `tools/render.py` | Deterministic renderer: approved extraction.md + profile.md + template → cv.html + PDF (Playwright via Chrome), trims bullets on overflow | Claude, on request |
| `tools/ui.py`, `tools/ui/` | CV Studio: local web UI (127.0.0.1) over the same files. Four tabs. Apps runs the /apply loop (new JD, extractor, answers, revise, preview, Approve, final render, and an Overview card with each selected entry's score breakdown). Experiences runs the /curate loop (new experience, uploads, interview rounds, curator runs with Keep or Undo) where each experience shows its CV label (In CV, Planned, Archived, or its interview step) and an In Progress marker while it is ongoing, with Status, Type, Year and Sort menus. Master CV shows the sections, tags, Refresh ranking and the Keep or Undo review. Goals edits goals.md by hand or with an AI draft, with Save and History. Agents run as headless Claude Code | Claude, on request |
| `tools/appstate.py`, `tools/trackerfile.py` | Folder state, answer lines, Approve, file moves and tracker.md edits used by CV Studio (state rules mirror `skills/apply/SKILL.md`) | Claude, on request |
| `tools/expstate.py` | Experience folders, the `index.md` template (mirrors `skills/curate/SKILL.md`, change both together), `interview.md` parsing, uploads and the ownership checks run after each interviewer or curator run | Claude, on request |
| `tools/undo.py` | Snapshot before each CV Studio curator run, the diff shown for review, Keep and Undo (store in gitignored `tools/undo/`) | Claude, on request |
| `tools/goalsfile.py` | Goals tab logic: the AI proposal store, diff, the new-names check, backups, save, restore and `goals-log.md` | Claude, on request |
| `tools/mastercv.py` | Edits to `master-cv.md` made through CV Studio (Archive, Move back to CV): code moves the entry, adds a `pin:` line the curator keeps, and the change goes through Keep or Undo. The to-do list and the experience edits (Edit details, Edit notes, Answer, Skip, Cancel) live in `tools/expstate.py` and `tools/trackerfile.py` | Claude, on request |
| `tools/example.py` | Loads the example persona, or clears it and writes blank files | Claude, on request |
| `tools/test_*.py` | Unit tests. They read `examples/robin/`, never the live folders | Claude, on request |
| `launcher/` | `build.sh` builds `CV Studio.app` for macOS and copies it to the Desktop | Claude, on request |
| `templates/cv.html` | The single HTML/CSS template with `{{placeholders}}` | The user only |
| `.claude/skills/apply/SKILL.md` | Manager | — |
| `.claude/skills/curate/SKILL.md` | Runs the interview, writes `index.md`, calls the curator agent. Its "Interviewing" and "Writing index.md" sections also bind the interviewer agent | — |
| `.claude/agents/{curator,extractor,generator}.md` | The three core agents | — |
| `.claude/agents/interviewer.md` | One round of the /curate interview, run headless by CV Studio | — |
| `.claude/agents/goals-drafter.md` | Drafts a revised `goals.md` from the file plus the user's note, run headless by CV Studio; writes only the proposal | — |

Slugs are lowercase kebab-case. Application folders use the month the JD was saved, e.g. `applications/2026-10-brightmart-data-analyst/`.

## Hard rules

1. **Never invent facts.** Every bullet in `master-cv.md` must trace to a sentence in an `experiences/*/index.md`. Every bullet in `extraction.md` cites its source as `(source: <path> L<line>)`. If a claim has no source, ask; do not write it. The same holds for `goals.md`: the goals-drafter may restructure and reword what the file says and apply the user's note, and never adds a target, company, industry, date, course or preference that neither names.
2. **Ownership is fixed.** Only two writers edit `master-cv.md`: the curator, and the user through CV Studio's own edits, which code (never an agent) writes, each reviewed with Keep or Undo like a curator run and marked with a `pin: <fields> (<short name>, <date>)` line that later curator runs must respect. Only the extractor and the user edit `extraction.md`. The manager (or CV Studio) may only add `answer:` lines copying the user's answers word for word; the extractor then applies them in revise mode. Approval is the user's act: they set `status: approved` in the file, or click Approve in CV Studio, whose code (never an agent) flips the line after confirming 0 unticked questions. No agent ever sets it. Likewise `status: interviewed` in `index.md` is set by the `/curate` skill or by CV Studio's code when the user clicks Finish, never by the interviewer agent; the curator sets `condensed`. Nobody but the user edits `profile.md`, `goals.md`, `templates/cv.html` or anything in `artifacts/`. Changing `goals.md` is their act: by hand, or by clicking Save in CV Studio, whose code (never an agent) writes the file after showing them the diff.
3. **The vetting gate is the only human checkpoint, and nothing changes content after it.** The generator never adds, rewords or reorders content from an approved `extraction.md`; it may only drop bullets to fit the page, and must say which.
4. **No external information.** No agent uses WebSearch or WebFetch. CV content comes only from files in this repo. `examples/` and `templates/blank/` are a fictional persona and empty templates: never read them as a source or a format reference for the user's own files.
5. **Never delete an experience.** Demote it to an `## Archive` section in `master-cv.md` with a one-line reason.
6. **AI assistance: honest verbs, no labels.** Do not tag bullets with "with AI assistance" or similar; the Skills section carries one line, "AI-assisted development (Claude Code, ChatGPT)", when it applies. Honesty lives in the verb: "built", "designed" and "owned" only where index.md shows the user made the decisions and can defend them. Where AI did most of the design or they cannot yet explain it, use "co-designed", "directed" or "contributed to" instead.
7. **Ask, do not guess.** If a subagent reports an open question, the manager stops and asks the user.

## Tracker

`tracker.md` is the one list of everything outstanding. When work adds an open question, a "revisit when X" item or a `(quantify?)` marker, add a row naming the entry and what closes it. When an item is resolved, delete its row. Update its "Last updated" date. Subagents that cannot update it report the item in their final message instead, and the calling skill adds it.

## CV writing style

These are the default style rules. They apply to every line that can reach a CV: master CV entries, extraction.md bullets, education and skills. The curator writes the master CV in this style; the extractor writes and self-checks every bullet against it; `tools/render.py` refuses to render text that breaks rule 4. Change them to suit your own taste, and change `render.py`'s check with rule 4.

1. **Only what is done.** Planned work never appears on a CV: no planned modules, no planned exchange, no projects not yet built. Current roles and ongoing projects appear only with work already delivered, and without "(in progress)" labels; an end date of "Present" says it is ongoing. The master CV may keep planned items for tracking, but the extractor never selects them.
2. **Show strengths.** Lead with what the user built and what it achieved. Leave out context that makes them look worse: the incident that caused the work, a concern someone else flagged, a failure. Stay truthful: omit, never distort.
3. **Full sentences.** Each bullet is one complete sentence (two at most), ending with a full stop. Start with an action verb: past tense for finished work, present tense for current work. No first person ("I", "my", "myself").
4. **Punctuation.** No em dashes (—), en dashes (–) or semicolons anywhere, and no colons inside bullets. One exception, to save space: the Education coursework line reads "Relevant coursework: <modules>." Date ranges use a spaced plain hyphen: "May 2026 - Aug 2026", "2024 - 2028 (Expected)", "Sep 2026 - Present". Other ranges use "to": "90 to 95%". Where a dash or semicolon would go, use a comma or start a new sentence.
5. **One pattern per bullet.** What they did, how, and the result or number. Prefer a clause to a parenthetical aside; keep brackets for short lists of tools.
6. **Capitalisation.** Title case for qualifiers and labels in entry headings: "(Part-Time)", "Personal Project", "Group Project".
7. **Structure.** Work done inside a role appears as bullets under that role's entry, not as a separate project. Example: a client prototype built during a job sits under that job's entry.

## Agent conventions

- Subagents cannot talk to the user mid-run, so anything interactive (interviews, questions) happens in a skill in the user's session; subagents do the isolated reading and writing.
- Subagent tool lists: curator and extractor get `Read, Write, Glob, Grep`; generator gets `Read, Write, Glob, Grep, Bash`; interviewer gets `Read, Edit, Glob, Grep` (no Write, so it cannot rewrite a notes file); goals-drafter gets `Read, Write`.
- Subagents are stateless. Anything they need must be in a file they read or in the task message. Decisions the user makes go into the relevant `index.md` (or CLAUDE.md for rules), never only into a task message: the next run will not see them otherwise.
- CV Studio runs the extractor, interviewer and curator as the main agent of a fresh headless session (`claude -p --agent <name>`, effort `high`, on the user's Claude login, never an API key), with writes fenced to the files each owns: the extractor to its application folder, the interviewer to one experience's `index.md` and `interview.md`, the curator to `master-cv.md`, CLAUDE.md and the in-scope `index.md`. After an interviewer or curator run, code checks ownership (no note line lost, the curator changed only `status:` in `index.md` and only the tag vocabulary in CLAUDE.md) and undoes the run if it fails. Interviewer and curator runs never overlap an extractor run. The goals-drafter runs in a temp workspace outside the home folder holding copies of only CLAUDE.md, goals.md, its agent file and its last proposal, with Read denied under the home folder: `Read(path)` allow-rules do not limit reading (reads are allowed by default), so a deny rule is the only real read fence. A goals save waits for any running agent, since each reads goals.md. Do not edit goals.md by hand while a goals draft waits in CV Studio: the draft is marked stale and cannot be accepted. Do not run `/apply` on a folder, or `/curate` on a slug, while CV Studio has a job running on it.
- Updating an experience shifts the line numbers that drafts cite. After an update, re-extract any draft `extraction.md` that cites that experience (`/apply --redo <slug>`).
- Agent definitions are loaded when a Claude Code session starts. After editing a file in `.claude/agents/`, either start a new session or run a general-purpose agent told to read that file from disk and follow it.
- Every subagent's final message is at most 5 lines. The manager relays it verbatim.
- The manager routes by the state table in `skills/apply/SKILL.md`. It never calls a subagent it does not need: one JD, one extractor call.

## master-cv.md entry format

```markdown
### <Role>, <Organisation> (<dates>)
- 2 to 4 bullets, numbers wherever possible; mark missing numbers with (quantify?). A role that absorbs work done inside it (style rule 7) may hold up to 6 in the master CV so the extractor can choose; a CV still shows at most 4 per entry.
- Stack: ...
tags: [tag, tag, ...]
retrieve: experiences/<slug>/index.md; <optional pointer to a specific artifact and what to find there>
```

Sections, in order: Experience, Projects, Hackathons and case competitions, Leadership & Co-Curricular Activities, Education, Skills, Archive. Student leadership, sport, service and volunteer roles go under Leadership & Co-Curricular Activities. The header (name and contacts) is not in the master CV: the renderer reads it from `master/profile.md`.

## Tag vocabulary

Tags must come from this list. Any agent may add a tag here when an experience or JD needs one that no existing tag covers. Never add silently: name every new tag and its group in your final message so the user can veto it. Prefer an existing tag over a near-synonym.

- **Role and function:** `fde`, `solutions-engineering`, `software-engineering`, `data-engineering`, `data-science`, `data-analysis`, `business-analysis`, `product`, `consulting`, `operations`, `research`
- **Domain:** `finance`, `fintech`, `banking`, `risk`, `investment`, `insurance`, `customer-support-ai`, `ecommerce`, `retail`, `logistics`, `saas`, `education`, `sports`
- **Languages:** `python`, `typescript`, `javascript`, `sql`, `r`
- **Data:** `data-pipelines`, `etl`, `data-modelling`, `data-warehousing`, `databases`, `statistics`, `dashboards`, `data-visualisation`, `data-quality`, `excel`
- **AI and ML:** `machine-learning`, `deep-learning`, `nlp`, `computer-vision`, `llm-agents`, `rag`, `prompt-engineering`, `ai-automation`
- **Engineering:** `integrations`, `apis`, `automation`, `backend`, `frontend`, `web-dev`, `cloud`, `serverless`, `devops`, `testing`, `bots`
- **Ways of working:** `client-facing`, `leadership`, `cross-functional`, `stakeholder-management`, `project-management`, `mentoring`, `public-speaking`, `entrepreneurship`
- **Context:** `hackathon`, `case-competition`, `internship`, `part-time`, `freelance`, `volunteer`

Disambiguation: `automation` is rule-based workflow work (scripts, n8n, cron jobs); `ai-automation` is workflows where an LLM or model makes decisions. `finance` is the domain (corporate finance, accounting, markets); `fintech` is building technology for it. Tag an entry with both when both apply.

## Rendering

- Renderer: **Playwright** (headless Chromium). Render `cv.html` to PDF. Paper size is A4, set in the template's CSS `@page` rule.
- Default length: **one page**. If the PDF overflows, drop the lowest-scored bullet from the bottom entry and re-render, at most 3 times, then report.
- Output filename: `applications/<slug>/<Name>_CV_<Company>.pdf`, with the name from `master/profile.md` (spaces become underscores).
- Vetting a draft: `.venv/bin/python tools/render.py <folder> --preview` renders an unapproved extraction to `*_PREVIEW` files so the user can vet the real page. The final render refuses anything not `status: approved`, and refuses text that breaks style rule 4.
- CV Studio's final render calls `render.py` directly (the user checks the PDF in the page); the generator agent is the chat path.
- An application folder holds `jd.md`, `extraction.md`, `cv.html` and the PDF. Superseded drafts go in `<folder>/drafts/` so the folder state stays unambiguous.
- Setup: a gitignored `.venv` at the repo root holds `playwright` and `pypdf` (see docs/SETUP.md). Rendering uses the installed Google Chrome; if Chrome is missing, run `.venv/bin/playwright install chromium`.
