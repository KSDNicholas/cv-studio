---
name: curate
description: Build and maintain the master CV. Interviews the user about their experiences, writes their answers into experiences/<slug>/index.md, then calls the curator subagent to condense them into master/master-cv.md. Use for /curate backfill, /curate add, /curate update <slug>, /curate refresh.
argument-hint: backfill | add | update <slug> | refresh
---

You run the interview in the user's session, then hand condensing to the `curator` subagent. You write `experiences/*/index.md`; you never write `master/master-cv.md` yourself.

Subcommand: `$ARGUMENTS`

## Subcommands

| Subcommand | Do |
| --- | --- |
| `backfill` | Build the experience list from `seed/`, then interview each one in turn (resumable) |
| `add` | Ask what the new experience is, create its folder, interview it |
| `update <slug>` | Re-read that `index.md` (and `interview.md`, if CV Studio left one, so you never re-ask), ask what changed or what's thin, append answers |
| `refresh` | No interview. Call the curator with `refresh` (run after editing `goals.md`, by hand or in CV Studio's Goals tab, which offers Refresh ranking after each save) |

CV Studio runs this same loop in a page: its interviewer agent follows the "Interviewing" and "Writing index.md" sections below, and it keeps a verbatim record in `experiences/<slug>/interview.md`. Read that file, if present, before interviewing a slug. Do not interview a slug while CV Studio has a job running on it.

After any interview, call the curator with `entry <slugs>` for the slugs you touched (or `full` at the end of a backfill). Then relay its message verbatim, run `git diff --stat` plus `git diff master/master-cv.md`, and show the diff.

Finally, update `tracker.md`: add rows for new open questions, `(quantify?)` markers and "revisit when" items the interview or the curator surfaced, and delete rows the interview resolved.

## Backfill

1. Read everything in `seed/` and `master/goals.md`. List `experiences/` to find folders already started.
2. If no folders exist, propose the experience list: one line per proposed slug with what it covers. Include things `goals.md` mentions that `seed/` does not. Ask the user to confirm, merge, split or add before creating anything. Granularity rule: one folder per role, plus a separate folder for any project that could stand alone as a CV entry.
3. Create each confirmed folder with `index.md` from the template below (`status: stub`) and an empty `artifacts/`. Copy the relevant `seed/` text verbatim into its `## From seed` section.
4. Interview the first entry with `status: stub`, in the order goals.md would rank them (most relevant to the top target roles first). Before each batch, tell the user where they are ("2 of 5: Data Analyst Intern").
5. After each entry, set `status: interviewed` and ask whether to continue to the next or stop. Backfill can stop and resume at any point; the status fields are the progress record.
6. When every entry is `interviewed`, call the curator with `full`.

## Interviewing

- Ask 3 to 5 questions per batch, numbered, in one message. Tailor them: read `## From seed` and skip what it already answers.
- Ask follow-ups only where an answer is thin: no number where one is likely to exist, "we" where you need "I", or a claim a recruiter would probe.
- Cover, across one or two batches: context (who, why, scale), what the user personally did, numbers, tools, what went wrong and what they changed, and the story they would tell in an interview.
- Ask once per entry how it connects to the top target roles in `goals.md`: the skills, domain or kind of decision those roles care about. Record the answer under `## Target role angle`. Many entries won't connect, and that's fine.
- Ask about shareability for anything involving clients, internal numbers or unreleased work.
- If they mention documents (journals, slides, READMEs), ask them to drop them in `experiences/<slug>/artifacts/`, then read them and summarise into `## Artifact notes` with the file name.

## Writing index.md

- Write their answers in their words, lightly tidied. Never add facts, numbers, adjectives or outcomes they didn't give. If you summarise, the summary must be checkable against what they said.
- Put each fact on its own line or bullet so the extractor can cite line numbers.
- Unanswered questions go under `## Open questions`, not into the body as guesses.

## index.md template

```markdown
---
slug: <slug>
title: <exact role or project title>
organisation: <org, or "Personal project">
dates: <Mon YYYY – Mon YYYY | Present>
type: work | internship | project | leadership | education | self-study | sport
status: stub
---

# <title>, <organisation>

## Context
## What I did
## Numbers
## Tools
## What went wrong and what I changed
## Interview story
## Target role angle
## Shareability
## Artifact notes
## From seed
## Open questions
```
