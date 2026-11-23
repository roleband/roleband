/* What a paste into the notes keeps. The page holds text, lists, links and
 * checklists, kept as Markdown, so a table or a picture has no place on it as
 * it is: the editor would run a table's cells together into one word and drop
 * a picture without a sign. Pasted HTML is rewritten first into what the page
 * can hold. */

/** Elements that start a line of their own. */
const BLOCK_SELECTOR = /* not copy */ "p, div, li, ul, ol, h1, h2, h3, h4, h5, h6, blockquote, pre, table";

/** A copy of a cell whose lines and line breaks stand apart by a space, on
 *  both sides, so no two of its lines run together. */
function spacedCell(cell: HTMLTableCellElement): HTMLTableCellElement {
  const copy = cell.cloneNode(true) as HTMLTableCellElement;
  for (const end of Array.from(copy.querySelectorAll(`br, ${BLOCK_SELECTOR}`))) {
    end.before(" ");
    end.after(" ");
  }
  return copy;
}

/** A cell as one line of text, spaces folded: a column's name. */
const cellText = (cell: HTMLTableCellElement) => (spacedCell(cell).textContent ?? "").replace(/\s+/g, " ").trim();

/** A cell as one line: its words, spaces folded, and its links kept as links
 *  (a picture on the web among them). Empty when the cell says nothing. */
function cellLine(doc: Document, cell: HTMLTableCellElement): Node[] {
  const parts: (string | Element)[] = [];
  const walk = (node: Node) => {
    for (const child of Array.from(node.childNodes)) {
      const href = child.nodeName === "A" ? (child as Element).getAttribute("href") : null;
      if (child.nodeType === Node.TEXT_NODE) parts.push(child.textContent ?? "");
      else if (href) {
        const link = doc.createElement("a");
        link.setAttribute("href", href);
        link.textContent = (child.textContent ?? "").replace(/\s+/g, " ").trim() || href;
        parts.push(link);
      } else walk(child);
    }
  };
  walk(spacedCell(cell));
  const line: Node[] = [];
  let words = "";
  const endWords = () => {
    if (words) line.push(doc.createTextNode(words.replace(/\s+/g, " ")));
    words = "";
  };
  for (const part of parts) {
    if (typeof part === "string") words += part;
    else {
      endWords();
      line.push(part);
    }
  }
  endWords();
  const [first, last] = [line[0], line[line.length - 1]];
  if (first?.nodeType === Node.TEXT_NODE) first.textContent = first.textContent!.trimStart();
  if (last?.nodeType === Node.TEXT_NODE) last.textContent = last.textContent!.trimEnd();
  return line.filter((node) => node.textContent);
}

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
  const head = hasHead(rows) ? Array.from(rows[0].cells, cellText) : null;
  const body = head && rows.length > 1 ? rows.slice(1) : rows;
  const list = doc.createElement("ul");
  for (const row of body) {
    const named = head && row !== rows[0];
    const item = doc.createElement("li");
    Array.from(row.cells).forEach((cell, at) => {
      const line = cellLine(doc, cell);
      if (line.length === 0) return;
      if (item.hasChildNodes()) item.append(" · ");
      if (named && head[at]) item.append(`${head[at]}: `);
      item.append(...line);
    });
    if (item.hasChildNodes()) list.append(item);
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
