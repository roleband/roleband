import "./ProgressBar.css";

// ProgressBar (F1 primitive): a determinate bar with its value exposed to
// assistive technology, or, with no value, an indeterminate one for a wait
// nothing can measure (one request): a segment runs along the track, and no
// value is claimed (ARIA reads a progressbar without aria-valuenow as
// indeterminate).

export type ProgressBarProps = {
  /** What is being counted or waited for; the accessible name. */
  label: string;
  className?: string;
} & ({ value: number; max: number } | { value?: undefined; max?: undefined });

export function ProgressBar({ value, max, label, className }: ProgressBarProps) {
  if (value === undefined || max === undefined) {
    return (
      <span
        className={`ui-progress ui-progress-indeterminate${className ? ` ${className}` : ""}`}
        role="progressbar"
        aria-label={label}
      >
        <i />
      </span>
    );
  }
  const bounded = Math.max(0, Math.min(value, max));
  const percent = max > 0 ? Math.round((100 * bounded) / max) : 0;
  return (
    <span
      className={`ui-progress${className ? ` ${className}` : ""}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={bounded}
    >
      <i style={{ width: `${percent}%` }} />
    </span>
  );
}
