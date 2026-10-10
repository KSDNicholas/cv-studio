import os
import tempfile
import unittest
from pathlib import Path

import goalsfile as g

EXAMPLE = g.ROOT / "examples" / "robin"

GOALS = """# Career goals

Last updated: 2026-10-06

## Target roles
<!-- In priority order -->
1. Business Analyst
2. Data Scientist
3. Data Engineer

## Industries and domains
- Priority: retail and logistics firms, BrightMart
"""


class Text(unittest.TestCase):
    def test_stamp_replaces_or_inserts(self):
        out = g.stamp(GOALS, "2026-10-07")
        self.assertEqual(out, GOALS.replace("2026-10-06", "2026-10-07"))
        bare = GOALS.replace("Last updated: 2026-10-06\n\n", "")
        self.assertEqual(g.last_updated(g.stamp(bare, "2026-10-07")), "2026-10-07")
        self.assertTrue(g.stamp(bare, "2026-10-07").startswith("# Career goals\n\nLast updated: 2026-10-07\n"))

    def test_check(self):
        self.assertEqual(g.check(GOALS), [])
        self.assertEqual(g.check("  \n"), ["goals.md can't be empty"])
        self.assertEqual(len(g.check("## Target roles\n- x\n")), 1)
        self.assertEqual(len(g.check("# Goals\n## Roles\n")), 1)
        self.assertEqual(g.check(g.read(EXAMPLE)), [])  # the example persona's file passes

    def test_new_terms(self):
        notes = ["Add Harbour Foods as a target, from 2027"]
        clean = GOALS.replace("BrightMart", "BrightMart and Harbour Foods (2027)")
        self.assertEqual(g.new_terms(GOALS, notes, clean), [])
        flagged = GOALS.replace("BrightMart", "BrightMart, Megamart, by 2029")
        self.assertEqual(g.new_terms(GOALS, notes, flagged), ["Megamart", "2029"])
        reordered = GOALS.replace("2. Data Scientist\n3. Data Engineer", "2. Data Engineer\n3. Data Scientist\n4. Retail")
        self.assertEqual(g.new_terms(GOALS, notes, reordered), [])  # list numbers and known words in any case

    def test_log_keeps_long_notes_as_a_quote(self):
        entry = g.log_entry("2026-10-08", "AI draft", [{"text": "# Goals\n\n- analyst first\n- engineer second", "date": "x"}], "reordered")
        self.assertEqual(entry, "## 2026-10-08 (AI draft)\n- note:\n> # Goals\n> - analyst first\n> - engineer second\n- changed: reordered\n")

    def test_counts_and_normalise(self):
        self.assertEqual(g.normalise("a\r\nb\n\n\n"), "a\nb\n")
        self.assertEqual(g.counts("a\nb\n", "a\nc\nd\n"), (2, 1))


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "master").mkdir()
        (self.root / "master" / "goals.md").write_text(GOALS)
        self.old_dir, g.DIR = g.DIR, self.root / "goals-draft"

    def tearDown(self):
        g.DIR = self.old_dir
        self.tmp.cleanup()

    def test_proposal_lifecycle(self):
        self.assertIsNone(g.pending(self.root))
        g.start_proposal("Move Data Engineer up", "2026-10-07", g.sha(GOALS))
        self.assertTrue(g.unsealed())
        self.assertIsNone(g.pending(self.root))  # not sealed yet
        g.proposal_path().write_text(GOALS.replace("2. Data Scientist\n3. Data Engineer", "2. Data Engineer\n3. Data Scientist"))
        g.seal_proposal("proposal: written", {"changed": "Data Engineer moved to 2", "not done": "none"}, [])
        p = g.pending(self.root)
        self.assertEqual([n["text"] for n in p["notes"]], ["Move Data Engineer up"])
        self.assertEqual((p["changed"], p["not_done"], p["stale"]), ("Data Engineer moved to 2", "none", False))
        self.assertIn("+2. Data Engineer", p["diff"])
        g.add_note("keep it", "2026-10-07")
        self.assertTrue(g.unsealed())
        g.undo_revision(g.proposal_path().read_text())
        self.assertEqual(len(g.notes()), 1)
        self.assertIsNotNone(g.pending(self.root))
        g.add_note("keep it", "2026-10-07")
        self.assertEqual([n["text"] for n in g.notes()], ["Move Data Engineer up", "keep it"])
        g.seal_proposal("proposal: written", {}, [])
        (self.root / "master" / "goals.md").write_text(GOALS + "- edited in VS Code\n")
        self.assertTrue(g.pending(self.root)["stale"])
        g.discard()
        self.assertIsNone(g.pending(self.root))
        self.assertEqual(g.notes(), [])

    def test_save_backup_log_restore(self):
        m0 = g.mtime(self.root)
        new = GOALS.replace("3. Data Engineer", "3. Data Engineer\n4. ML Engineer")
        notes = [{"text": "Add ML Engineer at 4", "date": "2026-10-07"}]
        r = g.save(new, "2026-10-07", "AI draft", notes, "Target roles: ML Engineer added", m0, self.root)
        saved = (self.root / "master" / "goals.md").read_text()
        self.assertEqual(g.last_updated(saved), "2026-10-07")
        self.assertIn("4. ML Engineer", saved)
        self.assertEqual(g.read_backup(r["backup"]), GOALS)  # the previous version, byte for byte
        log = (self.root / "master" / "goals-log.md").read_text()
        self.assertTrue(log.startswith("# Goals log\n"))
        self.assertIn("## 2026-10-07 (AI draft)\n- note: Add ML Engineer at 4\n- changed: Target roles: ML Engineer added\n", log)
        with self.assertRaises(g.Conflict):
            g.save(new, "2026-10-07", "manual edit", [], "", m0, self.root)  # stale mtime
        with self.assertRaises(ValueError):
            g.save("# no roles\n", "2026-10-07", "manual edit", [], "", g.mtime(self.root), self.root)
        g.restore(r["backup"], "2026-10-08", g.mtime(self.root), self.root)
        self.assertEqual((self.root / "master" / "goals.md").read_text(), GOALS.replace("2026-10-06", "2026-10-08"))
        self.assertEqual(len(g.list_backups()), 2)
        self.assertIn("(restored version from ", (self.root / "master" / "goals-log.md").read_text())
        self.assertIn("- note: (none given)", (self.root / "master" / "goals-log.md").read_text())

    def test_backups_cap_and_names(self):
        for i in range(g.KEEP_BACKUPS + 3):
            g.backup(f"v{i}\n")
        names = [b["name"] for b in g.list_backups()]
        self.assertEqual(len(names), g.KEEP_BACKUPS)
        self.assertEqual(g.read_backup(names[0]), f"v{g.KEEP_BACKUPS + 2}\n")  # newest first
        for bad in ("../goals.md", "x.md", ""):
            with self.assertRaises(ValueError):
                g.read_backup(bad)


if __name__ == "__main__":
    unittest.main()
