import type { ReactNode } from "react";

/** Page chrome only. The route owns its measure, wording and actions. */
export function PageHeader({ title, eyebrow, meta, actions, offScreen }: {
  title: string;
  /** The screen leads with a row of its own and leaves its name to the top
   *  bar and the rail: the title is the page's heading for assistive
   *  technology and is not drawn. */
  offScreen?: boolean;
  /** A recognition label over the title, such as where a flow stands. */
  eyebrow?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  if (offScreen) return <h1 className="sr-only">{title}</h1>;
  return (
    <section className="page-hero">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {meta}
      </div>
      {actions}
    </section>
  );
}
