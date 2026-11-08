# Presentation notes

Rolling working notes for the agent-building talk. Add to the log at the bottom as the deck changes; keep the sections above it current.

## Theme: the mental shift

The talk is about how we, as developers, need to change the way we think to get the most out of agents. It is not a tool pitch; PDLC is only the worked example.

The shift, in one line each:

- **From taking turns to working apart.** Prompt → wait → read → prompt keeps the agent as slow as me. The goal is agents that run without me watching.
- **From doing the work to building the lever.** The agent is the force; the lever is the tools, checks, and records around it. Building levers beat writing better prompts.
- **From prompting to tooling.** Don't let the agent fish bare-handed: have it build a rod (a script/CLI) and a skill that says when and how to use it. Rough rule: asked for it twice → maybe a tool.
- **From prose to state.** Anything a later step depends on becomes checked data, not a sentence for the agent to interpret. Prose drifts; state doesn't.
- **From "it says it's done" to evidence.** Trust comes from an independent reviewer and machine-checked evidence, not the author's summary.
- **From constant supervision to interrupt-on-decision.** Agents stop only for real decisions and approvals.
- **From chat memory to a durable record.** Requirements, decisions, and progress live outside the session (the board), so any agent or teammate can pick up.

Core message: code for the process, skills for the judgement. Prompts alone leave too much to the agent; scripts alone leave too little.

## Finalised vs draft

Finalised: slides 1–5 (title, TL;DR, one agent taking turns, more agents at once, three jobs). Everything after slide 5 is a draft.

- **Finalised slides:** don't change their content, layout, or notes without asking Sudara first. Propose the change and wait for a yes.
- **Draft slides:** free to edit, reorder, merge, or rewrite, slides and notes alike, without asking.
- **Goal:** raise the finalised count as we go. A slide becomes finalised only when Sudara says so; then move the boundary above and log it.
- Reordering drafts must not change the finalised slides' position or flow; the first draft slide has to follow on from the last finalised slide's notes.

## Speaker notes style

Every `<aside class="notes">` is written down in full, but in Sudara's spoken voice, never as a script. Follow this for every new or edited note:

- Write it the way it would be said out loud, not the way an essay reads. Read it aloud; if it sounds recited, rewrite it.
- Short sentences, one idea per line or paragraph, so a glance down finds the place again.
- Blank lines are breath points: put one wherever a natural pause falls.
- Contractions and plain words ("I'd", "it's", "honestly", "so"); no formal set-ups like "For those of you who…".
- Uneven rhythm. Avoid neat symmetrical pairs ("While X, I Y. While Y, X waits.") and tidy "First… Then… Finally…" summaries.
- First person, with small honest reactions and admissions ("nice", "I wasn't comfortable putting my name on that").
- Tell a real moment where possible rather than a summary of what happened; leave a `[Your story: …]` placeholder rather than inventing one.
- Say each point once: don't preview what a later slide covers.
- End on the line the slide must land, usually a question or the punch line.
- Anything not meant to be said (stage directions, timing, reminders, placeholders) goes in `[square brackets]`, inline or as its own paragraph. `notes.html` renders it smaller, italic, and dimmed. Never use square brackets in spoken text.

Reference example: slide 1's notes.

## Narrative arc

1. Hook: the old loop, taking turns with the agent.
2. Where I started: one agent, and we took turns waiting; only one of us ever working.
3. What I did: ran more agents, and did all the work around them by hand (break down, verify, browser, review, tests, lint, requirements, Storybook, reuse) → 16 context switches; each one still needed me. Framed as the setup's limit, not the person's.
4. Three jobs: every switch on slide 4 was checking ("is it right?"), directing ("what's next?"), or reminding ("how do we do things here?"); none needed to be me, so I started handing them over.
5. Rabbit hole: my first tries at handing the jobs over were writing them down (put it in the prompt → skills → a skill of skills), until I had the agent build a tool.
6. The idea: the lever, then "build a rod plus a skill to use it".
7. Proof: one example (`pdlc inspect` replacing a long skill file).
8. Handing over the three jobs, one slide each, "I used to → Now" rows with the PDLC piece doing it: checking (pdlc-implement fixes CI/comments, reviewer agents, FR-* traceability in pdlc-test, pdlc-verify journeys), directing (pdlc-tasks planner, `pdlc inspect` Due Next, pdlc-loop, gates for approvals/decisions), reminding (pdlc-plan spikes current code, repo skills via `.pdlc/config.toml`, record on the board, anyone picks up via `pdlc inspect`).
9. Payoff: slide 9 puts slide 4's timeline (outline) above the "now" timeline, 16 switches down to 2.
10. Lessons learnt, things to try, close on a question to the audience.

