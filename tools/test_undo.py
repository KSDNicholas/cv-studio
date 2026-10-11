import tempfile
import unittest
from pathlib import Path

import expstate as e
import undo


class Undo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_dir, self.old_history = undo.DIR, undo.HISTORY
        undo.DIR, undo.HISTORY = self.root / "undo-store", self.root / "history"   # never the real store or history
        (self.root / "master").mkdir()
        (self.root / "experiences" / "demo").mkdir(parents=True)
        (self.root / "master" / "master-cv.md").write_text("A\n")
        (self.root / "experiences" / "demo" / "index.md").write_text("---\nstatus: interviewed\n---\nnotes\n")

    def tearDown(self):
        undo.DIR, undo.HISTORY = self.old_dir, self.old_history
        self.tmp.cleanup()

    def run_curator(self):
        undo.take(["master/master-cv.md", "experiences/demo/index.md"], {"kind": "curate", "slugs": ["demo"]}, root=self.root)
        (self.root / "master" / "master-cv.md").write_text("A\nB\n")
        idx = self.root / "experiences" / "demo" / "index.md"
        idx.write_text(e.set_status(idx.read_text(), "condensed"))
        undo.seal(root=self.root)

    def test_pending_keep(self):
        self.run_curator()
        p = undo.pending(root=self.root)
        self.assertIn("+B", p["diffs"]["master/master-cv.md"])
        with self.assertRaises(RuntimeError):
            undo.take(["master/master-cv.md"], {}, root=self.root)
        undo.keep(root=self.root)
        self.assertIsNone(undo.pending(root=self.root))

    def test_keep_saves_the_version_before(self):
        self.run_curator()
        undo.keep(root=self.root)
        h = undo.history()
        self.assertEqual(len(h), 1)
        self.assertEqual(undo.history_text(h[0]["name"]), "A\n")
        with self.assertRaises(ValueError):
            undo.history_text("../master/master-cv.md")

    def test_undo_restores_and_keeps_notes(self):
        self.run_curator()
        idx = self.root / "experiences" / "demo" / "index.md"
        idx.write_text(idx.read_text() + "a later note\n")
        r = undo.undo(e.set_status, lambda md: e.front_matter(md).get("status"), root=self.root)
        self.assertEqual(r["restored"], ["master/master-cv.md"])
        self.assertEqual((self.root / "master" / "master-cv.md").read_text(), "A\n")
        self.assertIn("status: interviewed", idx.read_text())
        self.assertIn("a later note", idx.read_text())

    def test_undo_refuses_file_changed_since(self):
        self.run_curator()
        (self.root / "master" / "master-cv.md").write_text("A\nB\nhand edit\n")
        r = undo.undo(e.set_status, lambda md: e.front_matter(md).get("status"), root=self.root)
        self.assertEqual(r["refused"], ["master/master-cv.md"])

    def test_no_change_needs_no_review(self):
        undo.take(["master/master-cv.md"], {"kind": "refresh"}, root=self.root)
        undo.seal(root=self.root)
        self.assertIsNone(undo.pending(root=self.root))


if __name__ == "__main__":
    unittest.main()
