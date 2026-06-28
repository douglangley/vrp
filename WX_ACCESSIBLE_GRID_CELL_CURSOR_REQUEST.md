# wx-accessible-grid — request: restore the Left/Right cell cursor on the DataViewListCtrl backend

> **Filed upstream 2026-06-27 as [Community-Access/wx-accessible-grid#2](https://github.com/Community-Access/wx-accessible-grid/issues/2).**
> This file is the source text; track status on the issue.

**To:** maintainer(s) of [Community-Access/wx-accessible-grid](https://github.com/Community-Access/wx-accessible-grid)
**From:** Versatile Radio Programmer (VRP), an accessible desktop radio
programmer (wxPython + CHIRP). Primary user is **blind, NVDA on Windows**;
VoiceOver on macOS secondary.
**Re:** 0.7.0 (commit `f8f44ad8bfa8c5d5700929c827ba6332ed52fd73`)

> First — thank you. The move to a native backend, and specifically the
> **0.7.0 rebase onto `DataViewListCtrl`**, fixed the VoiceOver-silence problem we
> reported earlier (the report-mode `wx.ListCtrl` exposed nothing to
> NSAccessibility). On macOS, VoiceOver now reads the table and each cell by
> column for free. This is exactly the right backend.

## The ask

Please **bring back the app-level Left/Right cell cursor that 0.6.0 added, on top
of the 0.7.0 `DataViewListCtrl` backend.** Right now they are mutually exclusive
across the version history, and neither version satisfies a blind NVDA user *and*
a VoiceOver user at once:

| Version | Backend | App Left/Right cell cursor (NVDA hears it) | VoiceOver reads cells (macOS) |
|---|---|---|---|
| 0.6.1 | virtual `wx.ListCtrl` | ✅ via the `announce` callback | ❌ **silent under VoiceOver** |
| 0.7.0 | `DataViewListCtrl` | ❌ **removed** | ✅ native |

We believe these are **composable**, not in conflict — see "Why it composes"
below.

## What 0.7.0 removed (for reference)

The `0.6.0` "native left/right cell cursor" commit added, and `0.6.1` kept:

- an `EVT_KEY_DOWN` handler (`_on_key_down`) that, on plain `Left`/`Right` with no
  modifiers, moved a `self._current_col` cursor via `clamp_column(...)`;
- `_speak_current_cell()`, which voiced the moved-to cell as
  `"<value>, <column label>"` through an **`announce` callback the host passes
  in** (wired to the app's own speech path; if omitted, the cursor still moves but
  says nothing);
- public `current_column()` and `current_cell() -> (row, column_index)` so the
  host can wire a per-cell action (e.g. "edit just this column").

The `0.7.0` rebase diff deletes all of the above (`_on_key_down`,
`current_column`, `current_cell`, `_speak_current_cell`, the `announce`
parameter, the `EVT_KEY_DOWN` bind, the `clamp_column` import).

## Why it composes cleanly with DataViewListCtrl

The cursor **synthesizes its own speech via the host `announce` callback**, so it
does **not** depend on the native control exposing a per-cell focus/cursor to the
platform a11y API. That is the key property:

- On **Windows/NVDA**, `wxDataViewCtrl` is wx's *generic* (custom-drawn) control,
  and NVDA does not announce a per-cell cursor as you arrow within a row. The
  0.6.0-style cursor fills exactly that gap: the host speaks `"<value>,
  <column>"` itself, so NVDA users get cell-by-cell reading the control can't
  give them.
- On **macOS/VoiceOver**, VoiceOver does its own cell reading with **VO + Left/
  Right**, which is a *different key channel* from the app's plain `Left`/`Right`.
  So the two don't fight. To avoid double-speech, keep the `announce` callback
  **optional** (as 0.6.0 did) — the host can choose to wire it only where the
  control doesn't read cells natively (e.g. Windows), and leave it unwired on
  macOS so VoiceOver stays the single voice.

A clean shape might be:

- `AccessibleGrid(parent, model, label, announce=None)` — when `announce` is
  given, bind `EVT_KEY_DOWN` on the `DataViewListCtrl`, track `_current_col`,
  consume unmodified `Left`/`Right`, clamp to the column range, and call
  `announce("<value>, <column label>")`. When `announce is None`, behave exactly
  like 0.7.0 today (no cursor, no key binding) so nothing regresses for current
  users.
- Re-expose `current_column()` / `current_cell()` so the host can target a
  per-cell edit from the cursor position.

That keeps 0.7.0's VoiceOver-correct default untouched and makes the NVDA
cell-cursor strictly opt-in.

## Why this matters to us

Our primary user is blind and uses **NVDA on Windows**. Cell-by-cell navigation
of the channel table (and a contextual per-cell edit — "F2: edit frequency",
"F2: change CTCSS") is core to the editing UX. On 0.7.0 today, NVDA gets
**row-level reading only**; the 0.6.x cursor that would have served them was
removed. We'd rather wire your `announce` callback to our existing speech path
than reimplement the cursor downstream and drift from the library.

(If a downstream cursor on top of your `DataViewListCtrl` — via `grid.control`
and our own key handler — is the answer you'd prefer instead, tell us and we'll
do that; we just wanted to ask before forking behavior you've already written
once.)

## Environment

- wxPython **4.2.5** (msw, Phoenix), wxWidgets **3.2.9**, Python **3.11**,
  Windows 11; macOS/VoiceOver secondary.
- wx-accessible-grid **0.7.0** (commit `f8f44ad`), wx-accessible-webview,
  wx-accessible-menubar, prismatoid (speech).