## Deck status (`presentation.html`)

| # | Slide | Status |
|---|---|---|
| 1 | Title: From taking turns to working apart | **Finalised.** Notes in spoken voice (style reference) |
| 2 | TL;DR (`.cards cascade`, default large card type) | **Finalised.** Notes in spoken voice |
| 3 | Where I started: One agent, and me. We took turns waiting. (two lanes, Me and Agent; my pink stints labelled, grey stripes = task on hold for me, teal = agent working, red stripes = agent blocked on me; two takeaway lines and punch line on load) | **Finalised.** Spoken-voice notes |
| 4 | What I did: I tried running more agents at once. Each one still needed me. (no legend; red stripes = agent blocked on me, empty = not started yet; taller agent lanes; a line traces my attention, numbered pink badge at each of the 16 switches, each pink stint labelled with what I did: break down task, check the diff, verify in the browser, ask a reviewer, run the tests, fix lint, covered by the requirements?, new tests written?, add a Storybook story, reuse an existing component, re-prompt; draws itself over ~8s) | **Finalised.** Spoken-voice notes; `[Your story]` placeholder still open |
| 5 | Looking back at the switches: Every switch was one of three jobs. (Checking / Directing / Reminding columns, slide 4's stint labels as pink chips, punch on load) | **Finalised.** Spoken-voice notes |
| 6 | Rabbit hole 1 of 3: To hand them over, I wrote down the workflow. In a skill. (three columns: skill | flowchart | headline-only Liked/Disliked; left ~400 words, all-pink bar, `implement/SKILL.md`, if/then flowchart; right 👍 Liked / 👎 Disliked two-up with detail lines, on load) | Draft. Disliked list is Sudara’s; Liked and notes drafted |
| 7 | Rabbit hole 2 of 3: Then the workflow became a skill of skills. (same 1/4 · 1/4 · 2/4 layout as slide 6: left ~1,500 words, `loop/SKILL.md`; middle skills-starting-skills chart; right 👍 Liked / 👎 Disliked two-up with detail lines) | Draft. Liked/Disliked drafted; `[Your story]` open |
| 8 | Rabbit hole 3 of 3: Then the workflow became a tool. (same 1/4 · 1/4 · 2/4 layout: left 1 command, 50/50 bar, `pdlc-loop/SKILL.md` + `pdlc next loop` output; middle loop chart in green code / purple agent / indigo me; right 👍 Liked / 👎 Disliked two-up with detail lines) | Draft. Liked/Disliked drafted from the repo |
| 9 | Example: "What's next on this work item?" (skill file vs `pdlc inspect`; right side still on steps) | Draft. Spoken-voice notes absorb the old "huge skill file" slide and bridge to the questions |
| 10 | Rabbit hole, what stuck: Don't fish bare-handed. Build a rod, and a skill to use it. (slide 8's 1/4 · 1/4 · 2/4 layout: left `2×` rule, sample `check-ci.sh` tool and its skill; middle bare-handed vs with-a-rod chart; right 🎣 What stuck two-up + 📏 My rule now) | Draft. Merges the old lever and fishing-rod slides; Archimedes dropped |
| 11 | Rabbit hole, then it could loop: Same result every time. So it could loop until it needed me. (slide 8's layout: left ↻ and an illustrative shortened run; middle the whole Feature workflow with green self-loops per stage, a verify→implement bounce, indigo approval dots between stages; right 🔁 Loops on its own two-up + ✋ Stops for me in indigo; punch: reviewed to find out if it worked → review to decide if it's what I want) | Draft. Drawn from `pdlc-workflow.md`; `[Your story]` open |
| 12 | Checking. Not me, and not the agent that wrote it. (job tabs, 4 "I used to → Now" rows with PDLC piece in grey) | Draft. Spoken-voice notes; `[Your example]` open |
| 13 | Directing. The state decides what's next, not me. (4 rows) | Draft. Spoken-voice notes |
| 14 | Reminding. Written down once, not said every time. (4 rows) | Draft. Spoken-voice notes; `[Your story]` open |
| 15 | A few things I learnt the hard way (3 cards on load) | Draft, replace with own stories |
| 16 | Some things you might try + closing question | Draft, guidance notes only |

