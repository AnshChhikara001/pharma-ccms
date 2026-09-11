import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

const TOKEN_KEY = 'ccms.access_token'

interface AuthState {
  token: string | null
}

const initialState: AuthState = {
  token: localStorage.getItem(TOKEN_KEY),
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setToken: (state, action: PayloadAction<string>) => {
      state.token = action.payload
      localStorage.setItem(TOKEN_KEY, action.payload)
    },
    clearToken: (state) => {
      state.token = null
      localStorage.removeItem(TOKEN_KEY)
    },
  },
})

export const { setToken, clearToken } = authSlice.actions
export default authSlice.reducer
