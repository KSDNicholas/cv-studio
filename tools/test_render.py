import unittest

import render


class Entries(unittest.TestCase):
    def test_score_line_is_ignored_and_bullets_kept(self):
        lines = ["### Data Intern, Acme (May 2026 - Aug 2026)   [score 8/10]", "section: Experience",
                 "score: tags 5, relevance 3, goals -1, recency +1", "why: Python",
                 "- Built a thing. (source: experiences/x/index.md L1)", "- Built another. (source: experiences/x/index.md L2)"]
        [e] = render.parse_entries(lines)
        self.assertEqual((e["score"], e["section"]), (8, "Experience"))
        self.assertEqual(e["bullets"], ["Built a thing.", "Built another."])


class StyleRule4(unittest.TestCase):
    def test_coursework_label_is_the_one_allowed_colon(self):
        edu = ["BSc Business Analytics, Harbourview University", "Relevant coursework: Probability, Mathematical Statistics."]
        self.assertEqual(render.style_problems([], edu, "", ""), [])

    def test_other_colons_and_banned_characters_are_refused(self):
        edu = ["BSc, Harbourview University", "Minor: Economics", "Relevant coursework: Probability; Calculus."]
        problems = render.style_problems([], edu, "", "")
        self.assertTrue(any("colon inside an education line" in p for p in problems))
        self.assertTrue(any("semicolon" in p for p in problems))


class Profile(unittest.TestCase):
    def test_example_profile_gives_header_short_name_and_pdf_stem(self):
        profile = render.read_profile(render.ROOT / "examples" / "robin" / "master" / "profile.md")
        name, contact = render.parse_header(profile)
        self.assertEqual(name, "Robin Tay")
        self.assertIn("linkedin.com/in/robin-tay-example", contact)
        self.assertNotIn("https://", contact)
        self.assertEqual(render.short_name(profile), "Robin")
        self.assertEqual(render.pdf_stem(profile), "Robin_Tay_CV")

    def test_fallbacks(self):
        self.assertEqual(render.short_name({"name": "Sam Lee"}), "Sam")
        self.assertEqual(render.short_name({}), "the user")
        self.assertEqual(render.pdf_stem({"name": "Lee, Sam (Jr.)"}), "Lee_Sam_Jr_CV")


if __name__ == "__main__":
    unittest.main()
