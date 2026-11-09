# UI POLISH PROMPT — Find the Right Talk (paste this to Claude Code / Codex)

Task: polish the existing UI in `static/index.html`, `static/styles.css`,
`static/app.js` only. Do NOT redesign, do NOT change the colour palette
(green #254e3d, lime #d9edaa, cream #f7f8f4), do NOT add a framework,
images, dark mode, or a new dependency. Small CSS + JS changes only.
Keep every existing feature working. `pytest -q` must still pass, and
the app must still run at http://localhost:8000 with Elasticsearch up.

## 1. Shrink the hero so the product is above the fold (highest priority)

- Halve the hero vertical padding (64px top / 51px bottom -> ~28px / ~20px).
- Reduce the `h1` from 55px to ~40px on desktop, 42px to ~34px on mobile.
- Shrink `.hero-mark` to ~70% size, or hide it below 1000px width.
- Goal after this change: on a 1440x900 laptop screen, "Build my day"
  and the first 1-2 talk cards are visible without scrolling.

## 2. Make talk cards scannable

- Add a bold time chip at the top of each `.talk-card`, e.g. "10:00-10:45 AM",
  dark green background, white text, 11px, semibold.
- Turn the level into a visible pill next to the track tag (same size as
  `.track-tag`, keep the existing track colours).
- Add a speaker avatar: a 32px circle with the speaker's initials
  (e.g. "MC" for Maya Chen), deterministic background colour picked from
  the existing palette by hashing the speaker name, white initials.
  Pure CSS/JS, no images, no new font.
- Highlight the matched search terms in the talk title and description
  with a `<mark>` (lime background #d9edaa), using the current query.

## 3. Make the Elasticsearch proof visible

- The `#source` pill next to the search box must show, in one line:
  "Elasticsearch · {took_ms}ms · {total} results" when source is
  elasticsearch, e.g. "Elasticsearch · 12ms · 7 results".
- Make it 11px, semibold, dark green text on lime background, not the
  current 9px grey pill. When source is `fallback`, keep the amber
  warning style and the word "fallback" visible — never hide it.
- The API already returns `source`, `took_ms`, `total` — use those fields,
  do not hardcode the numbers.

## 4. Make "why this talk" stand out in Build My Day

- In the agenda / built-day timeline, the `.reason` line must be the
  first line under the talk title, 11px, dark green (#254e3d),
  semibold, with a "Why:" prefix, e.g. "Why: matches your interest in
  security, captioned, no clash".
- Increase `.reason` from 9px to 11px and raise its contrast. Do not
  change the reason text itself.

## 5. Make the clash fix a real button

- In the `.conflict` box, the alternative talk must be a proper button,
  not a small text link: full-width, dark green background, white text,
  11px semibold, label "Swap to this instead — {title} · {time}".
- Clicking it must do the swap (remove the clashing talk, add the
  alternative, re-check clashes) and show the updated agenda.
- Keep the amber conflict box styling; only the alternative action
  becomes a primary button.

## Do NOT do

- No redesign, no new palette, no new fonts, no images, no dark mode.
- No new backend endpoint, no new dependency, no change to the API.
- No change to the Build My Day algorithm, search ranking, or clash logic.

## Verify before you finish

1. `pytest -q` passes.
2. App runs, `curl localhost:8000/health` shows elasticsearch up, 28 talks.
3. Check at 1440x900 and at 390px wide (mobile): Build My Day visible
   without scrolling on desktop, agenda readable on mobile, no horizontal
   overflow, no text clipped in the time chip / reason / swap button.
4. Search "maya", build a day for "kubernetes, security, beginner",
   add two clashing talks and use "Swap to this instead" — all three
   flows work and the source pill shows real Elasticsearch ms.
