import { KeyRound, ShieldCheck, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { setToken } from './authSlice'
import { useLoginMutation } from './authApi'
import { useAppDispatch } from '@/app/store'
import { getErrorMessage } from '@/components/ui'

export default function LoginPage() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const [login, { isLoading, error }] = useLoginMutation()
  const [email, setEmail] = useState('complaint.officer@pharmaco.com')
  const [password, setPassword] = useState('Demo@12345')

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      const result = await login({ email, password }).unwrap()
      dispatch(setToken(result.access_token))
      navigate('/complaints', { replace: true })
    } catch {
      // RTK Query exposes the useful server message through `error` below.
    }
  }

  return (
    <main className="min-h-screen bg-canvas px-5 py-10 sm:px-8">
      <div className="mx-auto grid max-w-5xl overflow-hidden rounded-card border border-line bg-surface shadow-card lg:grid-cols-[1.1fr_0.9fr]">
        <section className="bg-slate-950 p-8 text-white sm:p-12">
          <div className="flex items-center gap-2 text-blue-200">
            <Sparkles className="h-5 w-5" aria-hidden />
            <span className="text-sm font-semibold tracking-wide">CCMS · Quality Operations</span>
          </div>
          <h1 className="mt-20 max-w-md text-4xl font-bold tracking-tight sm:text-5xl">
            Turn complaint narratives into confident triage.
          </h1>
          <p className="mt-5 max-w-md text-sm leading-6 text-slate-300">
            A reviewer-first workspace for pharmaceutical complaints, with AI assistance that stays advisory and auditable.
          </p>
          <div className="mt-10 flex items-center gap-2 text-xs text-slate-400">
            <ShieldCheck className="h-4 w-4 text-emerald-300" aria-hidden />
            Role-based access · AI recommendations require QA review
          </div>
        </section>

        <section className="p-8 sm:p-12">
          <div className="mb-8">
            <p className="ccms-section-label">Welcome back</p>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-ink-900">Sign in to CCMS</h2>
            <p className="mt-2 text-sm text-ink-500">Use one of the seeded demo accounts to explore the workflow.</p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            <label className="block">
              <span className="ccms-label">Email address</span>
              <input className="ccms-input mt-2" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <label className="block">
              <span className="ccms-label">Password</span>
              <input className="ccms-input mt-2" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
            </label>
            {error && <p className="rounded-field border border-risk-line bg-risk-bg p-3 text-sm text-risk-ink">{getErrorMessage(error, 'Incorrect email or password.')}</p>}
            <button className="ccms-button ccms-button--primary w-full" type="submit" disabled={isLoading}>
              <KeyRound className="h-4 w-4" aria-hidden />
              {isLoading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <div className="mt-8 rounded-field border border-line bg-field p-4 text-xs text-ink-500">
            <p className="font-semibold text-ink-700">Demo account</p>
            <p className="mt-1">Complaint officer · complaint.officer@pharmaco.com</p>
            <p>Password · Demo@12345</p>
          </div>
        </section>
      </div>
    </main>
  )
}
