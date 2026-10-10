import tempfile
import unittest
from datetime import date
from pathlib import Path

import expstate as e

IV = """# Interview record: demo

Written by CV Studio.

## Session 2026-10-01 (add)
status: closed

### Round 1
- [x] 1. Old question?
  answer: old

## Session 2026-10-07 (update)
note: Datathon results are in
status: open

### Round 1
- [x] 1. What was the rank?
  answer: 2nd of 30
- [ ] 2. Which parts did you build?
- [ ] 3. Any numbers
  for the drawdown?
"""


EXAMPLE = e.ROOT / "examples" / "robin"  # the example persona, never your own data


class Example(unittest.TestCase):
    def test_list_and_master_entry(self):
        master = (EXAMPLE / "master" / "master-cv.md").read_text()
        exps = {x["slug"]: x for x in e.list_experiences(EXAMPLE / "experiences", master)}
        self.assertIn("larkspur-analytics-intern", exps)
        self.assertEqual(exps["larkspur-analytics-intern"]["status"], "condensed")
        self.assertTrue(exps["larkspur-analytics-intern"]["in_master"])
        entry = e.master_entry(master, "datathon-2026")
        self.assertIn("Datathon", entry["heading"])
        self.assertIn("hackathon", entry["tags"])

    def test_tag_vocabulary(self):
        groups = {g["group"]: g["tags"] for g in e.tag_vocabulary((e.ROOT / "CLAUDE.md").read_text())}
        self.assertIn("python", groups["Languages"])

    def test_resolve(self):
        for bad in ["../master", "2026-10-brightmart-data-analyst", "Bad Slug", "", "a/../../b"]:
            with self.assertRaises(ValueError):
                e.resolve_exp(bad)


class Create(unittest.TestCase):
    def test_create_template_status_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            exps = Path(tmp)
            exp = e.create_experience("Throwaway Test Project", "Personal project", "Oct 2026", "project", exps=exps)
            md = (exp / "index.md").read_text()
            fm = e.front_matter(md)
            self.assertEqual((fm["slug"], fm["status"], fm["type"]), ("throwaway-test-project", "stub", "project"))
            for s in e.SECTIONS:
                self.assertIn(f"## {s}\n", md)
            self.assertEqual(e.front_matter(e.set_status(md, "interviewed"))["status"], "interviewed")
            with self.assertRaises(FileExistsError):
                e.create_experience("Throwaway Test Project", "x", "y", "project", exps=exps)
            name = e.save_artifact(exp, "My Notes (final).md", b"hello")
            self.assertEqual(name, "My-Notes-final.md")
            self.assertEqual(e.save_artifact(exp, "My Notes (final).md", b"again"), "My-Notes-final-v1.md")
            self.assertEqual([a["name"] for a in e.list_artifacts(exp)], ["My-Notes-final-v1.md", "My-Notes-final.md"])
            with self.assertRaises(ValueError):
                e.save_artifact(exp, "deck.pptx", b"x")
            with self.assertRaises(ValueError):
                e.save_artifact(exp, "big.pdf", b"x" * (e.MAX_UPLOAD + 1))


class Interview(unittest.TestCase):
    def test_parse(self):
        s = e.parse_interview(IV)
        self.assertEqual([x["status"] for x in s], ["closed", "open"])
        cur = e.open_session_of(s)
        self.assertEqual(cur["note"], "Datathon results are in")
        qs = cur["rounds"][-1]["questions"]
        self.assertEqual([q["ticked"] for q in qs], [True, False, False])
        self.assertEqual(qs[2]["text"], "3. Any numbers for the drawdown?")
        self.assertEqual(e.round_count(IV), 1)

    def test_open_session(self):
        with self.assertRaises(ValueError):
            e.open_session(IV, "demo", "update")
        md = e.open_session("", "demo", "add", "", date(2026, 10, 7))
        self.assertTrue(md.startswith("# Interview record: demo"))
        self.assertIn("## Session 2026-10-07 (add)\nstatus: open\n", md)

    def test_answers_and_close(self):
        skipped = []
        md = e.write_round_answers(IV, {"0": "again", "2": "about\n4%"}, "I led the feature work", skipped)
        self.assertEqual(skipped, [0])
        self.assertIn("  for the drawdown?\n  answer: about 4%", md)
        self.assertTrue(md.rstrip().endswith("- [ ] Also noted in CV Studio\n  answer: I led the feature work"))
        self.assertEqual(e.pending_round_answers(md), 2)
        closed = e.close_session(md)
        self.assertIsNone(e.open_session_of(e.parse_interview(closed)))
        self.assertEqual(closed.count("status: closed"), 2)


class Guards(unittest.TestCase):
    BEFORE = "---\nslug: x\nstatus: stub\n---\n\n# X\n\n## Numbers\n- 12 panels\n\n## Open questions\n- old q\n"

    def test_guard_allows_additions_and_open_question_removal(self):
        after = self.BEFORE.replace("- 12 panels\n", "- 12 panels\n- 4 alert rules (Robin, 2026-10-07)\n").replace("- old q\n", "")
        self.assertEqual(e.index_guard(self.BEFORE, after), [])

    def test_guard_catches_lost_line_and_front_matter(self):
        self.assertTrue(e.index_guard(self.BEFORE, self.BEFORE.replace("- 12 panels\n", "")))
        self.assertTrue(e.index_guard(self.BEFORE, self.BEFORE.replace("status: stub", "status: interviewed")))

    def test_status_only_and_section_compare(self):
        self.assertTrue(e.status_only_change(self.BEFORE, self.BEFORE.replace("status: stub", "status: condensed")))
        self.assertFalse(e.status_only_change(self.BEFORE, self.BEFORE.replace("12", "13")))
        a = "## Rules\nx\n## Tag vocabulary\n- a\n## Other\ny\n"
        self.assertTrue(e.outside_section_equal(a, a.replace("- a\n", "- a\n- b\n"), "Tag vocabulary"))
        self.assertFalse(e.outside_section_equal(a, a.replace("x\n", "z\n"), "Tag vocabulary"))


if __name__ == "__main__":
    unittest.main()
