import { describe, expect, it } from "vitest";
import { holdReason } from "./holdReason";

describe("holdReason", () => {
  it.each(["schema_pending", "dependencies_pending"])("tells a source install that %s waits on ./setup.sh", (reason) => {
    expect(holdReason(reason, "source")).toBe("setup_source");
  });

  it.each(["schema_pending", "dependencies_pending"])("leaves %s as it is in the app, which finishes the update itself", (reason) => {
    expect(holdReason(reason, "app")).toBe(reason);
  });

  it("passes every other code through on a source install", () => {
    for (const reason of ["supervisor_stale", "preflight_failed", "waiting_for_mains", "backoff"]) {
      expect(holdReason(reason, "source")).toBe(reason);
    }
  });

  it("assumes nothing before the status says how it was installed", () => {
    expect(holdReason("schema_pending", undefined)).toBe("schema_pending");
  });
});
