// Card 2: assistant apps, which reach RoleBand through the `roleband` command.
// Cloud-connected, and it says so.
//
// The card is the one consent (docs/decisions/0017): one switch lets apps
// connect, and from then on they get everything. Most people turn it on, set
// up one app and never come back, so the card holds only that. The few who
// want less open Customize; the card's last line names what they held back,
// and only that. The tiles stay dimmed and their setup unreachable until the
// switch is on.
//
// Each tile says what the engine knows of its app (`AgentAppState`): what the
// app's own settings say, and its most recent call. An app that is connected
// or has called wears a check, and trades its Connect button for its
// Activity and the gear that reopens its command; one that needs a step
// (an older skill, a removed rule) keeps a single button for that step.
import { errorText } from "../../api/errorText";
import { useCallback, useEffect, useRef, useState } from "react";
import { type AgentAccessChoices, type AgentAccessState, api } from "../../api";
import { ageLabel } from "../../format";
import { list } from "../../copy/format";
import { Button, CompanyIcon, Dialog, Icon, RouterLink, Switch } from "../../ui";
import {
  AgentAccessDialog,
  CATEGORIES,
  GROUPS,
  categoryChoice,
  groupChoice,
} from "./AgentAccessDialog";
import { OriginBadge } from "./OriginBadge";
import { ACTIVITY_ROUTE } from "../../routing/paths";
import {
  aiAssistantsCardAllowAssistantAppsToConnect,
  aiAssistantsCardAllowAssistantAppsToConnect2,
  aiAssistantsCardAnthropic,
  aiAssistantsCardAppActivity,
  aiAssistantsCardAppState,
  aiAssistantsCardAssistantApps,
  aiAssistantsCardAssistantApps2,
  aiAssistantsCardAnyAppThatCanRunCommands,
  aiAssistantsCardAppClaudeCode,
  aiAssistantsCardAppCodexApp,
  aiAssistantsCardAppOtherApp,
  aiAssistantsCardChangesOff,
  aiAssistantsCardClipboardAccessWasBlockedSelect,
  aiAssistantsCardConnect,
  aiAssistantsCardConnectAnotherApp,
  aiAssistantsCardConnectClaudeCode,
  aiAssistantsCardConnected,
  aiAssistantsCardConnectTheCodexApp,
  aiAssistantsCardCopy,
  aiAssistantsCardActivity,
  aiAssistantsCardCustomize,
  aiAssistantsCardDone,
  aiAssistantsCardEverythingShared,
  aiAssistantsCardLetTheAppRunCommands,
  aiAssistantsCardLocalOnly,
  aiAssistantsCardNotShared,
  aiAssistantsCardOffNothingLeavesThisComputer,
  aiAssistantsCardOpenai,
  aiAssistantsCardOtherUsed,
  aiAssistantsCardReadOnly,
  aiAssistantsCardRunThisOnceInA,
  aiAssistantsCardUpdate,
  aiAssistantsCardUpToTheApp,
  aiAssistantsCardWhatAppsDo,
  aiCapabilitiesCardConfigure,
} from "../../copy/gen/ai";

type App = "claude-code" | "codex" | "other";

/** The hosts `roleband connect` sets up, each with the command the engine
 *  serves for it, plus the open door: any app that can run a command can call
 *  `roleband`, so a third tile asks it to start with `roleband capabilities`.
 *  `slug` is a company mark (Simple Icons); its absence means the tile wears a
 *  UI glyph instead: the two icon sets stay split by domain, and "any app" is
 *  not a company. */
const APPS: Record<
  App,
  { name: string; service: string; slug?: string; connect: string }
> = {
  "claude-code": {
    get name() { return aiAssistantsCardAppClaudeCode(); },
    get service() { return aiAssistantsCardAnthropic(); },
    slug: "claude",
    get connect() { return aiAssistantsCardConnectClaudeCode(); },
  },
  codex: {
    get name() { return aiAssistantsCardAppCodexApp(); },
    get service() { return aiAssistantsCardOpenai(); },
    slug: "codex",
    get connect() { return aiAssistantsCardConnectTheCodexApp(); },
  },
  other: {
    get name() { return aiAssistantsCardAppOtherApp(); },
    get service() { return aiAssistantsCardAnyAppThatCanRunCommands(); },
    get connect() { return aiAssistantsCardConnectAnotherApp(); },
  },
};

type AppState = AgentAccessState["apps"][number];

/** What one tile shows: its second line, whether it wears the check, and its
 *  one step when it has one. A connected host that has called says when,
 *  the stronger fact; a host whose files need a step names it, whatever its
 *  calls say, since the step is what the person can act on. The open door
 *  has no files to read: it shows only its last call. */
