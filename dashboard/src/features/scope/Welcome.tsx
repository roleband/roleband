import "./welcome/welcome.css";
import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../../api";
import { useAsyncResource } from "../../hooks/useAsyncResource";
import { SETUP_PATH } from "../../routing/setupMode";
import { useSetupZoom } from "./setupZoom";
import { SHARING_REVIEW, isSharingReview } from "./sharingReview";
import { ConsentPane } from "../../patterns/privacy/ConsentPane";
import { GROUPS, groupsToAsk } from "../../patterns/privacy/consentCopy";
import { applySharing } from "../../diagnostics/sharing";
import { sharingAnswered } from "../../diagnostics/sharingAnswered";
import { MotionStage } from "./motion/primitives";

/* The front door of first-run setup: the radar intro (the product narrative
   as a scene, not a form), then the usage-sharing question, then Profile's
   own walk in setup mode (routing/setupMode.ts). Setup is the walk every
   configured install edits later, so there is no second copy of its steps
   here to drift from it.

   The sharing question (docs/architecture.md) is asked BEFORE the walk, so a
   person who shares has the walk itself counted; nothing is counted before
   the answer. It is asked inside the intro's scene: the planet dims and the
   question takes the place of the intro's words. Skipped when nothing is left to ask, when an environment switch
   has turned sharing off, or when the state cannot be read (a failed read
   never blocks setup).

   The question has a way back. Before the walk is opened, the welcome's own
   history entry is marked (routing/setupMode.ts), and setup's first step has
   a Back to it: coming back to a marked entry opens the question at once, on
   every kind, on the answer given, marked "Your answer". With nothing to ask
   (sharing switched off here, or the state unreadable) it opens the intro,
   whose button goes on to the walk, so Back never bounces straight forward.

   The intro's planet is lazy: d3 and the world atlas load only when it shows. */

const RadarIntro = lazy(() => import("./welcome/RadarIntro"));

const SHARING_WAIT_MS = 3000;

function WelcomeBody({ page }: { page: RefObject<HTMLElement | null> }) {
  const navigate = useNavigate();
  const returning = isSharingReview(useLocation().state);
  const sharing = useAsyncResource((signal) => api.usage(signal), []);
  const readable = sharing.data && !sharing.data.blocked_by ? sharing.data : null;
  const toAsk = readable ? (returning ? [...GROUPS] : groupsToAsk(readable)) : [];
  // A press before the read has answered waits for it, since the answer
  // decides whether the question comes first. A failed read opens the walk,
  // and so does a read still unanswered once the wait is up.
  const [begun, setBegun] = useState(false);
  const [waitedOut, setWaitedOut] = useState(false);
  // A return wants the question without the intro's press; with nothing to
  // ask, it waits for the press like a first visit.
  const wanted = begun || returning;
  useEffect(() => {
    if (!wanted || !sharing.loading) return;
    const later = window.setTimeout(() => setWaitedOut(true), SHARING_WAIT_MS);
    return () => window.clearTimeout(later);
  }, [wanted, sharing.loading]);
  const decided = wanted && (!sharing.loading || waitedOut);
  const asking = decided && toAsk.length > 0;
  const walkNext = decided && toAsk.length === 0 && begun;
  // The question opens at the top: on a short screen the intro is scrolled to
  // reach its button, and the question would otherwise open part-way down.
  useLayoutEffect(() => {
    page.current?.scrollTo?.({ top: 0 });
  }, [page, asking]);
  // The question takes the keyboard to its safe answer, as the dialog that
  // asks an existing install does: Enter on a question that just opened
  // never shares, unless sharing is the answer already given and Enter keeps
  // it. The page stays at its top.
  const safe = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (asking) safe.current?.focus({ preventScroll: true });
  }, [asking]);
  // Pushed, not replaced: Back from setup's first step comes back here
  // rather than leaving RoleBand. This entry is marked first, so coming back
  // to it asks again.
  const toWalk = useCallback(() => {
    navigate("/welcome", { replace: true, state: SHARING_REVIEW });
    navigate(SETUP_PATH);
  }, [navigate]);
  useEffect(() => {
    if (walkNext) toWalk();
  }, [walkNext, toWalk]);
  // The walk comes next: its catalog is asked while the welcome is read, once
  // the welcome is on screen. Loaded apart, so the welcome does not carry the
  // draft's code.
  useEffect(() => {
    const later = window.setTimeout(() => {
      void import("./useScopeDraft").then((draft) => draft.primeScopeCatalog());
    }, 1000);
    return () => window.clearTimeout(later);
  }, []);

  return (
    <Suspense fallback={<div className="welcome-intro-fallback" aria-hidden="true" />}>
      <RadarIntro
        onBegin={() => setBegun(true)}
        question={asking && readable ? (
          <ConsentPane
            look="scene"
            state={readable}
            groups={toAsk}
            review={returning}
            safeRef={safe}
            onAnswered={(next) => {
              void applySharing(next);
              sharingAnswered(next);
              toWalk();
            }}
          />
        ) : null}
      />
    </Suspense>
  );
}

export function Welcome() {
  const page = useRef<HTMLElement>(null);
  useSetupZoom(true);
  return (
    <main ref={page} className="main settings-view welcome-main">
      <MotionStage>
        <WelcomeBody page={page} />
      </MotionStage>
    </main>
  );
}
