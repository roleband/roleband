/* The notes editor is a chunk of its own, the heaviest on a role's page, so a
 * posting outside the pipeline never loads it. It is asked for ahead of the
 * first Workspace (when the Pipeline or a role in it opens), and the notes
 * draw it the moment it is here. A `lazy` component would not: React holds a
 * fallback it has shown for a fixed time before replacing it, and for that
 * time the notes would look ready and take no caret and no key. */

type NotesEditorComponent = typeof import("./NotesEditor")["default"];

let here: NotesEditorComponent | null = null;
let onItsWay: Promise<NotesEditorComponent> | null = null;

/** The editor, if its chunk is already here. */
export const notesEditorNow = (): NotesEditorComponent | null => here;

/** Asks for the editor's chunk, once; a load that failed is asked for again
 *  by the next call. */
export function loadNotesEditor(): Promise<NotesEditorComponent> {
  onItsWay ??= import("./NotesEditor").then(
    (chunk) => (here = chunk.default),
    (error: unknown) => {
      onItsWay = null;
      throw error;
    },
  );
  return onItsWay;
}
