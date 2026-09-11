import { api } from '@/app/api'
import type { components } from '@/types/api'

type LoginRequest = components['schemas']['LoginRequest']
type Token = components['schemas']['Token']
type UserWithPermissions = components['schemas']['UserWithPermissions']

export const authApi = api.injectEndpoints({
  endpoints: (build) => ({
    login: build.mutation<Token, LoginRequest>({
      query: (body) => ({ url: '/auth/login/json', method: 'POST', body }),
    }),
    getMe: build.query<UserWithPermissions, void>({
      query: () => '/auth/me',
      providesTags: ['Auth'],
    }),
  }),
})

export const { useLoginMutation, useGetMeQuery } = authApi
export type { UserWithPermissions }
