// An assistant app's mark, for the places that name the apps a person can
// connect. Both are one-colour marks drawn alike, so the pair matches in size
// and in how it greys at rest and takes colour under the pointer: Claude's is
// its company mark, and the Codex app's is drawn for the set (marks/codex.ts).
import { BrandGlyph, CompanyIcon } from "./CompanyIcon";
import { CODEX_MARK } from "./marks/codex";

export type AssistantApp = "claude-code" | "codex";

export interface AssistantMarkProps {
  app: AssistantApp;
  /** The app's name, which the monogram falls back to if a mark is missing. */
  display: string;
  size?: number;
}

export function AssistantMark({ app, display, size = 20 }: AssistantMarkProps) {
  if (app === "codex") return <BrandGlyph path={CODEX_MARK.path} hex={CODEX_MARK.hex} size={size} evenOdd />;
  return <CompanyIcon slug="claude" display={display} size={size} />;
}
