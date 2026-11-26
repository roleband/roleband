import { useCallback, useRef, useState } from "react";
import { aiAccessDialogTuningTheRadar, aiAssistantsCardAllowAssistantAppsToConnect } from "../../copy/gen/ai";
import {
  picksHost,
  picksOnboardAccess,
  picksOnboardBack,
  picksOnboardConnected,
  picksOnboardCount,
  picksOnboardFootnote,
  picksOnboardHeadline,
  picksOnboardInHost,
  picksOnboardInTerminal,
  picksOnboardLine,
  picksOnboardReasonMore,
  picksOnboardReasonMoreLead,
  picksOnboardReasonWork,
  picksOnboardReasonWorkLead,
  picksOnboardResume,
  picksOnboardRow,
  picksOnboardRowNow,
  picksOnboardRowSaved,
  picksOnboardRowWaits,
  picksOnboardSay,
  picksOnboardSentence,
  picksOnboardSentenceConnected,
  picksOnboardStepArrive,
  picksOnboardStepSay,
  picksOnboardTerminal,
  picksOnboardTerminalHost,
  picksOnboardUnderWay,
  picksOnboardUnderWayLine,
  picksOnboardWaiting,
  picksOnboardWorksWith,
} from "../../copy/gen/picks";
import { shellNavTopPicks } from "../../copy/gen/shell";
import { F } from "../../copy/runtime";
import { api, type AgentAccessState, type PicksState } from "../../api";
import { errorText } from "../../api/errorText";
import { useMissionStats } from "../../context/MissionState";
import { useVisibleInterval } from "../../hooks/useVisibleInterval";
import { Onboarding } from "../../patterns/onboarding/Onboarding";
import { Button, CompanyIcon, CopyField, Icon, Msg, Select, Switch, useToast } from "../../ui";
import "./top-picks-onboarding.css";

/** How often onboarding reads what the conversation has saved, and whether
 *  an assistant has connected, while it is on screen. */
export const ONBOARD_POLL_MS = 3_000;

type Setup = PicksState["setup"];
type SetupStepId = Setup["next_step"];
type App = AgentAccessState["apps"][number];
/** The assistants `roleband connect` sets up. */
type Host = AgentAccessState["connect"][number]["host"];

const HOSTS: readonly Host[] = ["claude-code", "codex"];

/** A stage of setup as onboarding lists it: saved, the one the conversation
 *  is at, waiting for roles to exist, or the one after the current stage. */
export type SetupRow = { id: Exclude<SetupStepId, "done">; state: "saved" | "now" | "waits" | "next" };

/** The stages onboarding lists, in order: every saved one, every one that
 *  waits for the first scan wherever it falls, the one the conversation is
 *  at, and the one after it. The rest stay unnamed until the conversation
 *  reaches them. */
export function setupRows(setup: Setup): SetupRow[] {
  const rows: SetupRow[] = [];
  let named = false;
  for (const step of setup.steps) {
    if (step.id === "done") break;
    if (setup.deferred.includes(step.id) && !step.done) rows.push({ id: step.id, state: "waits" });
    else if (named) continue;
    else if (step.done) rows.push({ id: step.id, state: "saved" });
    else if (step.id === setup.next_step) rows.push({ id: step.id, state: "now" });
    else {
      rows.push({ id: step.id, state: "next" });
      named = true;
    }
  }
  return rows;
}

/** The assistant with an app connected, in the order Settings lists them. */
function connectedHost(access: AgentAccessState | null): Host | null {
  return HOSTS.find((host) => access?.apps.some((app) => app.app === host && app.connection === "connected")) ?? null;
}

/** The app that called most recently: the one holding the conversation. */
function latestCaller(apps: readonly App[]): App["app"] | null {
  let latest: App | null = null;
  for (const app of apps) {
    if (app.last_call_at && (!latest?.last_call_at || app.last_call_at > latest.last_call_at)) latest = app;
  }
  return latest?.app ?? null;
}

/* Top picks before it is set up: the Onboarding pattern in two steps. Step 1
   is one sentence the person says in their assistant, which connects it and
   starts the setup conversation there; Terminal is the quiet fallback. The
   screen mirrors what the conversation saves, read from `GET /api/picks/state`
   while it is on screen, and gives way to the list (step 2) once the checks
   are set up. Nothing here asks the person a question of its own. */
