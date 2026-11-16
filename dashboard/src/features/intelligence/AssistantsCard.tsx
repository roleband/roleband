// Card 2: assistant apps, which reach RoleBand through the `roleband` command.
// Cloud-connected, and it says so.
//
// The card is the one consent (docs/decisions/0017): one switch lets apps
// connect, and from then on they get everything. Most people turn it on, set
// up one app and never come back, so the card holds only that. The few who
// want less open Customize; the card's last line names what they held back,
// and only that. The tiles stay dimmed and their setup unreachable until the
// switch is on.
import { errorText } from "../../api/errorText";
import { useEffect, useState } from "react";
import { type AgentAccessInput, type AgentAccessState, api } from "../../api";
import { list } from "../../copy/format";
import { Button, CompanyIcon, Dialog, Icon, Switch } from "../../ui";
import {
  type AccessChoices,
  AgentAccessDialog,
  CATEGORIES,
  GROUPS,
  categoryChoice,
  groupChoice,
} from "./AgentAccessDialog";
import { OriginBadge } from "./OriginBadge";
import {
  aiAssistantsCardAllowAssistantAppsToConnect,
  aiAssistantsCardAllowAssistantAppsToConnect2,
  aiAssistantsCardAnthropic,
  aiAssistantsCardAssistantApps,
  aiAssistantsCardAssistantApps2,
  aiAssistantsCardAnyAppThatCanRunCommands,
  aiAssistantsCardAppClaudeCode,
  aiAssistantsCardAppCodexApp,
  aiAssistantsCardAppOtherApp,
  aiAssistantsCardChangesOff,
  aiAssistantsCardClipboardAccessWasBlockedSelect,
  aiAssistantsCardCopy,
  aiAssistantsCardCustomize,
  aiAssistantsCardDone,
  aiAssistantsCardEverythingShared,
  aiAssistantsCardLetTheAppRunCommands,
  aiAssistantsCardLocalOnly,
  aiAssistantsCardNotShared,
  aiAssistantsCardOffNothingLeavesThisComputer,
  aiAssistantsCardOpenai,
  aiAssistantsCardReadOnly,
  aiAssistantsCardRunThisOnceInA,
  aiAssistantsCardSetUp,
  aiAssistantsCardSetUpAnotherApp,
  aiAssistantsCardSetUpClaudeCode,
  aiAssistantsCardSetUpTheCodexApp,
  aiAssistantsCardUpToTheApp,
  aiAssistantsCardWhatAppsDo,
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
  { name: string; service: string; slug?: string; setup: string }
> = {
  "claude-code": {
    get name() { return aiAssistantsCardAppClaudeCode(); },
    get service() { return aiAssistantsCardAnthropic(); },
    slug: "claude",
    get setup() { return aiAssistantsCardSetUpClaudeCode(); },
  },
  codex: {
    get name() { return aiAssistantsCardAppCodexApp(); },
    get service() { return aiAssistantsCardOpenai(); },
    slug: "codex",
    get setup() { return aiAssistantsCardSetUpTheCodexApp(); },
  },
  other: {
    get name() { return aiAssistantsCardAppOtherApp(); },
    get service() { return aiAssistantsCardAnyAppThatCanRunCommands(); },
    get setup() { return aiAssistantsCardSetUpAnotherApp(); },
  },
};

/** What the open door's app is asked to run first. */
const FIRST_COMMAND = /* not copy */ "roleband capabilities";

/** The card's last line: what the person held back, one sentence per kind of
 *  choice, and nothing when they held back nothing. While the switch is off
 *  and nothing is held back, it says what turning it on shares instead. */
export function heldBack(state: AgentAccessState): string[] {
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

  useEffect(() => {
    api
      .agentAccess()
      .then(setState)
      .catch((e) => setError(errorText(e)));
  }, []);

  const save = async (access: AgentAccessInput) => {
    setSaving(true);
    setError(null);
    try {
      setState(await api.setAgentAccess(access));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const allowed = state?.enabled ?? false;
  // Changes ride on the connection: turning it on allows them, and each kind
  // the person switched off stays off, since the save leaves the groups out.
  const connect = (next: boolean) => save({ enabled: next, allow_writes: next });
  // A choice in Customize stores both whole maps, so what the dialog showed is
  // what is saved, whatever the row held before.
  const customize = (choices: AccessChoices) =>
    save({ enabled: allowed, allow_writes: allowed, ...choices });

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
        {(Object.keys(APPS) as App[]).map((app) => (
          <div key={app} className={`intel-tile${allowed ? "" : " is-waiting"}`}>
            <span className="intel-tile-mark">
              {APPS[app].slug ? (
                <CompanyIcon slug={APPS[app].slug!} display={APPS[app].name} size={22} />
              ) : (
                <Icon name="grid" size={20} />
              )}
            </span>
            <span>
              <span className="intel-tile-name">{APPS[app].name}</span>
              <span className="intel-tile-state">{APPS[app].service}</span>
            </span>
            <Button
              className="ui-btn-strong"
              disabled={!allowed}
              title={allowed ? undefined : aiAssistantsCardAllowAssistantAppsToConnect2()}
              onClick={() => setSetup(app)}
            >
              {aiAssistantsCardSetUp()}
            </Button>
          </div>
        ))}
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
      </div>

      {error && !customizing && (
        <div className="intel-error" role="alert">
          {error}
        </div>
      )}

      {state && setup && (
        <SetupDialog app={setup} state={state} onClose={() => setSetup(null)} />
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
      label={APPS[app].setup}
      width={520}
      className="app-overlay"
    >
      <div className="ledger-form">
        <h3>{APPS[app].setup}</h3>
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