function tileView(app: App, state: AppState | undefined, now: number): {
  line: string;
  done: boolean;
  step: "connect" | "update" | null;
} {
  const service = APPS[app].service;
  const age = state?.last_call_at
    ? ageLabel(Math.max(0, now - Date.parse(state.last_call_at)) / 3_600_000)
    : null;
  if (app === "other") {
    return age
      ? { line: aiAssistantsCardOtherUsed({ age }), done: true, step: null }
      : { line: service, done: false, step: "connect" };
  }
  const connection = state?.connection ?? null;
  if (connection === "outdated") {
    return { line: aiAssistantsCardAppState({ state: "outdated", service, age: "" }), done: true, step: "update" };
  }
  if (connection === "rule_missing") {
    return { line: aiAssistantsCardAppState({ state: "rule-missing", service, age: "" }), done: false, step: "connect" };
  }
  // Connect never changes the app's sandbox mode, so it is offered no button;
  // the gear still shows the command.
  if (connection === "read_only") {
    return { line: aiAssistantsCardAppState({ state: "read-only", service, age: "" }), done: false, step: null };
  }
  const used = age ? aiAssistantsCardAppState({ state: "used", service, age }) : null;
  if (connection === "connected") {
    return { line: used ?? aiAssistantsCardAppState({ state: "connected", service, age: "" }), done: true, step: null };
  }
  // A call made before the skill was removed, or without one: the call is a
  // fact worth keeping, but the app is not set up, so Connect stays offered.
  return { line: used ?? service, done: false, step: "connect" };
}

/** What the open door's app is asked to run first. */
const FIRST_COMMAND = /* not copy */ "roleband capabilities";

/** The card's last line: what the person held back, one sentence per kind of
 *  choice, and nothing when they held back nothing. While the switch is off
 *  and nothing is held back, it says what turning it on shares instead. */
function heldBack(state: AgentAccessState): string[] {
  const names = <T extends string>(rows: readonly { id: T; name: () => string }[], keep: (id: T) => boolean) =>
    rows.filter((row) => keep(row.id)).map((row) => row.name());
  const notShared = names(CATEGORIES, (id) => categoryChoice(state, id) === "not_shared");
  const localOnly = names(CATEGORIES, (id) => categoryChoice(state, id) === "local_only");
  const off = names(GROUPS, (id) => groupChoice(state, id) === "off");
  const lines: string[] = [];
  if (notShared.length) lines.push(aiAssistantsCardNotShared({ list: list(notShared) }));
  if (localOnly.length) lines.push(aiAssistantsCardLocalOnly({ list: list(localOnly) }));
  if (off.length === GROUPS.length) lines.push(aiAssistantsCardReadOnly());
  else if (off.length) lines.push(aiAssistantsCardChangesOff({ list: list(off) }));
  if (!lines.length && !state.enabled) lines.push(aiAssistantsCardEverythingShared());
  return lines;
}

