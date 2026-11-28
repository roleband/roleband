// An assistant app's mark, for the places that name the apps a person can
// connect. Claude's mark is in the company icon set; the Codex app's is not
// (the set carries no OpenAI marks), so it is the app's own icon, cropped to
// its tile, at the size the other mark takes.
import { CompanyIcon } from "./CompanyIcon";
import codexApp from "./marks/codex-app.png";
import "./AssistantMark.css";

export type AssistantApp = "claude-code" | "codex";

export interface AssistantMarkProps {
  app: AssistantApp;
  /** The app's name, which the monogram falls back to if a mark is missing. */
  display: string;
  size?: number;
}

export function AssistantMark({ app, display, size = 20 }: AssistantMarkProps) {
  if (app === "codex") {
    return (
      <img
        className="ui-assistant-mark"
        src={codexApp}
        alt=""
        aria-hidden="true"
        width={size}
        height={size}
        draggable={false}
      />
    );
  }
  return <CompanyIcon slug="claude" display={display} size={size} />;
}
