import { ClipboardList, LogOut, Plus, ShieldCheck, Sparkles } from 'lucide-react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'

import { useAppDispatch } from '@/app/store'
import { clearToken } from './authSlice'
import { useGetMeQuery } from './authApi'
import { PageSpinner } from '@/components/ui'
import { cn } from '@/lib/utils'

export default function AppShell() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { data: user, isLoading } = useGetMeQuery()

  if (isLoading || !user) return <PageSpinner label="Restoring your secure session…" />

  function logout() {
    dispatch(clearToken())
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4 px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white shadow-sm">
              <Sparkles className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <p className="text-sm font-bold text-ink-900">Pharma CCMS</p>
              <p className="text-xs text-ink-500">AI-assisted quality operations</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-ink-900">{user.full_name}</p>
              <p className="text-xs capitalize text-ink-500">{user.role.replaceAll('_', ' ')}</p>
            </div>
            <button type="button" className="ccms-button ccms-button--ghost" onClick={logout} aria-label="Log out">
              <LogOut className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">Log out</span>
            </button>
          </div>
        </div>
      </header>
      <div className="mx-auto flex max-w-[1500px] flex-col gap-6 px-5 py-6 sm:px-8 lg:flex-row">
        <aside className="shrink-0 lg:w-52">
          <nav className="flex gap-2 overflow-x-auto lg:flex-col">
            <NavLink className={({ isActive }) => navClass(isActive)} to="/complaints">
              <ClipboardList className="h-4 w-4" aria-hidden /> Complaints
            </NavLink>
            <NavLink className={({ isActive }) => navClass(isActive)} to="/complaints/new">
              <Plus className="h-4 w-4" aria-hidden /> New intake
            </NavLink>
          </nav>
          <div className="mt-6 hidden rounded-card border border-ai-line bg-ai-bg p-4 text-xs text-ai-ink lg:block">
            <ShieldCheck className="mb-2 h-4 w-4" aria-hidden />
            <p className="font-semibold">Reviewer-first AI</p>
            <p className="mt-1 leading-5">Every recommendation is advisory and requires qualified QA review.</p>
          </div>
        </aside>
        <main className="min-w-0 flex-1"><Outlet /></main>
      </div>
    </div>
  )
}

function navClass(isActive: boolean) {
  return cn(
    'inline-flex items-center gap-2 whitespace-nowrap rounded-field px-3 py-2 text-sm font-semibold transition lg:w-full',
    isActive ? 'bg-brand-600 text-white shadow-sm' : 'text-ink-500 hover:bg-surface hover:text-ink-900',
  )
}
