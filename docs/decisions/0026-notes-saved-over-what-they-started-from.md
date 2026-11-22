# 0026: Notes are saved over the text they started from

## Context

A role's notes are one Markdown text that the person writes on the role's page
and their assistant writes through the CLI. The page saves at every pause in
typing. Each save was last-writer-wins: a page open while the assistant added a
line wrote over that line without a word. Each save was also one
`pursuit_events` row holding the whole text before and after it, so an hour of
writing was dozens of History entries and dozens of copies of the notes, and
none of those copies could be put back from the app.

## Decision

- The page's notes save sends `notes_was`, the server's text it started from
  ("" for none). Under the role's write lock the server compares it with the
  stored notes and, when they differ, refuses with `notes-moved` and the notes as
  they are. The page then puts the two together line by line: a stretch one side
  changed takes that side's lines, a stretch both changed keeps both, the page's
  first. It saves the result over the text it was given and says that both
  versions were kept. A write that sends no `notes_was`, every agent write among
  them, is last-writer-wins as before; agents already write against the
  pursuit's revision.
- A writing session is the person's own notes saves from the page, each within
  ten minutes of the one before, with no other write to the role between them.
  Its first save's event keeps the text it replaced and the text it wrote; the
  saves after it name the session (`detail.session`) and keep no copy of the
  notes. History lists a session once, at its last save. Every save is still a
  write: it moves the revision and appends its event.
- An agent's write is never part of a session: its event keeps both versions,
  so the person can correct it from the record.
- The notes' earlier versions are what each session left: the text the next
  session replaced. `GET /api/applications/{job_id}/notes/versions` lists them
  newest first, leaving out the notes as they are. The page puts one back as an
  edit of its own, saved like any other and undone by the editor's undo.

## Consequences

- Events stay append-only; nothing rewrites an earlier event to fold a session.
- The text a session wrote between its first and last save is not kept. A
  version is what the person left, not each pause.
- Events written before this change keep both copies; each reads as a session
  of its own, and the versions read from them the same way.
- The agents' change feed reads no notes copies, so it is unchanged.

## Alternatives considered

- **Refuse a stale save and ask the person to choose.** The page saves at every
  pause, so the question would interrupt typing; keeping both loses nothing and
  asks nothing.
- **Fold a session by updating its first event.** The event log is append-only,
  and readers that have passed an event would not see it change.
- **A separate table of note versions.** A second record of the same writes,
  which every writer would have to keep in step with the events.
