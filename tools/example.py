"""Load the example persona, or start fresh with blank files.

Usage:
    .venv/bin/python tools/example.py load     copy examples/robin/ into the live folders
    .venv/bin/python tools/example.py fresh    remove the example, write blank files for your own data

Your data lives in master/, experiences/, applications/, seed/ and tracker.md. Those paths are gitignored,
so nothing you add there gets pushed by accident. Neither command deletes a file it did not copy.
`fresh` removes only example files that are still byte for byte the same as in examples/robin/.
"""

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "robin"
BLANK = ROOT / "templates" / "blank"
DATA = ["master", "experiences", "applications", "tracker.md"]
BLANKS = [("profile.md", "master/profile.md"), ("goals.md", "master/goals.md"),
          ("master-cv.md", "master/master-cv.md"), ("tracker.md", "tracker.md")]


def example_files():
    return sorted(p.relative_to(EXAMPLE) for p in EXAMPLE.rglob("*") if p.is_file() and p.name != ".DS_Store")


def has_data(rel: str) -> bool:
    path = ROOT / rel
    if path.is_file():
        return True
    return path.is_dir() and any(p.is_file() and p.name != ".DS_Store" for p in path.rglob("*"))


def load():
    clash = [d for d in DATA if has_data(d)]
    if clash:
        sys.exit(f"refused: {', '.join(clash)} already hold data. Run `fresh` first, or move them aside.")
    files = example_files()
    for rel in files:
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXAMPLE / rel, ROOT / rel)
    (ROOT / "seed").mkdir(exist_ok=True)
    print(f"Loaded the example persona ({len(files)} files). Start CV Studio with .venv/bin/python tools/ui.py")


def fresh():
    removed, kept = 0, []
    for rel in example_files():
        live = ROOT / rel
        if live.is_file() and filecmp.cmp(live, EXAMPLE / rel, shallow=False):
            live.unlink()
            removed += 1
        elif live.exists():
            kept.append(str(rel))
    for d in ("master", "experiences", "applications"):  # prune folders the example left empty
        if (ROOT / d).exists():
            for sub in sorted((ROOT / d).rglob("*"), reverse=True):
                if sub.is_dir() and not any(sub.iterdir()):
                    sub.rmdir()
    for name, dest in BLANKS:
        if not (ROOT / dest).exists():
            (ROOT / dest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BLANK / name, ROOT / dest)
    for d in ("experiences", "applications", "seed"):
        (ROOT / d).mkdir(exist_ok=True)
    print(f"Removed {removed} example files. Blank profile, goals, master CV and tracker are in place.")
    if kept:
        print("Kept because they changed since you loaded them (delete by hand if you do not need them):\n  "
              + "\n  ".join(kept))
    print("Next: fill in master/profile.md and master/goals.md, then add your first experience.")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("load", "fresh"):
        sys.exit(__doc__)
    {"load": load, "fresh": fresh}[command]()
