import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

import { clearToken } from '@/features/auth/authSlice'

const rawBaseQuery = fetchBaseQuery({
  // Relative base: Vite proxies /api to the backend in dev, and in production
  // the app is served behind the same origin.
  baseUrl: '/api/v1',
  prepareHeaders: (headers, { getState }) => {
    const token = (getState() as { auth?: { token?: string | null } }).auth?.token
    if (token) headers.set('authorization', `Bearer ${token}`)
    return headers
  },
})

const baseQueryWithAuth: typeof rawBaseQuery = async (args, api, extraOptions) => {
  const result = await rawBaseQuery(args, api, extraOptions)
  if (result.error?.status === 401) api.dispatch(clearToken())
  return result
}

/**
 * The single RTK Query API slice.
 *
 * Every feature injects its endpoints into this one slice (via
 * `api.injectEndpoints`) rather than creating its own. That gives the whole app
 * one cache, one tag-invalidation graph, and one place where the auth token is
 * attached - so a complaint mutation can invalidate the dashboard counts without
 * either feature knowing about the other.
 */
export const api = createApi({
  reducerPath: 'api',
  baseQuery: baseQueryWithAuth,
  // Declared up front so feature slices can invalidate across boundaries.
  tagTypes: ['Complaint', 'ComplaintList', 'Dashboard', 'Vocabulary', 'Auth', 'AuditTrail'],
  endpoints: () => ({}),
})
