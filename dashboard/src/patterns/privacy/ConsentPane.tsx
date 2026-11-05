import { Fragment, useEffect, useId, useRef, useState } from "react";
import type { Ref } from "react";
import { api } from "../../api";
import type { UsageGroup, UsageState } from "../../api";
import { errorText } from "../../api/errorText";
import { Button, Icon, type IconName } from "../../ui";
import {
  privacyChoose,
  privacyHappyToHelp,
  privacyNoThanks,
  privacySaveError,
  privacyYourAnswer,
} from "../../copy/gen/privacy";
import { consentPayload, consentWords, currentAnswer, neverSentence } from "./consentCopy";
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

   Asked again (`review`: the welcome walk's way back to the question), it
   opens on the answer given: their own earlier ticks, never a default, so the
   boxes show only when they chose some kinds, and the button of that answer is
   marked "Your answer". Pressing it moves on and records nothing; the other
   answer records anew. The mark shows only when every kind asked has an
   answer that still holds, and only while the boxes show that answer: once a
   tick changes, what the screen shows is a new answer, which Happy to help
   records. A marked answer takes the keyboard in place of the safe one, since
   Enter on it changes nothing.

   The welcome asks it in its own scene (`look="scene"`): each kind under an
   icon of its own, the never-sent promise as one more row of the same shape
   below a rule, the way to change it and to choose in quiet type, the two
   answers larger. Only the look changes; the words, and so the record, are
   the dialog's. A box takes the icon's place once someone chooses. */

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
  /** Asked again after an answer: the answer is marked, and can be kept. */
  review?: boolean;
}) {
  const scene = look === "scene";
  const titleId = useId();
  const introId = useId();
  const yoursId = useId();
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
  const yours = kept ? (kept.answer === "none" ? "no" : "yes") : null;
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

  // The button of the answer given is current (`aria-current`) and keeps that answer; its
  // caption is its description, so its name stays the answer's own. The
  // keyboard starts on it, or on No thanks when there is none.
  const answerButton = (which: "no" | "yes", label: string, record: () => void, disabled: boolean) => {
    const given = which === yours;
    return (
      <Button
        ref={(yours ?? "no") === which ? safeRef : undefined}
        size={scene ? "lg" : undefined}
        className={scene ? "ui-btn-strong" : undefined}
        aria-current={given || undefined}
        aria-describedby={given ? yoursId : undefined}
        onClick={given ? () => onAnswered(state) : record}
        disabled={disabled}
      >
        {label}
        {given && (
          <span id={yoursId} className="privacy-consent-yours-mark" aria-hidden="true">
            <Icon name="check" size={14} />
            {privacyYourAnswer()}
          </span>
        )}
      </Button>
    );
  };
  const never = scene ? (
    <div className="privacy-consent-choice privacy-consent-never">
      <span className="privacy-consent-icon"><Icon name="eyeOff" /></span>
      <span className="privacy-consent-group-label">{words.never.label}</span>
      <span className="privacy-consent-group-detail">{words.never.detail}</span>
    </div>
  ) : (
    <p className="privacy-consent-never">{neverSentence(words.never)}</p>
  );

  return (
    <section
      className={scene ? "privacy-consent privacy-consent--scene" : "privacy-consent"}
      aria-labelledby={titleId}
      aria-describedby={introId}
    >
      <header className="privacy-consent-head">
        <h2 id={titleId} className="privacy-consent-title">{words.title}</h2>
        <p id={introId} className="privacy-consent-intro">
          {words.intro?.map((line, index) => (
            <Fragment key={index}>
              {index > 0 && " "}
              <span className="privacy-consent-intro-line">{line}</span>
            </Fragment>
          ))}
        </p>
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
        {never}
        <p className="privacy-consent-change">
          {words.change}
          {!single && !choosing && (
            <>
              {" "}
              <Button variant="link" onClick={() => { openedByLink.current = true; setChoosing(true); }} disabled={saving}>
                {privacyChoose()}
              </Button>
            </>
          )}
        </p>
      </div>
      {error && <p className="privacy-consent-error" role="alert">{error}</p>}

      <div className="privacy-consent-actions">
        {answerButton("no", privacyNoThanks(), () => void answer(() => false), saving)}
        {answerButton(
          "yes",
          privacyHappyToHelp(),
          () => void answer(choosing ? (group) => chosen[group] === true : () => true),
          saving || (choosing && !picked),
        )}
      </div>
    </section>
  );
}
