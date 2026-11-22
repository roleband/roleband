import { vi } from "vitest";
import { api } from "../api";
import { forgetViewChoices } from "../hooks/viewChoices";

/** The two view-choice routes, kept in memory as the database would keep
 *  them. The page starts fresh: nothing read yet, so the first screen asks. */
export function fakeViewChoiceServer(initial: Record<string, unknown> = {}) {
  let saved: Record<string, unknown> = { ...initial };
  forgetViewChoices();
  const read = vi.spyOn(api, "viewChoices").mockImplementation(async () => ({ choices: saved as never }));
  const save = vi.spyOn(api, "saveViewChoice").mockImplementation(async (name: string, value: unknown) => {
    saved = { ...saved, [name]: value };
    return { name, value: value as never };
  });
  return {
    /** What the database holds now. */
    saved: () => saved,
    /** Replaces what the database holds, as another window would. */
    hold: (choices: Record<string, unknown>) => {
      saved = { ...choices };
    },
    read,
    save,
  };
}
