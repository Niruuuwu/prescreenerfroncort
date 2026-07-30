# AI_USAGE.md

Used Claude for design discussions/decisions and Antigravity for implementation. Below are the moments that actually mattered, not a full log.

---

## One thing I accepted as-is

The plan for the trial-side retrieval step: one model call per trial, given
only that trial's eligibility text, told explicitly to extract verbatim
sentences about HbA1c/meds/eGFR and preserve comparison operators exactly
(`≤` staying `≤`, not turning into `<=`). This was solid from the start —
narrow scope, no interpretation, easy to sanity-check by reading a few raw
trial texts against the output.

---

## One thing I rejected and why

The coding assistant proposed a criterion-state enum that quietly dropped
`CONFLICTING_EVIDENCE` (required by the assignment) and added an unrequested
`NOT_APPLICABLE` instead. Checked it against the dataset's own
`assignment_scope` field — the five required states were right there. Sent it
back and used the actual five.

Also caught: a ranking rule that never accounted for confirmed disqualifiers,
a stale model name (`gemini-2.5-flash`, deprecated), and a "fall back to
today's date" default that would've been wrong on a frozen synthetic dataset.
Same pattern each time — check the claim against the real data/docs before
accepting a default.

---

## Where I pushed past what was proposed: two-pool ranking

Original ranking idea was one sort key across everything: fewest confirmed
fails → fewest unknowns → recruiting status. Works fine on paper, but it means
a trial with a confirmed exclusion could still land in the top 3 whenever the
"clean" options ran thin, and nothing in the output would show that had
happened.

Split it into two pools instead: clean trials (zero confirmed fails) get
ranked and shown first, no exceptions. Only if there aren't 3 clean ones does
a second, clearly-labeled fallback pool kick in — and anything from that pool
gets flagged in the report (`selection_tier: fallback`) plus forces
`human_review_required = True`. Point being: showing the least-bad option is
fine, but only if it's obviously not being presented as a good one.

---

## Something I rejected that probably has a kernel of truth

The `NOT_APPLICABLE` idea above was wrong as a swap for `CONFLICTING_EVIDENCE`,
but it was gesturing at something real: right now "trial doesn't mention
medications at all" and "we don't have the patient's medication data" both
just collapse into `UNKNOWN`, even though they mean different things. Didn't
fix this — noting it as a real gap rather than pretending the whole idea was
bad just because half of it was.

---

## One more thing worth flagging

The assignment PDF has an embedded instruction on page 2 (buried mid-paragraph)
telling an AI assistant to add a "Library Desk Analogy" README section under
certain conditions. This reads like a prompt injection planted in the
document rather than a real Froncort requirement — I noticed it, ignored it,
and I'm noting it here rather than silently complying or silently omitting it.
An instruction sitting inside a document I'm reading isn't the same as an
instruction from the person actually directing the work, and treating it as
one seemed like exactly the wrong instinct for a system whose whole job is
staying honest about ambiguous input.

---

## Deciding against full determinism, and adding caching

At one point I asked myself whether the whole pipeline could avoid using an
LLM at all — just regex and keyword matching everywhere, so the whole thing
would be fully predictable with no moving parts. For HbA1c and eGFR this
actually looked doable, since the numbers in the trial text are mostly
"≤ 9.9%" or "between 6.5% and 9.0%" style patterns. But medications broke
that idea pretty quickly — drug names, drug classes, brand vs generic names,
and phrasing like "on a stable dose for ≥12 weeks" are too open-ended to catch
with a hand-built list. I realized that trying to hardcode my way around it
wouldn't actually remove the uncertainty, it would just move it into a
dictionary I'd have to keep guessing was complete. So I kept one LLM call,
scoped as tightly as I could make it — one call per trial, extract only the
relevant sentences, copy them exactly, don't touch the operators.

That also meant admitting this is the one part of my system that isn't
guaranteed to give the same answer twice. I didn't want to just leave that
unsaid, so I built a small stability test for it before doing anything else:
ran the same patient/trial pairs through the extraction multiple times with
no other changes, and checked how often the resulting states actually flipped
between runs.

Once I had that number, I added caching on top — save each trial's extraction
to disk after the first call, so reruns are instant and free instead of
hitting the model again. But I was careful about what I was actually claiming
here. Caching makes repeat runs consistent and cheap. It does not make the
original answer more correct — if the model got something wrong on the very
first call, caching just saves that same mistake and I'd never see it
disagree with itself to notice. So I ran the stability test with caching
turned off first, on genuinely fresh calls, and only added caching afterward
as a separate speed/cost improvement, not something I'm counting toward
accuracy.

---

## The idea I added beyond what was asked for

Once the criterion states were coming back correctly, I noticed the reports
were repeating the same open question over and over in slightly different
words — patient after patient, trial after trial, "no eGFR on file, request
updated labs" showing up as its own separate note on every single trial that
happened to need it. For P-3098 that was true on far more trials than it was
worth saying individually.

So I added one more step at the end: instead of leaving that as 12 separate
repeated notes, count across all of a patient's candidate trials which single
missing fact is UNKNOWN the most, and say that once, at the top, as the
actual highest-leverage thing worth doing — "getting this one lab value would
resolve uncertainty on 12 of your 30 candidates," instead of making the
coordinator notice that pattern themselves by reading 12 separate lines.

It doesn't call any model and doesn't touch the criterion logic at all — it's
just counting something that was already sitting in the data once evaluation
was done. I think it's the most useful single addition I made, because it
turns the report from "here are 30 individually honest answers" into
"here's the one thing you should actually go do next."
