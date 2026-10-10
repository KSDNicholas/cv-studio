import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

import appstate as s

EXAMPLE_APPS = s.ROOT / "examples" / "robin" / "applications"  # the example persona, never your own data
BRIGHTMART = EXAMPLE_APPS / "2026-10-brightmart-data-analyst"

SAMPLE = """# Extraction: Acme, Analyst

status: draft

## JD summary
- company: Acme
- unmatched: [SQL (advanced), Tableau]

## Open questions
- [ ] First question?
- [x] Second question?
  answer: yes
  decision: kept
- [ ] Third question
  spanning two lines?
"""


class ExampleFolders(unittest.TestCase):
    def test_states(self):
        self.assertEqual(s.folder_state(BRIGHTMART), "rendered")
        self.assertEqual(s.folder_state(EXAMPLE_APPS / "2026-10-nope-nothing"), "none")

    def test_questions_all_answered_and_ticked(self):
        qs = s.parse_questions((BRIGHTMART / "extraction.md").read_text())
        self.assertTrue(qs)
        self.assertTrue(all(q["ticked"] and q["answers"] for q in qs))

    def test_list_apps(self):
        slugs = {a["slug"]: a for a in s.list_apps(EXAMPLE_APPS)}
        self.assertEqual(slugs["2026-10-brightmart-data-analyst"]["company"], "BrightMart")
        self.assertEqual(slugs["2026-10-brightmart-data-analyst"]["unticked"], 0)


class Paths(unittest.TestCase):
    def test_rejects_traversal(self):
        for bad in ["../CLAUDE.md", "/etc", "2026-10-x/../../y", "applications/../master", "", "2026-10-UPPER"]:
            with self.assertRaises(ValueError):
                s.resolve_app(bad)

    def test_accepts_prefixed(self):
        self.assertEqual(s.resolve_app("applications/2026-10-brightmart-data-analyst/"), s.APPS / "2026-10-brightmart-data-analyst")


class Questions(unittest.TestCase):
    def test_parse(self):
        qs = s.parse_questions(SAMPLE)
        self.assertEqual([q["ticked"] for q in qs], [False, True, False])
        self.assertEqual(qs[1]["answers"], ["yes"])
        self.assertEqual(qs[1]["decisions"], ["kept"])
        self.assertEqual(qs[2]["text"], "Third question spanning two lines?")
        self.assertEqual(s.unticked("## Open questions\n- none\n"), 0)

    def test_write_answers_verbatim_and_other(self):
        md = s.write_answers(SAMPLE, {"0": "keep  it\nas is", "2": ""}, other="Put the parser second")
        lines = md.splitlines()
        self.assertEqual(lines[lines.index("- [ ] First question?") + 1], "  answer: keep it as is")
        self.assertEqual(lines[-2:], ["- [ ] Change requested in UI", "  answer: Put the parser second"])
        self.assertEqual(s.pending_answers(md), 2)
        self.assertTrue(md.endswith("\n"))

    def test_write_answer_after_continuation_line(self):
        md = s.write_answers(SAMPLE, {"2": "fine"})
        self.assertIn("  spanning two lines?\n  answer: fine", md)

    def test_write_answers_skips_ticked_and_refuses_empty(self):
        skipped = []
        md = s.write_answers(SAMPLE, {"1": "again", "0": "new"}, skipped=skipped)
        self.assertEqual(skipped, [1])
        self.assertNotIn("answer: again", md)
        self.assertIn("  answer: new", md)
        with self.assertRaises(ValueError):
            s.write_answers(SAMPLE, {"1": "only a ticked one"})
        with self.assertRaises(ValueError):
            s.write_answers(SAMPLE, {"0": "  "}, other="")

    def test_last_question_answer_stays_with_it(self):
        """Bug from 2026-10-07: an answer to the last question landed under the 'Change requested' item."""
        md = s.write_answers(SAMPLE, {"2": "nil"}, other="make sure the page fits")
        lines = md.splitlines()
        self.assertEqual(lines[lines.index("  spanning two lines?") + 1], "  answer: nil")
        self.assertEqual(lines[-2:], ["- [ ] Change requested in UI", "  answer: make sure the page fits"])

    def test_stale_answers_regression(self):
        """Bug from 2026-10-07: a second Apply re-sent an answer to a question the revise had ticked."""
        first = s.write_answers(SAMPLE, {"0": "keep"})
        revised = first.replace("- [ ] First question?", "- [x] First question?")
        md = s.write_answers(revised, {"0": "keep"}, other="Drop the Datathon suffix")
        self.assertIn("- [ ] Change requested in UI", md)
        self.assertEqual(md.count("answer: keep"), 1)

    def test_approve(self):
        with self.assertRaises(ValueError):
            s.approve(SAMPLE)
        done = SAMPLE.replace("- [ ]", "- [x]")
        out = s.approve(done)
        self.assertIn("status: approved", out)
        self.assertEqual(out.replace("status: approved", "status: draft"), done)

    def test_unmatched(self):
        self.assertEqual(s.unmatched(SAMPLE), ["SQL (advanced)", "Tableau"])


