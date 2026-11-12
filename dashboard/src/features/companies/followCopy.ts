import { wordsLanguage } from "../../copy/runtime";
import type { CompanyConsent, CompanyDiscoveryCompany } from "../../api";
import { CURATED_LIST } from "../../copy/vocabulary";
import { aboutCount, type FollowEstimate, type SectorGroup } from "./companiesModel";
import {
  companiesFollowCopyByFollowingThem,
  companiesFollowCopyByFollowingYouChooseTo,
  companiesFollowCopyByPickingThis,
  companiesFollowCopyChangeItAnyTimeIn,
  companiesFollowCopyCancel,
  companiesFollowCopyFollow,
  companiesFollowCopyFollowCompany,
  companiesFollowCopyFollowAndScan,
  companiesFollowCopyFollowEveryCompany,
  companiesFollowCopyFollowEveryCompanyQuestion,
  companiesFollowCopyFollowAll,
  companiesFollowCopyFollowAllIn,
  companiesFollowCopyFollowMore,
  companiesFollowCopyHundredsOfRoles,
  companiesFollowCopyKeep,
  companiesFollowCopyKeepFollowing,
  companiesFollowCopyKeepFollowingCount,
  companiesFollowCopyKeepFollowingOne,
  companiesFollowCopyKeepFollowingThese,
  companiesFollowCopyLetMeChoose,
  companiesFollowCopyNotNow,
  companiesFollowCopySitesChanged,
  companiesFollowCopyKeepScanning,
  companiesFollowCopyMoreRoles,
  companiesFollowCopyRolebandScansTheBestKnown,
  companiesFollowCopyRolebandStartsYouWithA,
  companiesFollowCopyRolebandStopsScanningThemYour,
  companiesFollowCopyOnlyCompaniesHiringForRoles,
  companiesFollowCopySJobListingsStopBeing,
  companiesFollowCopyScanAboutMoreCompanies,
  companiesFollowCopyScannedAtYourDirection,
  companiesFollowCopySomeAreScannedAtYourDirection,
  companiesFollowCopySomeOfTheseCompaniesLimit,
  companiesFollowCopyStartScanning,
  companiesFollowCopyThisWillLikelyAddTo,
  companiesFollowCopyThousandsOfRoles,
  companiesFollowCopyUnfollow,
  companiesFollowCopyUnfollowCompanyQuestion,
  companiesFollowCopyUnfollowAnyTime,
  companiesFollowCopyUnfollowCompany,
  companiesFollowCopyUnfollowOutsideYour,
  companiesFollowCopyWithMoreCompaniesScansTake,
  companiesFollowCopyYouCanStopAtAny,
  companiesFollowCopyYourRadarCoversTheWhole,
} from "../../copy/gen/companies";

/* What the follow confirmations SAY, as data.
 *
 * One function builds every dialog's words, and the dialog renders exactly
 * what it returns. That is not tidiness: for a walled company, or one whose
 * careers site is scanned only at its person's direction, the words ARE the
 * agreement — the server stores the text the user confirmed — so the text
 * shown and the text recorded must be the same string by construction, never
 * two renderings that happen to agree.
 *
 * The wording is pinned (`copy/pinned.en.json`): one sentence for every wall
 * and one for every directed site, naming no company, no reason and not the
 * product, so a change here is a change to what was agreed.
 */

/** A follow or unfollow waiting on the reader's answer. `companies` is exactly
 *  what the write would change, fixed when it was asked, so the dialog and the
 *  write cannot disagree about the count. */
