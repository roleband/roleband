/* Applications: the pipeline board, one application, its activity, and the
   comment and interview writes on it. One domain of the typed client;
   `index.ts` composes `api`. A stage move, a priority, the notes and the next
   step are `setPursuit` in `profile.ts`, the route every surface writes a
   pursuit through. */

import type { Schemas } from "./schemas";
import { deleteJSON, getJSON, patchJSON, postJSON, putJSON } from "./transport";

/** One application as the board shows it. A starred role with no pursuit yet
 *  is a card at `saved` with `pursuit_id` null. */
export type ApplicationCard = Schemas["ApplicationCard"];

export type ApplicationBoard = Schemas["ApplicationBoardResponse"];

/** One application: its card, every interview, and when it reached each stage. */
export type ApplicationDetail = Schemas["ApplicationDetailResponse"];

export type ApplicationInterview = Schemas["ApplicationInterview"];

/** One entry of an application's feed: a comment or a recorded change. */
export type ActivityItem = Schemas["ApplicationActivityResponse"]["items"][number];

/** An interview as a write sends it. */
export type InterviewWrite = Schemas["InterviewWrite"];

/** A partial interview write: an absent field is left as it is. */
export type InterviewUpdate = Schemas["InterviewUpdate"];

/** One interview or dated next step on the calendar, naming its application by job id. */
export type ApplicationCalendarItem = Schemas["ApplicationCalendarResponse"]["items"][number];

export const applicationsApi = {
  applications: (signal?: AbortSignal) => getJSON<ApplicationBoard>("/api/applications", signal),
  application: (jobId: number, signal?: AbortSignal) =>
    getJSON<ApplicationDetail>(`/api/applications/${jobId}`, signal),
  /** Every interview and dated next step from `start` up to `end`, six weeks at most. */
  calendar: (start: Date, end: Date, signal?: AbortSignal) =>
    getJSON<Schemas["ApplicationCalendarResponse"]>(
      `/api/applications/calendar?${new URLSearchParams({ start: start.toISOString(), end: end.toISOString() })}`,
      signal,
    ),
  activity: (jobId: number, signal?: AbortSignal) =>
    getJSON<Schemas["ApplicationActivityResponse"]>(`/api/applications/${jobId}/activity`, signal),
  addComment: (jobId: number, body: string) =>
    postJSON<Schemas["ApplicationCommentResponse"]>(`/api/jobs/${jobId}/pursuit/comments`, { body }),
  editComment: (jobId: number, commentId: number, body: string) =>
    putJSON<Schemas["ApplicationCommentResponse"]>(`/api/jobs/${jobId}/pursuit/comments/${commentId}`, { body }),
  deleteComment: (jobId: number, commentId: number) =>
    deleteJSON<Schemas["ApplicationDeleted"]>(`/api/jobs/${jobId}/pursuit/comments/${commentId}`),
  addInterview: (jobId: number, interview: InterviewWrite) =>
    postJSON<Schemas["ApplicationInterviewResponse"]>(`/api/jobs/${jobId}/pursuit/interviews`, interview),
  updateInterview: (jobId: number, interviewId: number, update: InterviewUpdate) =>
    patchJSON<Schemas["ApplicationInterviewResponse"]>(
      `/api/jobs/${jobId}/pursuit/interviews/${interviewId}`, update,
    ),
  deleteInterview: (jobId: number, interviewId: number) =>
    deleteJSON<Schemas["ApplicationDeleted"]>(`/api/jobs/${jobId}/pursuit/interviews/${interviewId}`),
};
