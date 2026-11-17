import { forwardRef } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { buttonClasses, type ButtonSize, type ButtonVariant } from "./Button";
import "./Button.css";

/* A move to another screen of the app, in the look of `ui/Button`
 * (docs/ui.md, Controls). It stays a router `Link`, so it keeps what a
 * `<button>` cannot: an address, middle-click and open in a new tab, and the
 * link role. Variants and sizes are Button's, with the same defaults; `link`
 * is the text rank and takes no size. There is no `disabled`: a move that is
 * not available is not rendered. */
export interface RouterLinkProps extends LinkProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export const RouterLink = forwardRef<HTMLAnchorElement, RouterLinkProps>(function RouterLink(
  { variant = "ghost", size = "md", className, ...rest },
  ref,
) {
  return <Link ref={ref} className={buttonClasses(variant, size, className)} {...rest} />;
});
