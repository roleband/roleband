import type { Job } from "../../api";
import { fmtCompIn } from "../../money";
import { Icon } from "../../ui/Icon";
import {
  rolePayFloorLineBelowYourPayFloor,
  rolePayFloorLineYourPayFloorFallsInside,
} from "../../copy/gen/role";

/** The pay floor line. The server decides the verdict and sends
 *  nothing it cannot verify, so a missing check is silence, never "unknown".
 *  Pay that clears the floor is silence too: the person set the floor and the
 *  stated base is on the line above, so the line speaks only when the pay
 *  falls short of the floor or the floor sits inside the band.
 *  It lives apart from `JobCompPanel` because it reads the user's
 *  floor against the stated pay, not the package the panel draws. */
const FLOOR_LINE = {
  straddles: { icon: "alert", text: (floor: string) => rolePayFloorLineYourPayFloorFallsInside({ floor: String(floor) }) },
  below: { icon: "xCircle", text: (floor: string) => rolePayFloorLineBelowYourPayFloor({ floor: String(floor) }) },
} as const;

export function PayFloorLine({ check }: { check: Job["pay_floor_check"] }) {
  if (!check || check.verdict === "clears") return null;
  const line = FLOOR_LINE[check.verdict];
  return (
    <div className={`pkg-floor pkg-floor-${check.verdict}`} data-testid="pkg-floor">
      <Icon name={line.icon} size={14} />
      <span>{line.text(fmtCompIn(check.amount, check.currency))}</span>
    </div>
  );
}