export type FollowConfirmation =
  | { kind: "include"; companies: CompanyDiscoveryCompany[]; estimate: FollowEstimate }
  | { kind: "exclude"; companies: CompanyDiscoveryCompany[] }
  | {
      kind: "sector";
      group: SectorGroup;
      companies: CompanyDiscoveryCompany[];
      estimate: FollowEstimate;
    }
  /** Follow one company that needs the user's agreement (walled, or scanned
   *  only at their direction) — or agree for one already followed without
   *  it, which is not scanned on its own until the user answers. */
  | { kind: "agree-follow"; company: CompanyDiscoveryCompany }
  | { kind: "walled-unfollow"; company: CompanyDiscoveryCompany }
  /** Companies already followed that wait for the user's agreement (the
   *  site's rules changed, or the company moved its site): one question for
   *  all of them, in name order. Agreeing keeps them followed and scanned;
   *  the ones the user ticks in "Let me choose" are unfollowed instead. */
  | { kind: "keep-following"; companies: CompanyDiscoveryCompany[] }
  /** Follow every other company RoleBand can scan, as one decision. */
  | { kind: "directory"; size: number }
  /** Setup's "Plus other companies": every listed company still unfollowed
   *  (`companies`, possibly none) and the set of other companies, in one
   *  answer. */
  | { kind: "everything"; companies: CompanyDiscoveryCompany[] };

export interface FollowCopy {
  title: string;
  /** What the answer brings. */
  paragraphs: string[];
  /** Present when the answer starts collecting a company that needs the
   *  user's agreement: one fact per kind of site, then what following means. */
  consent?: { facts: ConsentFact[]; choice: string };
  /** A quiet line above the answers. */
  note?: string;
  /** The link to a second step that picks companies one by one. A control,
   *  not a sentence: the agreement never records it. */
  choose?: string;
  /** The safe answer. It takes focus. */
  safe: string;
  act: string;
  /** Present when the answer covers companies scanned only at the user's
   *  direction: the label of the switch that puts them on the scan schedule,
   *  on at first. Its state is the agreement's `scan_on_schedule`. */
  keepScanning?: string;
}

/** One reason a site waits for the user's agreement, said once for every
 *  company it covers. */
export interface ConsentFact {
  site: "walled" | "directed";
  text: string;
}

/** A company this write would start collecting without the user's agreement:
 *  walled, or scanned only at the user's direction. The ones a bulk dialog
 *  must name and record. */
export function awaitingConsent(companies: readonly CompanyDiscoveryCompany[]): CompanyDiscoveryCompany[] {
  return companies.filter((company) => (company.wall !== null || company.directed) && !company.consented);
}

/** What one company's agreement is about. A company added by its link has no
 *  discovery row yet, so the dialog asks about this, not the row. */
export interface AgreementSubject {
  display: string;
  walled: boolean;
  directed: boolean;
}

/** One company's agreement: the wall's sentence, the directed site's, or both
 *  (a company can be both), then what following means. */
export function agreementCopy(subject: AgreementSubject): FollowCopy {
  const display = String(subject.display);
  const facts: ConsentFact[] = [];
  if (subject.walled) facts.push({ site: "walled", text: SITE_WALL_SENTENCE });
  if (subject.directed) facts.push({ site: "directed", text: companiesFollowCopyScannedAtYourDirection() });
  return {
    title: companiesFollowCopyFollow({ display }),
    paragraphs: [],
    consent: { facts, choice: companiesFollowCopyByFollowingYouChooseTo({ display }) },
    safe: companiesFollowCopyCancel(),
    act: subject.directed ? companiesFollowCopyFollowAndScan() : companiesFollowCopyFollowCompany({ display }),
    ...(subject.directed ? { keepScanning: companiesFollowCopyKeepScanning({ count: 1 }) } : {}),
  };
}

/** What a bulk follow agrees to, and its Keep scanning switch: one fact for
 *  its walled companies and one for its directed ones, naming none of them,
 *  then `choice` once for both. Absent when none of them needs agreement. */
