/* The history state of a welcome entry that setup has been entered from:
   coming back to it (setup's first Back, or the browser's) opens the sharing
   question on the answer given, not the intro (Welcome.tsx). Its own module,
   shared by the welcome and the walk's route, so the startup shell does not
   carry it. */

export const SHARING_REVIEW = { sharing: "review" } as const;

/** Whether a history entry's state asks for the sharing question again, read
    as untrusted. */
export function isSharingReview(state: unknown): boolean {
  return (state as { sharing?: unknown } | null)?.sharing === SHARING_REVIEW.sharing;
}
