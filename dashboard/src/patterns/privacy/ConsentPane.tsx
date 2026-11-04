import { useEffect, useId, useRef, useState } from "react";
import type { Ref } from "react";
import { api } from "../../api";
import type { UsageGroup, UsageState } from "../../api";
import { errorText } from "../../api/errorText";
import { Button, Icon, type IconName } from "../../ui";
import {
  privacyChoose,
  privacyConsentCurrent,
  privacyHappyToHelp,
  privacyKeepAnswer,
  privacyNoThanks,
  privacySaveError,
} from "../../copy/gen/privacy";
import { consentPayload, consentWords, currentAnswer } from "./consentCopy";
import "./privacy.css";

/* The usage-sharing question (docs/architecture.md), asked the way
   consent is asked where it has to hold up: a reason to help, what each kind
   covers, what is never sent, and two answers side by side.

   "Happy to help" shares every kind listed, in one click; "No thanks" shares
   none. Nothing is pre-ticked, because a ticked box is not a consent (CJEU
   Planet49): a person who wants only some kinds opens "Let me choose",
   which shows one clear box per kind, and "Happy to help" then shares exactly
   the ticked ones (nothing ticked, nothing to share: it waits). Asked about a
   single kind (one widened since it was shared) there is nothing to choose.
   The safe answer is the one the caller focuses (`safeRef`): Enter on a screen
   that just opened never shares.

   Used by the welcome walk (a phase before the first step) and by the dialog
   that asks an existing install once. Settings has its own switches.

   Asked again (`review`: the welcome walk's way back to the question), it says
   what the person answered and opens on that answer: their own earlier ticks,
   never a default, so the boxes show only when they chose some kinds. "Keep my
   answer" moves on and records nothing; either answer records anew. Keep is
   offered only when every kind asked has an answer that still holds, and only
   while the boxes show that answer: once a tick changes, what the screen shows
   is a new answer, which only No thanks or Happy to help records, so neither
   Keep nor the sentence about the earlier answer stays beside it.

   The welcome asks it in its own scene (`look="scene"`): each kind under an
   icon of its own, the never-sent promise in full ink with its own mark, the
   two answers larger. Only the look changes; the words, and so the record,
   are the dialog's. A box takes the icon's place once someone chooses. */

const GROUP_ICON: Record<UsageGroup, IconName> = { usage: "chart", crashes: "alertCircle", questions: "help" };

export function ConsentPane({
  state,
  groups,
  onAnswered,
  safeRef,
  look = "plain",
  review = false,
}: {
  state: UsageState;
  /** The groups this screen asks about; the record names only these. */
  groups: UsageGroup[];
  onAnswered: (next: UsageState) => void;
  safeRef?: Ref<HTMLButtonElement>;
  look?: "plain" | "scene";
  /** Asked again after an answer: the answer shows, and can be kept. */
  review?: boolean;
}) {
  const scene = look === "scene";
  const titleId = useId();
  const introId = useId();
  const words = consentWords(groups);
  const single = words.groups.length === 1;
  const held = review ? currentAnswer(state, groups) : null;
  const [choosing, setChoosing] = useState(held?.answer === "some");
  const [chosen, setChosen] = useState<Partial<Record<UsageGroup, boolean>>>(() => held?.shared ?? {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picked = words.groups.some((group) => chosen[group.group] === true);
  const kept = held && words.groups.every((group) => (chosen[group.group] === true) === (held.shared[group.group] === true))
    ? held
    : null;
  // The link that opened the boxes is gone: keep the keyboard where it was going.
  // Boxes open from the start (asked again) leave focus to the safe answer.
  const firstBox = useRef<HTMLInputElement>(null);
  const openedByLink = useRef(false);
  useEffect(() => {
    if (choosing && openedByLink.current) firstBox.current?.focus();
  }, [choosing]);

  const answer = async (share: (group: UsageGroup) => boolean) => {
    setSaving(true);
    setError(null);
    const answers = Object.fromEntries(groups.map((group) => [group, share(group)]));
    try {
      onAnswered(await api.saveUsageConsent(consentPayload(state, answers, words)));
    } catch (caught) {
      setError(errorText(caught, privacySaveError()));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className={scene ? "privacy-consent privacy-consent--scene" : "privacy-consent"}
      aria-labelledby={titleId}
      aria-describedby={introId}
    >
      <header className="privacy-consent-head">
        <h2 id={titleId} className="privacy-consent-title">{words.title}</h2>
        <p id={introId} className="privacy-consent-intro">{words.intro}</p>
      </header>

      <div className="privacy-consent-groups" role="group" aria-labelledby={titleId}>
        {words.groups.map((group, index) =>
          choosing ? (
            <label key={group.group} className="privacy-consent-choice">
              <input
                ref={index === 0 ? firstBox : undefined}
                type="checkbox"
                checked={chosen[group.group] === true}
                disabled={saving}
                onChange={(event) => setChosen((now) => ({ ...now, [group.group]: event.target.checked }))}
              />
              <span className="privacy-consent-group-label">{group.label}</span>
              <span className="privacy-consent-group-detail">{group.detail}</span>
            </label>
          ) : (
            <div key={group.group} className="privacy-consent-choice">
              {scene && <span className="privacy-consent-icon"><Icon name={GROUP_ICON[group.group]} /></span>}
              <span className="privacy-consent-group-label">{group.label}</span>
              <span className="privacy-consent-group-detail">{group.detail}</span>
            </div>
          ),
        )}
      </div>

      <div className="privacy-consent-notes">
        <p className="privacy-consent-never">
          {scene && <span className="privacy-consent-icon"><Icon name="eyeOff" /></span>}
          {words.never}
        </p>
        {kept && <p className="privacy-consent-current">{privacyConsentCurrent({ answer: kept.answer })}</p>}
        <p>{words.change}</p>
        {!single && !choosing && (
          <Button variant="link" onClick={() => { openedByLink.current = true; setChoosing(true); }} disabled={saving}>
            {privacyChoose()}
          </Button>
        )}
      </div>
      {error && <p className="privacy-consent-error" role="alert">{error}</p>}

      <div className="privacy-consent-actions">
        <Button
          ref={safeRef}
          size={scene ? "lg" : undefined}
          className={scene ? "ui-btn-strong" : undefined}
          onClick={() => void answer(() => false)}
          disabled={saving}
        >
          {privacyNoThanks()}
        </Button>
        <Button
          size={scene ? "lg" : undefined}
          className={scene ? "ui-btn-strong" : undefined}
          onClick={() => void answer(choosing ? (group) => chosen[group] === true : () => true)}
          disabled={saving || (choosing && !picked)}
        >
          {privacyHappyToHelp()}
        </Button>
        {kept && (
          <Button
            variant="ghost"
            size={scene ? "lg" : undefined}
            className="privacy-consent-keep"
            onClick={() => onAnswered(state)}
            disabled={saving}
          >
            {privacyKeepAnswer()}
          </Button>
        )}
      </div>
    </section>
  );
}
