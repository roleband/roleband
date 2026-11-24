/* The notes editor is a chunk of its own, the heaviest on a role's page, so a
 * posting outside the pipeline never loads it. It is asked for ahead of the
 * first Workspace (when the Pipeline or a role in it opens), and the notes
 * draw it the moment it is here. A `lazy` component would not: React holds a
 * fallback it has shown for a fixed time before replacing it, and for that
 * time the notes would look ready and take no caret and no key. */

type NotesEditorComponent = typeof import("./NotesEditor")["default"];

/** One chunk, asked for at most once at a time. A load that failed is
 *  forgotten, so the next call asks again: an early ask that met a dropped
 *  connection does not leave the Workspace without its editor. */
export function chunkOnce<T>(importer: () => Promise<T>) {
  let here: T | null = null;
  let onItsWay: Promise<T> | null = null;
  return {
    /** What was loaded, if it is already here. */
    now: (): T | null => here,
    load: (): Promise<T> => {
      onItsWay ??= importer().then(
        (loaded) => (here = loaded),
        (error: unknown) => {
          onItsWay = null;
          throw error;
        },
      );
      return onItsWay;
    },
  };
}

const editor = chunkOnce<NotesEditorComponent>(() => import("./NotesEditor").then((chunk) => chunk.default));

/** The editor, if its chunk is already here. */
export const notesEditorNow = editor.now;

/** Asks for the editor's chunk. */
export const loadNotesEditor = editor.load;
