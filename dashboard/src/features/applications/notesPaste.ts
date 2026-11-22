/* What a paste into the notes keeps. The page holds text, lists, links and
 * checklists, kept as Markdown, so a table or a picture has no place on it as
 * it is: the editor would run a table's cells together into one word and drop
 * a picture without a sign. Pasted HTML is rewritten first into what the page
 * can hold. */

/** Elements that start a line of their own. */
const BLOCK_SELECTOR = /* not copy */ "p, div, li, ul, ol, h1, h2, h3, h4, h5, h6, blockquote, pre, table";

/** A cell as one line of text: its lines and line breaks apart by a space,
 *  spaces folded. */
function cellText(cell: HTMLTableCellElement): string {
  const copy = cell.cloneNode(true) as HTMLTableCellElement;
  for (const end of Array.from(copy.querySelectorAll(`br, ${BLOCK_SELECTOR}`))) end.after(" ");
  return (copy.textContent ?? "").replace(/\s+/g, " ").trim();
}

/** The cells of a row as text. */
const cellTexts = (row: HTMLTableRowElement) => Array.from(row.cells, cellText);

/** Whether a table's first row names its columns. */
const hasHead = (rows: HTMLTableRowElement[]) => {
  const first = rows[0];
  if (!first) return false;
  return first.parentElement?.tagName === "THEAD" || Array.from(first.cells).every((cell) => cell.tagName === "TH");
};

/** A table as a list, one line per row, its cells apart: "Round: Screen ·
 *  Who: Sam" when the first row names the columns, "Screen · Sam" when not.
 *  A table one cell wide is a frame around content, as mail lays a letter
 *  out: its cells' content stands as it is, in order. */
function tableAsLines(doc: Document, table: HTMLTableElement) {
  const rows = Array.from(table.rows);
  if (rows.every((row) => row.cells.length <= 1)) {
    const content = doc.createDocumentFragment();
    for (const row of rows) {
      for (const cell of Array.from(row.cells)) {
        // A cell of words alone becomes a line, so the rows stay apart.
        const line = cell.querySelector(BLOCK_SELECTOR) ? content : content.appendChild(doc.createElement("p"));
        line.append(...Array.from(cell.childNodes));
      }
    }
    table.replaceWith(content);
    return;
  }
  const head = hasHead(rows) ? cellTexts(rows[0]) : null;
  const body = head && rows.length > 1 ? rows.slice(1) : rows;
  const list = doc.createElement("ul");
  for (const row of body) {
    const named = head && row !== rows[0];
    const line = cellTexts(row)
      .map((text, at) => (text && named && head[at] ? `${head[at]}: ${text}` : text))
      .filter(Boolean)
      .join(" · ");
    if (!line) continue;
    const item = doc.createElement("li");
    item.textContent = line;
    list.append(item);
  }
  table.replaceWith(list);
}

/** An image the size of a dot: mail's read receipts, not a picture. */
const isDot = (image: HTMLImageElement) =>
  ["width", "height"].some((side) => {
    const size = image.getAttribute(side);
    return size != null && Number.parseFloat(size) <= 2;
  });

/** Pasted HTML as the notes can hold it, and how many pictures it had that
 *  the notes cannot keep. A picture on the web stays as a link to it, named
 *  by its own description or by `pictureName`; a picture pasted as data, such
 *  as a screenshot, has no address to keep and is counted. */
export function readablePaste(html: string, pictureName: string): { html: string; leftOut: number } {
  const doc = new DOMParser().parseFromString(html, "text/html");
  let leftOut = 0;
  for (const image of Array.from(doc.querySelectorAll("img"))) {
    const words = (image.getAttribute("alt") ?? "").trim();
    const source = image.getAttribute("src") ?? "";
    if (isDot(image)) {
      image.remove();
    } else if (image.closest("a")) {
      // A linked picture: the link stays, named by the picture.
      image.replaceWith(doc.createTextNode(words || (image.closest("a")!.textContent?.trim() ? "" : pictureName)));
    } else if (/^https?:/i.test(source)) {
      const link = doc.createElement("a");
      link.setAttribute("href", source);
      link.textContent = words || pictureName;
      image.replaceWith(link);
    } else {
      leftOut += 1;
      image.replaceWith(doc.createTextNode(words));
    }
  }
  // Tables after pictures, so a picture in a cell is counted or kept as a
  // link's name. The innermost table first: an outer one then reads its
  // cells' new text.
  for (const table of Array.from(doc.querySelectorAll("table")).reverse()) tableAsLines(doc, table);
  return { html: doc.body.innerHTML, leftOut };
}

/** How many pictures a paste or a drop carries as files alone, with no text
 *  or page around them: what the notes leave out of it. */
export function pictureFiles(data: DataTransfer | null): number {
  if (!data) return 0;
  return Array.from(data.files).filter((file) => file.type.startsWith("image/")).length;
}
