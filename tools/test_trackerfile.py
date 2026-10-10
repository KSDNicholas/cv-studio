import shutil
import tempfile
import unittest
from pathlib import Path

import trackerfile as t


SAMPLE = """# Tracker

Last updated: 2026-10-06 (test)

## Waiting on a date or event

| When | Entry | What to do |
| --- | --- | --- |
| After 12 Nov 2026 | datathon-2026 | Add result |

## Waiting on you (no deadline)

| Entry | Question |
| --- | --- |
| (LinkedIn) | Change the post count |

## Applications

| Application | Status | What closes it |
| --- | --- | --- |
| 2026-10-brightmart-data-analyst | rendered | nothing |
| 2026-10-larkspur-ops-analyst | rendered | send it |

## Skill gaps surfaced by applications

- BrightMart: dbt, A/B testing.
- Larkspur: Spark.

## Interview prep only (never on a CV)
"""


class Tracker(unittest.TestCase):
    def setUp(self):
        self.text = SAMPLE

    def test_upsert_existing_row(self):
        out = t.upsert_application(self.text, "2026-10-brightmart-data-analyst", "rendered | again", "nothing")
        self.assertIn("| 2026-10-brightmart-data-analyst | rendered / again | nothing |", out)
        self.assertEqual(out.count("| 2026-10-brightmart-data-analyst |"), 1)

    def test_upsert_new_row_lands_in_applications(self):
        out = t.upsert_application(self.text, "2026-10-acme-analyst", "extracted", "vet it")
        lines = out.split("\n")
        i = lines.index("| 2026-10-acme-analyst | extracted | vet it |")
        self.assertTrue(lines[i - 1].startswith("| 2026-10-larkspur"))

    def test_waiting_item(self):
        out = t.add_waiting_item(self.text, "2026-10-acme-analyst", "Decide on dates")
        self.assertIn("| 2026-10-acme-analyst | Decide on dates |", out)
        self.assertEqual(t.add_waiting_item(out, "2026-10-acme-analyst", "Decide on dates"), out)

    def test_skill_gaps(self):
        out = t.merge_skill_gap(self.text, "BrightMart", ["dbt", "Kafka streams"], "2026-10-07")
        self.assertIn("Also (2026-10-07): Kafka streams.", out)
        self.assertNotIn("Also (2026-10-07): dbt", out)
        out = t.merge_skill_gap(self.text, "Acme", ["Tableau"], "2026-10-07")
        self.assertIn("- Acme: Tableau.", out)

    def test_update_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "tracker.md"
            p.write_text(SAMPLE)
            t.update(lambda x: t.set_last_updated(x, "2026-10-07", "UI: test"), path=p)
            self.assertIn("Last updated: 2026-10-07 (UI: test)", p.read_text())

    def test_dated_mentions_delete(self):
        out = t.add_dated_item(self.text, "Dec 2026", "demo-slug", "Add the result")
        self.assertIn("| Dec 2026 | demo-slug | Add the result |", out)
        rows = t.rows_mentioning(out, "datathon-2026")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cells"], ["After 12 Nov 2026", "datathon-2026", "Add result"])
        self.assertEqual(t.rows_mentioning(out, "datathon"), [])
        out = t.delete_row(out, rows[0]["line"])
        self.assertNotIn("Add result |", out)
        with self.assertRaises(ValueError):
            t.delete_row(out, rows[0]["line"])

    def test_delete_rows_mentioning_goals_only(self):
        out = t.add_waiting_item(self.text, "(goals)", "goals.md changed 2026-10-07: run Refresh ranking")
        out = t.add_waiting_item(out, "(goals) extra", "goals.md changed 2026-10-08: run Refresh ranking")
        self.assertEqual(len(t.rows_mentioning(out, "(goals)")), 2)
        out = t.delete_rows_mentioning(out, "(goals)")
        self.assertEqual(t.rows_mentioning(out, "(goals)"), [])
        self.assertIn("| (LinkedIn) | Change the post count |", out)
        self.assertEqual(t.delete_rows_mentioning(self.text, "(goals)"), self.text)

    def test_example_tracker_has_every_section(self):
        text = (t.ROOT / "examples" / "robin" / "tracker.md").read_text().split("\n")
        for h in ("Applications", "Waiting on you (no deadline)", "Skill gaps surfaced by applications"):
            t._section(text, h)


if __name__ == "__main__":
    unittest.main()
