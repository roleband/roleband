import { useState } from "react";
import { Button } from "../../ui/Button";
import { Icon } from "../../ui/Icon";
import { Sheet } from "../../ui/Sheet";
import { STEPS } from "./walk/walkSteps";
import type { CSSProperties } from "react";
import {
  profileScopeGuideARoleWeHavenT,
  profileScopeGuideAboutTheCounts,
  profileScopeGuideCloseGuide,
  profileScopeGuideDecide,
  profileScopeGuideFiveAnswersDecideWhatReaches,
  profileScopeGuideHowYourRadarWorks,
  profileScopeGuideHowYourRadarWorks2,
  profileScopeGuideHowYourRadarWorks3,
  profileScopeGuideNothingHiddenByAGuess,
  profileScopeGuideProgressShowsHowManyOf,
  profileScopeGuideRadarGuide,
  profileScopeGuideSaveAppliesYourAnswersTo,
  profileScopeGuideSharpenOptional,
  profileScopeGuideWhenChangesApply,
  profileScopeGuideYourRadar,
} from "../../copy/gen/profile";

/* Long-form scope help lives in one deliberate overlay. Step headings keep only
   compact InfoTips; this panel owns the system model.
   It is `ui/Sheet` right-docked, so the scroll lock, Escape from anywhere and
   a reachable backdrop button come with the primitive.
   The guide explains Profile's five answers: the first three decide what
   reaches the radar, the last two sharpen it, one line per step from the
   walk's own table (the radar pyramid says it too). The trigger is an icon in
   the Profile header, at the right end of the title's row, the side the sheet
   opens from. */
export function ScopeGuideButton({ className = "" }: { className?: string }) {
  const [open, setOpen] = useState(false);
  // Read at render: a step's label and gist are message getters.
  const decide = STEPS.filter((step) => !step.optional);
  const sharpen = STEPS.filter((step) => step.optional);

  return (
    <>
      {/* Focus the trigger before opening, because a TAP does not.
          `Overlay` restores focus to whatever was active when it opened, which
          is the right contract and silently wrong on touch: a tap moves
          focus nowhere, so closing the panel would send focus to whatever the
          user last focused. Naming the opener is what makes the primitive's
          restore correct. */}
      <Button
        variant="icon"
        size="sm"
        className={className || undefined}
        aria-label={profileScopeGuideHowYourRadarWorks3()}
        title={profileScopeGuideHowYourRadarWorks2()}
        onClick={(event) => {
          event.currentTarget.focus();
          setOpen(true);
        }}
      >
        <Icon name="info" size={16} />
      </Button>

      <Sheet
        isOpen={open}
        onClose={() => setOpen(false)}
        label={profileScopeGuideHowYourRadarWorks()}
        className="scope-guide-sheet app-overlay"
      >
        <div className="scope-guide-head">
          <div>
            <div className="scope-guide-eyebrow">{profileScopeGuideRadarGuide()}</div>
            <h2>{profileScopeGuideHowYourRadarWorks2()}</h2>
          </div>
          <Button variant="icon" aria-label={profileScopeGuideCloseGuide()} onClick={() => setOpen(false)}>
            <Icon name="close" size={17} />
          </Button>
        </div>

        <p className="scope-guide-intro">
          {profileScopeGuideFiveAnswersDecideWhatReaches()}
        </p>

        <div className="scope-guide-flow">
          <span className="scope-guide-group" data-selection="chrome">{profileScopeGuideDecide()}</span>
          {decide.map((step, index) => (
            <div className="scope-guide-gate" key={step.id} style={{ "--gate-delay": `${index * 110}ms` } as CSSProperties}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{step.label}</strong>
              <small>{step.gist}</small>
            </div>
          ))}
          <span className="scope-guide-group" data-selection="chrome">{profileScopeGuideSharpenOptional()}</span>
          {sharpen.map((step, index) => (
            <div className="scope-guide-gate" key={step.id} style={{ "--gate-delay": `${(index + 3) * 110}ms` } as CSSProperties}>
              <span>{String(index + 4).padStart(2, "0")}</span>
              <strong>{step.label}</strong>
              <small>{step.gist}</small>
            </div>
          ))}
          <div className="scope-guide-result">
            <span className="scope-guide-pulse" />
            {profileScopeGuideYourRadar()}
          </div>
        </div>

        <section className="scope-guide-note">
          <h3>{profileScopeGuideWhenChangesApply()}</h3>
          <p>
            {profileScopeGuideSaveAppliesYourAnswersTo()}
          </p>
        </section>

        <section className="scope-guide-note">
          <h3>{profileScopeGuideAboutTheCounts()}</h3>
          <p>
            {profileScopeGuideProgressShowsHowManyOf()}
          </p>
        </section>

        <section className="scope-guide-note">
          <h3>{profileScopeGuideNothingHiddenByAGuess()}</h3>
          <p>{profileScopeGuideARoleWeHavenT()}</p>
        </section>
      </Sheet>
    </>
  );
}
