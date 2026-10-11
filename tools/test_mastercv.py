import unittest
from datetime import date

import mastercv as mc

MD = '''# Master CV

## Header
- Name: Robin Tay

## Experience

### Analyst, Acme (May 2026 - Aug 2026)
- Built a dashboard.
tags: [sql]
retrieve: experiences/acme/index.md; experiences/client-poc/index.md

## Projects

### Budget Buddy, Personal Project (Jan 2026)
- Built a tool.
retrieve: experiences/budget-buddy/index.md

## Skills
- Python
retrieve: experiences/acme/index.md

## Archive
'''


class MoveEntry(unittest.TestCase):
    D = date(2026, 10, 11)

    def test_archive_and_back(self):
        a = mc.move_entry(MD, "budget-buddy", "Archive", "Robin", "Older work.", self.D)
        self.assertTrue(a.rstrip().endswith("pin: section (Robin, 2026-10-11)"))
        self.assertIn("- Archived by Robin on 2026-10-11 because older work.", a)
        self.assertNotIn("Budget Buddy", a.split("## Archive")[0])
        b = mc.move_entry(a, "budget-buddy", "Projects", "Robin", today=self.D)
        self.assertNotIn("Archived by", b)
        self.assertIn("Budget Buddy", b.split("## Skills")[0].split("## Projects")[1])
        self.assertNotIn("\\n\\n\\n", b)

    def test_needs_a_reason_and_an_owned_entry(self):
        with self.assertRaisesRegex(ValueError, "say why"):
            mc.move_entry(MD, "budget-buddy", "Archive", "Robin", "", self.D)
        with self.assertRaisesRegex(ValueError, "no entry of its own"):
            mc.move_entry(MD, "client-poc", "Archive", "Robin", "x", self.D)   # merged into Acme, not its own
        with self.assertRaises(ValueError):
            mc.move_entry(MD, "acme", "Skills", "Robin", today=self.D)

    def test_pin_fields_accumulate(self):
        out = mc.with_pin(["### X", "pin: order (Robin, 2026-10-01)"], "section", "Robin", self.D)
        self.assertEqual(out[-1], "pin: order, section (Robin, 2026-10-11)")


if __name__ == "__main__":
    unittest.main()
