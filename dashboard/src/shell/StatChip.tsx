import { ReactNode } from "react";
import { NavLink } from "react-router-dom";

/* The top bar's count chip: a number and the noun it counts, in one of three
 * shapes — a fact, a lens toggle, or a link to the list it counts. One recipe
 * spelled once, so no caller writes `.stat-chip` by hand. */
type Base = {
  n: ReactNode;
  label: string;
  /** The live-market hue for a count that is market data (new roles). */
  good?: boolean;
  ariaLabel: string;
  title?: string;
  /** A hook for the compact bar's rules, which hide a chip by what it counts. */
  className?: string;
};

type Shape =
  | { kind?: "fact" }
  | { kind: "lens"; onClick: () => void; pressed: boolean }
  | { kind: "link"; to: string; state?: unknown };

export function StatChip(props: Base & Shape) {
  const base = ["stat-chip", props.good && "good", props.className].filter(Boolean).join(" ");
  const body = (
    <>
      {/* The space is for the accessible name, not the layout (flex drops it):
          without it the visible text reads "4compare", which the name
          "4 roles in compare" does not contain. */}
      <span className="n">{props.n}</span>{" "}
      <span className="l">{props.label}</span>
    </>
  );
  if (props.kind === "lens") {
    return (
      <button
        className={`${base} clickable`}
        onClick={props.onClick}
        aria-label={props.ariaLabel}
        aria-pressed={props.pressed}
        title={props.title}
      >
        {body}
      </button>
    );
  }
  if (props.kind === "link") {
    return (
      <NavLink
        to={props.to}
        state={props.state}
        className={`${base} clickable`}
        aria-label={props.ariaLabel}
        title={props.title}
      >
        {body}
      </NavLink>
    );
  }
  return (
    <div className={base} role="group" aria-label={props.ariaLabel}>
      {body}
    </div>
  );
}