function bulkConsent(
  companies: readonly CompanyDiscoveryCompany[],
  choice: () => string,
): Pick<FollowCopy, "consent" | "keepScanning"> {
  const waiting = awaitingConsent(companies);
  const directed = waiting.filter((company) => company.directed).length;
  const facts: ConsentFact[] = [];
  if (waiting.some((company) => company.wall !== null)) {
    facts.push({ site: "walled", text: companiesFollowCopySomeOfTheseCompaniesLimit() });
  }
  if (directed > 0) facts.push({ site: "directed", text: companiesFollowCopySomeAreScannedAtYourDirection() });
  return {
    ...(facts.length > 0 ? { consent: { facts, choice: choice() } } : {}),
    ...(directed > 0 ? { keepScanning: companiesFollowCopyKeepScanning({ count: directed }) } : {}),
  };
}


function volume(estimate: FollowEstimate): string {
  if (estimate.volume === "thousands") return companiesFollowCopyThousandsOfRoles();
  if (estimate.volume === "hundreds") return companiesFollowCopyHundredsOfRoles();
  return companiesFollowCopyMoreRoles();
}

/** Why a company waits for the user. Every wall is the SITE's — a company the
 *  product itself leaves to the user is not walled at all and never reaches a
 *  dialog. Names no company: the dialog's title does. */
export const SITE_WALL_SENTENCE = "Its careers site limits automated collection.";

export function wallSentence(company: CompanyDiscoveryCompany): string | null {
  return company.wall === null ? null : SITE_WALL_SENTENCE;
}

export function followCopy(pending: FollowConfirmation): FollowCopy {
  switch (pending.kind) {
    case "include": {
      const n = pending.companies.length;
      return {
        title: companiesFollowCopyFollowMore(),
        paragraphs: [companiesFollowCopyRolebandStartsYouWithA({ curatedList: CURATED_LIST() })],
        ...bulkConsent(pending.companies, companiesFollowCopyByFollowingThem),
        note: companiesFollowCopyUnfollowAnyTime(),
        safe: companiesFollowCopyKeep({ curatedList: CURATED_LIST() }),
        act: companiesFollowCopyFollowAll({ count: n }),
      };
    }
    case "exclude": {
      const n = pending.companies.length;
      return {
        title: companiesFollowCopyUnfollowOutsideYour({ count: n, curatedList: CURATED_LIST() }),
        paragraphs: [
          companiesFollowCopyRolebandStopsScanningThemYour({ count: n, curatedList: CURATED_LIST() }),
        ],
        safe: companiesFollowCopyKeepFollowing(),
        act: companiesFollowCopyUnfollow({ count: n }),
      };
    }
    case "sector": {
      const n = pending.group.bulk.length;
      return {
        title: companiesFollowCopyFollowAllIn({ count: n, sector: pending.group.display }),
        paragraphs: [companiesFollowCopyThisWillLikelyAddTo({ estimate: String(volume(pending.estimate)) })],
        ...bulkConsent(pending.companies, companiesFollowCopyByFollowingThem),
        safe: companiesFollowCopyCancel(),
        act: companiesFollowCopyFollowAll({ count: n }),
      };
    }
    case "agree-follow": {
      const { company } = pending;
      return agreementCopy({ display: company.display, walled: company.wall !== null, directed: company.directed });
    }
    case "directory": {
      const about = aboutCount(pending.size);
      return {
        title: companiesFollowCopyScanAboutMoreCompanies({ about: String(about) }),
        paragraphs: [
          companiesFollowCopyOnlyCompaniesHiringForRoles(),
          companiesFollowCopyRolebandScansTheBestKnown(),
          companiesFollowCopyYouCanStopAtAny(),
        ],
        safe: companiesFollowCopyCancel(),
        act: companiesFollowCopyStartScanning(),
      };
    }
    case "everything": {
      // Says that some sites limit collection, never how many: the choice is
      // the list and the other companies, and the consent is the same for one company or ten.
      return {
        title: companiesFollowCopyFollowEveryCompanyQuestion(),
        paragraphs: [companiesFollowCopyYourRadarCoversTheWhole(), companiesFollowCopyWithMoreCompaniesScansTake()],
        ...bulkConsent(pending.companies, companiesFollowCopyByPickingThis),
        note: companiesFollowCopyChangeItAnyTimeIn(),
        safe: companiesFollowCopyCancel(),
        act: companiesFollowCopyFollowEveryCompany(),
      };
    }
    case "keep-following": {
      const { companies } = pending;
      const count = companies.length;
      if (count === 1) {
        const [company] = companies;
        const agreement = agreementCopy({
          display: company.display,
          walled: company.wall !== null,
          directed: company.directed,
        });
        return {
          ...agreement,
          title: companiesFollowCopyKeepFollowingOne({ display: String(company.display) }),
          paragraphs: [companiesFollowCopySitesChanged({ count })],
          safe: companiesFollowCopyNotNow(),
          act: companiesFollowCopyKeepFollowing(),
        };
      }
      return {
        title: companiesFollowCopyKeepFollowingThese({
          first: String(companies[0].display),
          second: String(companies[1].display),
          rest: count - 2,
        }),
        paragraphs: [companiesFollowCopySitesChanged({ count })],
        ...bulkConsent(companies, companiesFollowCopyByFollowingThem),
        choose: companiesFollowCopyLetMeChoose(),
        safe: companiesFollowCopyNotNow(),
        act: companiesFollowCopyKeepFollowingCount({ count }),
      };
    }
    case "walled-unfollow": {
      const { display } = pending.company;
      return {
        title: companiesFollowCopyUnfollowCompanyQuestion({ display: String(display) }),
        paragraphs: [
          companiesFollowCopySJobListingsStopBeing({ display: String(display) }),
        ],
        safe: companiesFollowCopyCancel(),
        act: companiesFollowCopyUnfollowCompany({ display: String(display) }),
      };
    }
  }
}

