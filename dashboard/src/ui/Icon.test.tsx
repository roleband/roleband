import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Icon, OPTICAL_SIZE } from "./Icon";

const drawn = (ui: React.ReactElement) => {
  const svg = render(ui).container.querySelector("svg")!;
  return { width: Number(svg.getAttribute("width")), height: Number(svg.getAttribute("height")), glyph: svg.getAttribute("class") };
};

describe("an icon is drawn at the size its caller asks for", () => {
  it("a square glyph keeps the asked size", () => {
    expect(drawn(<Icon name="more" size={14} />)).toMatchObject({ width: 14, height: 14 });
    expect(drawn(<Icon name="check" size={14} />)).toMatchObject({ width: 14, height: 14 });
  });

  it("compare is the scale, drawn a step larger so it weighs as much as the star beside it", () => {
    // The row and the docked pill ask for 14, the posting for 16, the compare screen's tab for 13.
    expect(drawn(<Icon name="compare" size={14} />)).toEqual({ width: 18, height: 18, glyph: expect.stringContaining("lucide-scale") });
    expect(drawn(<Icon name="compare" size={16} />)).toMatchObject({ width: 20, height: 20 });
    expect(drawn(<Icon name="compare" size={13} />)).toMatchObject({ width: 16, height: 16 });
  });

  it("a grown glyph draws its lines as thick as any other icon's at the asked size, so it stays one of the set", () => {
    // The stroke on screen is the stroke width scaled by the drawn size over the 24 grid.
    const line = (ui: React.ReactElement) => {
      const svg = render(ui).container.querySelector("svg")!;
      return (Number(svg.getAttribute("stroke-width")) * Number(svg.getAttribute("width"))) / 24;
    };
    for (const size of [13, 14, 15, 16]) {
      expect(line(<Icon name="compare" size={size} />), `at ${size}`).toBeCloseTo(line(<Icon name="sparkle" size={size} />), 5);
    }
    // Negative control: grown with the default stroke, the line would be a quarter thicker.
    expect(line(<Icon name="compare" size={16} />)).toBeLessThan((2 * 20) / 24 - 0.1);
  });

  it("only glyphs that need it are drawn larger", () => {
    expect(Object.keys(OPTICAL_SIZE)).toEqual(["compare"]);
  });
});