## Presenter tooling

- `presentation.html`: single-file deck. Arrow keys / PageUp/Down navigate; `.step` elements reveal one at a time; `N` toggles inline notes; URL hash tracks slide so reload stays put. Long `.mdfile` boxes auto-scroll and hand control to the presenter on wheel/touch.
- `notes.html`: presenter window. `[Bracketed]` guidance in notes shows smaller, italic, dimmed. Syncs over `BroadcastChannel('presentation')`: shows slide/step counter, title, notes, next slide title; arrows drive the deck; `+`/`−` resize text.
- `run.sh` (and `run.ps1`): serves `site/` on the LAN via `uv` so both pages share an origin. Open both in the same browser, share only the deck window.
- Speaker notes live in each slide's `<aside class="notes">`.

## Open items

- Fill the `[Your story]` / `[Your example]` placeholders on slides 4, 7, 12, 13, 15.
- Lessons (slide 16): replace drafts with real "I thought X, then learned Y" stories.
- Parked: the old "Step 12 · Not yet" idea (start from the ticket, release on merge, logs become bugs); add back as an honest-gap slide if the talk needs it.
- Rehearse timing; slide 5 (three jobs) targets about 45s.
- Worktrees/stacked PRs and failure recovery dropped from the job slides; mention verbally or add back if needed.

## Log

