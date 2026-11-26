import { useState } from "react";
import { NAV_TABS, type NavTabDef, type SideBarChoice } from "../../navigation";
import { useListed } from "../../hooks/sideBar";
import { setViewChoice } from "../../hooks/viewChoices";
import { Icon, Switch } from "../../ui";
import { Card, CardMessage, CardRow } from "../../ui/Card";
import {
  settingsSaveFailed,
  settingsSideBarDuplicates,
  settingsSideBarIntro,
  settingsSideBarTitle,
} from "../../copy/gen/settings";
import { LanguageSection } from "./LanguageSection";
import "./PreferencesSection.css";

/* Settings > Preferences: how the app is laid out for the person. Which
   optional places the side bar lists, then language and region. Each switch
   commits at once, as Settings' switches do. */

const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

type OptionalPlace = NavTabDef & { optional: SideBarChoice };
const OPTIONAL = NAV_TABS.filter((t): t is OptionalPlace => t.optional != null);

/** The one place whose name does not say what it holds. */
const DESCRIPTIONS: Record<string, () => string> = { "/review": settingsSideBarDuplicates };

function SideBarCard() {
  const isListed = useListed();
  const [failed, setFailed] = useState(false);

  const turn = async (place: OptionalPlace, shown: boolean) => {
    setFailed(false);
    // Shown at once; a failed save still holds until the page is reloaded.
    if (!(await setViewChoice(place.optional.choice, shown))) setFailed(true);
  };

  return (
    <Card title={settingsSideBarTitle()} intro={settingsSideBarIntro({ platform: MAC ? "mac" : "other" })}>
      {OPTIONAL.map((place) => (
        <CardRow
          key={place.path}
          title={
            <span className="preferences-place">
              <Icon name={place.icon} size={16} />
              {place.label}
            </span>
          }
          description={DESCRIPTIONS[place.path]?.()}
          toggle={(slot) => (
            <Switch
              {...slot}
              checked={isListed(place.optional)}
              onChange={(shown) => void turn(place, shown)}
              label={place.label}
            />
          )}
        />
      ))}
      {failed && <CardMessage role="alert">{settingsSaveFailed()}</CardMessage>}
    </Card>
  );
}

export function PreferencesSection() {
  return (
    <>
      <SideBarCard />
      <LanguageSection />
    </>
  );
}
