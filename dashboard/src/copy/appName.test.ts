// The Mac app's own sentences speak about the person's work, never about the app by name:
// the person is already in it. Names stay where they name something (a button, a title).
import { join } from "node:path";
import { expect, it } from "vitest";
import { readLocale } from "../../scripts/copy/catalog.mjs";

const COPY = join(__dirname);
const NAMING_KINDS = new Set(["label", "button", "heading", "link", "aria"]);
// Windows Setup runs before the app is on the PC, where the reader may not know what is being installed: the
// installer names it (docs/copy.md, "Nobody speaks").
const INSTALLER = /^launcher-windows-setup-/;

it.each(["en", "es", "zh-Hans"])("no %s launcher sentence names the app", (locale) => {
  const english = new Map(readLocale(COPY, "en").messages.map((m: { id: string; meta: { kind?: string } }) => [m.id, m]));
  const offenders = readLocale(COPY, locale).messages
    .filter((m: { id: string; file: string }) => /(^|\/)launcher[^/]*\.ftl$/.test(m.file))
    .filter((m: { id: string }) => !NAMING_KINDS.has(english.get(m.id)?.meta.kind ?? "") && !INSTALLER.test(m.id))
    .filter((m: { src: string; pattern: { span: { start: number; end: number } } }) =>
      m.src.slice(m.pattern.span.start, m.pattern.span.end).includes("RoleBand"))
    .map((m: { id: string }) => m.id);
  expect(offenders).toEqual([]);
});
