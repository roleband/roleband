// Writes tests/ux/shard-weights.json, the seconds each spec file takes, from the
// JSON reports of a green CI run (its playwright-results-* artifacts), so the
// browser shards stay balanced as specs grow.
//
//   node scripts/ux-shard-weights.mjs <results.json>...
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

/** Seconds per spec file, rounded to a tenth, keyed and sorted by its path below tests/ux/.
 *
 *  A test is charged to the spec file whose top-level suite holds it, the file the
 *  shards split. Its own `file` names where the test is written, which for a test
 *  a spec builds from a shared helper is the helper: no shard ever runs that. */
export function specSeconds(reports) {
  const seconds = {};
  function walk(suite, specFile) {
    for (const spec of suite.specs ?? []) {
      for (const test of spec.tests) {
        for (const result of test.results) seconds[specFile] = (seconds[specFile] ?? 0) + result.duration / 1000;
      }
    }
    for (const child of suite.suites ?? []) walk(child, specFile);
  }
  for (const report of reports) {
    for (const suite of report.suites) walk(suite, suite.file.replaceAll("\\", "/"));
  }
  return Object.fromEntries(Object.keys(seconds).sort().map((file) => [file, Math.round(seconds[file] * 10) / 10]));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const out = join(dirname(fileURLToPath(import.meta.url)), "..", "tests", "ux", "shard-weights.json");
  const reports = process.argv.slice(2);
  if (!reports.length) {
    console.error("usage: node scripts/ux-shard-weights.mjs <results.json>...");
    process.exit(2);
  }
  const sorted = specSeconds(reports.map((report) => JSON.parse(readFileSync(report, "utf8"))));
  writeFileSync(out, `${JSON.stringify(sorted, null, 2)}\n`);
  console.log(`${Object.keys(sorted).length} spec files, ${Math.round(Object.values(sorted).reduce((a, b) => a + b, 0))} s in all -> ${out}`);
}
