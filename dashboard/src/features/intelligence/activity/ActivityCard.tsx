import { Link } from "react-router-dom";
import { ACTIVITY_ROUTE } from "../../../routing/paths";
import "./activity-card.css";
import { activityCardBody, activityCardOpen, activityCardTitle } from "../../../copy/gen/activity";

/** The AI tab's way into Settings › AI › Activity. */
export function ActivityCard() {
  return (
    <section className="intel-card" aria-labelledby="activity-card-title">
      <div className="intel-head">
        <div className="intel-head-title">
          <h2 id="activity-card-title">{activityCardTitle()}</h2>
        </div>
        <Link className="ui-btn ui-btn-ghost ui-btn-md" to={ACTIVITY_ROUTE}>
          {activityCardOpen()}
        </Link>
      </div>
      <p className="activity-card-body">{activityCardBody()}</p>
    </section>
  );
}
