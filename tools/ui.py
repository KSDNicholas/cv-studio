"""CV Studio: a local web UI over the /apply loop.

Usage:
    .venv/bin/python tools/ui.py [--port 8765] [--no-browser]

Serves tools/ui/ on 127.0.0.1 only. Does the manager's non-LLM work itself (folder, jd.md, answer lines,
Approve, file moves, tracker.md) and runs the extractor through the installed Claude Code CLI, headless,
on the user's own login. Final renders call tools/render.py directly. Same files and rules as /apply in chat.
"""

import argparse
import atexit
import difflib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import appstate as s
import mastercv as mc
import expstate as e
import trackerfile as t
import goalsfile as g
import undo
from render import md_problems, short_name

ROOT = s.ROOT
UI_DIR = Path(__file__).resolve().parent / "ui"
PIDFILE = Path(__file__).resolve().parent / "ui.pid"
CLAUDE = shutil.which("claude") or "/opt/homebrew/bin/claude"
STATIC = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
          "style.css": "text/css; charset=utf-8", "icon.png": "image/png"}
FILE_TYPES = {".pdf": "application/pdf", ".html": "text/html; charset=utf-8", ".md": "text/plain; charset=utf-8"}
JOB_TIMEOUT = 15 * 60   # wall-clock seconds, sleep included (see _watchdog)
WATCHDOG_POLL = 5
PORT = 8765
EFFORT = "high"  # extractor effort. The Claude Code default (xhigh) took 8 min per run

HISTORY = Path(__file__).resolve().parent / "ui-history.json"    # run durations per kind (gitignored)
JOB_HISTORY = Path(__file__).resolve().parent / "ui-jobs"   # the last finished run per page, kept across restarts (gitignored)
SETTINGS = Path(__file__).resolve().parent / "ui-settings.json"  # notification switches (gitignored)
READERS = {"extract", "revise"}                               # read experiences/ and master-cv.md
WRITERS = {"ask", "next", "finish", "curate", "refresh"}      # change them (line numbers the extractor cites)
AGENT_KINDS = READERS | WRITERS | {"goals"}                 # goals: reads goals.md, writes only a gitignored proposal
STAGES = {
    "extract": ["Starting up", "Reading the job description", "Scoring your master CV",
                "Reading notes for the best matches", "Writing your draft"],
    "revise": ["Reading the draft", "Re-reading the cited notes", "Applying your answers",
               "Re-checking citations and style"],
    "preview": ["Rendering your CV"],
    "render": ["Rendering your final CV", "Tidying up"],
    "ask": ["Reading your notes", "Reading your documents", "Writing your questions"],
    "next": ["Reading your notes", "Recording your answers", "Writing follow-up questions"],
    "finish": ["Recording your answers", "Updating your master CV", "Checking the changes"],
    "curate": ["Reading your notes and goals", "Rewriting your CV entry", "Checking the changes"],
    "refresh": ["Reading your goals", "Re-ranking your master CV", "Checking the changes"],
    "goals": ["Reading your goals", "Drafting the new version", "Checking the draft"],
}
KIND_NAMES = {"extract": "Extractor", "revise": "Your answers", "preview": "Preview", "render": "Final CV",
              "ask": "Interview questions", "next": "Interview round", "finish": "Interview",
              "curate": "Curator", "refresh": "Ranking refresh",
              "goals": "Goals drafter"}

JOBS, ACTIVE, CHILDREN = {}, {}, set()
TABLE = threading.Lock()
FILES_LOCK = threading.Lock()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def settings():
    return {"notify": True, "sound": True} | read_json(SETTINGS, {})


