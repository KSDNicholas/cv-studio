"""One pending, reviewable change to the master CV (CV Studio's Keep / Undo).

Before a curator run, take() copies the files it may touch into tools/undo/ (gitignored, so it survives a
server restart). seal() records how the run left them. The user then Keeps (snapshot deleted) or Undoes:
each file is restored only if nobody changed it since the run. For index.md only the status line goes back,
so the user's notes always stay.
"""

import difflib
import hashlib
import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = Path(__file__).resolve().parent / "undo"
HISTORY = Path(__file__).resolve().parent / "master-history"   # the master CV before each kept change (gitignored)


def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _meta():
    try:
        return json.loads((DIR / "pending.json").read_text())
    except (OSError, ValueError):
        return None


def take(paths, meta: dict, root: Path = ROOT):
    """Snapshot files (paths relative to the repo root). Refuses while another change awaits review."""
    if _meta():
        raise RuntimeError("Keep or Undo the last master CV change first")
    if DIR.exists():
        shutil.rmtree(DIR)
    DIR.mkdir(parents=True)
    files = {}
    for i, rel in enumerate(paths):
        src = root / rel
        files[rel] = {"copy": f"{i}.bak", "existed": src.exists()}
        if src.exists():
            shutil.copy2(src, DIR / f"{i}.bak")
    (DIR / "pending.json").write_text(json.dumps({**meta, "files": files, "taken": time.time(), "sealed": False}, indent=1))


def seal(root: Path = ROOT):
    meta = _meta()
    if not meta:
        return
    for rel, f in meta["files"].items():
        f["after"] = _sha(root / rel)
    meta["sealed"] = True
    # nothing actually changed: no review needed
    if all(f["after"] == (_sha(DIR / f["copy"]) if f["existed"] else None) for f in meta["files"].values()):
        return discard()
    (DIR / "pending.json").write_text(json.dumps(meta, indent=1))


def discard():
    if DIR.exists():
        shutil.rmtree(DIR)


def restore_all(root: Path = ROOT):
    """Put every snapshotted file back (used when a run fails its post-checks or is stopped)."""
    meta = _meta()
    if not meta:
        return []
    restored = []
    for rel, f in meta["files"].items():
        dest = root / rel
        if f["existed"]:
            shutil.copy2(DIR / f["copy"], dest)
        elif dest.exists():
            dest.unlink()
        restored.append(rel)
    discard()
    return restored


def pending(root: Path = ROOT):
    meta = _meta()
    if not meta or not meta.get("sealed"):
        return None
    diffs = {}
    for rel, f in meta["files"].items():
        before = (DIR / f["copy"]).read_text() if f["existed"] else ""
        now = (root / rel).read_text() if (root / rel).exists() else ""
        if before != now:
            diffs[rel] = "".join(difflib.unified_diff(before.splitlines(True), now.splitlines(True), f"{rel} (before)", f"{rel} (after)"))
    return {k: v for k, v in meta.items() if k != "files"} | {"diffs": diffs, "files": list(meta["files"])}


def before_text(rel: str):
    meta = _meta()
    f = meta and meta["files"].get(rel)
    return (DIR / f["copy"]).read_text() if f and f["existed"] else ""


def keep(root: Path = ROOT):
    meta = _meta()
    if not meta:
        raise RuntimeError("there is no change waiting for review")
    _remember(meta, root)
    discard()


def _remember(meta, root: Path = ROOT):
    """Keep the master CV as it was before a kept change, so History can bring it back."""
    f = meta["files"].get("master/master-cv.md")
    if not f or not f["existed"] or _sha(DIR / f["copy"]) == _sha(root / "master/master-cv.md"):
        return
    HISTORY.mkdir(exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    shutil.copy2(DIR / f["copy"], HISTORY / f"{stamp}.md")
    (HISTORY / f"{stamp}.json").write_text(json.dumps({"label": meta.get("label") or meta.get("kind", ""), "kind": meta.get("kind", "")}))


def history():
    """Saved versions, newest first: {name, when, label}. Each is the master CV just before that change."""
    if not HISTORY.exists():
        return []
    out = []
    for f in sorted(HISTORY.glob("*.md"), reverse=True):
        info = {}
        try:
            info = json.loads(f.with_suffix(".json").read_text())
        except (OSError, ValueError):
            pass
        day, clock = (f.stem.split("T") + [""])[:2]
        out.append({"name": f.name, "when": f"{day} {clock[:5].replace('-', ':')}".strip(), "label": info.get("label", "")})
    return out


def history_text(name: str) -> str:
    f = HISTORY / name
    if f.parent != HISTORY or not f.is_file() or not name.endswith(".md"):
        raise ValueError("no such saved version")
    return f.read_text()


def undo(set_status, front_status, root: Path = ROOT):
    """Restore each file the run changed, if untouched since. index.md: only its status line."""
    meta = _meta()
    if not meta:
        raise RuntimeError("there is no change waiting for review")
    restored, refused, kept = [], [], []
    for rel, f in meta["files"].items():
        dest = root / rel
        if _sha(dest) == (_sha(DIR / f["copy"]) if f["existed"] else None):
            continue  # unchanged by the run
        if rel.endswith("/index.md"):
            old = front_status((DIR / f["copy"]).read_text()) if f["existed"] else None
            if old and dest.exists():
                dest.write_text(set_status(dest.read_text(), old))
                kept.append(rel)
            continue
        if _sha(dest) != f.get("after"):
            refused.append(rel)
            continue
        if f["existed"]:
            shutil.copy2(DIR / f["copy"], dest)
        elif dest.exists():
            dest.unlink()
        restored.append(rel)
    discard()
    return {"restored": restored, "refused": refused, "status_only": kept}
