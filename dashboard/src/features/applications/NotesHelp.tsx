import { useState } from "react";
import { Button, Icon, Kbd, Popover } from "../../ui";
import {
  applicationsNotesHelp,
  applicationsNotesHelpLines,
  applicationsNotesHelpLinks,
  applicationsNotesHelpSelect,
  applicationsNotesHelpSlash,
  applicationsNotesHelpTitle,
  applicationsNotesHelpWords,
} from "../../copy/gen/applications";
import { BLOCKS } from "./notesBlocks";
import { STYLES, linkKeys, modKey } from "./notesStyles";

/** What the notes page can do, opened from its card's head: the marks that
 *  start a block, the keys that style words, and how a link is made and
 *  opened. The page shows none of these until they are used. */
export function NotesHelp() {
  const [open, setOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLButtonElement | null>(null);
  return (
    <>
      <Button
        ref={setAnchor}
        variant="icon"
        size="sm"
        aria-label={applicationsNotesHelp()}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <Icon name="help" size={14} />
      </Button>
      <Popover isOpen={open} onClose={() => setOpen(false)} anchor={anchor} align="end" label={applicationsNotesHelpTitle()} className="app-overlay app-notes-help">
        <h3>{applicationsNotesHelpTitle()}</h3>
        {/* Blocks and words side by side, so the guide opens under its
            button on a short window too. */}
        <div className="app-notes-help-cols">
          <section>
            <h4>{applicationsNotesHelpLines()}</h4>
            <dl>
              {BLOCKS.filter((block) => block.mark).map((block) => (
                <div key={block.key}>
                  <dt>{block.name()}</dt>
                  <dd><Kbd>{block.mark}</Kbd></dd>
                </div>
              ))}
            </dl>
            <p>{applicationsNotesHelpSlash()}</p>
          </section>
          <section>
            <h4>{applicationsNotesHelpWords()}</h4>
            <dl>
              {STYLES.map((style) => (
                <div key={style.key}>
                  <dt>{style.name()}</dt>
                  <dd><Kbd>{style.keys()}</Kbd></dd>
                </div>
              ))}
            </dl>
            <p>{applicationsNotesHelpSelect()}</p>
            <p>{applicationsNotesHelpLinks({ key: modKey(), link: linkKeys() })}</p>
          </section>
        </div>
      </Popover>
    </>
  );
}
