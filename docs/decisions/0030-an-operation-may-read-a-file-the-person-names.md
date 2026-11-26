# 0030: An operation may read a file the person names

## Context

Top picks starts from the person's background. Their assistant reads the CV
the person gives it in the conversation, and saves what it read as a reading
(`background.set`); the engine never parses the CV itself. The reading is a
summary. Reading again later, with another assistant, after the person
corrects something, or to check a reading against its source, needs the
original.

Every operation takes JSON, and the `roleband` command makes one flag of each
field. A file's bytes as a flag would have an assistant paste megabytes of
base64 into a command line, and the engine refuses a request body over its
usual bound. A path instead would have the engine open any file a request
names.

## Decision

- An operation that reads a file declares the `file_read` client effect and
  takes the file's name and bytes as fields (`background.add_document`:
  `filename`, `content_base64`). The command reads the file the person names:
  `--file PATH` stands in for those two fields. The client sends one regular,
  non-empty file of at most 10 MiB, refuses a named pipe at once rather than
  waiting on it, and refuses a second `--file` or one whose fields `--input`
  also gives.
- The engine receives bytes, never a path. Such an operation declares its own
  body bound (`max_body_bytes`), and no other operation's bound grows.
- The engine stores the file as it came, unparsed, in the data folder's
  `documents` directory under a name it makes, readable by this account only,
  and records its name, type, size and SHA-256 (`candidate_document`). It
  takes a CV's kinds of file by extension (PDF, Word, OpenDocument, RTF, plain
  text, Markdown). The same bytes given again answer the document already
  stored.
- No operation and no route returns the stored bytes. An assistant reads the
  reading, and the Activity entry names the document by id, not by its name.
- Remove deletes every file in that directory with the readings, the brief and
  the receipts of the writes that saved them (`DELETE /api/picks/setup`).

## Consequences

- The person's CV is on disk beside the database, not in it: a database
  backup does not hold it, and a copy of the data folder does.
  [SECURITY.md](../../SECURITY.md#the-security-model) says where it is kept.
- A write whose transaction rolls back deletes the file it made, and a failed
  write leaves no part of one. Remove clears every file in the folder, whether
  or not a row names it, since the folder is the engine's own.
- A later operation that takes a file uses the same effect, flag and checks.
- `backend/tests/test_cli_file_input.py` holds the client's checks, and
  `backend/tests/test_picks_engine.py` and `test_agent_picks_db.py` hold the
  stored file, its bound and Remove.

## Alternatives considered

- **Keep no original.** Only the confirmed reading is stored, so less of the
  person's data is on disk. Every later reading would need the person to find
  and give the file again, and no reading could be checked against what it was
  read from. Remove takes the original back with everything else.
- **The engine opens a path it is given.** No bytes in the request, but any
  caller that reaches the engine could have it read any file the account can
  read. The command reads the file as the person's own process, and the engine
  takes only the bytes.
