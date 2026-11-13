import { describe, expect, it } from "vitest";
import { shapeBlocks } from "./descriptionShape";

const kinds = (content: string) => shapeBlocks(content).map((block) => block.kind);

describe("shapeBlocks", () => {
  it("keeps prose as paragraphs, with their line breaks", () => {
    const blocks = shapeBlocks("We build tools for offices.\nForty of them.\n\nThe team is small. It ships often.");
    expect(blocks).toEqual([
      { kind: "para", lines: ["We build tools for offices.", "Forty of them."] },
      { kind: "para", lines: ["The team is small. It ships often."] },
    ]);
  });

  it("reads three or more unfinished one-line paragraphs in a row as a list", () => {
    const blocks = shapeBlocks([
      "This is a cross-functional role.",
      "Own a portfolio of programs with global scope",
      "Write the playbook a new office manager can follow",
      "Report progress to leadership in one page",
      "You will have a sponsor.",
    ].join("\n\n"));
    expect(blocks).toEqual([
      { kind: "para", lines: ["This is a cross-functional role."] },
      { kind: "list", items: [
        "Own a portfolio of programs with global scope",
        "Write the playbook a new office manager can follow",
        "Report progress to leadership in one page",
      ] },
      { kind: "para", lines: ["You will have a sponsor."] },
    ]);
  });

  it("reads a paragraph of three or more lines as a list, one item a line", () => {
    const blocks = shapeBlocks("Responsibilities include:\n\nCollaborate with engineering teams.\nWork with end customers.\nEstablish relationships with partners.\n\nYou report to the director.");
    expect(blocks).toEqual([
      { kind: "heading", text: "Responsibilities include" },
      { kind: "list", items: ["Collaborate with engineering teams.", "Work with end customers.", "Establish relationships with partners."] },
      { kind: "para", lines: ["You report to the director."] },
    ]);
  });

  it("leaves two unfinished lines, and finished sentences, as paragraphs", () => {
    expect(kinds("Join us\n\nSee you soon")).toEqual(["para", "para"]);
    expect(kinds("You lead programs.\n\nYou write clearly.\n\nYou coach others.")).toEqual(["para", "para", "para"]);
  });

  it("reads a short line ending in a colon as a sub-heading, without its colon", () => {
    const blocks = shapeBlocks("The Community you will join:\n\nThe team runs forty offices.");
    expect(blocks[0]).toEqual({ kind: "heading", text: "The Community you will join" });
    expect(blocks[1].kind).toBe("para");
  });

  it("does not make a heading of a closing line, a long lead-in or a sentence that only ends in a colon", () => {
    expect(kinds("Send your questions to:")).toEqual(["para"]);
    const long = "In this part of the job, working across every office and every region we operate in, you will be expected to:";
    expect(kinds(`${long}\n\nMap how teams operate.`)).toEqual(["para", "para"]);
    expect(kinds("A core pillar is modernisation. In this part of the job, you will:\n\nMap how teams operate.")[0]).toBe("para");
  });

  it("takes bullet marks as a list and drops the marks, but keeps a hyphenated word", () => {
    expect(shapeBlocks("• Medical cover\n• Paid leave\n\n- A learning allowance")).toEqual([
      { kind: "list", items: ["Medical cover", "Paid leave", "A learning allowance"] },
    ]);
    expect(kinds("-based in Seattle.")).toEqual(["para"]);
  });

  it("keeps a mark that opens the employer's own word", () => {
    // A bullet is a mark and a space. Stripped without one, "*nix" becomes
    // "nix" and the requirement changes.
    expect(shapeBlocks("*nix experience is required.")).toEqual([
      { kind: "para", lines: ["*nix experience is required."] },
    ]);
    expect(shapeBlocks("* Medical cover\n* Paid leave\n* Equity")).toEqual([
      { kind: "list", items: ["Medical cover", "Paid leave", "Equity"] },
    ]);
  });

  it("reads a short title with no closing mark, before whole sentences, as a sub-heading", () => {
    const blocks = shapeBlocks([
      "Team Leadership",
      "Hire, develop and manage engineers on site. Set clear expectations.",
      "Build a 24x7 on-call rotation with your team.",
      "Site Delivery",
      "Own build timelines from site readiness to handoff.",
    ].join("\n\n"));
    expect(blocks.map((block) => block.kind)).toEqual(["heading", "para", "para", "heading", "para"]);
    expect(blocks[0]).toEqual({ kind: "heading", text: "Team Leadership" });
    expect(blocks[3]).toEqual({ kind: "heading", text: "Site Delivery" });
  });

  it("a title can stand over a list", () => {
    expect(kinds("What we offer\n\n• Medical cover\n• Paid leave")).toEqual(["heading", "list"]);
  });

  it("leaves a short line as prose when nothing marks it as a title", () => {
    // The last line of a section has nothing to stand over.
    expect(kinds("We read every application.\n\nApply today")).toEqual(["para", "para"]);
    // A long unfinished line, a line that opens in lower case and a line with a sentence inside it.
    expect(kinds("For Bay Area based hires the estimated annual salary range\n\nPay varies by place.")[0]).toBe("para");
    expect(kinds("and much more\n\nPay varies by place.")[0]).toBe("para");
    expect(kinds("Ready? Join us\n\nPay varies by place.")[0]).toBe("para");
    expect(kinds("For Bay Area hires: $174,000\n\nPay varies by place.")[0]).toBe("para");
    // Two unfinished lines in a row: neither stands over whole sentences.
    expect(kinds("Team Leadership\n\nPeople first\n\nOne more line")).toEqual(["list"]);
  });

  it("a heading can open a list", () => {
    expect(kinds("A typical day:\n\nRun programs\n\nMap a process\n\nCoach two people")).toEqual(["heading", "list"]);
  });
});
