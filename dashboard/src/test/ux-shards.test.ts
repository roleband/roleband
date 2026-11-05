// @vitest-environment node
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { specSeconds } from "../../scripts/ux-shard-weights.mjs";
import { recordedWeights, shardTestMatch, splitSpecs, testFiles, uxShard } from "../../tests/ux/shards";

const testDir = join(__dirname, "..", "..", "tests", "ux");
const specs = testFiles(testDir);
const time = (files: string[], weights: Record<string, number>) => files.reduce((sum, file) => sum + weights[file], 0);

describe("browser shards", () => {
  it.each([1, 2, 3, 4, 6])("runs every spec file on exactly one of %i shards", (total) => {
    const files = ["a", "b", "c", "new", "d", "e", "a"];
    const shards = splitSpecs(files, { "a": 9, "b": 3, "c": 3, "d": 1, "gone": 50 }, total);
    expect(shards).toHaveLength(total);
    expect(shards.flat().sort()).toEqual([...new Set(files)].sort());
  });

  it("balances by time where an equal count would hand the heavy files at the end to one shard", () => {
    const weights = { "a": 1, "b": 1, "c": 1, "d": 1, "e": 1, "f": 1, "g": 10, "h": 10 };
    const shards = splitSpecs(Object.keys(weights), weights, 2);
    expect(shards.map((files) => time(files, weights))).toEqual([13, 13]);
  });

  it("weighs a spec with no recorded time as the median one", () => {
    const weights = { "a": 4, "b": 4, "c": 2 };
    expect(splitSpecs([...Object.keys(weights), "d"], weights, 2)).toEqual([
      ["a", "d"],
      ["b", "c"],
    ]);
  });

  it("gives every runner the same split whatever order it lists the files in", () => {
    const weights = { "a": 3, "b": 3, "c": 2, "d": 2 };
    const files = Object.keys(weights);
    expect(splitSpecs([...files].reverse(), weights, 2)).toEqual(splitSpecs(files, weights, 2));
  });

  it("matches each spec file in the tree to exactly one shard, and never a file of a longer name", () => {
    const matchers = [1, 2, 3, 4].map((index) => shardTestMatch(testDir, { index, total: 4 }));
    for (const file of specs) {
      const owners = matchers.filter((patterns) => patterns.some((pattern) => pattern.test(join(testDir, file))));
      expect(owners, file).toHaveLength(1);
    }
    const companies = matchers.flat().find((pattern) => pattern.test(join(testDir, "companies.spec.ts")));
    expect(companies?.test(join(testDir, "companies-register.spec.ts"))).toBe(false);
  });

  it("gives a shard every file Playwright would run, nested or named .test", () => {
    // Built, so source-evidence.test.ts does not read them as pointers to real specs.
    const spec = (name: string) => `${name}.spec.ts`;
    const dir = mkdtempSync(join(tmpdir(), "ux-shards-"));
    mkdirSync(join(dir, "nested"));
    mkdirSync(join(dir, "node_modules"));
    for (const file of [spec("top"), `nested/${spec("deep")}`, "other.test.ts", "kept.spec.tsx", "helper.ts", `node_modules/${spec("dep")}`]) {
      writeFileSync(join(dir, file), "");
    }
    writeFileSync(join(dir, "shard-weights.json"), JSON.stringify({ [spec("top")]: 5 }));
    const found = ["kept.spec.tsx", `nested/${spec("deep")}`, "other.test.ts", spec("top")];
    expect(testFiles(dir)).toEqual(found);
    const matchers = [1, 2].map((index) => shardTestMatch(dir, { index, total: 2 }));
    for (const file of [...found, "helper.ts"]) {
      const owners = matchers.filter((patterns) => patterns.some((pattern) => pattern.test(join(dir, file))));
      expect(owners, file).toHaveLength(file === "helper.ts" ? 0 : 1);
    }
  });

  it("tells apart two files of one name in different directories", () => {
    const spec = (name: string) => `${name}.spec.ts`;
    const dir = mkdtempSync(join(tmpdir(), "ux-shards-"));
    mkdirSync(join(dir, "nested"));
    const files = [spec("top"), `nested/${spec("top")}`];
    for (const file of files) writeFileSync(join(dir, file), "");
    writeFileSync(join(dir, "shard-weights.json"), JSON.stringify({ [files[0]]: 5, [files[1]]: 5 }));
    const matchers = [1, 2].map((index) => shardTestMatch(dir, { index, total: 2 }));
    expect(matchers.map((patterns) => patterns.length)).toEqual([1, 1]);
    for (const file of files) {
      const owners = matchers.filter((patterns) => patterns.some((pattern) => pattern.test(join(dir, file))));
      expect(owners, file).toHaveLength(1);
    }
  });

  it("splits the recorded suite into four shards within a tenth of their mean", () => {
    // A spec heavier than a quarter of the suite cannot balance: split it.
    const weights = recordedWeights(testDir);
    const recorded = specs.filter((file) => file in weights);
    const times = splitSpecs(recorded, weights, 4).map((files) => time(files, weights));
    const mean = times.reduce((a, b) => a + b, 0) / 4;
    expect(Math.max(...times)).toBeLessThan(1.1 * mean);
  });

  it("charges a test written in a shared helper to the spec file that runs it", () => {
    const spec = (name: string) => `${name}.spec.ts`;
    const run = (seconds: number) => ({ tests: [{ results: [{ duration: seconds * 1000 }] }] });
    const report = {
      suites: [
        { file: spec("zoom"), specs: [{ file: "zoomHelper.ts", ...run(4) }], suites: [
          { file: "zoomHelper.ts", specs: [{ file: "zoomHelper.ts", ...run(2) }] },
        ] },
        { file: spec("zoom-webkit"), specs: [{ file: "zoomHelper.ts", ...run(3) }] },
        { file: `nested/${spec("plain")}`, specs: [{ file: `nested/${spec("plain")}`, ...run(1.25) }] },
      ],
    };
    // A second report, such as the other browser project, adds to the same files.
    expect(specSeconds([report, report])).toEqual({
      [`nested/${spec("plain")}`]: 2.5,
      [spec("zoom")]: 12,
      [spec("zoom-webkit")]: 6,
    });
  });

  it("records time only under spec files, never under a helper no shard runs", () => {
    const helpers = Object.keys(recordedWeights(testDir)).filter((file) => !/\.(spec|test)\.[cm]?[jt]sx?$/.test(file));
    expect(helpers).toEqual([]);
  });

  it("reads ROLEBAND_UX_SHARD as INDEX/TOTAL and refuses anything else", () => {
    expect(uxShard({})).toBeUndefined();
    expect(uxShard({ ROLEBAND_UX_SHARD: "3/4" })).toEqual({ index: 3, total: 4 });
    for (const value of ["0/4", "5/4", "1/0", "4", "a/b", "1/4 ", ""]) {
      expect(() => uxShard({ ROLEBAND_UX_SHARD: value }), value).toThrow("ROLEBAND_UX_SHARD");
    }
  });
});
