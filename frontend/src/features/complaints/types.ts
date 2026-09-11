import type { components } from '@/types/api'

/**
 * Complaint types, aliased from the generated contract rather than re-declared.
 *
 * `metaApi.ts` hand-rolls its own interfaces because the vocabulary shape is
 * small and stable. The complaint shape is neither - it is the contract this
 * whole project is built around - so every type here is a direct alias into
 * `components['schemas']`. An alias cannot drift from `openapi.json`; a
 * hand-copied interface eventually would.
 */
export type Complaint = components['schemas']['ComplaintRead']
export type ComplaintListItem = components['schemas']['ComplaintListItem']
export type ComplaintPage = components['schemas']['ComplaintPage']
export type ComplaintCreate = components['schemas']['ComplaintCreate']
export type ComplaintUpdate = components['schemas']['ComplaintUpdate']
export type ComplaintSort = components['schemas']['ComplaintSort']
export type StatusTransition = components['schemas']['StatusTransitionRead']
export type TransitionRequest = components['schemas']['TransitionRequest']

export type ComplaintStatus = components['schemas']['ComplaintStatus']
export type Severity = components['schemas']['Severity']
export type Priority = components['schemas']['Priority']

export type WorkflowResponse = components['schemas']['WorkflowResponse']
export type TransitionOption = components['schemas']['TransitionOptionResponse']

/**
 * The complaint list query, as the API accepts it.
 *
 * Mirrors `ComplaintFilters` field-for-field but as plain optional properties:
 * the backend's `extra='forbid'` rejects any key it does not recognise, so
 * this type is what stops a typo from becoming a silent 422 at request time
 * instead of a compile error.
 */
export interface ComplaintFilters {
  q?: string
  status?: ComplaintStatus[]
  severity?: Severity[]
  priority?: Priority[]
  complaint_type?: components['schemas']['ComplaintType'][]
  source?: components['schemas']['ComplaintSource'][]
  customer_name?: string
  product_name?: string
  batch_number?: string
  assigned_investigator_id?: number
  unassigned_only?: boolean
  overdue_only?: boolean
  date_from?: string
  date_to?: string
  sort?: ComplaintSort
  page?: number
  page_size?: number
}
