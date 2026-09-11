import { api } from '@/app/api'

import type {
  Complaint,
  ComplaintCreate,
  ComplaintFilters,
  ComplaintPage,
  ComplaintUpdate,
  StatusTransition,
  TransitionRequest,
  WorkflowResponse,
} from './types'

/**
 * Build the query string for GET /complaints by hand rather than handing the
 * filters object to `fetchBaseQuery`'s `params` option.
 *
 * `ComplaintFilters` has repeatable fields - `status`, `severity` and friends -
 * and the backend (a FastAPI query-parameter model) expects those as repeated
 * keys: `status=new&status=under_review`. `fetchBaseQuery` builds its `params`
 * option with `new URLSearchParams(params)`, which stringifies an array with
 * `Array.prototype.toString` into a single comma-joined value instead of
 * repeating the key - a shape the backend's `extra='forbid'` model would
 * reject outright rather than silently misread.
 */
function buildComplaintQuery(filters: ComplaintFilters): string {
  const params = new URLSearchParams()

  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, String(item))
    } else {
      params.set(key, String(value))
    }
  }

  return params.toString()
}

const LIST_TAG = { type: 'ComplaintList' as const, id: 'LIST' }
const timelineTag = (id: number) => ({ type: 'Complaint' as const, id: `${id}-timeline` })

export const complaintsApi = api.injectEndpoints({
  endpoints: (build) => ({
    getComplaints: build.query<ComplaintPage, ComplaintFilters | void>({
      query: (filters) => `/complaints?${buildComplaintQuery(filters ?? {})}`,
      providesTags: (result) =>
        result
          ? [
              ...result.items.map((item) => ({ type: 'Complaint' as const, id: item.id })),
              LIST_TAG,
            ]
          : [LIST_TAG],
    }),

    getComplaint: build.query<Complaint, number>({
      query: (id) => `/complaints/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Complaint', id }],
    }),

    createComplaint: build.mutation<Complaint, ComplaintCreate>({
      query: (body) => ({ url: '/complaints', method: 'POST', body }),
      invalidatesTags: [LIST_TAG, 'Dashboard'],
    }),

    updateComplaint: build.mutation<Complaint, { id: number; body: ComplaintUpdate }>({
      // exclude_unset only works if fields genuinely absent from the payload
      // never reach the wire; RTK Query's fetch body already drops `undefined`
      // values via JSON.stringify, so a caller sending `{ batch_number: '...' }`
      // sends exactly that key and nothing else.
      query: ({ id, body }) => ({ url: `/complaints/${id}`, method: 'PATCH', body }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'Complaint', id }, LIST_TAG],
    }),

    deleteComplaint: build.mutation<void, number>({
      query: (id) => ({ url: `/complaints/${id}`, method: 'DELETE' }),
      invalidatesTags: (_result, _error, id) => [{ type: 'Complaint', id }, LIST_TAG],
    }),

    transitionComplaint: build.mutation<Complaint, { id: number; body: TransitionRequest }>({
      query: ({ id, body }) => ({
        url: `/complaints/${id}/transition`,
        method: 'POST',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'Complaint', id },
        timelineTag(id),
        LIST_TAG,
        'Dashboard',
        'AuditTrail',
      ],
    }),

    getComplaintTimeline: build.query<StatusTransition[], number>({
      query: (id) => `/complaints/${id}/transitions`,
      providesTags: (_result, _error, id) => [timelineTag(id)],
    }),

    // Not complaint-specific, but the lifecycle table a complaint's action
    // buttons are derived from - kept here rather than in metaApi so every
    // complaint-workflow consumer has one import to make.
    getWorkflow: build.query<WorkflowResponse, void>({
      query: () => '/meta/workflow',
      providesTags: ['Vocabulary'],
    }),
  }),
})

export const {
  useGetComplaintsQuery,
  useGetComplaintQuery,
  useCreateComplaintMutation,
  useUpdateComplaintMutation,
  useDeleteComplaintMutation,
  useTransitionComplaintMutation,
  useGetComplaintTimelineQuery,
  useGetWorkflowQuery,
} = complaintsApi

export type { Complaint, ComplaintCreate, ComplaintFilters, ComplaintPage, ComplaintUpdate }
