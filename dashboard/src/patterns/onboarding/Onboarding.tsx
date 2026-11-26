import { useId, type ReactNode } from "react";
import { sharedOnboardSteps } from "../../copy/gen/shared";
import "./onboarding.css";

/* Onboarding: what a feature shows before it is set up, the app's one way to
   introduce a feature. It is a pattern of its own, apart from the working
   screens: a headline at its own size, one line, one picture, at most three
   steps on one line, one action at a time with its live state, and one line
   on cost and privacy. The picture shows the shape of the result, never a
   sample of its content. Once the feature is set up the working screen takes
   its place; the two are never on screen together. */
export function Onboarding({ headline, line, picture, steps, current, children, footnote }: {
  headline: ReactNode;
  line: ReactNode;
  picture?: ReactNode;
  /** At most three, in order. */
  steps: readonly ReactNode[];
  /** The index of the step the person is on. */
  current: number;
  /** The action, with its live state. */
  children: ReactNode;
  footnote?: ReactNode;
}) {
  const headingId = useId();
  return (
    <section className="onboard" aria-labelledby={headingId}>
      <header className="onboard-head">
        <h2 id={headingId} className="onboard-headline">{headline}</h2>
        <p className="onboard-line">{line}</p>
      </header>
      {picture}
      <ol className="onboard-steps" aria-label={sharedOnboardSteps()}>
        {steps.map((step, i) => (
          <li
            key={i}
            aria-current={i === current ? "step" : undefined}
            className={i < current ? "is-done" : undefined}
          >
            <span className="onboard-step-mark" aria-hidden="true">{i + 1}</span>
            {step}
          </li>
        ))}
      </ol>
      <div className="onboard-action">{children}</div>
      {footnote && <p className="onboard-footnote">{footnote}</p>}
    </section>
  );
}
