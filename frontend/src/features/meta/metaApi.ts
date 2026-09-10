import { api } from '@/app/api'

/** One option in a domain dropdown, as served by /meta/vocabulary. */
export interface EnumOption {
  value: string
  label: string
}

/**
 * Every enum the UI needs, fetched once and cached.
 *
 * Dropdown options are never hard-coded in components. They come from the
 * backend, which derives them from the same Python enums the database and the
 * AI structured-output schema use - so the three can never disagree.
 */
export interface Vocabulary {
  user_roles: EnumOption[]
  complaint_statuses: EnumOption[]
  severities: EnumOption[]
  priorities: EnumOption[]
  complaint_sources: EnumOption[]
  complaint_types: EnumOption[]
  dosage_forms: EnumOption[]
  quantity_units: EnumOption[]
  document_kinds: EnumOption[]
}

export const metaApi = api.injectEndpoints({
  endpoints: (build) => ({
    getVocabulary: build.query<Vocabulary, void>({
      query: () => '/meta/vocabulary',
      providesTags: ['Vocabulary'],
    }),
  }),
})

export const { useGetVocabularyQuery } = metaApi
