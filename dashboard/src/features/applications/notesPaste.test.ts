import { describe, expect, it } from "vitest";
import { readablePaste } from "./notesPaste";

/** The pasted HTML as the notes would read it: each line of text it holds. */
const lines = (html: string) => {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return Array.from(doc.body.querySelectorAll("li, p"), (block) => block.textContent);
};

describe("a pasted table", () => {
  // As a document editor puts a table on the clipboard: header cells, then
  // a row per interview round, each cell's text in a paragraph and a span.
  const rounds = `<meta charset="utf-8"><b id="docs-internal-guid-1"><div dir="ltr"><table><colgroup><col><col></colgroup><tbody>
    <tr><th><p dir="ltr"><span>Round</span></p></th><th><p dir="ltr"><span>Who</span></p></th></tr>
    <tr><td><p dir="ltr"><span>Screen</span></p></td><td><p dir="ltr"><span>Sam</span></p></td></tr>
    <tr><td><p><span>Panel</span></p></td><td><p><span>Mo and   Ana</span></p></td></tr>
  </tbody></table></div></b>`;

  it("becomes a line per row, each cell named by its column, never one run-together word", () => {
    const { html, leftOut } = readablePaste(rounds, "Picture");
    expect(lines(html)).toEqual(["Round: Screen · Who: Sam", "Round: Panel · Who: Mo and Ana"]);
    expect(html).not.toContain("<table");
    expect(html).not.toMatch(/RoundWho|ScreenSam/);
    expect(leftOut).toBe(0);
  });

  it("keeps its cells apart when no row names the columns, and skips an empty row and cell", () => {
    const sheet = `<google-sheets-html-origin><table><tbody>
      <tr><td>Stripe</td><td>Applied</td><td></td></tr>
      <tr><td></td><td></td><td></td></tr>
      <tr><td>Notion</td><td>Screen</td><td>Fri</td></tr>
    </tbody></table></google-sheets-html-origin>`;
    expect(lines(readablePaste(sheet, "Picture").html)).toEqual(["Stripe · Applied", "Notion · Screen · Fri"]);
  });

  it("names the cells from a head row, and a table that is only a head says its names", () => {
    const head = "<table><thead><tr><td>Round</td><td>Who</td></tr></thead><tbody><tr><td>Screen</td><td>Sam</td></tr></tbody></table>";
    expect(lines(readablePaste(head, "Picture").html)).toEqual(["Round: Screen · Who: Sam"]);
    const only = "<table><tr><th>Round</th><th>Who</th></tr></table>";
    expect(lines(readablePaste(only, "Picture").html)).toEqual(["Round · Who"]);
  });

  it("is let go of when it is one cell wide, as a letter laid out in mail is, keeping what is in it", () => {
    const letter = `<table width="100%"><tr><td><p>Hi Sam,</p><p>Thanks for your time. <a href="https://cal.example.test/book">Pick a slot</a></p></td></tr>
      <tr><td><p>Best, Mo</p></td></tr></table>`;
    const { html } = readablePaste(letter, "Picture");
    expect(html).not.toContain("<table");
    expect(html).not.toContain("<li");
    expect(lines(html)).toEqual(["Hi Sam,", "Thanks for your time. Pick a slot", "Best, Mo"]);
    expect(html).toContain('href="https://cal.example.test/book"');
  });

  it("keeps a one-column table's rows apart when its cells hold words alone", () => {
    const list = "<table><tr><td>Hi Sam,</td></tr><tr><td>Thanks for your <b>time</b>.</td></tr></table>";
    expect(lines(readablePaste(list, "Picture").html)).toEqual(["Hi Sam,", "Thanks for your time."]);
  });

  it("keeps a cell's lines apart within its row", () => {
    const cells = `<table><tr><th>Round</th><th>Who</th></tr>
      <tr><td>Panel</td><td><p>Mo</p><p>Ana</p></td></tr>
      <tr><td>Onsite</td><td>Lee<br>Kim</td></tr></table>`;
    expect(lines(readablePaste(cells, "Picture").html)).toEqual(["Round: Panel · Who: Mo Ana", "Round: Onsite · Who: Lee Kim"]);
  });

  it("keeps the words before a line in a cell apart from that line", () => {
    const cells = "<table><tr><td>Panel</td><td>Mo<div>Ana</div></td></tr></table>";
    expect(lines(readablePaste(cells, "Picture").html)).toEqual(["Panel · Mo Ana"]);
  });

  it("keeps a cell's links as links, a picture on the web among them", () => {
    const cells = `<table><tr><th>Round</th><th>Notes</th></tr>
      <tr><td><a href="https://jobs.example/round">Panel</a></td><td>See <img src="https://x.example/plan.png" alt="Floor plan"> first</td></tr></table>`;
    const { html, leftOut } = readablePaste(cells, "Picture");
    expect(lines(html)).toEqual(["Round: Panel · Notes: See Floor plan first"]);
    const links = Array.from(new DOMParser().parseFromString(html, "text/html").querySelectorAll("li a"), (link) => [link.textContent, link.getAttribute("href")]);
    expect(links).toEqual([["Panel", "https://jobs.example/round"], ["Floor plan", "https://x.example/plan.png"]]);
    expect(leftOut).toBe(0);
  });

  it("counts a screenshot in a cell as left out, keeping its description", () => {
    const shot = '<table><tr><td>Floor plan</td><td><img src="data:image/png;base64,iVBORw0KGgo=" alt="Third floor"></td></tr></table>';
    const { html, leftOut } = readablePaste(shot, "Picture");
    expect(lines(html)).toEqual(["Floor plan · Third floor"]);
    expect(leftOut).toBe(1);
  });
});

