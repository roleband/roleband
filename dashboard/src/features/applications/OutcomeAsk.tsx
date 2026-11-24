import { useState } from "react";
import type { ApplicationInterview } from "../../api";
import { applicationsUpnextOutcomeLabel, applicationsWsAskOutcome } from "../../copy/gen/applications";
import { Button, Icon, Menu, MenuGroup, MenuItem } from "../../ui";
import { OUTCOME_LABEL } from "./interviewWords";

export type Outcome = NonNullable<ApplicationInterview["outcome"]>;

/** A past round asks once how it went, and the three outcomes open from the
 *  question. One control wherever a round waits for its outcome: Up next's
 *  row and the Workspace's round. */
export function OutcomeAsk({ interview, onOutcome }: {
  interview: Pick<ApplicationInterview, "label">;
  onOutcome: (outcome: Outcome) => void;
}) {
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        ref={setAnchor}
        variant="ghost"
        size="sm"
        className="ui-btn-bar app-outcome-ask"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        {applicationsWsAskOutcome()}
        <Icon name="chevronDown" size={12} />
      </Button>
      <Menu isOpen={open} onClose={() => setOpen(false)} anchor={anchor} label={applicationsUpnextOutcomeLabel({ label: interview.label })}>
        <MenuGroup>
          {(Object.keys(OUTCOME_LABEL) as Outcome[]).map((outcome) => (
            <MenuItem
              key={outcome}
              onSelect={() => {
                setOpen(false);
                onOutcome(outcome);
              }}
            >
              {OUTCOME_LABEL[outcome]()}
            </MenuItem>
          ))}
        </MenuGroup>
      </Menu>
    </>
  );
}
