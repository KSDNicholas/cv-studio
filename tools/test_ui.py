import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import ui


class Watchdog(unittest.TestCase):
    def test_timeout_counts_time_the_mac_slept(self):
        """Wall clock jumps past the deadline with no monotonic time passing, as after a sleep: the run is stopped."""
        now = [1_000_000.0]
        job = ui.Job("test", "preview")
        with mock.patch.object(ui, "WATCHDOG_POLL", 0.02), mock.patch.object(ui.time, "time", lambda: now[0]):
            proc, done, _ = ui.spawn(job, [sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                time.sleep(0.2)
                self.assertIsNone(proc.poll(), "stopped before the deadline")
                now[0] += ui.JOB_TIMEOUT + 1
                proc.wait(timeout=5)
            finally:
                ui._kill(proc)
                ui._finish(proc, done)
                proc.stdout.close(), proc.stderr.close()
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(any("timed out" in line["text"] for line in job.log))

    def test_finished_run_is_not_stopped(self):
        job = ui.Job("test", "preview")
        with mock.patch.object(ui, "WATCHDOG_POLL", 0.02):
            proc, done, _ = ui.spawn(job, [sys.executable, "-c", "pass"])
            ui._finish(proc, done)
            proc.stdout.close(), proc.stderr.close()
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(done.is_set())
        self.assertFalse(any("timed out" in line["text"] for line in job.log))


class TrackItem(unittest.TestCase):
    def rows(self, item):
        got, edits = [], []
        ui.track_item(edits, "demo-slug", item, "interviewer")
        with mock.patch.object(ui.t, "add_waiting_item", lambda x, entry, what: got.append(("waiting", entry, what))), \
             mock.patch.object(ui.t, "add_dated_item", lambda x, when, entry, what: got.append((when, entry, what))):
            for edit in edits:
                edit("")
        return got

    def test_repeated_entry_is_stripped(self):
        [(kind, entry, what)] = self.rows("demo-slug | 2 open questions")
        self.assertEqual((kind, entry), ("waiting", "demo-slug"))
        self.assertTrue(what.startswith("2 open questions ("))

    def test_dated_and_plain_items(self):
        self.assertEqual(self.rows("when 12 Nov 2026 | add the result")[0][:2], ("12 Nov 2026", "demo-slug"))
        self.assertTrue(self.rows("ask about X")[0][2].startswith("ask about X ("))
        self.assertEqual(self.rows("none"), [])


class NeedsReview(unittest.TestCase):
    def test_only_master_cv_or_tag_changes_need_review(self):
        self.assertTrue(ui.needs_review({"diffs": {"master/master-cv.md": "…", "tracker.md": "…"}}))
        self.assertTrue(ui.needs_review({"diffs": {"CLAUDE.md": "…"}}))
        self.assertFalse(ui.needs_review({"diffs": {"tracker.md": "…", "experiences/x/index.md": "…"}}))
        self.assertFalse(ui.needs_review({"diffs": {}}))


class GoalsDrafter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_dir, ui.g.DIR = ui.g.DIR, Path(self.tmp.name) / "goals-draft"

    def tearDown(self):
        ui.g.DIR = self.old_dir
        self.tmp.cleanup()

    def test_drafter_is_fenced_to_a_workspace_and_writes_only_the_proposal(self):
        seen = {}

        def fake_run(job, agent, prompt, fences, stage_fn=None, extra_disallowed=(), cwd=None):
            files = sorted(str(f.relative_to(cwd)) for f in Path(cwd).rglob("*") if f.is_file())
            seen.update(agent=agent, prompt=prompt, fences=fences, deny=extra_disallowed, cwd=Path(cwd), files=files)
            fences[0].write_text(ui.g.read().replace("3. Business Analyst", "3. Business Analyst (test)"))
            job.result["seconds"] = 1
            return "proposal: written\nchanged: test\nkept: none\nnot done: none\nopen: none"

        root = Path(self.tmp.name) / "repo"  # CLAUDE.md, the agent file and the example persona's goals.md
        for rel, src in [("CLAUDE.md", ui.ROOT / "CLAUDE.md"),
                         (".claude/agents/goals-drafter.md", ui.ROOT / ".claude/agents/goals-drafter.md"),
                         ("master/goals.md", ui.ROOT / "examples/robin/master/goals.md")]:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, root / rel)
        with mock.patch.object(ui, "ROOT", root), mock.patch.object(ui.g, "ROOT", root), \
             mock.patch.object(ui, "short_name", lambda: "Robin"):
            ui.g.start_proposal("Test only", "2026-10-07", ui.g.sha(ui.g.read()))
            job = ui.Job("goals", "goals")
            with mock.patch.object(ui, "run_claude", fake_run):
                ui.run_goals_drafter(job, "draft")
            pending = ui.g.pending()
        home = Path.home().resolve()
        self.assertEqual(seen["agent"], "goals-drafter")
        self.assertFalse(seen["cwd"].is_relative_to(home))  # outside the home folder, so the deny rule fences reads
        self.assertIn(f"Read(/{home}/**)", seen["deny"])
        self.assertEqual(seen["files"], [".claude/agents/goals-drafter.md", "CLAUDE.md", "master/goals.md"])
        self.assertEqual(seen["fences"], [seen["cwd"] / "tools" / "goals-draft" / "proposal.md"])
        self.assertFalse(seen["cwd"].exists())  # the workspace is removed afterwards
        self.assertIn("note (Robin, 2026-10-07): Test only", seen["prompt"])
        self.assertTrue(job.result["review"])
        self.assertIn("(test)", ui.g.proposal_path().read_text())
        self.assertEqual(pending["changed"], "test")

    def test_goals_runs_alongside_an_extractor_but_save_waits(self):
        busy = ui.Job("2026-10-acme", "revise", "Acme")
        with mock.patch.dict(ui.JOBS, {busy.id: busy}), mock.patch.dict(ui.ACTIVE, {"2026-10-acme": busy.id}):
            job = ui.start_job("goals", "goals", lambda j: None)
            with self.assertRaises(ui.Refused) as err:
                ui.goals_action("save", {"source": "manual", "text": "x", "mtime": ui.g.mtime()})
            self.assertIn("finish first", str(err.exception))
        for _ in range(50):
            if job.status != "running":
                break
            time.sleep(0.01)
        ui.JOBS.pop(job.id, None)


class FailedRunRollsBack(unittest.TestCase):
    """A failed or timed-out agent run undoes its partial edits, the same as Stop."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    @staticmethod
    def failing(write):
        def fake(job, agent, prompt, fences, *a, **k):
            write()
            raise RuntimeError(f"the {agent} exited (1) without a result")
        return fake

    def test_extractor_revise_restores_the_draft(self):
        app = self.tmp / "2026-10-acme-analyst"
        app.mkdir()
        (app / "extraction.md").write_text("draft before\n")
        job = ui.Job(app.name, "revise")
        with mock.patch.object(ui, "run_claude", self.failing(lambda: (app / "extraction.md").write_text("half"))):
            with self.assertRaises(RuntimeError):
                ui.run_extractor(job, app, revise=True)
        self.assertEqual((app / "extraction.md").read_text(), "draft before\n")
        self.assertIn("restored", job.result["rolled_back"])

    def test_extractor_first_run_removes_the_partial_draft(self):
        app = self.tmp / "2026-10-acme-analyst"
        app.mkdir()
        (app / "jd.md").write_text("jd\n")
        job = ui.Job(app.name, "extract")
        with mock.patch.object(ui, "run_claude", self.failing(lambda: (app / "extraction.md").write_text("half"))):
            with self.assertRaises(RuntimeError):
                ui.run_extractor(job, app, revise=False)
        self.assertFalse((app / "extraction.md").exists())
        self.assertEqual((app / "jd.md").read_text(), "jd\n")

    def test_interviewer_restores_notes_and_record(self):
        exp = self.tmp / "acme-intern"
        exp.mkdir()
        (exp / "index.md").write_text("notes before\n")
        (exp / "interview.md").write_text("record before\n")
        job = ui.Job("exp:acme-intern", "next")

        def half():
            (exp / "index.md").write_text("half notes")
            (exp / "interview.md").write_text("half record")
        with mock.patch.object(ui, "run_claude", self.failing(half)):
            with self.assertRaises(RuntimeError):
                ui.run_interviewer(job, exp, "next")
        self.assertEqual((exp / "index.md").read_text(), "notes before\n")
        self.assertEqual((exp / "interview.md").read_text(), "record before\n")
        self.assertIn("restored", job.result["rolled_back"])


class HostCheck(unittest.TestCase):
    """GETs must name this server too, or a DNS rebinding page could read CV data."""

    def setUp(self):
        import http.server, threading
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), ui.Handler)
        self.port = self.server.server_address[1]
        self.old_port, ui.PORT = ui.PORT, self.port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        ui.PORT = self.old_port

    def get(self, host):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/", headers={"Host": host})
        status = c.getresponse().status
        c.close()
        return status

    def test_own_host_is_served(self):
        self.assertEqual(self.get(f"127.0.0.1:{self.port}"), 200)
        self.assertEqual(self.get(f"localhost:{self.port}"), 200)

    def test_foreign_host_is_refused(self):
        self.assertEqual(self.get(f"evil.example:{self.port}"), 403)


class Phase1Fixes(unittest.TestCase):
    """Bugs found by the 2026-10-11 end-to-end audit."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_last_run_survives_a_restart(self):
        job = ui.Job("2026-10-acme-analyst", "extract", "Acme")
        job.add("Reading jd.md")
        job.status, job.ended = "done", time.time()
        with mock.patch.object(ui, "JOB_HISTORY", self.tmp):
            ui.save_job(job)
            with mock.patch.dict(ui.JOBS, {}, clear=True):
                back = ui.last_job("2026-10-acme-analyst")
                self.assertEqual((back.status, back.kind), ("done", "extract"))
                self.assertEqual(back.view(0)["lines"][0]["text"], "Reading jd.md")
                self.assertIs(ui.JOBS[back.id], back)   # its log loads through /api/jobs/<id>
        ui.JOBS.pop(job.id, None)

    def test_approve_refuses_what_the_render_would_refuse(self):
        md = ("# Extraction\n\nstatus: draft\n\n## Selected experiences (ordered)\n\n"
              "### Analyst, Acme (May 2026 - Aug 2026)\nsection: Experience\n"
              "- Built a dashboard \u2014 used weekly. (source: experiences/x/index.md L3)\n")
        self.assertTrue(any("dash" in p.lower() for p in ui.md_problems(md)))

    def test_missing_goals_file_reads_as_empty(self):
        import goalsfile as g
        self.assertEqual(g.read(self.tmp), "")


if __name__ == "__main__":
    unittest.main()
