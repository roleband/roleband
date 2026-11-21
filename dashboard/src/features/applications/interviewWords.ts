import type { ApplicationInterview } from "../../api";
import {
  applicationsInterviewFormatOnsite,
  applicationsInterviewFormatPhone,
  applicationsInterviewFormatVideo,
  applicationsInterviewOutcomeCancelled,
  applicationsInterviewOutcomeNotPassed,
  applicationsInterviewOutcomePassed,
} from "../../copy/gen/applications";

/** What a round's format is called wherever a round is shown. */
export const FORMAT_LABEL: Record<NonNullable<ApplicationInterview["format"]>, () => string> = {
  video: applicationsInterviewFormatVideo,
  phone: applicationsInterviewFormatPhone,
  onsite: applicationsInterviewFormatOnsite,
};

/** What a round's outcome is called, in the order they are offered. */
export const OUTCOME_LABEL: Record<NonNullable<ApplicationInterview["outcome"]>, () => string> = {
  passed: applicationsInterviewOutcomePassed,
  not_passed: applicationsInterviewOutcomeNotPassed,
  cancelled: applicationsInterviewOutcomeCancelled,
};
