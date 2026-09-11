import { api } from '@/app/api'
import type { components } from '@/types/api'

type ExtractRequest = components['schemas']['ExtractRequest']
type ExtractedComplaint = components['schemas']['ExtractedComplaint']
type AssessResponse = components['schemas']['AssessResponse']

export const aiApi = api.injectEndpoints({
  endpoints: (build) => ({
    extractComplaint: build.mutation<ExtractedComplaint, ExtractRequest>({
      query: (body) => ({ url: '/ai/extract', method: 'POST', body }),
    }),
    assessComplaint: build.mutation<AssessResponse, number>({
      query: (id) => ({ url: `/ai/complaints/${id}/assess`, method: 'POST' }),
      invalidatesTags: (_result, _error, id) => [{ type: 'Complaint', id }],
    }),
    getSavedAssessment: build.query<AssessResponse, number>({
      query: (id) => `/ai/complaints/${id}/assessment`,
      providesTags: (_result, _error, id) => [{ type: 'Complaint', id }],
    }),
  }),
})

export const {
  useExtractComplaintMutation,
  useAssessComplaintMutation,
  useGetSavedAssessmentQuery,
} = aiApi
