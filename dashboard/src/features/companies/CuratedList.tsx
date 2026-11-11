import { wordsLanguage } from "../../copy/runtime";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { Button, Dialog, Icon, Switch, type IconName } from "../../ui";
import { useCompanies } from "./CompaniesData";
import { followCopy, type ConsentFact, type FollowCopy } from "./followCopy";
// The dialog form these confirmations wear (`.ledger-form`, `.ledger-confirm`)
// belongs to the register material; setup asks them without Settings' chunk.
import "../../design/materials/register-material.css";
import {
  companiesCuratedListConfirm,
} from "../../copy/gen/companies";

/* The follow confirmations.
 *
 * Every bulk follow asks first (the toolbar's Follow all, a sector's Follow
 * all, the set of other companies), because it changes what the radar holds
 * and how long each scan takes. There is no follow switch under the sector
 * index: it would read as a promise of companies not on screen, while the
 * toolbar action says plainly that it follows the ones that are.
 */

/** A settings path ("Settings › Followed companies"), a hyphenated word, or a
 *  short word that opens a sentence with the word after it ("By following"). */
const UNBROKEN = /[^\s›]+ › [^.,;。，]+|\p{L}+(?:-\p{L}+)+|(?<=[.?!] )\p{L}{1,3} \p{L}+/gu;

/** The paragraph's own text, with each UNBROKEN run kept on one line. The words
 *  are unchanged: they are the consent the server stores. */
function keepTogether(line: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let at = 0;
  for (const match of line.matchAll(UNBROKEN)) {
    if (match.index > at) parts.push(line.slice(at, match.index));
    parts.push(<span key={match.index} className="ledger-confirm-unbroken">{match[0]}</span>);
    at = match.index + match[0].length;
  }
  if (at < line.length) parts.push(line.slice(at));
  return parts;
}

const FACT_ICON = { walled: "shield", directed: "pointer" } as const satisfies Record<ConsentFact["site"], IconName>;

/** A confirmation's body, one zone per kind of word: what the answer brings,
 *  what following agrees to, the Keep scanning switch when the answer covers
 *  companies scanned only at the user's direction, and a quiet note above the
 *  two answers. Every sentence is a paragraph in the order `shownSentences`
 *  records it. The safe answer carries `safeRef`, so its dialog can focus it. */
export function ConfirmBody({
  copy,
  keepScanning,
  onKeepScanning,
  safeRef,
  onSafe,
  onAct,
  busy = false,
}: {
  copy: FollowCopy;
  keepScanning: boolean;
  onKeepScanning: (keep: boolean) => void;
  safeRef: RefObject<HTMLButtonElement | null>;
  onSafe: () => void;
  onAct: () => void;
  /** The answer's request is in flight: a second press would send it twice. */
  busy?: boolean;
}) {
  return (
    <div className="ledger-form ledger-confirm ledger-follow">
      <h3>{copy.title}</h3>
      {copy.paragraphs.map((line) => <p key={line}>{keepTogether(line)}</p>)}
      {copy.consent && (
        <div className="ledger-confirm-zone ledger-confirm-consent">
          {copy.consent.facts.map((fact) => (
            <p key={fact.site} className="ledger-confirm-fact">
              <Icon name={FACT_ICON[fact.site]} />
              {keepTogether(fact.text)}
            </p>
          ))}
          <p className="ledger-confirm-agree">{keepTogether(copy.consent.choice)}</p>
        </div>
      )}
      {copy.keepScanning && (
        <Switch className="ledger-confirm-zone ledger-confirm-switch" checked={keepScanning} onChange={onKeepScanning}>
          {copy.keepScanning}
        </Switch>
      )}
      {copy.note && <p className="ledger-confirm-zone ledger-confirm-note">{keepTogether(copy.note)}</p>}
      <div className="ledger-form-actions">
        <Button ref={safeRef} onClick={onSafe}>
          {copy.safe}
        </Button>
        <Button variant="primary" onClick={onAct} disabled={busy}>
          {copy.act}
        </Button>
      </div>
    </div>
  );
}

export function FollowConfirmDialog({
  onAnswered,
}: {
  /** Told which way the reader answered, after the write is asked for: first-run
   *  setup goes on only once a follow it asked for is confirmed. */
  onAnswered?: (followed: boolean) => void;
} = {}) {
  const { confirmation, confirmFollow, dismissFollow } = useCompanies();
  const dismiss = () => {
    dismissFollow();
    onAnswered?.(false);
  };
  const pending = confirmation;
  const safeRef = useRef<HTMLButtonElement>(null);
  // Ticked for every new question: regular scans are the default answer.
  const [keepScanning, setKeepScanning] = useState(true);

  // The safe answer takes focus: Enter on a dialog that just opened must never
  // follow seventy companies — or consent to a wall. A child's effect runs
  // before the Overlay's, which keeps focus it finds already inside.
  useEffect(() => {
    setKeepScanning(true);
    if (pending) safeRef.current?.focus();
  }, [pending]);

  // Rendered from the same words the consent records (followCopy.ts).
  const copy = pending ? followCopy(pending) : null;
  const shownLocale = wordsLanguage();

  return (
    <Dialog
      isOpen={pending !== null}
      onClose={dismiss}
      label={copy?.title ?? companiesCuratedListConfirm()}
      width={440}
      closeOnScrim={false}
      className="app-overlay"
    >
      {copy && (
        <ConfirmBody
          copy={copy}
          keepScanning={keepScanning}
          onKeepScanning={setKeepScanning}
          safeRef={safeRef}
          onSafe={dismiss}
          onAct={() => {
            confirmFollow({ copy, locale: shownLocale, keepScanning });
            onAnswered?.(true);
          }}
        />
      )}
    </Dialog>
  );
}
