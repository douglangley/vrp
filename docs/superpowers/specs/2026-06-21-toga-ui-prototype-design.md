# Toga UI Prototype Design

Date: 2026-06-21
Branch: codex/toga-ui

## Goal

Build a parallel BeeWare Toga prototype for VRP without removing or weakening
the existing wxPython application. The prototype should prove that a native
Toga UI can preserve the screen-reader-first behavior that VRP currently gets
from wxPython, `AccessibleWebView`, `wx-accessible-menubar`, and related
accessibility work.

The first prototype uses a native `toga.Table` for the memory-channel list.
This is an intentional experiment: if `toga.Table` does not provide acceptable
screen-reader behavior on the target desktop platforms, that result is a valid
prototype outcome and should be documented before widening the port.

## Non-Goals

- Do not delete or replace `main.py`, `vrp/app.py`, or the wxPython app.
- Do not edit `./chirp`; it remains an unmodified, pinned dependency.
- Do not port every dialog in the first slice.
- Do not ship the Toga app as the default launcher until screen-reader behavior
  is verified against the acceptance criteria below.

## Architecture

Add a new package, `vrp_toga/`, plus a separate launcher such as
`main_toga.py`. The existing wx app remains the production path.

The Toga prototype reuses:

- `chirp_backend.radio` for image load/save, model listing, serial entry points,
  and memory access.
- `chirp_backend.memory_ops`, `bank_ops`, and `query` for backend behavior as
  features are ported.
- `chirp_backend.col_defs.build_column_defs()` for the channel table schema.
- `vrp.config` for shared preferences where those preferences are UI-neutral.
- `vrp.speech.Speaker` if supplemental speech still works outside wx.

The Toga prototype owns:

- App/window construction, commands, menus, shortcuts, and status presentation.
- The `toga.Table` data adapter for current-page memory rows.
- Toga-native dialogs as each workflow is ported.
- A small accessibility verification harness or checklist describing what must
  be checked manually with screen readers.

## First Usable Slice

The first implementation should deliver a usable read/navigation workflow:

1. Launch the Toga prototype with `uv run python main_toga.py`.
2. Show an accessible welcome screen with the VRP purpose and required CHIRP
   attribution.
3. Open a CHIRP image file through a Toga file dialog.
4. Populate a native `toga.Table` with one page of memory channels.
5. Preserve the current page size behavior, including previous/next page
   commands and status messages that identify the visible channel range.
6. Save and Save As through the existing backend.
7. Provide commands and shortcuts for Open, Save, Save As, Previous Page,
   Next Page, Find, Edit Channel, and Keyboard Shortcuts, even where some
   commands initially report that the workflow is not ported yet.
8. Keep the wx app runnable and keep existing tests passing.

Editing can start with a selected-row Edit command that opens a simple
Toga-native dialog for the highest-value fields once the table navigation
behavior is proven. Bulk operations, serial download/upload, settings, banks,
and query sources should follow as separate slices.

## Table Model

The table adapter should build rows from `radio_backend.get_memory()` and the
same column definitions used by the wx view. Each row should include:

- Channel number.
- Empty-state text such as `(empty)`, not color-only state.
- The visible CHIRP-backed fields used in the existing channel grid.
- A stable hidden channel number in dictionary row data for command handlers,
  even if that value is not displayed as a separate column.

The prototype should page data instead of loading every memory at once. Large
radios can have thousands of channels, and the wx version already discovered
that loading everything hurts screen-reader performance.

## Commands And Keyboard

Use `toga.Command` for application commands so menus, toolbar exposure, and
shortcuts come from Toga's command system. The initial command map should mirror
the existing VRP names and shortcuts. If a specific shortcut is not accepted by
Toga on a platform, keep the command available through menus/buttons and record
the shortcut gap in the prototype notes.

- Open Image File
- Open Recent
- Save
- Save As
- Close Image
- Previous Channel Page
- Next Channel Page
- Edit Channel
- Find
- Find Next
- Organize Channels
- Keyboard Shortcuts

Single-letter table shortcuts remain forbidden because they conflict with
screen-reader browse/navigation modes. Commands that require a loaded radio
must be disabled or announce a clear unavailable-state message.

## Accessibility Requirements

The wxPython version is the behavioral accessibility spec. The Toga prototype
must preserve these rules:

- Every control has a clear accessible name.
- The channel list communicates headers, row position, selected channel, and
  empty channels to screen readers.
- No workflow requires drag and drop.
- Operation results, errors, page changes, and loading states are announced.
- Dialogs trap focus, support Escape where appropriate, and return focus to the
  invoking control or selected table row.
- Color is never the only state indicator.
- Keyboard access reaches every command that mouse users can reach.
- The required CHIRP attribution remains visible in every top-level screen.

Because Toga does not document a VRP-equivalent accessibility wrapper, manual
screen-reader verification is part of the prototype rather than a polish task.
If `toga.Table` cannot meet the row/header/focus expectations with NVDA on
Windows, the prototype should record the limitation and consider a fallback
table presentation in a later design.

## Error Handling

All backend operations should return user-facing status text through one Toga
status path. Errors should be announced and should not leave the UI in a stale
state. Long-running radio operations are out of scope for the first slice; when
ported, they must remain off the UI thread and report progress.

## Testing And Verification

Automated tests:

- Keep `uv run --extra dev python -m pytest` green for existing backend and wx
  view behavior.
- Add pure tests for the Toga table-row adapter: loaded radio rows, empty
  channel text, page math, and command enabled-state decisions.
- Avoid GUI-only tests for the first slice unless Toga's test backend is simple
  to add without destabilizing setup.

Manual screen-reader verification:

- NVDA on Windows reads the main window title, commands, table headers, selected
  row, selected cell/row values, empty-channel text, and status changes.
- Keyboard-only users can open an image, navigate pages, select rows, invoke
  commands, and return from dialogs without losing context.
- The wx app still launches separately after the Toga prototype is added.

## Documentation Sources

Toga documentation checked on 2026-06-21:

- https://toga.beeware.org/en/stable/
- https://toga.beeware.org/en/stable/reference/api/application/command/
- https://toga.beeware.org/en/stable/reference/api/widgets/table/
- https://toga.beeware.org/en/stable/reference/api/widgets/webview/