describe("a pasted picture", () => {
  it("on the web stays as a link to it, named by its own description or as a picture", () => {
    const page = '<p>The office <img src="https://img.example.test/office.jpg" alt="Office floor plan"></p><p><img src="https://img.example.test/team.png"></p>';
    const { html, leftOut } = readablePaste(page, "Picture");
    const doc = new DOMParser().parseFromString(html, "text/html");
    expect(Array.from(doc.querySelectorAll("a"), (link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["Office floor plan", "https://img.example.test/office.jpg"],
      ["Picture", "https://img.example.test/team.png"],
    ]);
    expect(doc.querySelector("img")).toBeNull();
    expect(leftOut).toBe(0);
  });

  it("pasted as data, such as a screenshot, is counted as left out, its description kept as words", () => {
    const shot = '<p>Before <img src="data:image/png;base64,iVBORw0KGgo=" alt="Offer letter"> after</p><img src="blob:https://app.example.test/3f2a">';
    const { html, leftOut } = readablePaste(shot, "Picture");
    expect(leftOut).toBe(2);
    expect(html).not.toContain("<img");
    expect(html).not.toContain("data:");
    expect(lines(html)).toEqual(["Before Offer letter after"]);
  });

  it("inside a link leaves the link, named by the picture only when the link has no words", () => {
    const linked = '<a href="https://jobs.example.test/1"><img src="https://img.example.test/logo.png"></a> <a href="https://jobs.example.test/2"><img src="https://img.example.test/x.png">Apply here</a>';
    const doc = new DOMParser().parseFromString(readablePaste(linked, "Picture").html, "text/html");
    expect(Array.from(doc.querySelectorAll("a"), (link) => link.textContent)).toEqual(["Picture", "Apply here"]);
    expect(doc.querySelector("a a")).toBeNull();
  });

  it("the size of a dot, as mail's read receipts are, goes without a word", () => {
    const mail = '<p>See you Friday<img src="https://track.example.test/o.gif" width="1" height="1"></p>';
    const { html, leftOut } = readablePaste(mail, "Picture");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<a");
    expect(leftOut).toBe(0);
  });
});

it("leaves a paste with no table and no picture as it came", () => {
  const plain = '<p>Ask about <strong>the team</strong></p><ul><li>Read the <a href="https://example.test/post">posting</a></li></ul>';
  expect(readablePaste(plain, "Picture")).toEqual({ html: plain, leftOut: 0 });
});
