# Setup

This gets you from a fresh clone to your own first CV. It takes about ten minutes, plus however long you spend talking about your experiences.

## What you need

- **Claude Code**, installed and logged in. Run `claude` once in a terminal and finish the login. CV Studio runs the agents through this CLI on your own account, so there is no API key to set up.
- **Python 3.11 or newer.** Check with `python3 --version`.
- **Google Chrome.** The renderer prints the CV with your installed Chrome. If you don't have it, Playwright can download a copy (see Troubleshooting).
- **macOS or Linux.** I built and use it on macOS. The server and renderer are plain Python, so Linux should work the same. The macOS app and notifications are the only Mac-only parts. I have not tried Windows.

## Install

```sh
git clone https://github.com/KSDNicholas/cv-system.git
cd cv-system
python3 -m venv .venv
.venv/bin/pip install playwright pypdf
```

The `.venv` folder is gitignored. Everything runs from it, so nothing gets installed system wide.

## Try the example first

```sh
.venv/bin/python tools/example.py load
.venv/bin/python tools/ui.py
```

`load` copies Robin Tay, the fictional example persona, from `examples/robin/` into the live folders. `ui.py` starts CV Studio at http://127.0.0.1:8765 and opens it in your browser. Press Ctrl+C in the terminal to stop it, or click Quit in the page.

CV Studio has four tabs: Apps, Experiences, Master CV and Goals. On Apps, open the BrightMart application. Its Overview shows which experiences were picked for that job and the score behind each one.

I'd suggest trying one real agent run on Robin before you start your own. On Experiences, switch the filter to Pending. Robin's bakery dashboard project is mid-interview there, so you can answer round 1 in Robin's place and watch the interviewer turn the answers into notes. It is the fastest way to see what the agents do.

## Start your own

```sh
.venv/bin/python tools/example.py fresh
```

This removes Robin's files and writes blank ones. It only deletes example files you have not changed, and it lists any it kept.

Then fill in two files by hand:

1. **`master/profile.md`**: your name, a short name, and your contact details. The renderer prints the header of every CV from this file, and the agents tag the facts you give them with your short name, like `(Sam, 2026-10-10)`. It is the only place your identity is stored. Leave out any line you don't want on the CV.
2. **`master/goals.md`**: your target roles in priority order, what you want to lead with and what to play down. The curator ranks your master CV by this and the extractor scores every job against it. A few honest lines are enough to start. You can change it later on CV Studio's Goals tab.

Now add your first experience. In CV Studio, open the Experiences tab and click New experience. Or, in a Claude Code chat in this folder, run `/curate add`. If you have an old CV or a LinkedIn export, drop it into `seed/` and run `/curate backfill` in chat instead. It reads them, proposes a list of experiences, and interviews you about each one.

[USING.md](USING.md) covers the rest.

## Keeping your data in git

Your data folders (`master/`, `experiences/`, `applications/`, `seed/`, `tracker.md`) are gitignored, so a public fork can never carry your CV.

I keep mine under version control anyway, because git diffs are the easiest way to see what an agent changed. If you want the same:

1. Create a **private** repository on GitHub (or anywhere).
2. Point your clone at it: `git remote set-url origin <your-private-repo-url>`.
3. Delete the "Your CV data" block at the bottom of `.gitignore`.
4. Commit and push as usual.

To pull framework updates later, add this repo as a second remote (`git remote add upstream https://github.com/KSDNicholas/cv-system.git`) and merge from it.

## The macOS app

If you'd rather double-click than open a terminal:

```sh
launcher/build.sh
```

This builds `CV Studio.app` with the repo path baked in and copies it to your Desktop. Double-click it to start the server in the background and open the page. Run the script again if you move the repo. The server writes its log to `tools/ui.log`.

## Running it without the app

On Linux, or if you just prefer the terminal, `ui.py` is all you need:

```sh
.venv/bin/python tools/ui.py                  # opens your browser
.venv/bin/python tools/ui.py --no-browser     # just the server
.venv/bin/python tools/ui.py --port 8800      # if 8765 is taken
.venv/bin/python tools/ui.py --effort medium  # faster, cheaper agent runs
```

You can also skip CV Studio completely and work in a Claude Code chat in this folder with `/curate` and `/apply`. Both paths read and write the same files.

## Running the tests

```sh
cd tools && ../.venv/bin/python -m unittest discover -s .
```

The tests read the example persona in `examples/robin/`, never your own data, so they pass whatever state your CV is in.

## Troubleshooting

**"No CV data yet."** You haven't loaded the example or started fresh. Run one of the two `tools/example.py` commands above.

**"refused: ANTHROPIC_API_KEY is set."** CV Studio refuses to run with an API key in the environment, because Claude Code would bill the API instead of using your login. Unset it in that terminal (`unset ANTHROPIC_API_KEY`) and start again.

**"Claude Code CLI not found."** The server looks for `claude` on your PATH. Check that `which claude` prints a path. If it lives somewhere unusual, add that folder to your PATH.

**Rendering fails with a browser error.** Chrome is missing or Playwright can't find it. Run `.venv/bin/playwright install chromium` and the renderer will fall back to that copy.

**"CV Studio is already running."** Another server holds port 8765. Open http://127.0.0.1:8765, or start on another port with `--port`.

**An agent ignores a change I made to its instructions.** Claude Code loads agent files when a session starts. CV Studio starts a fresh session for every run, so its runs pick up changes right away. In a chat, start a new session after editing anything in `.claude/agents/`.

**A run is refused with "finish first" or a lock message.** That is on purpose. Interviews and curator runs change your notes and shift the line numbers that drafts cite, so they never run at the same time as the extractor. Wait for the other job to finish.

**The page says a file changed and asks me to reload.** You edited the file in an editor or in chat while the page had it open. Reload so you are not vetting a stale copy.
