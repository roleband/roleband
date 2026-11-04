/* The words of the usage-sharing consent, and the record an answer carries
   (docs/architecture.md).

   The screen renders these strings and the record stores the same strings,
   joined: what the user saw and what was agreed to are one value by
   construction, as the walled-company consent does it (followCopy.ts). The
   consent sentences are pinned (src/copy/pinned.en.json), so a change to one
   is deliberate, never a side effect. Resolved at render: nothing here is evaluated at module scope. */

import type { UsageConsent, UsageGroup, UsageState } from "../../api";
import {
  privacyConsentChange,
  privacyConsentIntro,
  privacyConsentIntroData,
  privacyConsentTitle,
  privacyGroupCrashes,
  privacyGroupCrashesDetail,
  privacyGroupQuestions,
  privacyGroupQuestionsDetail,
  privacyGroupUsage,
  privacyGroupUsageDetail,
  privacyNever,
  privacyNeverLabel,
} from "../../copy/gen/privacy";

/** The order every screen lists the groups in. */
export const GROUPS: readonly UsageGroup[] = ["usage", "crashes", "questions"];

export interface GroupWords {
  group: UsageGroup;
  label: string;
  detail: string;
}

export function groupWords(group: UsageGroup): GroupWords {
  switch (group) {
    case "usage":
      return { group, label: privacyGroupUsage(), detail: privacyGroupUsageDetail() };
    case "crashes":
      return { group, label: privacyGroupCrashes(), detail: privacyGroupCrashesDetail() };
    case "questions":
      return { group, label: privacyGroupQuestions(), detail: privacyGroupQuestionsDetail() };
  }
}

/** What is never sent, whatever is shared: a name over the list, as a kind is. */
export interface NeverWords {
  label: string;
  detail: string;
}

export function neverWords(): NeverWords {
  return { label: privacyNeverLabel(), detail: privacyNever() };
}

/** The never-sent promise as the one sentence the record stores. */
export function neverSentence(never: NeverWords): string {
  return `${never.label}: ${never.detail}`;
}

export interface ConsentWords {
  title: string;
  /** The reason to help, one sentence a line. Absent where the screen does not
   *  show it (a Settings switch row). */
  intro?: string[];
  groups: GroupWords[];
  never: NeverWords;
  change?: string;
}

/** What the consent screen shows when it asks about `groups`. */
export function consentWords(groups: readonly UsageGroup[] = GROUPS): ConsentWords {
  return {
    title: privacyConsentTitle(),
    intro: [privacyConsentIntro(), privacyConsentIntroData()],
    groups: GROUPS.filter((group) => groups.includes(group)).map(groupWords),
    never: neverWords(),
    change: privacyConsentChange(),
  };
}

/** The record of `words`: every string shown, in order, one paragraph each.
 *  A paragraph the screen lays out on several lines (the intro, a name over
 *  its sentence) is stored as the one paragraph it reads as, so a change of
 *  layout never changes what was agreed to. */
export function consentText(words: ConsentWords): string {
  return [
    words.title,
    ...(words.intro ? [words.intro.join(" ")] : []),
    ...words.groups.map((group) => `${group.label}: ${group.detail}`),
    neverSentence(words.never),
    ...(words.change ? [words.change] : []),
  ].join("\n\n");
}

/** The language the words were shown in: always English. Consent wording is
 *  never machine translated (AGENTS.md), so every string the record carries is
 *  on `englishOnly` in src/copy/locales.json and shows in English in any
 *  language. */
const consentLocale = (): string => "en";

/** Groups a screen still has to ask about: never answered, or widened since. */
export function groupsToAsk(state: UsageState): UsageGroup[] {
  return state.groups
    .filter((group) => group.status === "undecided" || group.status === "stale")
    .map((group) => group.group);
}

/** The answer that still holds for `groups`: which of them are shared, and
 *  whether that is none, all or some. Null while any of them has no answer
 *  that holds (never answered, or shared before it was widened), since there
 *  is then nothing to keep. */
export function currentAnswer(
  state: UsageState,
  groups: readonly UsageGroup[],
): { answer: "none" | "all" | "some"; shared: Partial<Record<UsageGroup, boolean>> } | null {
  const asked = state.groups.filter((group) => groups.includes(group.group));
  if (asked.length === 0 || asked.some((group) => group.status !== "shared" && group.status !== "declined")) return null;
  const shared = Object.fromEntries(asked.map((group) => [group.group, group.status === "shared"]));
  const count = asked.filter((group) => group.status === "shared").length;
  return { answer: count === 0 ? "none" : count === asked.length ? "all" : "some", shared };
}

/** The PUT body for answering `answers`, with the words shown and the
 *  fingerprints the screen was built from (a stale one is refused with 409). */
export function consentPayload(
  state: UsageState,
  answers: Partial<Record<UsageGroup, boolean>>,
  words: ConsentWords,
): UsageConsent {
  const answered = GROUPS.filter((group) => answers[group] !== undefined);
  const fingerprints: Partial<Record<UsageGroup, string>> = {};
  for (const group of state.groups) {
    if (answered.includes(group.group)) fingerprints[group.group] = group.fingerprint;
  }
  return {
    answers: Object.fromEntries(answered.map((group) => [group, answers[group] === true])),
    text: consentText(words),
    locale: consentLocale(),
    fingerprints,
  };
}
