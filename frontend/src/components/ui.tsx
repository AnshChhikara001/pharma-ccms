import { AlertCircle, CheckCircle2, LoaderCircle, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

export function PageSpinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex min-h-56 items-center justify-center gap-2 text-sm text-ink-500">
      <LoaderCircle className="h-4 w-4 animate-spin text-brand-600" aria-hidden />
      {label}
    </div>
  )
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-field border border-risk-line bg-risk-bg p-4 text-sm text-risk-ink">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <div>
          <p className="font-semibold">Something went wrong</p>
          <p className="mt-1 opacity-90">{message}</p>
          {onRetry && (
            <button type="button" className="mt-3 font-semibold underline" onClick={onRetry}>
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function AdvisoryNote({ children }: { children?: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-field border border-ai-line bg-ai-bg p-3 text-xs text-ai-ink">
      <Sparkles className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{children ?? 'AI-generated recommendation. Review before taking action.'}</span>
    </div>
  )
}

export function StatusBadge({ value, tone }: { value: string; tone?: 'ok' | 'risk' | 'pending' }) {
  const selectedTone = tone ?? badgeTone(value)
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold capitalize',
        selectedTone === 'ok' && 'border-ok-line bg-ok-bg text-ok-ink',
        selectedTone === 'risk' && 'border-risk-line bg-risk-bg text-risk-ink',
        selectedTone === 'pending' && 'border-pending-line bg-pending-bg text-pending-ink',
      )}
    >
      {formatLabel(value)}
    </span>
  )
}

export function SectionHeading({ number, children }: { number: number; children: ReactNode }) {
  return (
    <div className="mb-4 flex items-center gap-2 border-b border-line pb-2">
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-50 text-[10px] font-bold text-brand-700">
        {number}
      </span>
      <h2 className="ccms-section-label">{children}</h2>
    </div>
  )
}

export function formatLabel(value: string | null | undefined): string {
  if (!value) return 'Not provided'
  return value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function getErrorMessage(error: unknown, fallback = 'Please try again.') {
  if (typeof error === 'object' && error !== null && 'data' in error) {
    const data = (error as { data?: { detail?: string } }).data
    if (data?.detail) return data.detail
  }
  return fallback
}

export function SuccessNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-field border border-ok-line bg-ok-bg p-3 text-sm text-ok-ink">
      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{children}</span>
    </div>
  )
}

function badgeTone(value: string): 'ok' | 'risk' | 'pending' {
  if (['closed', 'under_review', 'root_cause_identified'].includes(value)) return 'ok'
  if (['critical', 'urgent', 'overdue'].includes(value)) return 'risk'
  return 'pending'
}
