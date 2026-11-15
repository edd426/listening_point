# Intent: what Evan wants from The Listening Point

Standing intent for the whole project. Quoted text is Evan's own; the rest is a record of his answers
as written down at the time, with its source. Claude adds entries when Evan states a want; Evan
corrects anything misread. Interpretations are labelled as Claude's.

Per-change intents live in `intent/<change>/intent.md`, with the spec and plan beside them. Current
state and decisions stay in `STATUS.md`; the v3 history stays in `docs/V3-PLAN.md`.

## What I want

- **A window onto one place that follows the real day.** Sky, weather, tide and seasons drive
  everything; a frame for every minute. (v2, 2026-10-05; `README.md`)
- **More defined.** The ground and the objects, toward "a detailed hand-drawn 2D game background":
  rich texture, readable shapes, a little stylisation. Not a photo, not a realist oil painting.
  (interview 2026-11-01, `docs/V3-PLAN.md`)
- **More interesting in three ways:** visible at a glance, rewarding when you look close, and telling
  a story that builds over weeks. He left out "different each day". (interview 2026-11-01)
- **"A bit livelier."** Noticeably more going on, but nothing fast or flashing: it sits behind his
  work all day. (interview 2026-11-01)
- **Restraint.** "The grass is a bit distracting, but I like what you did with everything else."
  (2026-11-01, on the first phase 1 look test)
- **A look test before a look change is installed.** Before and after pictures at his real screen
  size (1440x900 pt); he says go. (interview 2026-11-01) For v3 phases 2-5 he gave a standing
  go-ahead ("Yes, please keep going without asking for my go-ahead", 2026-11-01). Claude's reading:
  that covered those phases, not later look changes.
- **A light load on the Mac.** It is an 8 GB laptop that sleeps often and that he games on. Render
  budget: up to about 6 hours of background rendering a day (interview 2026-11-01). Renders give way
  to a game. (`CLAUDE.md`, 2026-11-01)
- **The hourly lock screen.** He prefers the lock screen and Space switches to show the right hour.
  (`STATUS.md`, Decisions)
- **On the 2026-11-15 review** (Claude's list of improvements): "Please do 1-3 and 6." That is: stop
  rendering tomorrow twice; fix the mid-level cloud projection; catch renderer crashes before the
  nightly job does; housekeeping. He did not pick the time-lapse (4) or the painterly pass (5).

## What must not change

- **The layout:** tower left of centre, tree, bench, lamp, pier bottom right, island on the horizon.
- **The colour and mood.**
- **The real-world ties:** sky, weather, tide and seasons.
- **No people.** The place is seen, never peopled; the observer and the listener stay offstage.
- **Hidden events stay hidden:** `docs/SPOILERS.md`, never in chat or the README.

(All from the 2026-11-01 interview and `CLAUDE.md`.)

## What he has said about the result

- Phase 3 (2026-11-03): "I like the after."
- Puddles (2026-11-03): too white under overcast; they read as snow, not water.
- Phase 5 (2026-11-04): "It all looks really great. I couldn't always notice the differences, but
  I'm sure after some time I'll notice more and more."