export function TopPicksOnboarding({ picks, onPicksChange }: {
  picks: PicksState;
  onPicksChange: (next: PicksState) => void;
}) {
  const [access, setAccess] = useState<AgentAccessState | null>(null);
  // A read answers unless a read of the same kind that started after it has
  // answered already: an older answer never overwrites a newer one, and reads
  // slower than the interval still answer.
  const started = useRef({ picks: 0, access: 0 });
  const answered = useRef({ picks: 0, access: 0 });
  const poll = useCallback(() => {
    const picksRead = ++started.current.picks;
    api.picksState()
      .then((next) => {
        if (picksRead <= answered.current.picks) return;
        answered.current.picks = picksRead;
        onPicksChange(next);
      })
      .catch(() => {});
    const accessRead = ++started.current.access;
    api.agentAccess()
      .then((next) => {
        if (accessRead <= answered.current.access) return;
        answered.current.access = accessRead;
        setAccess(next);
      })
      .catch(() => {});
  }, [onPicksChange]);
  useVisibleInterval(poll, ONBOARD_POLL_MS);
  // A save answers for every read started before it: a read that left before
  // the save cannot put the old access back.
  const saved = useCallback((next: AgentAccessState) => {
    answered.current.access = started.current.access;
    setAccess(next);
  }, []);

  const steps = [picksOnboardStepSay(), picksOnboardStepArrive()];
  if (picks.setup.started) {
    const host = picksHost({ host: latestCaller(access?.apps ?? []) ?? "" });
    return (
      <Onboarding
        headline={picksOnboardUnderWay()}
        line={picksOnboardUnderWayLine({ host })}
        steps={steps}
        current={0}
      >
        {access && setupRefused(access) && <AccessLine access={access} onAccess={saved} />}
        <SetupRows setup={picks.setup} host={host} />
        <div className="picks-onboard-resume">
          <span>{picksOnboardResume()}</span>
          <CopyField text={picksOnboardSentenceConnected()} className="picks-onboard-resume-field" />
        </div>
      </Onboarding>
    );
  }
  return (
    <Onboarding
      headline={picksOnboardHeadline()}
      line={picksOnboardLine()}
      picture={<PickPicture />}
      steps={steps}
      current={0}
      footnote={picksOnboardFootnote()}
    >
      <Invitation access={access} onAccess={saved} />
    </Onboarding>
  );
}

/** Step 1's action: the sentence to say, or the command for Terminal, and
 *  under it whether an assistant has connected. */
function Invitation({ access, onAccess }: {
  access: AgentAccessState | null;
  onAccess: (next: AgentAccessState) => void;
}) {
  const connected = connectedHost(access);
  const [terminal, setTerminal] = useState(false);
  // An assistant that is connected needs only the sentence's second half.
  const sentence = connected ? picksOnboardSentenceConnected() : picksOnboardSentence();
  return (
    <>
      {access && setupRefused(access) && <AccessLine access={access} onAccess={onAccess} />}
      {terminal && !connected ? (
        <TerminalLines access={access} onBack={() => setTerminal(false)} />
      ) : (
        <>
          <div className="picks-onboard-say">
            <span className="picks-onboard-label">{picksOnboardSay()}</span>
            <span className="picks-onboard-marks" role="img" aria-label={picksOnboardWorksWith()}>
              <span aria-hidden="true"><CompanyIcon slug="claude" display={picksHost({ host: "claude-code" })} size={16} /></span>
              <span aria-hidden="true"><CompanyIcon slug="codex" display={picksHost({ host: "codex" })} size={16} /></span>
            </span>
          </div>
          <CopyField key={sentence} text={sentence} />
        </>
      )}
      <div className="picks-onboard-foot">
        <p className={`picks-onboard-live${connected ? " is-connected" : ""}`} role="status">
          <i aria-hidden="true" />
          {connected ? picksOnboardConnected({ host: picksHost({ host: connected }) }) : picksOnboardWaiting()}
        </p>
        {!connected && !terminal && (
          <Button variant="link" onClick={() => setTerminal(true)}>{picksOnboardTerminal()}</Button>
        )}
      </div>
    </>
  );
}

/** The setup conversation saves through changes in the "Tuning the radar"
 *  group: the engine refuses them unless assistant apps may connect, may make
 *  changes, and that group is on (a group left out is on). */
function setupRefused(access: AgentAccessState): boolean {
  return !access.enabled || !access.allow_writes || access.groups.tuning_radar === "off";
}

/** What refuses the setup's saves comes first, as a switch: Settings › AI's
 *  own switch while assistant apps may not connect, else its "Tuning the
 *  radar" change, each saved the way Settings › AI saves it. */
function AccessLine({ access, onAccess }: {
  access: AgentAccessState;
  onAccess: (next: AgentAccessState) => void;
}) {
  const { toast } = useToast();
  const [saving, setSaving] = useState(false);
  const label = access.enabled ? aiAccessDialogTuningTheRadar() : aiAssistantsCardAllowAssistantAppsToConnect();
  const allow = (next: boolean) => {
    if (!next) return;
    setSaving(true);
    // On a connection that makes no changes, the engine turns on only the
    // group named; every other kind of change stays off.
    const tuning = () => api.patchAgentAccess({ groups: { tuning_radar: "on" } });
    const open = access.enabled
      ? tuning()
      : api.setAgentAccess({ enabled: true, allow_writes: true })
        .then((opened) => (opened.groups.tuning_radar === "off" ? tuning() : opened));
    open
      .then(onAccess)
      .catch((e: unknown) => toast({ key: "top-picks-access", text: errorText(e), tone: "error" }))
      .finally(() => setSaving(false));
  };
  return (
    <div className="picks-onboard-access">
      <div>
        <b>{label}</b>
        <p>{picksOnboardAccess()}</p>
      </div>
      <Switch checked={false} disabled={saving} onChange={allow} label={label} />
    </div>
  );
}