def typical(kind):
    runs = sorted(read_json(HISTORY, {}).get(kind, []))
    return round(runs[len(runs) // 2]) if runs else None


def record_duration(kind, seconds):
    with FILES_LOCK:
        data = read_json(HISTORY, {})
        data[kind] = (data.get(kind, []) + [round(seconds, 1)])[-8:]
        HISTORY.write_text(json.dumps(data, indent=1))


def notify(title, message):
    """macOS notification (free, local). Silently skipped elsewhere or when switched off."""
    prefs = settings()
    if not prefs["notify"] or sys.platform != "darwin":
        return
    q = lambda x: str(x).replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{q(message)}" with title "CV Studio" subtitle "{q(title)}"'
    if prefs["sound"]:
        script += ' sound name "Glass"'
    try:
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def today() -> str:
    return date.today().isoformat()


WORKSPACES = set()  # temp folders agents run in (the goals drafter). Paths inside show relative to them


def rel(path) -> str:
    for base in (ROOT, *WORKSPACES):
        try:
            return str(Path(path).resolve().relative_to(base))
        except (ValueError, OSError):
            continue
    return str(path)


def mtime(app: Path) -> str:
    f = app / "extraction.md"
    return str(f.stat().st_mtime_ns) if f.exists() else ""


class Refused(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.extra = status, extra


# ---------- jobs ----------

class Job:
    def __init__(self, slug, kind, label=""):
        self.id, self.slug, self.kind, self.label = uuid.uuid4().hex[:12], slug, kind, label
        self.status, self.started, self.ended = "running", time.time(), None
        self.log, self.result, self.error, self.proc = [], {}, None, None
        self.stages, self.stage, self.latest = STAGES.get(kind, []), 0, ""
        self.typical, self.cancelled = typical(kind), False

    def advance(self, i):
        if i is not None:
            self.stage = max(self.stage, min(i, len(self.stages) - 1))

    def add(self, text, kind="info"):
        for line in str(text).splitlines() or [""]:
            self.log.append({"t": round(time.time() - self.started, 1), "kind": kind, "text": line})
        del self.log[:-3000]

    def view(self, since=0):
        return {"id": self.id, "slug": self.slug, "kind": self.kind, "status": self.status,
                "started": self.started, "ended": self.ended, "lines": self.log[since:],
                "next": len(self.log), "result": self.result, "error": self.error,
                "stages": self.stages, "stage": self.stage, "latest": self.latest,
                "typical": self.typical, "label": self.label, "now": time.time()}


class SavedJob:
    """A finished run read back from JOB_HISTORY after a restart, so Activity still shows what happened."""

    def __init__(self, v):
        self.v, self.log = v, v.get("lines", [])
        self.id, self.slug, self.kind, self.status = v["id"], v["slug"], v["kind"], v["status"]
        self.started, self.ended, self.label = v["started"], v.get("ended"), v.get("label", "")
        self.result, self.error = v.get("result", {}), v.get("error")

    def view(self, since=0):
        return self.v | {"lines": self.log[since:], "next": len(self.log), "now": self.ended or self.started}


def _job_file(slug) -> Path:
    return JOB_HISTORY / (re.sub(r"[^a-z0-9-]+", "__", slug) + ".json")


def save_job(job):
    try:
        JOB_HISTORY.mkdir(exist_ok=True)
        _job_file(job.slug).write_text(json.dumps(job.view(0)))
    except OSError:
        pass  # history is a convenience: never fail a run over it


def start_job(slug, kind, target, label=""):
    """slug is the lock key: an application slug, exp:<slug> or master."""
    with TABLE:
        if slug in ACTIVE:
            raise Refused(409, "a run is already going here; wait for it to finish", job=ACTIVE[slug])
        others = [JOBS[i] for i in ACTIVE.values()]
        clash = next((o for o in others if (kind in WRITERS and o.kind in WRITERS | READERS)
                      or (kind in READERS and o.kind in WRITERS)), None)
        if clash:
            raise Refused(409, f"wait for {KIND_NAMES.get(clash.kind, clash.kind).lower()} on {clash.label or clash.slug} "
                               "to finish first (it changes or reads your notes)", job=clash.id)
        job = Job(slug, kind, label)
        JOBS[job.id] = job
        ACTIVE[slug] = job.id

    def run():
        try:
            target(job)
            if job.status == "running":
                job.status = "done"
        except Stopped:
            job.status = "stopped"
        except Exception as e:  # reported in the page, never swallowed
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            job.add(job.error, "error")
        finally:
            job.ended = time.time()
            with TABLE:
                ACTIVE.pop(slug, None)
            took = job.ended - job.started
            if job.status == "done":
                record_duration(kind, took)
            save_job(job)
            announce(job, took)

    threading.Thread(target=run, daemon=True).start()
    return job


def announce(job, took):
    """Notification when a job ends: always for agent runs, for renders only if they were slow."""
    if job.status == "stopped" or (job.kind not in AGENT_KINDS and job.status == "done" and took < 15):
        return
    name, who = KIND_NAMES.get(job.kind, job.kind), job.label or job.slug
    if job.status == "failed":
        return notify(f"{name} failed", f"{who} · open CV Studio for details")
    n = job.result.get("unticked")
    if job.kind == "extract":
        notify("Extractor finished", f"{who} · " + (f"{n} question{'s' if n != 1 else ''} for you" if n else "ready to approve"))
    elif job.kind == "revise":
        notify("Your answers are applied", f"{who} · " + (f"{n} question{'s' if n != 1 else ''} left" if n else "ready to approve"))
    elif job.kind in ("ask", "next"):
        q = job.result.get("questions")
        notify("Your interview questions are ready" if q else "Interview round recorded",
               f"{who} · " + (f"{q} question{'s' if q != 1 else ''} for you" if q else "nothing more to ask, click Finish"))
    elif job.kind in ("finish", "curate", "refresh"):
        notify("Master CV updated" if job.result.get("review") else "Curator finished",
               f"{who} · " + ("review the change" if job.result.get("review") else "no changes to the master CV"))
    elif job.kind == "goals":
        notify("Goals draft ready" if job.result.get("review") else "Goals drafter finished",
               "Review it in CV Studio" if job.result.get("review") else "No change proposed")
    elif job.kind == "render":
        notify("Final CV ready", who)
    else:
        notify("Preview ready", who)


def last_job(slug):
    with TABLE:
        if slug in ACTIVE:
            return JOBS[ACTIVE[slug]]
    mine = [j for j in JOBS.values() if j.slug == slug]
    if mine:
        return max(mine, key=lambda j: j.started)
    try:  # nothing this session: the last run before a restart
        job = SavedJob(json.loads(_job_file(slug).read_text()))
    except (OSError, ValueError, KeyError):
        return None
    JOBS[job.id] = job   # so its full log loads like any other run
    return job


def spawn(job, argv, env=None, cwd=None):
    proc = subprocess.Popen(argv, cwd=cwd or ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1, start_new_session=True)
    job.proc = proc
    CHILDREN.add(proc)
    done = threading.Event()
    threading.Thread(target=_watchdog, args=(job, proc, done), daemon=True).start()
    stderr = []
    threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True).start()
    return proc, done, stderr


def _watchdog(job, proc, done):
    """Stop the run after JOB_TIMEOUT of wall-clock time. threading.Timer waits on the monotonic clock,
    which stops while the Mac sleeps, so a run caught by a sleep could hang for hours."""
    deadline = time.time() + JOB_TIMEOUT
    while not done.wait(WATCHDOG_POLL):
        if time.time() >= deadline:
            job.add(f"timed out after {JOB_TIMEOUT // 60} minutes (wall clock, counting any time the Mac slept), "
                    "stopping", "error")
            _kill(proc)
            return


def _kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def _finish(proc, done):
    proc.wait()
    done.set()
    CHILDREN.discard(proc)


# ---------- extractor via Claude Code ----------

def claude_env():
    return {k: v for k, v in os.environ.items()
            if not (k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_CODE_") or k == "CLAUDECODE")}


def describe_tool(block):
    name, inp = block.get("name", "?"), block.get("input") or {}
    target = inp.get("file_path") or inp.get("path") or ""
    if name == "Grep":
        return f"Grep {inp.get('pattern', '')!r} in {rel(target) if target else 'repo'}"
    if name == "Glob":
        return f"Glob {inp.get('pattern', '')}"
    return f"{name} {rel(target)}" if target else name


def extractor_stage(job, block):
    """Map a tool call to a stage index (STAGES['extract'] / ['revise']). Stages only move forward."""
    name, inp = block.get("name", ""), block.get("input") or {}
    target = str(inp.get("file_path") or inp.get("path") or "")
    writes = name in ("Write", "Edit") and target.endswith("extraction.md")
    if job.kind == "extract":
        if writes:
            return 4
        if "/experiences/" in target or target.startswith("experiences/"):
            return 3
        if target.endswith(("master-cv.md", "goals.md")):
            return 2
        if target.endswith("jd.md"):
            return 1
        return None
    if writes:
        return 2
    if job.stage >= 2:
        return 3
    if "/experiences/" in target or target.startswith("experiences/"):
        return 1
    return 0


class Stopped(Exception):
    pass


def allowed_tools(fences):
    return ["Read", "Glob", "Grep"] + [f"Edit(/{f})" for f in fences]


def run_claude(job, agent, prompt, fences, stage_fn=None, extra_disallowed=(), cwd=None):
    """Run one headless Claude Code session as `agent`, with writes fenced to `fences` (absolute paths;
    a folder fence ends in /**). `cwd` runs it in another folder (a deny rule in extra_disallowed then fences
    reads: Read allow-rules do not restrict reading). Streams tool calls into the job log. Returns the agent's final message,
    or None if the job was stopped (the caller rolls back). Raises if the run did not finish cleanly."""
    allowed = ",".join(allowed_tools(fences))
    argv = [CLAUDE, "-p", prompt, "--agent", agent,
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--allowedTools", allowed,
            "--disallowedTools", ",".join(["Bash", "WebFetch", "WebSearch", "Agent", *extra_disallowed]),
            "--output-format", "stream-json", "--verbose", "--effort", EFFORT]
    proc, done, stderr = spawn(job, argv, env=claude_env(), cwd=cwd)
    final = None
    for raw in proc.stdout:
        try:
            ev = json.loads(raw)
        except json.JSONDecodeError:
            if raw.strip():
                job.add(raw.rstrip(), "raw")
            continue
        typ, sub = ev.get("type"), ev.get("subtype")
        if typ == "system" and sub == "init":
            job.add(f"Session {ev.get('session_id', '')[:8]} · {ev.get('model', '')} · tools: {', '.join(ev.get('tools', []))}")
            job.latest = "Connected to Claude"
        elif typ == "system" and "denied" in str(sub):
            job.add(f"DENIED {json.dumps(ev)[:300]}", "error")
        elif typ == "system" and sub == "api_retry":
            job.add("API busy, retrying", "warn")
        elif typ == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    job.add(describe_tool(block), "tool")
                    job.latest = describe_tool(block).replace("Read ", "Reading ", 1).replace("Edit ", "Editing ", 1) \
                        .replace("Write ", "Writing ", 1).replace("Grep ", "Searching ", 1).replace("Glob ", "Listing ", 1)
                    if stage_fn:
                        job.advance(stage_fn(job, block))
                elif block.get("type") == "text" and block.get("text", "").strip():
                    job.add(block["text"].strip(), "say")
        elif typ == "result":
            final = ev
    _finish(proc, done)
    if job.cancelled:
        return None
    for line in stderr:
        if line.strip():
            job.add(line.rstrip(), "warn")
    if final is None:
        raise RuntimeError(f"the {agent} exited ({proc.returncode}) without a result")
    message = (final.get("result") or "").strip()
    denials = final.get("permission_denials") or []
    job.result.update({"message": message, "turns": final.get("num_turns"), "kind": job.kind,
                       "seconds": round((final.get("duration_ms") or 0) / 1000),
                       "session": final.get("session_id"), "denials": denials})
    for d in denials:
        job.add(f"DENIED {d.get('tool_name')} {rel((d.get('tool_input') or {}).get('file_path', ''))}", "error")
    if proc.returncode != 0 or final.get("is_error") or denials:
        raise RuntimeError(f"the {agent} did not finish cleanly; see the log")
    return message


def labelled(message: str) -> dict:
    """The `label: value` lines of an agent's final message."""
    out = {}
    for line in message.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def run_extractor(job, app: Path, revise: bool):
    slug = app.name
    before = (app / "extraction.md").read_text() if revise else ""
    old_mtime = mtime(app)
    prompt = f"Application folder: applications/{slug}/" + ("\nmode: revise" if revise else "")
    job.add(f"Starting the extractor{' in revise mode' if revise else ''} for applications/{slug}/ (effort: {EFFORT})")

    def roll_back():  # a stopped, failed or timed-out run leaves no half-written draft behind
        ext = app / "extraction.md"
        if revise:
            ext.write_text(before)
            undone = "extraction.md restored to how it was before this run (your answers are kept)"
        else:
            if ext.exists():
                ext.unlink()
            undone = "the half-written extraction.md was removed; the job description is kept"
        job.result["rolled_back"] = undone
        return undone

    try:
        message = run_claude(job, "extractor", prompt, [f"{app}/**"], extractor_stage)
    except Exception:
        roll_back()
        raise
    if message is None:
        undone = roll_back()
        job.result = {"rolled_back": undone}
        job.add(f"Stopped. {undone[0].upper() + undone[1:]}.", "warn")
        raise Stopped()
    ext = app / "extraction.md"
    if not ext.exists() or (revise and mtime(app) == old_mtime):
        raise RuntimeError("the extractor finished but did not write extraction.md; see its message")
    md = ext.read_text()
    n = s.unticked(md)
    job.result["unticked"] = n
    if revise:
        job.result["diff"] = "".join(difflib.unified_diff(before.splitlines(True), md.splitlines(True),
                                                          "extraction.md (before)", "extraction.md (after)"))
    edits = [lambda x: t.upsert_application(
                 x, slug, f"{'revised' if revise else 'extracted'} {today()} via CV Studio, waiting on vetting ({n} open questions)",
                 "Answer the open questions in CV Studio, then Approve" if n else "Approve in CV Studio, then render"),
             lambda x: t.set_last_updated(x, today(), f"CV Studio: {slug} {'revised' if revise else 'extracted'}")]
    item = labelled(message).get("tracker", "")
    if item and not item.lower().startswith("none"):
        edits.append(lambda x: t.add_waiting_item(x, slug, f"{item} (extractor via CV Studio, {today()})"))
    gaps = s.unmatched(md)
    if gaps and not revise:
        edits.append(lambda x: t.merge_skill_gap(x, s.company_from(app, md), gaps, today()))
    t.update(*edits)
    job.add(f"Done in {job.result['seconds']}s, {job.result['turns']} turns. {n} open question(s) unticked.", "ok")


# ---------- interviewer and curator via Claude Code ----------

def _target(block):
    inp = block.get("input") or {}
    return block.get("name", ""), str(inp.get("file_path") or inp.get("path") or "")


def interviewer_stage(job, block):
    name, target = _target(block)
    edits = name in ("Edit", "Write")
    if job.kind == "ask":
        if "/artifacts/" in target or (edits and target.endswith("index.md")):
            return 1
        return 2 if edits and target.endswith("interview.md") else 0
    if job.kind == "next":
        if edits and target.endswith("index.md"):
            return 1
        return 2 if edits and target.endswith("interview.md") and job.stage >= 1 else None
    return 0  # finish: the interviewer phase is stage 0


def curator_stage(job, block):
    name, target = _target(block)
    return 1 if name in ("Edit", "Write") and target.endswith("master-cv.md") else None


def track_item(edits, entry, item, who):
    """A `tracker:` value as a dated row ('when <x> | <what>') or a waiting row."""
    if not item or item.lower().startswith("none"):
        return
    head, sep, rest = item.partition("|")
    if sep and head.strip().lower() == entry.lower():  # the agent repeated the entry column: "<slug> | <what>"
        item = rest.strip()
    if item.lower().startswith("when ") and "|" in item:
        when, what = item[5:].split("|", 1)
        edits.append(lambda x: t.add_dated_item(x, when.strip(), entry, f"{what.strip()} ({who} via CV Studio, {today()})"))
    else:
        edits.append(lambda x: t.add_waiting_item(x, entry, f"{item} ({who} via CV Studio, {today()})"))


def run_interviewer(job, exp: Path, mode: str):
    slug, idx, iv = exp.name, exp / "index.md", exp / "interview.md"
    before_idx, before_iv = idx.read_text(), iv.read_text()
    job.add(f"Starting the interviewer ({mode}) for experiences/{slug}/ (effort: {EFFORT})")
    undone = "your notes and the interview record were restored to how they were before this run"
    try:
        message = run_claude(job, "interviewer", f"Experience: experiences/{slug}/\nmode: {mode}",
                             [idx, iv], interviewer_stage, extra_disallowed=("Write",))
    except Exception:  # failed or timed out: undo partial edits, the same as Stop
        idx.write_text(before_idx)
        iv.write_text(before_iv)
        job.result["rolled_back"] = undone
        raise
    if message is None:
        idx.write_text(before_idx)
        iv.write_text(before_iv)
        job.result = {"rolled_back": undone}
        job.add("Stopped. Notes and interview record restored.", "warn")
        raise Stopped()
    problems = e.index_guard(before_idx, idx.read_text())
    if problems:
        idx.write_text(before_idx)
        iv.write_text(before_iv)
        for p in problems:
            job.add(p, "error")
        raise RuntimeError("the interviewer changed your notes in a way it must not, so the run was undone")
    fields = labelled(message)
    rnd = e.current_round(iv.read_text())
    job.result.update({"thin": fields.get("thin", ""), "closes": fields.get("closes", ""),
                       "questions": sum(1 for q in rnd["questions"] if not q["ticked"]) if rnd and mode != "finish" else 0,
                       "nothing_more": "nothing more" in fields.get("interview.md", "").lower()})
    edits = [lambda x: t.set_last_updated(x, today(), f"CV Studio: {slug} interview {mode}")]
    track_item(edits, slug, fields.get("tracker", ""), "interviewer")
    t.update(*edits)
    job.add(f"Done in {job.result['seconds']}s. " + (f"{job.result['questions']} question(s) for you." if job.result["questions"]
                                                    else "Answers recorded."), "ok")
    return message


def needs_review(pending) -> bool:
    """Keep/Undo is asked for only when a curator run changed the master CV or the tag vocabulary."""
    return any(k in pending["diffs"] for k in ("master/master-cv.md", "CLAUDE.md"))


def run_curator(job, mode: str, slugs, stage_base=0):
    """Curator `entry <slugs>` or `refresh`, reviewable: snapshot, run, post-checks, tracker rows, seal."""
    paths = ["master/master-cv.md", "CLAUDE.md", "tracker.md"] + [f"experiences/{x}/index.md" for x in slugs]
    try:
        undo.take(paths, {"kind": job.kind, "slugs": list(slugs), "when": today(), "label": job.label})
    except RuntimeError as err:
        raise Refused(409, str(err))
    before = {p: (ROOT / p).read_text() for p in paths if (ROOT / p).exists()}
    fences = [ROOT / "master" / "master-cv.md", ROOT / "CLAUDE.md"] + [e.EXPS / x / "index.md" for x in slugs]
    prompt = "refresh" if mode == "refresh" else "entry " + " ".join(slugs)
    job.add(f"Starting the curator ({prompt}) (effort: {EFFORT})")
    try:
        message = run_claude(job, "curator", prompt, fences,
                             (lambda j, b: None if curator_stage(j, b) is None else stage_base + 1) if stage_base else curator_stage)
    except Exception:
        undo.restore_all()
        job.result["rolled_back"] = "your master CV and notes were restored to how they were before this run"
        raise
    if message is None:
        undo.restore_all()
        job.result = {"rolled_back": "your master CV and notes were restored to how they were before this run"}
        job.add("Stopped. Master CV restored.", "warn")
        raise Stopped()
    job.advance(stage_base + 2)
    job.latest = "Checking what changed"
    problems = []
    for x in slugs:
        rel_idx = f"experiences/{x}/index.md"
        if not e.status_only_change(before[rel_idx], (ROOT / rel_idx).read_text()):
            problems.append(f"the curator changed more than the status line in {rel_idx}")
    if not e.outside_section_equal(before["CLAUDE.md"], (ROOT / "CLAUDE.md").read_text(), "Tag vocabulary"):
        problems.append("the curator changed CLAUDE.md outside the tag vocabulary")
    if problems:
        undo.restore_all()
        for p in problems:
            job.add(p, "error")
        raise RuntimeError("the curator broke an ownership rule, so the run was undone")
    f = labelled(message)
    entry = slugs[0] if len(slugs) == 1 else "(master CV)"
    edits = [lambda x: t.set_last_updated(x, today(), f"CV Studio: curator {prompt}")]
    q = f.get("quantify?", "")
    if q and not q.startswith("0"):
        edits.append(lambda x: t.replace_waiting_item(x, entry, "Curator marked bullets (quantify?)",
                                                      f"Curator marked bullets (quantify?): {q}. Give the numbers with Update in CV Studio"))
    tags = f.get("new tags", "")
    if tags and not tags.lower().startswith("none"):
        edits.append(lambda x: t.add_waiting_item(x, "(tag vocabulary)", f"Curator added {tags} via CV Studio, {today()}. Veto with Undo or by editing CLAUDE.md"))
        job.result["new_tags"] = tags
    track_item(edits, entry, f.get("open", ""), "curator")
    if f.get("skipped", "none").lower() not in ("none", ""):
        job.add(f"Skipped: {f['skipped']}", "warn")
    t.update(*edits)
    undo.seal()
    if undo.pending() and not needs_review(undo.pending()):
        undo.keep()  # only bookkeeping changed (status line, tracker rows): nothing for the user to review
    job.result["review"] = bool(undo.pending())
    if mode == "refresh" and not job.result["review"]:  # re-ranked with nothing to review: the goals row is done
        t.update(lambda x: t.delete_rows_mentioning(x, g.TRACKER_ENTRY))
    job.add("Done. " + ("Review the change to your master CV." if job.result["review"] else "The master CV did not change."), "ok")
    return message


def run_finish(job, exp: Path, record: bool):
    """Interviewer finish (if there is anything to record) -> status interviewed + session closed -> curator."""
    idx, iv = exp / "index.md", exp / "interview.md"
    if record:
        run_interviewer(job, exp, "finish")
        job.result["interviewer"] = job.result.get("message", "")
    idx.write_text(e.set_status(idx.read_text(), "interviewed"))
    if e.open_session_of(e.parse_interview(iv.read_text())):
        iv.write_text(e.close_session(iv.read_text()))
    job.add("Marked interviewed and closed the interview session.", "ok")
    job.advance(1)
    run_curator(job, "entry", [exp.name], stage_base=0)


# ---------- goals drafter via Claude Code ----------

def goals_stage(job, block):
    name, target = _target(block)
    return 1 if name in ("Edit", "Write") and target.endswith("proposal.md") else None


def goals_workspace(revise: bool) -> Path:
    """A temp folder outside the home folder holding only what the drafter may read. Its run denies Read under
    the home folder, so it cannot open the master CV, notes or tracker (CLAUDE.md rule 1 for goals)."""
    ws = Path(tempfile.mkdtemp(prefix="cv-goals-")).resolve()
    for rel_path in ("CLAUDE.md", g.GOALS, ".claude/agents/goals-drafter.md"):
        (ws / rel_path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel_path, ws / rel_path)
    (ws / "tools" / "goals-draft").mkdir(parents=True)
    if revise and g.proposal_path().exists():
        shutil.copy2(g.proposal_path(), ws / "tools" / "goals-draft" / "proposal.md")
    return ws


def run_goals_drafter(job, mode: str):
    """Draft or revise tools/goals-draft/proposal.md from goals.md and the user's notes. Never writes goals.md."""
    ws = goals_workspace(mode == "revise")
    WORKSPACES.add(ws)
    try:
        return _run_goals_drafter(job, mode, ws)
    finally:
        WORKSPACES.discard(ws)
        shutil.rmtree(ws, ignore_errors=True)


def _run_goals_drafter(job, mode: str, ws: Path):
    proposal, ws_proposal = g.proposal_path(), ws / "tools" / "goals-draft" / "proposal.md"
    previous = proposal.read_text() if mode == "revise" and proposal.exists() else None
    before_mtime = ws_proposal.stat().st_mtime_ns if ws_proposal.exists() else None
    notes = g.notes()
    prompt = f"mode: {mode}\n" + "\n".join(
        f"{'note' if i == 0 else f'revision {i}'} ({short_name()}, {n['date']}): {n['text']}" for i, n in enumerate(notes))

    def give_back():  # a revise keeps the previous draft, and a first draft has nothing worth keeping
        if previous is not None:
            g.undo_revision(previous)
        else:
            g.discard()

    job.add(f"Starting the goals drafter ({mode}) (effort: {EFFORT})")
    # A failed run raises here: the real proposal was never touched and the notes stay unsealed, so Retry works.
    message = run_claude(job, "goals-drafter", prompt, [ws_proposal], goals_stage,
                         extra_disallowed=("Glob", "Grep", f"Read(/{Path.home().resolve()}/**)"), cwd=ws)
    if message is None:
        give_back()
        job.result = {"rolled_back": "nothing, since goals.md was never touched" if previous is None
                      else "your previous draft is back, and goals.md was never touched"}
        job.add("Stopped. goals.md was never touched.", "warn")
        raise Stopped()
    if not ws_proposal.exists() or ws_proposal.stat().st_mtime_ns == before_mtime:
        give_back()
        raise RuntimeError("the drafter finished but did not write a proposal; see its message")
    text, goals = ws_proposal.read_text(), g.read()
    problems = g.check(text)
    if problems:
        give_back()
        raise RuntimeError(f"the drafter's proposal lost part of the file ({'; '.join(problems)}), so it was discarded")
    job.advance(2)
    job.latest = "Checking the draft"
    fields = labelled(message)
    if g.normalise(text) == g.normalise(goals):
        g.discard()
        job.result.update(review=False, changed=fields.get("changed", ""), not_done=fields.get("not done", ""))
        job.add("No change proposed: the draft matches your current goals.", "ok")
        return message
    terms = g.new_terms(goals, [n["text"] for n in notes], text)
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(text)
    g.seal_proposal(message, fields, terms)
    job.result.update(review=True, changed=fields.get("changed", ""), not_done=fields.get("not done", ""),
                      new_terms=len(terms))
    job.add(f"Draft ready in {job.result['seconds']}s. Review it before anything is saved.", "ok")
    return message


# ---------- render.py ----------

def run_render(job, app: Path, preview: bool):
    argv = [sys.executable, str(ROOT / "tools" / "render.py"), f"applications/{app.name}"] + (["--preview"] if preview else [])
    job.add(f"Rendering {'a preview' if preview else 'the final CV'} with tools/render.py")
    job.latest = "Laying out the page in Chrome"
    proc, done, stderr = spawn(job, argv)
    out = proc.stdout.read()
    _finish(proc, done)
    err = "".join(stderr).strip()
    try:
        data = json.loads(out) if out.strip() else {}
    except json.JSONDecodeError:
        data = {}
    if proc.returncode == 2 and data.get("refused"):
        job.result = data
        for p in data.get("problems", []):
            job.add(p, "error")
        raise RuntimeError(f"render.py refused: {data['refused']}")
    if proc.returncode != 0:
        raise RuntimeError(err or out or f"render.py exited {proc.returncode}")
    job.result = data
    for d in data.get("dropped", []):
        job.add(f"Trimmed to fit: {d['entry']}: {d['bullet'][:90]}", "warn")
    job.add(f"{data.get('pages')} page(s): {data.get('pdf')}", "ok")
    if not preview:
        job.advance(1)
        moved = s.archive_previews(app)
        if moved:
            job.add(f"Moved to drafts/: {', '.join(moved)}")
        pdf = Path(data["pdf"]).name
        t.update(lambda x: t.upsert_application(x, app.name, f"final CV rendered {today()} via CV Studio ({pdf})",
                                                "Review the PDF before sending"),
                 lambda x: t.set_last_updated(x, today(), f"CV Studio: {app.name} rendered"))


# ---------- API ----------

def detail(app: Path):
    state = s.folder_state(app)
    out = {"slug": app.name, "state": state, "company": s.company_from(app), "role": s.role_from(app), "jd": "",
           "final_pdf": None, "preview_pdf": None, "extraction": None, "drafts": [], "job": None}
    if (app / "jd.md").exists():
        out["jd"] = (app / "jd.md").read_text()
    for key, fn in (("final_pdf", s.final_pdf), ("preview_pdf", s.preview_pdf)):
        f = fn(app) if app.is_dir() else None
        out[key] = {"name": f.name, "v": f.stat().st_mtime_ns} if f else None
    out["preview_stale"] = app.is_dir() and s.preview_stale(app)
    if (app / "drafts").is_dir():
        out["drafts"] = sorted(p.name for p in (app / "drafts").iterdir() if p.is_file())
    ext = app / "extraction.md"
    if ext.exists():
        md = ext.read_text()
        on = s.jd_date(app)
        entries = s.parse_entries(md)
        for entry in entries:  # computed here so a draft without a score: line still shows the recency term
            entry["recency"] = s.recency(entry["heading"], on)
        out["extraction"] = {"mtime": mtime(app), "raw": md, "questions": s.parse_questions(md),
                             "unticked": s.unticked(md), "pending": s.pending_answers(md),
                             "approved": bool(s.APPROVED_RE.search(md)), "entries": entries, "jd_date": on.isoformat()}
    job = last_job(app.name)
    out["job"] = job.view(len(job.log)) | {"next": 0} if job else None
    return out


def create_app(body):
    company, role, jd = (body.get(k, "").strip() for k in ("company", "role", "jd"))
    if not (company and role and jd):
        raise Refused(400, "company, role and the job description are all needed")
    exact, similar = s.find_existing(company, role)
    if exact:
        raise Refused(409, "this application already exists", existing=exact[0])
    if similar and not body.get("confirm_similar"):
        raise Refused(409, "there is already an application for this company", similar=similar)
    slug = s.build_slug(company, role)
    app = s.resolve_app(slug)
    s.write_jd(app, company, role, jd)
    t.update(lambda x: t.upsert_application(x, slug, f"JD saved {today()} via CV Studio", "Run the extractor in CV Studio"),
             lambda x: t.set_last_updated(x, today(), f"CV Studio: {slug} created"))
    return {"slug": slug}


def label(app: Path) -> str:
    return f"{s.company_from(app)}, {s.role_from(app)}"


def check_fresh(app, body):
    if body.get("mtime") != mtime(app):
        raise Refused(409, "extraction.md changed since you opened it (maybe in chat). Reload first.")
    if app.name in ACTIVE:
        raise Refused(409, "a job is running for this application")


def action(app: Path, verb: str, body):
    state = s.folder_state(app)
    if verb == "extract":
        if state != "jd only":
            raise Refused(409, f"the extractor runs only on a new application (this one is '{state}')")
        return {"job": start_job(app.name, "extract", lambda j: run_extractor(j, app, False), label(app)).id}
    if verb == "answers":
        if state != "draft":
            raise Refused(409, f"answers can only be added while the extraction is a draft (it is '{state}')")
        check_fresh(app, body)
        ext = app / "extraction.md"
        try:
            skipped = []
            ext.write_text(s.write_answers(ext.read_text(), body.get("answers") or {}, body.get("other") or "", skipped))
        except ValueError as e:
            raise Refused(400, str(e))
        try:
            job = start_job(app.name, "revise", lambda j: run_extractor(j, app, True), label(app))
        except Refused as err:  # the answers stay in the file and the page offers Apply now
            raise Refused(err.status, f"{err}. Your answers are saved: click Apply now when it's done.", **err.extra)
        return {"job": job.id, "skipped": skipped}
    if verb == "revise":  # answers already written (e.g. a failed run): retry
        if state != "draft" or not s.pending_answers((app / "extraction.md").read_text()):
            raise Refused(409, "there are no unapplied answers to revise with")
        return {"job": start_job(app.name, "revise", lambda j: run_extractor(j, app, True), label(app)).id}
    if verb == "preview":
        if state not in ("draft", "approved"):
            raise Refused(409, f"nothing to preview (state '{state}')")
        return {"job": start_job(app.name, "preview", lambda j: run_render(j, app, True), label(app)).id}
    if verb == "approve":
        if state != "draft":
            raise Refused(409, f"only a draft can be approved (this one is '{state}')")
        check_fresh(app, body)
        ext = app / "extraction.md"
        preview, fresh = s.preview_pdf(app), not s.preview_stale(app)
        jd = app / "jd.md"
        problems = md_problems(ext.read_text(), jd.read_text() if jd.exists() else "")
        if problems:  # the final render would refuse this draft, so approving it would be a dead end
            raise Refused(409, "this draft breaks the CV style rules, so it could not be rendered: " + "; ".join(problems[:3]))
        try:
            ext.write_text(s.approve(ext.read_text()))
        except ValueError as e:
            raise Refused(409, str(e))
        if preview and fresh:
            os.utime(preview)  # Approve changes only the status line: the preview still shows this CV
        t.update(lambda x: t.upsert_application(x, app.name, f"approved {today()} via CV Studio", "Render the final CV in CV Studio"),
                 lambda x: t.set_last_updated(x, today(), f"CV Studio: {app.name} approved"))
        return {"state": "approved"}
    if verb == "render":
        if state == "rendered":
            if not body.get("confirm_rerender"):
                raise Refused(409, "a final PDF already exists", confirm="rerender")
            if not s.APPROVED_RE.search((app / "extraction.md").read_text()):
                raise Refused(409, "extraction.md is not approved")
            if app.name in ACTIVE:
                raise Refused(409, "a job is running for this application")
            s.archive_final(app)
        elif state != "approved":
            raise Refused(409, f"approve the extraction first (it is '{state}')")
        return {"job": start_job(app.name, "render", lambda j: run_render(j, app, False), label(app)).id}
    raise Refused(404, f"unknown action {verb}")


# ---------- experiences and the master CV ----------

FILE_TYPES.update({".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
                   ".txt": "text/plain; charset=utf-8", ".csv": "text/plain; charset=utf-8", ".tsv": "text/plain; charset=utf-8",
                   ".json": "text/plain; charset=utf-8", ".html": "text/plain; charset=utf-8", ".htm": "text/plain; charset=utf-8"})


def iv_mtime(exp: Path) -> str:
    f = exp / "interview.md"
    return str(f.stat().st_mtime_ns) if f.exists() else ""


def job_summary(key):
    job = last_job(key)
    return job.view(len(job.log)) | {"next": 0} if job else None


def review_summary():
    p = undo.pending()
    return {k: p[k] for k in ("kind", "slugs", "when", "label", "diffs")} if p else None


def who() -> str:
    """How notes and pins name the person (the owner's short name)."""
    return short_name()


def index_mtime(exp: Path) -> str:
    f = exp / "index.md"
    return str(f.stat().st_mtime_ns) if f.exists() else ""


def needs_curating(old: str, new: str) -> str:
    """Notes or details changed on an entry already in the CV: mark it Update to curate, so the CV catches up."""
    if new != old and e.front_matter(new).get("status") == "condensed":
        return e.set_status(new, "interviewed")
    return new


def exp_detail(exp: Path):
    if not (exp / "index.md").exists():
        raise Refused(404, "no such experience")
    md = (exp / "index.md").read_text()
    iv = (exp / "interview.md").read_text() if (exp / "interview.md").exists() else ""
    sessions = e.parse_interview(iv)
    open_s = e.open_session_of(sessions)
    master_md = e.MASTER.read_text() if e.MASTER.exists() else ""
    review = review_summary()
    return {"slug": exp.name, "front": e.front_matter(md), "index": md,
            "interview": {"mtime": iv_mtime(exp), "sessions": sessions, "open": open_s,
                          "rounds": len(open_s["rounds"]) if open_s else 0, "max_rounds": e.MAX_ROUNDS,
                          "pending": e.pending_round_answers(iv) if open_s else 0},
            "artifacts": e.list_artifacts(exp), "master_entry": e.master_entry(master_md, exp.name),
            "tracker": t.rows_mentioning(t.TRACKER.read_text(), exp.name),
            "job": job_summary(f"exp:{exp.name}"),
            "review": review if review and exp.name in review["slugs"] else None, "types": e.TYPES,
            "index_mtime": index_mtime(exp), "sections": mc.sections(master_md),
            "own_entry": bool(mc.owned_block(master_md, exp.name))}


def create_exp(body):
    try:
        exp = e.create_experience(body.get("title"), body.get("organisation"), body.get("dates"),
                                  body.get("type"), (body.get("slug") or "").strip() or None)
    except FileExistsError as err:
        raise Refused(409, str(err))
    t.update(lambda x: t.set_last_updated(x, today(), f"CV Studio: experience {exp.name} added"))
    return {"slug": exp.name}


def exp_label(exp: Path) -> str:
    return e.front_matter((exp / "index.md").read_text()).get("title", exp.name)


def exp_action(exp: Path, verb: str, body):
    if not (exp / "index.md").exists():
        raise Refused(404, "no such experience")
    key, lab = f"exp:{exp.name}", exp_label(exp)
    iv_path = exp / "interview.md"
    iv = iv_path.read_text() if iv_path.exists() else ""
    open_s = e.open_session_of(e.parse_interview(iv))
    status = e.front_matter((exp / "index.md").read_text()).get("status", "stub")

    def fresh():
        if body.get("mtime", "") != iv_mtime(exp):
            raise Refused(409, "the interview changed since you opened it (maybe in another tab). Reload first.")
        if key in ACTIVE:
            raise Refused(409, "a run is already going for this experience")

    def no_review():
        if undo.pending():
            raise Refused(409, "Keep or Undo the last master CV change first (Master CV, Changes)")

    if verb == "start":
        if open_s:
            raise Refused(409, "an interview is already open for this experience")
        kind = "add" if status == "stub" else "update"
        note = (body.get("note") or "").strip()
        if kind == "update" and not note:
            raise Refused(400, "say what changed, so the interviewer knows what to ask about")
        iv_path.write_text(e.open_session(iv, exp.name, kind, note))
        try:
            job = start_job(key, "ask", lambda j: run_interviewer(j, exp, "ask"), lab)
        except Refused:
            iv_path.write_text(iv) if iv else iv_path.unlink()
            raise
        return {"job": job.id}
    if verb == "ask":  # retry round 1 after a failed or stopped first run
        if not open_s or open_s["rounds"]:
            raise Refused(409, "there is no interview waiting for its first questions")
        return {"job": start_job(key, "ask", lambda j: run_interviewer(j, exp, "ask"), lab).id}
    if verb in ("next", "finish"):
        if not open_s:
            raise Refused(409, "there is no open interview")
        fresh()
        skipped = []
        updated = e.write_round_answers(iv, body.get("answers") or {}, body.get("other") or "", skipped)
        if verb == "next":
            if len(open_s["rounds"]) >= e.MAX_ROUNDS:
                raise Refused(409, f"that was round {e.MAX_ROUNDS}, the last one. Click Finish")
            if not e.pending_round_answers(updated):
                raise Refused(400, "type at least one answer first, or click Finish")
            target, kind = (lambda j: run_interviewer(j, exp, "next")), "next"
        else:
            no_review()
            record = bool(open_s["rounds"])
            target, kind = (lambda j: run_finish(j, exp, record)), "finish"
        iv_path.write_text(updated)
        try:
            job = start_job(key, kind, target, lab)
        except Refused:
            iv_path.write_text(iv)
            raise
        return {"job": job.id, "skipped": skipped}
    if verb == "curate":
        if open_s:
            raise Refused(409, "finish the open interview first")
        if status == "stub":
            raise Refused(409, "interview this experience first; the curator needs notes")
        no_review()
        return {"job": start_job(key, "curate", lambda j: run_curator(j, "entry", [exp.name]), lab).id}
    if verb == "tracker-resolve":
        t.update(lambda x: t.delete_row(x, body.get("line", "")),
                 lambda x: t.set_last_updated(x, today(), f"CV Studio: tracker row for {exp.name} resolved"))
        return {"ok": True}
    # ----- the user's own edits: CV Studio code writes them, never an agent -----

    def idle():
        if key in ACTIVE:
            raise Refused(409, "wait for the run on this experience to finish")
        if any(JOBS[i].kind in WRITERS for i in ACTIVE.values()):
            raise Refused(409, "wait for the running curator or interview to finish (it may be writing these notes)")

    def index_fresh():
        if body.get("index_mtime", "") != index_mtime(exp):
            raise Refused(409, "the notes changed since you opened them (maybe in VS Code or chat). Reload first.")

    idx = exp / "index.md"
    try:
        if verb == "details":
            idle()
            index_fresh()
            old = idx.read_text()
            new = e.edit_details(old, body.get("title"), body.get("organisation"), body.get("dates"), body.get("type"))
            master_md = e.MASTER.read_text() if e.MASTER.exists() else ""
            idx.write_text(needs_curating(old, new) if e.master_entry(master_md, exp.name) else new)
            t.update(lambda x: t.set_last_updated(x, today(), f"CV Studio: {exp.name} details edited"))
            return {"ok": True}
        if verb == "notes":
            idle()
            index_fresh()
            old = idx.read_text()
            new = e.replace_notes(old, body.get("text") or "")
            if new == old:
                return {"unchanged": True}
            idx.write_text(needs_curating(old, new))
            t.update(lambda x: t.set_last_updated(x, today(), f"CV Studio: {exp.name} notes edited by hand"))
            return {"ok": True}
        if verb == "skip":
            if not open_s:
                raise Refused(409, "there is no open interview")
            fresh()
            iv_path.write_text(e.skip_question(iv, int(body.get("index", -1)), who(), date.today()))
            return {"ok": True}
        if verb == "cancel":
            if not open_s:
                raise Refused(409, "there is no open interview")
            if key in ACTIVE:
                raise Refused(409, "stop the running interview first")
            iv_path.write_text(e.close_session(iv))
            return {"ok": True}
        if verb == "doc-remove":
            idle()
            e.remove_artifact(exp, body.get("name") or "")
            return {"ok": True}
        if verb in ("archive", "unarchive"):
            idle()
            no_review()
            master_md = e.MASTER.read_text()
            to = "Archive" if verb == "archive" else body.get("section") or ""
            new = mc.move_entry(master_md, exp.name, to, who(), body.get("reason") or "", date.today())
            undo.take(["master/master-cv.md"], {"kind": "manual", "slugs": [exp.name], "when": today(),
                                                "label": f"{'Archived' if verb == 'archive' else 'Moved back to ' + to}: {lab}"})
            e.MASTER.write_text(new)
            undo.seal()
            return {"review": True}
    except ValueError as err:
        raise Refused(400, str(err))
    raise Refused(404, f"unknown action {verb}")


def tracker_view():
    text = t.TRACKER.read_text() if t.TRACKER.exists() else ""
    exps = e.list_experiences()
    return {"items": t.all_items(text), "titles": {x["slug"]: x["title"] for x in exps}, "waiting": t.WAITING}


def tracker_action(verb, body):
    line = body.get("line") or ""
    note = lambda what: (lambda x: t.set_last_updated(x, today(), f"CV Studio: tracker {what}"))
    try:
        if verb == "resolve":
            t.update(lambda x: t.delete_row(x, line), note("row resolved"))
            return {"ok": True}
        if verb == "edit":
            cells = [str(c) for c in body.get("cells") or []]
            if not cells or not all(c.strip() for c in cells):
                raise ValueError("fill in every column")
            t.update(lambda x: t.replace_item(x, line, cells), note("row edited"))
            return {"ok": True}
        if verb == "add":
            entry, what, when = (" ".join(str(body.get(k) or "").split()) for k in ("entry", "text", "when"))
            if not (entry and what):
                raise ValueError("say what it is about and what closes it")
            add = (lambda x: t.add_dated_item(x, when, entry, what)) if when else (lambda x: t.add_waiting_item(x, entry, what))
            t.update(add, note("row added"))
            return {"ok": True}
        if verb == "answer":
            item = next((i for i in t.all_items(t.TRACKER.read_text()) if i["line"] == line), None)
            if not item:
                raise ValueError("that row changed or is gone. Reload the page")
            dated = item["section"] == "Waiting on a date or event"
            slug, question = (item["cells"][1], item["cells"][2]) if dated else (item["cells"][0], item["cells"][-1])
            exp = e.EXPS / slug
            if not (exp / "index.md").exists():
                raise ValueError("only a row about one experience can be answered here. Resolve or edit this one")
            if f"exp:{slug}" in ACTIVE or any(JOBS[i].kind in WRITERS for i in ACTIVE.values()):
                raise Refused(409, "wait for the running curator or interview to finish")
            old = (exp / "index.md").read_text()
            (exp / "index.md").write_text(needs_curating(old, e.add_answer_note(old, question, body.get("text"), who(), date.today())))
            t.update(lambda x: t.delete_row(x, line), note(f"answered for {slug}"))
            return {"ok": True, "slug": slug}
    except ValueError as err:
        raise Refused(400, str(err))
    raise Refused(404, f"unknown action {verb}")


def master_view():
    md = e.MASTER.read_text() if e.MASTER.exists() else ""
    return {"raw": md, "tags": e.tag_vocabulary((ROOT / "CLAUDE.md").read_text()), "review": review_summary(),
            "goals": goals_summary(),
            "job": job_summary("master"), "experiences": e.list_experiences(master_md=md)}


def master_action(verb, body):
    if verb == "refresh":
        if undo.pending():
            raise Refused(409, "Keep or Undo the last master CV change first")
        return {"job": start_job("master", "refresh", lambda j: run_curator(j, "refresh", []), "Master CV").id}
    if any(JOBS[i].kind in WRITERS for i in ACTIVE.values()):
        raise Refused(409, "wait for the running curator or interview to finish")
    if verb == "keep":
        refreshed = (undo.pending() or {}).get("kind") == "refresh"
        undo.keep()
        t.update(lambda x: t.set_last_updated(x, today(), "CV Studio: master CV change kept"),
                 *([lambda x: t.delete_rows_mentioning(x, g.TRACKER_ENTRY)] if refreshed else []))
        return {"kept": True}
    if verb == "undo":
        return undo.undo(e.set_status, lambda md: e.front_matter(md).get("status"))
    raise Refused(404, f"unknown action {verb}")


# ---------- career goals ----------

def needs_refresh() -> bool:
    return bool(t.rows_mentioning(t.TRACKER.read_text(), g.TRACKER_ENTRY))


def draft_apps():
    return [{"slug": a["slug"], "label": f"{a['company']}, {a['role']}"} for a in s.list_apps() if a["state"] == "draft"]


def goals_summary():
    raw = g.read()
    return {"last_updated": g.last_updated(raw), "proposal": bool(g.pending()), "needs_refresh": needs_refresh(),
            "running": "goals" in ACTIVE}


def goals_view():
    raw = g.read()
    job = job_summary("goals")
    running = bool(job and job["status"] == "running")
    log = ROOT / g.LOG
    return {"raw": raw, "mtime": g.mtime(), "last_updated": g.last_updated(raw), "proposal": g.pending(),
            "unfinished": g.notes() if g.unsealed() and not running else [], "job": job,
            "needs_refresh": needs_refresh(), "review_pending": bool(undo.pending()), "drafts": draft_apps(),
            "backups": g.list_backups(), "log": log.read_text() if log.exists() else ""}


def agent_running():
    with TABLE:
        return next((JOBS[i] for i in ACTIVE.values() if JOBS[i].kind in AGENT_KINDS), None)


def goals_action(verb, body):
    note = (body.get("note") or "").strip()
    if verb in ("draft", "revise", "discard") and "goals" in ACTIVE:
        raise Refused(409, "the goals drafter is still working; wait for it or stop it")
    if verb == "draft":
        if body.get("retry"):
            if not g.unsealed():
                raise Refused(409, "there is no unfinished draft to retry")
            mode = "revise" if len(g.notes()) > 1 and g.proposal_path().exists() else "draft"
        else:
            if not note:
                raise Refused(400, "say what changed in your direction, in your own words")
            if g.pending():
                raise Refused(409, "accept, revise or discard the waiting draft first")
            g.start_proposal(note, today(), g.sha(g.read()))
            mode = "draft"
        return {"job": start_job("goals", "goals", lambda j: run_goals_drafter(j, mode), "Career goals").id}
    if verb == "revise":
        if not note:
            raise Refused(400, "say what should change in the draft")
        if not g.pending():
            raise Refused(409, "there is no draft to revise (it may have been saved or discarded in another tab)")
        g.add_note(note, today())
        return {"job": start_job("goals", "goals", lambda j: run_goals_drafter(j, "revise"), "Career goals").id}
    if verb == "discard":
        g.discard()
        return {"discarded": True}
    if verb == "preview":  # the manual editor's "Review changes": nothing is written
        text = g.normalise(body.get("text") or "")
        return {"diff": g.diff(g.read(), text), "problems": g.check(text), "stale": body.get("mtime") != g.mtime()}
    if verb in ("save", "restore"):
        busy = agent_running()
        if busy:
            raise Refused(409, f"wait for {KIND_NAMES.get(busy.kind, busy.kind).lower()} on {busy.label or busy.slug} "
                               "to finish first (it reads your goals)")
        try:
            if verb == "restore":
                r = g.restore(body.get("name") or "", today(), body.get("mtime"))
            else:
                source = body.get("source")
                if source == "manual":
                    notes = [{"text": note, "date": today()}] if note else []
                    r = g.save(body.get("text") or "", today(), "manual edit", notes, "", body.get("mtime"))
                elif source in ("ai", "ai-edited"):
                    p = g.pending()
                    if not p:
                        raise Refused(409, "that draft is gone (saved or discarded in another tab). Reload.")
                    if p["stale"]:
                        raise Refused(409, "goals.md changed after this draft was made. Revise it, or edit the current file instead.")
                    text = p["text"] if source == "ai" else body.get("text") or ""
                    r = g.save(text, today(), "AI draft" if source == "ai" else "AI draft, edited by hand",
                               p["notes"], p["changed"], body.get("mtime"))
                    g.discard()
                else:
                    raise Refused(400, "unknown source")
        except g.Conflict as err:
            raise Refused(409, str(err))
        t.update(lambda x: t.add_waiting_item(t.delete_rows_mentioning(x, g.TRACKER_ENTRY), g.TRACKER_ENTRY,
                                              f"goals.md changed {today()} via CV Studio: run Refresh ranking on the Master CV "
                                              "page so the master CV is re-ranked against it"),
                 lambda x: t.set_last_updated(x, today(), f"CV Studio: goals.md {'restored' if verb == 'restore' else 'updated'}"))
        return r | {"saved": True, "drafts": draft_apps()}
    raise Refused(404, f"unknown action {verb}")


class Handler(BaseHTTPRequestHandler):
    server_version = "CVStudio/1"

    def log_message(self, fmt, *args):
        pass

    def send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def check_host(self):
        """Every request, GET included, must name this server. A DNS rebinding page sends its own domain
        as Host, so without this check another website could read CV data while the server runs."""
        if self.headers.get("Host") not in {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}:
            raise Refused(403, "request refused (unknown Host)")

    def guard(self):
        self.check_host()
        hosts = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
        origin = self.headers.get("Origin")
        if (origin and origin.split("//", 1)[-1] not in hosts) or self.headers.get("X-CV-UI") != "1":
            raise Refused(403, "request refused (not from the CV Studio page)")

    def handle_errors(self, fn):
        try:
            fn()
        except Refused as e:
            self.send(e.status, {"error": str(e)} | e.extra)
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self.handle_errors(self._get)

    def do_POST(self):
        self.handle_errors(self._post)

    def _get(self):
        self.check_host()
        url = urlparse(self.path)
        parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
        if not parts:
            parts = ["static", "index.html"]
        if parts[0] == "static" and len(parts) == 2 and parts[1] in STATIC:
            f = UI_DIR / parts[1]
            if not f.exists():
                raise Refused(404, "not found")
            return self.send(200, f.read_bytes(), STATIC[parts[1]])
        if parts == ["api", "apps"]:
            return self.send(200, {"apps": s.list_apps(), "active": dict(ACTIVE)})
        if parts[:2] == ["api", "apps"] and len(parts) == 3:
            return self.send(200, detail(s.resolve_app(parts[2])))
        if parts == ["api", "exp"]:
            return self.send(200, {"exps": e.list_experiences(), "active": dict(ACTIVE), "review": bool(undo.pending()),
                                   "types": e.TYPES, "goals": goals_summary()})
        if parts[:2] == ["api", "exp"] and len(parts) == 3:
            return self.send(200, exp_detail(e.resolve_exp(parts[2])))
        if parts == ["api", "tracker"]:
            return self.send(200, tracker_view())
        if parts == ["api", "master"]:
            return self.send(200, master_view())
        if parts == ["api", "goals"]:
            return self.send(200, goals_view())
        if parts[:3] == ["api", "goals", "backup"] and len(parts) == 4:
            try:
                return self.send(200, {"text": g.read_backup(parts[3])})
            except ValueError as err:
                raise Refused(404, str(err))
        if parts == ["api", "settings"]:
            return self.send(200, settings())
        if parts == ["api", "ping"]:
            return self.send(200, {"ok": True})
        if parts[:2] == ["api", "jobs"] and len(parts) == 3:
            job = JOBS.get(parts[2])
            if not job:
                raise Refused(404, "no such job (the server may have restarted)")
            since = int(parse_qs(url.query).get("since", ["0"])[0])
            return self.send(200, job.view(since))
        if parts[:2] == ["files", "exp"] and len(parts) == 5 and parts[3] == "artifacts":
            exp = e.resolve_exp(parts[2])
            f = (exp / "artifacts" / parts[4]).resolve()
            if f.parent != (exp / "artifacts").resolve() or not f.is_file() or f.name.startswith("."):
                raise Refused(404, "not found")
            ctype = FILE_TYPES.get(f.suffix.lower(), "application/octet-stream")
            return self.send(200, f.read_bytes(), ctype, {"Content-Disposition": f'inline; filename="{f.name}"'})
        if parts[0] == "files" and len(parts) in (3, 4):
            app = s.resolve_app(parts[1])
            sub = parts[2:]
            if len(sub) == 2 and sub[0] != "drafts":
                raise Refused(400, "bad path")
            name = sub[-1]
            if not all(c.isalnum() or c in "_.-" for c in name) or name.startswith("."):
                raise Refused(400, "bad file name")
            f = (app / Path(*sub)).resolve()
            if not str(f).startswith(str(app) + os.sep) or not f.is_file():
                raise Refused(404, "not found")
            ctype = FILE_TYPES.get(f.suffix, "application/octet-stream")
            disp = "attachment" if parse_qs(url.query).get("download") else "inline"
            return self.send(200, f.read_bytes(), ctype, {"Content-Disposition": f'{disp}; filename="{f.name}"'})
        raise Refused(404, "not found")

    def _post(self):
        self.guard()
        length = int(self.headers.get("Content-Length") or 0)
        parts = [unquote(p) for p in urlparse(self.path).path.strip("/").split("/") if p]
        if parts[:2] == ["api", "exp"] and len(parts) == 4 and parts[3] == "upload":
            exp = e.resolve_exp(parts[2])
            if length > e.MAX_UPLOAD:
                raise Refused(413, f"too large: {length / 1048576:.0f} MB, limit {e.MAX_UPLOAD // 1048576} MB")
            name = unquote(self.headers.get("X-File-Name") or "")
            saved = e.save_artifact(exp, name, self.rfile.read(length))
            return self.send(200, {"name": saved})
        if length > 2_000_000:
            raise Refused(413, "too large")
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        if parts == ["api", "apps"]:
            return self.send(200, create_app(body))
        if parts[:2] == ["api", "apps"] and len(parts) == 4:
            return self.send(200, action(s.resolve_app(parts[2]), parts[3], body))
        if parts == ["api", "exp"]:
            return self.send(200, create_exp(body))
        if parts[:2] == ["api", "exp"] and len(parts) == 4:
            return self.send(200, exp_action(e.resolve_exp(parts[2]), parts[3], body))
        if parts[:2] == ["api", "goals"] and len(parts) == 3:
            return self.send(200, goals_action(parts[2], body))
        if parts[:2] == ["api", "tracker"] and len(parts) == 3:
            return self.send(200, tracker_action(parts[2], body))
        if parts[:2] == ["api", "master"] and len(parts) == 3:
            try:
                return self.send(200, master_action(parts[2], body))
            except RuntimeError as err:
                raise Refused(409, str(err))
        if parts[:2] == ["api", "jobs"] and len(parts) == 4 and parts[3] == "stop":
            job = JOBS.get(parts[2])
            if not job or job.status != "running":
                raise Refused(409, "that job is not running")
            if job.kind not in AGENT_KINDS:
                raise Refused(409, "renders take a few seconds and can't be stopped")
            job.cancelled = True
            job.add("Stopping…", "warn")
            if job.proc:
                _kill(job.proc)
            return self.send(200, {"stopping": True})
        if parts == ["api", "settings"]:
            prefs = settings() | {k: bool(body[k]) for k in ("notify", "sound") if k in body}
            with FILES_LOCK:
                SETTINGS.write_text(json.dumps(prefs, indent=1))
            if body.get("test"):
                notify("Notifications are on", "You'll get one like this when a run finishes")
            return self.send(200, prefs)
        if parts == ["api", "quit"]:
            running = list(ACTIVE)
            self.send(200, {"quitting": True, "stopped_jobs": running})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        raise Refused(404, "not found")


def cleanup():
    for proc in list(CHILDREN):
        _kill(proc)
    try:
        if PIDFILE.exists() and PIDFILE.read_text().strip() == str(os.getpid()):
            PIDFILE.unlink()
    except OSError:
        pass


def main():
    global PORT, EFFORT
    ap = argparse.ArgumentParser(description="CV Studio: local UI for the /apply loop")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--effort", default=EFFORT, choices=["low", "medium", "high", "xhigh", "max"],
                    help="extractor effort level (default: high)")
    args = ap.parse_args()
    PORT, EFFORT = args.port, args.effort
    url = f"http://127.0.0.1:{PORT}/"
    if os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("refused: ANTHROPIC_API_KEY is set, so Claude Code would bill the API. Unset it; "
                 "CV Studio uses your Claude login.")
    if not Path(CLAUDE).exists():
        sys.exit(f"refused: Claude Code CLI not found at {CLAUDE}")
    if not (ROOT / "master" / "master-cv.md").exists():
        sys.exit("No CV data yet. Run `.venv/bin/python tools/example.py load` to try the example persona, "
                 "or `.venv/bin/python tools/example.py fresh` to start with your own.")
    for folder in ("experiences", "applications"):
        (ROOT / folder).mkdir(exist_ok=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"CV Studio is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    server.daemon_threads = True
    PIDFILE.write_text(str(os.getpid()))
    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print(f"CV Studio running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        cleanup()
        print("CV Studio stopped.")


if __name__ == "__main__":
    main()
