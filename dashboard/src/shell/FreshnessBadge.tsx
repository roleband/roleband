import { list } from "../copy/format";
import {
  shellFreshnessAria,
  shellFreshnessLabel,
  shellFreshnessLoadingAria,
  shellFreshnessMarketTitle,
  shellFreshnessNever,
  shellFreshnessOffline,
  shellFreshnessOfflineAria,
  shellFreshnessOfflineTitle,
  shellFreshnessOldest,
  shellFreshnessWaiting,
} from "../copy/gen/shell";
import { useSyncStatus } from "../context/SyncState";
import { companyName, formatWhen, freshnessLabel } from "../format";
import { launcherNeedsAttention, launcherWaiting } from "../copy/gen/launcher-status";
import { launcherHoldText } from "./launcherStatus";

export function FreshnessBadge() {
  const { status, statusFailed } = useSyncStatus();

  if (statusFailed && !status) {
    return (
      <span className="freshness-badge unknown" role="status" aria-label={shellFreshnessOfflineAria()} title={shellFreshnessOfflineTitle()}>
        <span className="dot" aria-hidden="true" />
        <span className="freshness-label">{shellFreshnessLabel()}</span>
        <strong>{shellFreshnessOffline()}</strong>
      </span>
    );
  }

  const freshness = freshnessLabel(status);
  const hold = status?.launcher?.status.hold;
  const text = hold ? (hold.kind === "attention" ? launcherNeedsAttention() : launcherWaiting()) : freshness.text;
  const tone = hold ? (hold.kind === "attention" ? "stale" : "unknown") : freshness.tone;
  // Closure eligibility (`overdue`) does not determine whether a board was
  // recently read. The tooltip lists only boards waiting for a full read.
  const behind = (status?.scheduler.unread ?? []).map((row) => companyName(row.company));
  const market = status?.wider_market;
  // While the badge shows the wider market, the tooltip says what it is first,
  // then the scan's own words, so they stay one hover away. The accessible
  // name is that whole tooltip: a screen reader hears what a hover shows.
  const marketShown = !hold && freshness.scan !== undefined;
  const title = [
    marketShown && market
      ? shellFreshnessMarketTitle({
        scan: market.waiting_for_power ? "paused" : "running",
        checked: market.checked,
        total: market.to_check,
        hiring: market.with_roles,
      })
      : null,
    marketShown ? freshness.scan : null,
    hold ? launcherHoldText(hold, status?.install) : null,
    status?.last_success_at
      ? shellFreshnessOldest({ when: formatWhen(status.last_success_at) })
      : marketShown ? null : shellFreshnessNever(),
    behind.length > 0 ? shellFreshnessWaiting({ companies: list(behind) }) : null,
  ].filter(Boolean).join(". ");

  return (
    <span className={`freshness-badge ${tone}`} role="status" aria-label={!status ? shellFreshnessLoadingAria() : marketShown ? title : shellFreshnessAria({ state: text })} title={status ? title : undefined}>
      <span className="dot" aria-hidden="true" />
      <span className="freshness-label">{shellFreshnessLabel()}</span>
      <strong>{text}</strong>
    </span>
  );
}