/** What the reader answered: the words shown, their language, the Keep
 *  scanning checkbox (ignored when the dialog had none), and the companies
 *  ticked to unfollow in "Let me choose", which no agreement covers. */
export interface FollowAnswer {
  copy: FollowCopy;
  locale: string;
  keepScanning: boolean;
  unfollow?: ReadonlySet<string>;
}

/** Every sentence the dialog shows, in the order it shows them: the
 *  paragraphs, the consent facts and what following means, then the note.
 *  The switch and the answers are controls, not part of what is agreed. */
export function shownSentences(copy: FollowCopy): string[] {
  return [
    ...copy.paragraphs,
    ...(copy.consent ? [...copy.consent.facts.map((fact) => fact.text), copy.consent.choice] : []),
    ...(copy.note ? [copy.note] : []),
  ];
}

/** The text an agreement stores: the whole dialog the user confirmed. */
export function agreementText(copy: FollowCopy): string {
  return [copy.title, ...shownSentences(copy)].join("\n\n");
}

/** The agreements this answer records: one per company it starts to collect
 *  that needs one, each carrying the whole dialog text the user confirmed.
 *  `scan_on_schedule` is the checkbox for a directed company; a walled-only
 *  company is always on the schedule once agreed. */
export function consentsFor(pending: FollowConfirmation, shown: FollowAnswer = { copy: followCopy(pending), locale: wordsLanguage(), keepScanning: true }): CompanyConsent[] {
  const text = agreementText(shown.copy);
  const agreeing =
    pending.kind === "agree-follow"
      ? [pending.company]
      : pending.kind === "include" || pending.kind === "sector" || pending.kind === "everything"
        ? awaitingConsent(pending.companies)
        : pending.kind === "keep-following"
          ? awaitingConsent(pending.companies).filter((company) => !shown.unfollow?.has(company.slug))
          : [];
  return agreeing.map((company) => ({
    slug: company.slug,
    text,
    locale: shown.locale,
    scan_on_schedule: company.directed ? shown.keepScanning : true,
  }));
}