- **2026-10-22** — Deck created (`a9de2d8`): title, problem framing, timelines, rabbit hole, lever, fishing-rod idea, example, trust, lessons, takeaways; Steps 01–12 as stubs.
- **2026-11-06** — Presenter notes window synced to the deck (`c308e4e`): `notes.html`, BroadcastChannel sync, `run.sh` LAN server.
- **2026-11-07** — Uncommitted deck edits on `presentation-speaker-notes` (~50 lines in `presentation.html`): fuller speaker notes on title/TL;DR, fishing-rod notes. This file started.
- **2026-11-07** — Slide 2 scaled up with a `.cards.big` modifier (larger headlines and body, wider gaps) to fill the white space without adding text.
- **2026-11-07** — Slide 1 notes rewritten in a spoken, unscripted voice; "Speaker notes style" added above as the rule for all notes going forward.
- **2026-11-07** — Slide 2 and 19 notes rewritten in the spoken voice.
- **2026-11-07** — Slide 2 notes: work arrives already tested and agent-reviewed, so the human review starts close to the goal; prompts-vs-scripts point expanded.
- **2026-11-07** — Slides 1–2 finalised; added "Finalised vs draft" rule.
- **2026-11-07** — Swapped slides 3 and 4 so the story goes attempt → diagnosis. Retitled in "what I did" style ("I ran more agents at once. I became the bottleneck."; "Why it broke: three questions I couldn't answer"), notes rewritten in spoken voice with story placeholders.
- **2026-11-07** — Presenter guidance in notes now goes in `[square brackets]`, shown smaller and dimmed in `notes.html`. Existing stage directions, placeholders, and draft-only notes converted.
- **2026-11-07** — Slide 3 timeline redesigned: Me lane replaced by an animated attention line across taller agent lanes, with numbered switch badges 1–20; notes updated to match.
- **2026-11-07** — Slide 3: each attention stint now names the manual work I did (break down task, check the diff, open the browser, ask a reviewer, run the tests, fix lint, re-prompt); 16 switches; notes walk through them and land on "that stuff needed to happen without me too".
- **2026-11-07** — Slide 3 retitled "I tried running more agents at once. I became the bottleneck."; blocked time in red stripes (not-yet-started time left empty); legend removed.
- **2026-11-07** — Slide 3: two stepped lines under the chart (agents blocked waiting on me; me never stopping switching), keyed by a red-stripe and a pink "16" swatch; replaced the old small note.
- **2026-11-07** — Slide 3 takeaway lines now match slide 2 body size and show on load (only the punch line is a step).
- **2026-11-07** — Slide 3 title second half changed from "I became the bottleneck." to "Everything still ran through me."
- **2026-11-07** — Slide 3 title second half softened to "Every step still needed me." so it blames the setup, not the human.
- **2026-11-07** — Slide 3 title second half now "Each one still needed me."
- **2026-11-07** — Slide 3 stint labels: "open the browser" → "verify in the browser"; repeats replaced with requirements coverage, new tests, Storybook story, reuse an existing component. Notes updated.
- **2026-11-07** — Slide 3 notes: added the hardest part (context switching; 2, maybe 3 agents in flow was the max; beyond that one synchronous agent was better; still felt there had to be something better).
- **2026-11-07** — Slide 3 punch line now "The hardest part was the switching. I needed a way to switch far less.", shown on load (slide has no steps); notes ending matched.
- **2026-11-07** — Slide 3 notes: opening now "break the task into smaller pieces and run more of them"; added "It looked parallel. But I was the mutex." after the blocked-agents line.
- **2026-11-07** — Slide 3 notes trimmed by about a third: breakdown and switching each said once, endings merged.
- **2026-11-07** — Slide 3 notes: opening reason fixed (I was idle while the agent worked, so I split the task and ran one per piece); added the twist "Before, I was waiting on the agent. Now they were all waiting on me."
- **2026-11-07** — New slide 3 "One agent, and me. We took turns waiting." (Me/Agent lanes, grey = me waiting, red = agent blocked on me) before the multi-agent slide, so its "before I waited on the agent, now they wait on me" twist is shown, not just said. Later slides renumbered +1; slide 4 opening shortened to "So I did the obvious thing…".
- **2026-11-07** — Slide 3: grey reframed as the task being on hold, not me idle ("Until it came back, I couldn't move that task forward."; chart label "on hold"; notes matched).
- **2026-11-07** — Slide 3 finalised. Slide 4 notes: timing improved (much less on hold) but the toll moved to me through context switching.
- **2026-11-07** — Slide 4 notes restructured: open with "this looks way better… but looks can be deceiving", then the walkthrough; dropped the requirements/tests/Storybook/component questions.
- **2026-11-07** — Slide 4 notes: setup/checking walkthrough collapsed to one sentence; the chart shows the detail.
- **2026-11-07** — Slide 4 finalised.
- **2026-11-07** — Slide 5 reworked as the bridge: "To step out of the loop, I had to answer three questions."; 9 items cut to 6, larger type, columns fade in on load; notes open "what would it take for all that to happen without me?" and end "So I started building them. One level at a time."
- **2026-11-07** — Drafts restructured around slide 5's three questions (26 → 15 slides): rabbit hole cut to 4 stairs ending on "A tool"; lever and fishing rod moved up as the turn; example kept, "huge skill file" slide merged into its notes; Steps 01–12 and the trust cards replaced by three question slides ("I noticed → So I built" rows, question tabs); after timeline rebuilt to mirror slide 4 (2 switches vs 16); duplicate lesson card dropped. All draft notes in spoken voice; on-load reveals via `.reveal`.
- **2026-11-07** — Slide 2's card sizes are now the `.cards` default (large headlines and body, wider gaps); the `.big` modifier is removed. Slide 2 looks the same; slides 8, 14, 15 pick up the larger type.
- **2026-11-07** — Three questions replaced by three jobs: slide 5 now sorts slide 4's switches into checking, directing, and reminding; slides 10–12 hand each job over, with the PDLC piece that does it under each row. Slide 9 notes bridge to "handing those three jobs over".
- **2026-11-07** — Slide 5 (three jobs) finalised.
- **2026-11-07** — Slide 6 visualised: each level shows its real artifact, a word counter, and an interprets-vs-code bar (all pink until the tool, then mostly teal); notes walk through both.
- **2026-11-07** — Slide 6 as a full-height waterfall: equal-height levels, each a step lower, with ↘ arrows between; the last lands at the bottom. Separate colour key dropped; the bar labels say it ("all interpreted by the agent", "mostly code, same every time").
- **2026-11-07** — Slide 6: each level now overlaps the one before (36px, shadowed, later on top), replacing the arrows, so the levels read as one evolving stack.
- **2026-11-07** — Slide 6 reframed to follow slide 5: "To hand them over, I wrote them down."; first level "Put it in the prompt"; notes open "So how do you hand a job over?" so it no longer reads as going back to before multiple agents.
- **2026-11-07** — Slide 6: a flowchart under each artifact grows branch by branch (a few branches in my head → a bigger tree in the skill → three trees under one loop → the tangle collapses into start → run pdlc → do it); bar and its label now share a row; levels pad their overlapped edge; notes walk the flowcharts.
- **2026-11-07** — Slide 6 flowcharts moved below each card and enlarged: prompt chart marks my decisions and checks in indigo; skill chart spells out real if/then steps (UI change → Storybook story, component exists → reuse, tests fail → read log, fix); skill-of-skills chart shows write starting plan starting review, with review sending work back; captions shortened; notes rewritten to walk them.
- **2026-11-07** — Slide 6 levels 2–4 are now arrow-key steps: level 1 shows on load, each → brings in the next level and starts its flowchart and bar animations then (held while hidden); notes carry `[→ …]` cues at each step.
- **2026-11-07** — Slide 6 skill-of-skills chart redrawn so nothing overlaps: write (top left) → plan (right) → review (bottom left), each "starts" arrow runs between frames without crossing a title, and the re-plan loop runs below.
- **2026-11-07** — Slide 6 tool level made accurate to the repo: real `pdlc-loop/SKILL.md` and `pdlc next loop` output (`action:` + `# Due Next`), counter "1 command decides what’s next", bar 50/50 "routing is code, work is skills" (skills are still ~23k words; code took the routing, not the work), flowchart runs `$ pdlc next loop`; notes match.
- **2026-11-07** — Slide 6 tool flowchart is now the loop: start → `$ pdlc next loop` (code) → run the skill (agent) → `$ pdlc post …` (code) → done? (code) → no: back to next / yes: hand it to me. Code is green (new `--green`, also the bar), agent purple, me indigo; legend under it; notes walk the loop.
- **2026-11-07** — Slide 6 loop diamond reads "needs me?" instead of "done?", matching where `pdlc next loop` really stops (a human action); notes match.
- **2026-11-08** — Slide 1 lede: "What went wrong, and what I learnt." → "What I tried, what stuck, and what didn't." (approved by Sudara).
- **2026-11-08** — Slide 5 (finalised; changed on request): Directing chips now "break down the task" and "what’s next?" (re-prompt dropped); Reminding gains "CI failing?"; notes match.
- **2026-11-08** — Slide 5: dropped "reuse an existing component" and "add a Storybook story" from Reminding (not pdlc-automated; they stay on slide 4). Rule: slide 5 chips are only things pdlc fully automates.
- **2026-11-08** — Slide 5 Reminding chips: "CI failing?", "what did we decide?", "update the board"; notes match.
- **2026-11-08** — Slide 4 notes (finalised; changed on request): added "This didn't stick for me." after "Just working with one agent, back and forth, was better."
- **2026-11-08** — Slide 6 level 1 reframed so it moves forward from slide 5: "Prompt it every time" (the longer "Hand it over in the prompt" wrapped and squashed the card); bubbles hand over the checks (tests, diff, review); flowchart now has the agent doing the checks in pink, with only "I type it all again" in indigo and a "next session" loop back to it; notes match. Level 1’s flaw is now "retyped every session", which written skills fix.
- **2026-11-08** — Slide 6 split into three slides (15 → 17): "Prompt it every time" level dropped (slides 3–4 already cover it); Skills, Skill of skills and Tool each get a slide with the skill, bar and rough flowchart on the left and Liked / Disliked lists on the right (on load). Skills’ Disliked list is Sudara’s wording; the other lists and all notes are drafts. Old waterfall and its arrow-key steps removed. Later slides shift by two.
- **2026-11-08** — Slides 6–8 framed around "the workflow": titles "I wrote down the workflow. In a skill." / "Then the workflow became a skill of skills." / "Then the workflow became a tool."; flow captions and opening notes match. Sudara’s Disliked text unchanged.
- **2026-11-08** — Slides 6–8 sized for the ~2000×1023 presenting window: three columns (skill and bar | flowchart | Liked/Disliked), much bigger type (lists up to 30px, counter up to 80px), lists cut to headlines only with the detail moved into the spoken notes. Checked at 2000×1023 and 1440×900.
- **2026-11-08** — Slide 6 only: columns 1/4 skill, 1/4 flowchart, 2/4 Liked/Disliked; each list is two-up with a one-line detail under every headline (shortened from Sudara’s full text, which the notes keep). Slides 7–8 keep the equal three columns with headlines only. Checked at 2000×1023 and 1440×900.
- **2026-11-08** — Liked / Disliked headings prefixed 👍 / 👎; slides 7–8 now use slide 6’s layout (1/4 skill, 1/4 flowchart, 2/4 two-up lists with a one-line detail under each headline). Checked at 2000×1023 and 1440×900.
- **2026-11-08** — Slide 6 Disliked: dropped "It drifts between copies." (7 items now).
- **2026-11-08** — Slide 8 Disliked: dropped "The work is still skills." and "Setup per repo." (3 items now); matching line cut from the notes.
- **2026-11-08** — Notes for slides 6 and 8 match their lists: slide 6 drops the drift line; slide 8 adds focused skills, stopping when it needs me, and new failure modes.
- **2026-11-08** — Slides 9 (lever) and 10 (fishing rod) merged into one slide in slide 8's style (17 → 16): "Don't fish bare-handed. Build a rod, and a skill to use it."; bare-handed vs with-a-rod chart; What stuck list (rods over prompts, a skill to use it, saves context, code for process / skills for judgement) plus the asked-twice rule. Archimedes dropped; notes merge both. Later slides shift by one. Checked at 2000×1023 and 1440×900.
- **2026-11-08** — New slide 10 after the rod slide (16 → 17): once the workflow was deterministic, the whole workflow could loop until it needed me. Chart follows `pdlc-workflow.md` (dry-run + local review ×3 for UI/tasks and plan, task by task + CI for implement, review + CI for test, verify fix loop and bounce ×3); lists split what loops on its own from what stops for me (spec, stage approvals, decisions, completion). Later slides shift by one. Checked at 2000×1023 and 1440×900.
- **2026-11-08** — Slide 8 loop chart: `$ pdlc inspect …` → run the skill → `$ pdlc post …` → "next autonomous?"; yes back to inspect, no "wait for my review". Notes and aria label match. Left column and Liked item still say `pdlc next loop`.
- **2026-11-08** — Slide 8 diamond now reads "needs Sudara’s review?" (no → back to inspect, yes → wait for my review); diamond widened; notes match.
- **2026-11-08** — Swapped slides 10 and 11: the example ("What's next on this work item?") now comes before the workflow-loop slide, so the story goes rod → example → loop.
- **2026-11-08** — New slide 9 after the tool slide (17 → 18): "It still needs my review. Twice, not sixteen times." Slide 4's timeline returns as a dark outline (before) above the after-timeline in colour (now), answering why review in pdlc differs from slide 4 (when, what arrives, what my job is, in the notes). Later slides shift by one; slide 16 (after) now repeats this timeline. Checked at 2000×1023 and 1440×900.
- **2026-11-08** — Removed the "Same day, same three agents" slide (18 → 17); slide 9 now carries its timeline. Lessons and takeaway are slides 16–17.
- **2026-11-08** — Slide 9 "now" timeline: the pale "my own work" blocks became solid indigo blocks naming the work only I can do (spec the next feature, talk to users, help a teammate, architecture, plan what’s next); notes add a line pointing at my lane.
- **2026-11-08** — Slide 8 fills the slide like the example slide: `.level.big` modifier (slide 8 only) with bigger type throughout (lists up to 32px, details 22px, skill/terminal 27px, counter 104px) and a wider flowchart column (0.95 · 1.3 · 1.75); no content removed. Content spans 74–905px at 2000×1023 (example slide 49–958); fits at 1440×900.
- **2026-11-08** — Slides 6–7 get slide 8’s bigger type (`.level.big`); the clipped skill box keeps a height cap (only slide 8’s tool box is uncapped). Slide 6 (longest lists) adds `.long`: columns 0.9 · 1 · 2.1 and tighter rows. Bottoms at 2000×1023: 948 / 921 / 905 (nav ~950); at 1440×900: 803 / 812 / 788 (nav 827).
- **2026-11-08** — Slide 6: "~400 words, read every run" is now plain Inter text (no hero number); the all-pink bar and "the agent interprets it all" label removed. Slides 7–8 keep their counters and bars.
- **2026-11-08** — Slide 6 skill box back to its original type size and runs down the column (cap 64vh), so all 12 steps show again with the fade; fits at 2000×1023 (932) and 1440×900 (805).
- **2026-11-08** — Slide 6 skill box taller (cap 72vh) with type up to 1.1vw (~22px at 2000 wide); runs from 210 to 946px, steps 1–10 visible before the fade. Sizing now targets only the ~2000×1023 presenting window; smaller screens are no longer tuned or checked.
- **2026-11-08** — Moved the example slide ("What's next on this work item?") to slide 9, straight after the tool slide; before/now is 10, rod is 11, loop stays 12.
- **2026-11-08** — Slides 7–8 counter lines now plain Inter text like slide 6 ("~1,500 words, across four files", "1 command decides what’s next"); their bars stay.
- **2026-11-08** — Slide 7: all-pink bar and "the agent interprets it all" removed (as on slide 6). Slide 8 keeps its half-and-half bar.
- **2026-11-08** — Slide 8: bar removed; "routing is code, work is skills" moved under the code/agent/me legend; notes now say "look at the colours". Diamond reads "needs human review?".
- **2026-11-08** — Slide 8: "routing" became "workflow" in the legend note ("workflow is code, work is skills"), the Liked item and the notes.
- **2026-11-08** — Slide 8: "workflow is code, work is skills" in Inter 600 (soft), matching the counter line, not mono.
- **2026-11-08** — Notes for slides 5–17 rewritten for flow: each slide now hands off to the next (5 → "the obvious one", 7 → "interpret the workflow at all", 8 → "show you in practice", 11 → "didn't see coming", 12 → "where each job went"); slide 5 says "just a few, over and over" instead of sixteen; lessons and takeaway now have spoken notes.
- **2026-11-08** — Slide 6 flowchart now shows the skill mixing two kinds of steps: workflow steps dashed (read the PBI, pick the next task, tests pass?, open a PR, get PR details, CI green/approved?, update the board, more tasks? → loop), work steps solid (write code and tests, read the log/fix, fix CI/comments). Legend "the work / the workflow", note "both mixed in one skill"; skill box cap 70vh. Notes point at the dashed boxes; slide 8 notes call back to them.
- **2026-11-08** — Slide 6 flowchart rebalanced to 6 workflow steps (read the PBI, pick the next task, open a PR, get PR details, CI green/approved?, more tasks?) and 5 work steps (plan the change, write code and tests, add a Storybook story, run tests/fix them, fix CI/comments), all solid on load. One arrow-key step at the end turns the workflow boxes dashed with marching dashes and shows the legend "the work / the workflow" plus "the workflow could move out". Notes end on pulling the workflow out for an orchestrator agent; slide 7 opens with the orchestrator; slide 8 says the dashed boxes "this time moved into code".
- **2026-11-08** — Slide 6: legend and "the workflow could move out" removed; the arrow-key step now only turns the workflow boxes dashed.
- **2026-11-08** — Slide 10: before (ghosted slide 4) timeline removed; lanes taller (13.5vh) with bigger type. My lane now: Tech planning for PBI 304564, technical refinement, Review PR 456, front end design discussion, spec the next feature (talk to users / help a teammate / architecture / plan removed). Notes recall slide 4 in words instead of pointing at the outline.
- **2026-11-08** — Slide 10: gates renamed "check and decide for C" and "check and approve A to continue"; lane spans rebalanced (agent blocked stretches and switch badges moved to match); labels on this timeline wrap. Notes updated.
- **2026-11-08** — Removed the before/now slide ("It still needs my review. Twice, not sixteen times."): it paid off gates and evidence before the loops and job slides set them up. Its punch line ("Before, I reviewed to find out if it worked. Now I review to decide if it's what I want.") moved onto the loops slide (now 11) and its notes. Dropped the unused before/now and after-timeline CSS. Deck is 16 slides. Also removed the stray `.mine` timeline background that was tinting the loops slide's "Stops for me" list.
- **2026-11-08** — Slide 10 (rod) uses the big type of slides 6–8 (`.level.big`); fits at 2000×1023 (left column ends 837).
- **2026-11-08** — Slide 10 (rod): "2× asked twice? build a rod" line removed; the tool and skill cards now start the left column.
- **2026-11-08** — Slide 10 rule: "Asked for it twice?" became "Needs the same answer every time? Make it a tool, and a skill to use it." Notes match.
- **2026-11-08** — Slide 16 takeaway: "ask for the same thing twice" became "When a step needs the same answer every time, see whether a small tool could give it." (slide and notes), matching slide 10.