SELECTED = """# Extraction: Acme, Analyst

status: draft

## Selected experiences (ordered)

### Data Intern, Acme (May 2026 - Aug 2026)   [score 8/10]
section: Experience
why: Python and SQL
score: tags 5, relevance 3, goals -1, recency +1
- Built a thing. (source: experiences/x/index.md L1)
- Built another. (source: experiences/x/index.md L2)

### Old Project, Personal Project (Nov 2024)   [score 4/10]
section: Projects
why: dashboards
- One bullet. (source: experiences/y/index.md L3)

## Dropped
- Nothing: 1/10, no overlap
"""


class Entries(unittest.TestCase):
    def test_parse_entries_with_and_without_breakdown(self):
        a, b = s.parse_entries(SELECTED)
        self.assertEqual(a["heading"], "Data Intern, Acme (May 2026 - Aug 2026)")
        self.assertEqual((a["score"], a["section"], a["why"]), (8, "Experience", "Python and SQL"))
        self.assertEqual(a["breakdown"], {"tags": 5, "relevance": 3, "goals": -1, "recency": 1})
        self.assertEqual(len(a["bullets"]), 2)
        self.assertEqual((b["score"], b["breakdown"], b["bullets"]), (4, None, ["One bullet. (source: experiences/y/index.md L3)"]))
        self.assertEqual(s.parse_entries(SAMPLE), [])

    def test_unicode_minus_in_breakdown(self):
        md = SELECTED.replace("goals -1", "goals −1")
        self.assertEqual(s.parse_entries(md)[0]["breakdown"]["goals"], -1)

    def test_end_date(self):
        self.assertEqual(s.end_date("Intern, Acme (May 2026 - Aug 2026)"), date(2026, 8, 1))
        self.assertEqual(s.end_date("Data Analysis, Harbourview Analytics Society (Nov 2024)"), date(2024, 11, 1))
        self.assertEqual(s.end_date("Engineer (Part-Time), Acme (Sep 2026 - Present)"), date.max)
        self.assertEqual(s.end_date("BSc, Harbourview University (2024 - 2028 (Expected))"), date(2028, 12, 1))
        self.assertEqual(s.end_date("Member, Team A (Jan 2024 - Jun 2025), and Captain, Team B (Aug 2025 - Aug 2026)"), date(2026, 8, 1))
        self.assertIsNone(s.end_date("Treasurer, Analytics Society (Member AY24/25, Treasurer AY25/26)"))

    def test_recency_boundaries(self):
        on = date(2026, 10, 10)
        self.assertEqual(s.recency("X (Sep 2026 - Present)", on), 1)
        self.assertEqual(s.recency("X (Oct 2025)", on), 1)   # 12 months ago
        self.assertEqual(s.recency("X (Sep 2025)", on), 0)   # 13 months ago
        self.assertEqual(s.recency("X (Oct 2023)", on), 0)   # 36 months ago
        self.assertEqual(s.recency("X (Sep 2023)", on), -1)  # 37 months ago
        self.assertEqual(s.recency("X (no date)", on), 0)

    def test_jd_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "2026-10-acme-analyst"
            s.write_jd(app, "Acme", "Analyst", "JD", date(2026, 10, 7))
            self.assertEqual(s.jd_date(app), date(2026, 10, 7))
            (app / "jd.md").write_text("# Acme: Analyst\n\nno source line\n")
            self.assertEqual(s.jd_date(app, date(2026, 10, 10)), date(2026, 10, 10))


