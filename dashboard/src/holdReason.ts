import type { SystemStatus } from "./api";

const HALF_INSTALLED = new Set(["schema_pending", "dependencies_pending"]);

/** The reason code a hold is told by. An update left half installed finishes
    by itself in the app, but only `./setup.sh` finishes it on a source
    install, so there it reads as `setup_source`. Every other code passes
    through unchanged. */
export function holdReason(reason: string, install: SystemStatus["install"] | undefined): string {
  return install === "source" && HALF_INSTALLED.has(reason) ? "setup_source" : reason;
}