export function AssistantsCard() {
  const [state, setState] = useState<AgentAccessState | null>(null);
  const [setup, setSetup] = useState<App | null>(null);
  const [customizing, setCustomizing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Read once per load: "5m ago" is the age the engine answered with.
  const [now, setNow] = useState(() => Date.now());
  const loaded = useCallback((next: AgentAccessState) => {
    setState(next);
    setNow(Date.now());
  }, []);
  // Counts the requests started. A read answers only if nothing started after
  // it: a later read saw newer files, and a save started or finished after it
  // answers with the access as saved, which the read may predate.
  const requests = useRef(0);
  const read = useCallback(() => {
    const ticket = ++requests.current;
    return api.agentAccess().then((next) => {
      if (requests.current === ticket) loaded(next);
    });
  }, [loaded]);

  useEffect(() => {
    read().catch((e) => setError(errorText(e)));
  }, [read]);

  // The person runs the command while the dialog is open, so its close is when
  // the tiles may have changed. A failed read keeps the tiles as they were, and
  // the next close reads again.
  const closeSetup = () => {
    setSetup(null);
    read().catch(() => undefined);
  };

  const save = async (write: () => Promise<AgentAccessState>) => {
    requests.current += 1;
    setSaving(true);
    setError(null);
    try {
      const next = await write();
      requests.current += 1;
      loaded(next);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const allowed = state?.enabled ?? false;
  // Changes ride on the connection: turning it on allows them, and each kind
  // the person switched off stays off, since the save leaves the groups out.
  const connect = (next: boolean) => save(() => api.setAgentAccess({ enabled: next, allow_writes: next }));
  const customize = (choices: AgentAccessChoices) => save(() => api.patchAgentAccess(choices));

  const lines = state ? heldBack(state) : [];

  return (
    <section className="intel-card" aria-label={aiAssistantsCardAssistantApps2()}>
      <div className="intel-head">
        <div className="intel-head-title">
          <h2>{aiAssistantsCardAssistantApps()}</h2>
          <OriginBadge origin="cloud" />
        </div>
        <span className="intel-aside">
          {aiAssistantsCardOffNothingLeavesThisComputer({ choice: allowed ? "yes" : "no" })}
        </span>
      </div>

      <div className="intel-access-gate">
        <Switch
          checked={allowed}
          disabled={saving || state == null}
          onChange={connect}
          label={aiAssistantsCardAllowAssistantAppsToConnect()}
        />
        <div className="intel-access-gate-copy">
          <b className="intel-grant-name">{aiAssistantsCardAllowAssistantAppsToConnect()}</b>
          {/* Once on, the person knows what apps read; the sentence that
              stays is the one no setting changes. */}
          {!allowed && <span className="intel-access-gate-note">{aiAssistantsCardWhatAppsDo()}</span>}
          <span className="intel-access-gate-note">{aiAssistantsCardUpToTheApp()}</span>
        </div>
      </div>

      <div className="intel-tiles">
        {(Object.keys(APPS) as App[]).map((app) => {
          const view = tileView(app, state?.apps.find((item) => item.app === app), now);
          return (
            <div key={app} className={`intel-tile${allowed ? "" : " is-waiting"}`} data-app={app}>
              <span className="intel-tile-mark">
                {APPS[app].slug ? (
                  <CompanyIcon slug={APPS[app].slug!} display={APPS[app].name} size={22} />
                ) : (
                  <Icon name="grid" size={20} />
                )}
                {view.done && (
                  <span className="intel-tile-check" role="img" aria-label={aiAssistantsCardConnected()}>
                    <Icon name="check" size={10} />
                  </span>
                )}
              </span>
              <span>
                <span className="intel-tile-name">{APPS[app].name}</span>
                <span className="intel-tile-state">{view.line}</span>
              </span>
              {view.step ? (
                <Button
                  className="ui-btn-strong"
                  disabled={!allowed}
                  title={allowed ? undefined : aiAssistantsCardAllowAssistantAppsToConnect2()}
                  onClick={() => setSetup(app)}
                >
                  {view.step === "update" ? aiAssistantsCardUpdate() : aiAssistantsCardConnect()}
                </Button>
              ) : (
                <span className="intel-tile-acts">
                  <RouterLink
                    to={`${ACTIVITY_ROUTE}?app=${app}`}
                    aria-label={aiAssistantsCardAppActivity({ app: APPS[app].name })}
                  >
                    {aiAssistantsCardActivity()}
                  </RouterLink>
                  <Button
                    variant="icon"
                    disabled={!allowed}
                    title={allowed ? undefined : aiAssistantsCardAllowAssistantAppsToConnect2()}
                    aria-label={aiCapabilitiesCardConfigure({ name: APPS[app].name })}
                    onClick={() => setSetup(app)}
                  >
                    <Icon name="gear" size={18} />
                  </Button>
                </span>
              )}
            </div>
          );
        })}
      </div>

      <div className="intel-access-foot">
        <span className="intel-access-held">
          {lines.map((line) => (
            <span key={line}>{line}</span>
          ))}
        </span>
        <Button variant="link" disabled={state == null} onClick={() => setCustomizing(true)}>
          {aiAssistantsCardCustomize()}
        </Button>
        <RouterLink variant="link" to={ACTIVITY_ROUTE}>
          {aiAssistantsCardActivity()}
        </RouterLink>
      </div>

      {error && !customizing && (
        <div className="intel-error" role="alert">
          {error}
        </div>
      )}

      {state && setup && (
        <SetupDialog app={setup} state={state} onClose={closeSetup} />
      )}
      {state && customizing && (
        <AgentAccessDialog
          state={state}
          saving={saving}
          error={error}
          onChange={customize}
          onClose={() => setCustomizing(false)}
        />
      )}
    </section>
  );
}

function SetupDialog({
  app,
  state,
  onClose,
}: {
  app: App;
  state: AgentAccessState;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  // A named host's command comes from the engine, which serves one for every
  // host `roleband connect` sets up.
  const value =
    app === "other"
      ? FIRST_COMMAND
      : (state.connect.find((item) => item.host === app)?.command ?? "");

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setCopyError(null);
    } catch {
      setCopyError(
        aiAssistantsCardClipboardAccessWasBlockedSelect(),
      );
    }
  };

  return (
    <Dialog
      isOpen
      onClose={onClose}
      label={APPS[app].connect}
      width={520}
      className="app-overlay"
    >
      <div className="ledger-form">
        <h3>{APPS[app].connect}</h3>
        <p className="intel-dialog-note">
          {app === "other"
            ? aiAssistantsCardLetTheAppRunCommands()
            : aiAssistantsCardRunThisOnceInA()}
        </p>
        <pre className="intel-snippet">{value}</pre>
        {copyError && (
          <p className="intel-dialog-note" role="alert">
            {copyError}
          </p>
        )}
        <div className="ledger-form-actions">
          <Button className="ui-btn-strong" onClick={onClose}>
            {aiAssistantsCardDone()}
          </Button>
          <Button variant="primary" onClick={copy}>
            <Icon name="copy" size={16} />
            {aiAssistantsCardCopy({ choice: (copied) ? "yes" : "no" })}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