/** The fallback: the command in Terminal for the chosen assistant, then the
 *  sentence's second half in it. */
function TerminalLines({ access, onBack }: { access: AgentAccessState | null; onBack: () => void }) {
  const [host, setHost] = useState<Host>("claude-code");
  // The engine serves the command for each assistant it sets up.
  const command = access?.connect.find((item) => item.host === host)?.command
    ?? /* not copy */ `roleband connect ${host} --apply`;
  const name = picksHost({ host });
  return (
    <>
      <ol className="picks-onboard-terminal">
        <li>
          <span className="picks-onboard-terminal-label">{picksOnboardInTerminal()}</span>
          <Select
            label={picksOnboardTerminalHost()}
            value={host}
            onChange={setHost}
            options={HOSTS.map((value) => ({ value, label: picksHost({ host: value }) }))}
          />
          <CopyField key={command} text={command} className="picks-onboard-command" />
        </li>
        <li>
          <span className="picks-onboard-terminal-label">{picksOnboardInHost({ host: name })}</span>
          <CopyField text={picksOnboardSentenceConnected()} className="picks-onboard-command" />
        </li>
      </ol>
      <p className="picks-onboard-back">
        <Button variant="link" onClick={onBack}>{picksOnboardBack()}</Button>
      </p>
    </>
  );
}

/** What the conversation has saved, stage by stage, as it saves it. */
function SetupRows({ setup, host }: { setup: Setup; host: string }) {
  return (
    <ol className="picks-setup-rows">
      {setupRows(setup).map((row) => (
        <li key={row.id} className={`picks-setup-row is-${row.state}`} aria-current={row.state === "now" ? "step" : undefined}>
          <span className="picks-setup-mark" aria-hidden="true">
            {row.state === "saved" && <Icon name="check" size={13} />}
          </span>
          <b>{picksOnboardRow({ step: row.id, host })}</b>
          <span>
            {row.state === "now" && picksOnboardRowNow({ step: row.id })}
            {row.state === "waits" && picksOnboardRowWaits()}
            {row.state === "saved" && <span className="sr-only">{picksOnboardRowSaved()}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The number of dots in the picture's field, and the few of them lit. */
const DOTS = 180;
const LIT = new Set([27, 76, 113]);

/* The picture: today's new roles as a field of dots with a few lit, an arrow,
   and a pick drawn as the row it will be, with blank bars for its title and
   facts and two reasons anyone can read as their own. It shows the shape of
   the result, never a sample of a role. Before any new role is counted today
   the figure and its caption are left out, and the field stands alone. */
function PickPicture() {
  const count = useMissionStats()?.new_today ?? 0;
  return (
    <div className="picks-picture">
      <div className="picks-picture-field">
        {count > 0 && (
          <p className="picks-picture-count">
            <span className="picks-picture-figure">{F(count)}</span>
            <span>{picksOnboardCount({ count })}</span>
          </p>
        )}
        <div className="picks-picture-dots" aria-hidden="true">
          {Array.from({ length: DOTS }, (_, i) => <i key={i} className={LIT.has(i) ? "is-lit" : undefined} />)}
        </div>
      </div>
      <svg className="picks-picture-arrow" viewBox="0 0 72 24" aria-hidden="true">
        <path d="M2 12h64" />
        <path d="m60 6 6 6-6 6" />
      </svg>
      <div className="picks-picture-card">
        <div className="picks-picture-card-head" aria-hidden="true">
          <i className="picks-picture-glow" />
          <span className="picks-picture-label">{shellNavTopPicks()}</span>
          <i className="picks-picture-bar is-tag" />
        </div>
        <div className="picks-picture-row" aria-hidden="true">
          <i className="picks-picture-bar is-title" />
          <span>
            <i className="picks-picture-bar is-fact" />
            <i className="picks-picture-bar is-fact-short" />
            <i className="picks-picture-bar is-fact-long" />
          </span>
        </div>
        <ul className="picks-picture-reasons">
          <li><Msg of={picksOnboardReasonWork} elems={{ lead: <b>{picksOnboardReasonWorkLead()}</b> }} /></li>
          <li><Msg of={picksOnboardReasonMore} elems={{ lead: <b>{picksOnboardReasonMoreLead()}</b> }} /></li>
        </ul>
        <div className="picks-picture-more" aria-hidden="true">
          <span><i className="picks-picture-glow" /><i className="picks-picture-bar is-more" /></span>
          <span><i className="picks-picture-glow" /><i className="picks-picture-bar is-more-long" /></span>
        </div>
      </div>
    </div>
  );
}
