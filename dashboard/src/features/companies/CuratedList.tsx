import { wordsLanguage } from "../../copy/runtime";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import type { CompanyDiscoveryCompany } from "../../api";
import { Button, Dialog, Icon, SearchField, Switch, type IconName } from "../../ui";
import { useCompanies } from "./CompaniesData";
import { followCopy, type ConsentFact, type FollowCopy } from "./followCopy";
// The dialog form these confirmations wear (`.ledger-form`, `.ledger-confirm`)
// belongs to the register material; setup asks them without Settings' chunk.
import "../../design/materials/register-material.css";
import "./CuratedList.css";
import {
  companiesCuratedListConfirm,
  companiesFollowCopyCompaniesToUnfollow,
  companiesFollowCopyCountToUnfollow,
  companiesFollowCopyFindACompany,
  companiesFollowCopyKeepFollowingCount,
  companiesFollowCopySelectAll,
  companiesFollowCopyUnfollow,
  companiesFollowCopyWhichToUnfollow,
  companiesSetupBack,
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
  onChoose,
  busy = false,
}: {
  copy: FollowCopy;
  keepScanning: boolean;
  onKeepScanning: (keep: boolean) => void;
  safeRef: RefObject<HTMLButtonElement | null>;
  onSafe: () => void;
  onAct: () => void;
  /** Opens the step that picks companies one by one (`copy.choose`). */
  onChoose?: () => void;
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
      {copy.choose && onChoose && (
        <p className="ledger-confirm-zone ledger-confirm-note">
          <Button variant="link" onClick={onChoose}>{copy.choose}</Button>
        </p>
      )}
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

/** "Let me choose": the same question, answered company by company. Only the
 *  task is on screen: which companies to unfollow. The agreement and the Keep
 *  scanning choice were read on the step before, and the answer records them
 *  in that step's words. Back takes focus, as the safe answer does there. */
function ChooseStep({
  companies,
  ticked,
  onTicked,
  backRef,
  onBack,
  onAct,
}: {
  /** In name order, fixed when the question was asked. */
  companies: CompanyDiscoveryCompany[];
  ticked: ReadonlySet<string>;
  onTicked: (ticked: Set<string>) => void;
  backRef: RefObject<HTMLButtonElement | null>;
  onBack: () => void;
  onAct: () => void;
}) {
  const [query, setQuery] = useState("");
  const needle = query.trim().toLocaleLowerCase();
  const shown = needle
    ? companies.filter((company) =>
        company.display.toLocaleLowerCase().includes(needle)
        || company.aliases.some((alias) => alias.toLocaleLowerCase().includes(needle)))
    : companies;
  const allShown = shown.length > 0 && shown.every((company) => ticked.has(company.slug));
  const total = companies.length;
  const count = ticked.size;

  const tick = (slug: string, on: boolean) => {
    const next = new Set(ticked);
    if (on) next.add(slug);
    else next.delete(slug);
    onTicked(next);
  };
  // Acts on the rows a search leaves, so a search then Select all ticks
  // exactly what is on screen.
  const tickShown = () => {
    const next = new Set(ticked);
    for (const company of shown) {
      if (allShown) next.delete(company.slug);
      else next.add(company.slug);
    }
    onTicked(next);
  };

  return (
    <div className="ledger-form ledger-confirm ledger-follow ledger-choose">
      <h3>{companiesFollowCopyWhichToUnfollow()}</h3>
      <div className="ledger-choose-tools">
        <SearchField
          className="ledger-choose-search"
          label={companiesFollowCopyFindACompany()}
          placeholder={companiesFollowCopyFindACompany()}
          value={query}
          onChange={setQuery}
        />
        <Button variant="link" onClick={tickShown} disabled={shown.length === 0}>
          {companiesFollowCopySelectAll({ state: allShown ? "all" : "some" })}
        </Button>
      </div>
      <div className="ledger-choose-list" role="group" aria-label={companiesFollowCopyCompaniesToUnfollow()}>
        {shown.map((company) => (
          <label key={company.slug} className="ledger-choose-row">
            <input
              type="checkbox"
              checked={ticked.has(company.slug)}
              onChange={(event) => tick(company.slug, event.target.checked)}
            />
            <span>{company.display}</span>
          </label>
        ))}
      </div>
      <div className="ledger-form-actions">
        {count > 0 && (
          <p className="ledger-choose-count is-leading" role="status">
            {companiesFollowCopyCountToUnfollow({ count })}
          </p>
        )}
        <Button ref={backRef} onClick={onBack}>
          {companiesSetupBack()}
        </Button>
        <Button variant="primary" onClick={onAct}>
          {count === total
            ? companiesFollowCopyUnfollow({ count })
            : companiesFollowCopyKeepFollowingCount({ count: total - count })}
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
  const backRef = useRef<HTMLButtonElement>(null);
  // Ticked for every new question: regular scans are the default answer.
  const [keepScanning, setKeepScanning] = useState(true);
  // "Let me choose" and its ticks; a new question starts on its first step
  // with nothing ticked.
  const [choosing, setChoosing] = useState(false);
  const [unfollow, setUnfollow] = useState<Set<string>>(() => new Set());

  // The safe answer takes focus: Enter on a dialog that just opened must never
  // follow seventy companies — or consent to a wall. A child's effect runs
  // before the Overlay's, which keeps focus it finds already inside.
  useEffect(() => {
    setKeepScanning(true);
    setChoosing(false);
    setUnfollow(new Set());
    if (pending) safeRef.current?.focus();
  }, [pending]);

  // Each step's safe answer takes focus as the step appears.
  const stepShown = useRef(false);
  useEffect(() => {
    if (!stepShown.current) {
      stepShown.current = true;
      return;
    }
    (choosing ? backRef : safeRef).current?.focus();
  }, [choosing]);

  // Rendered from the same words the consent records (followCopy.ts).
  const copy = pending ? followCopy(pending) : null;
  const shownLocale = wordsLanguage();
  const choosingFrom = choosing && pending?.kind === "keep-following" ? pending.companies : null;
  const answer = () => {
    if (!copy) return;
    confirmFollow({ copy, locale: shownLocale, keepScanning, ...(choosingFrom ? { unfollow } : {}) });
    onAnswered?.(true);
  };

  return (
    <Dialog
      isOpen={pending !== null}
      onClose={dismiss}
      label={choosingFrom ? companiesFollowCopyWhichToUnfollow() : copy?.title ?? companiesCuratedListConfirm()}
      width={440}
      closeOnScrim={false}
      className="app-overlay"
    >
      {choosingFrom ? (
        <ChooseStep
          companies={choosingFrom}
          ticked={unfollow}
          onTicked={setUnfollow}
          backRef={backRef}
          onBack={() => setChoosing(false)}
          onAct={answer}
        />
      ) : copy && (
        <ConfirmBody
          copy={copy}
          keepScanning={keepScanning}
          onKeepScanning={setKeepScanning}
          safeRef={safeRef}
          onSafe={dismiss}
          onAct={answer}
          onChoose={() => setChoosing(true)}
        />
      )}
    </Dialog>
  );
}