class NewApps(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(s.build_slug("BrightMart", "Data Analyst (Retail)", date(2026, 10, 7)),
                         "2026-10-brightmart-data-analyst-retail")

    def test_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ["2026-09-acme-analyst", "2026-10-acme-data-engineer", "2026-10-other-analyst"]:
                (Path(tmp) / name).mkdir()
            exact, similar = s.find_existing("Acme", "Analyst", Path(tmp))
        self.assertEqual(exact, ["2026-09-acme-analyst"])
        self.assertEqual(similar, ["2026-10-acme-data-engineer"])

    def test_write_jd_and_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "2026-10-acme-analyst"
            s.write_jd(app, "Acme", "Analyst", "Line one\r\nLine two\n\n", date(2026, 10, 7))
            self.assertEqual((app / "jd.md").read_text(),
                             "# Acme: Analyst\n\nSource: pasted in CV Studio, 2026-10-07.\n\nLine one\nLine two\n")
            for name in ["Robin_Tay_CV_Acme.pdf", "cv.html", "Robin_Tay_CV_Acme_PREVIEW.pdf", "cv-preview.html"]:
                (app / name).write_text("x")
            self.assertEqual(sorted(s.archive_previews(app)), ["Robin_Tay_CV_Acme_PREVIEW.pdf", "cv-preview.html"])
            self.assertEqual(sorted(s.archive_final(app)), ["Robin_Tay_CV_Acme-v1.pdf", "cv-v1.html"])
            (app / "cv.html").write_text("y")
            self.assertEqual(s.archive_final(app), ["cv-v2.html"])
            with self.assertRaises(FileExistsError):
                s.write_jd(app, "Acme", "Analyst", "again")

    def test_preview_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp)
            ext, pdf = app / "extraction.md", app / "Robin_Tay_CV_Acme_PREVIEW.pdf"
            ext.write_text("status: draft\n")
            self.assertFalse(s.preview_stale(app))  # no preview yet: nothing to call stale
            pdf.write_text("x")
            os.utime(ext, ns=(1_000_000_000, 1_000_000_000))
            os.utime(pdf, ns=(2_000_000_000, 2_000_000_000))
            self.assertFalse(s.preview_stale(app))
            os.utime(ext, ns=(3_000_000_000, 3_000_000_000))  # a revise after the preview
            self.assertTrue(s.preview_stale(app))


class MultiLineAnswers(unittest.TestCase):
    def test_line_breaks_become_separate_answer_lines(self):
        md = f"status: draft\n\n{s.QUESTIONS}\n\n- [ ] Keep it?\n"
        out = s.write_answers(md, {0: "Yes.\n\nBut shorten it."})
        self.assertIn("  answer: Yes.\n  answer: But shorten it.", out)
        self.assertEqual(s.parse_questions(out)[0]["answers"], ["Yes.", "But shorten it."])

    def test_blank_answer_is_skipped(self):
        md = f"status: draft\n\n{s.QUESTIONS}\n\n- [ ] Keep it?\n"
        with self.assertRaisesRegex(ValueError, "no answers given"):
            s.write_answers(md, {0: "   \n "})


if __name__ == "__main__":
    unittest.main()
