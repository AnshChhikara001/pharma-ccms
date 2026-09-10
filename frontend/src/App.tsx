import { Activity, CheckCircle2, Database, Sparkles } from 'lucide-react'

import { useGetVocabularyQuery } from '@/features/meta/metaApi'

/**
 * Phase 0 verification screen.
 *
 * This is scaffolding, not a product screen. It exists so the foundation proves
 * itself end-to-end: React renders, Redux is wired, RTK Query reaches FastAPI
 * through the Vite proxy, and the domain vocabulary crosses the language
 * boundary intact. Phase 4 replaces it with the real intake screen.
 */
export default function App() {
  const { data, isLoading, isError, error } = useGetVocabularyQuery()

  return (
    <div className="min-h-screen px-6 py-10">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8">
          <div className="mb-2 flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-brand-600" aria-hidden />
            <span className="ccms-section-label">Phase 0 · Foundation</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-ink-900">
            Customer Complaint Management System
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            API &amp; FDF Quality Assurance Module — foundation verification
          </p>
        </header>

        <section className="ccms-card p-6">
          <div className="mb-4 flex items-center gap-2">
            <Database className="h-4 w-4 text-ink-500" aria-hidden />
            <h2 className="text-sm font-semibold text-ink-900">
              Contract check: domain vocabulary
            </h2>
          </div>

          {isLoading && (
            <p className="flex items-center gap-2 text-sm text-ink-500">
              <Activity className="h-4 w-4 animate-pulse" aria-hidden />
              Loading vocabulary from FastAPI…
            </p>
          )}

          {isError && (
            <div className="rounded-field border border-risk-line bg-risk-bg p-4 text-sm text-risk-ink">
              <p className="font-semibold">Could not reach the backend.</p>
              <p className="mt-1">
                Start it with{' '}
                <code className="rounded bg-white/60 px-1 py-0.5">
                  uvicorn app.main:app --reload
                </code>{' '}
                from <code className="rounded bg-white/60 px-1 py-0.5">backend/</code>.
              </p>
              <pre className="mt-2 overflow-x-auto text-xs opacity-80">
                {JSON.stringify(error, null, 2)}
              </pre>
            </div>
          )}

          {data && (
            <>
              <div className="mb-4 flex items-center gap-2 rounded-field border border-ok-line bg-ok-bg px-3 py-2 text-sm text-ok-ink">
                <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
                Frontend ↔ backend contract verified across the language boundary.
              </div>

              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {(
                  [
                    ['Statuses', data.complaint_statuses],
                    ['Severities', data.severities],
                    ['Priorities', data.priorities],
                    ['Sources', data.complaint_sources],
                    ['Complaint types', data.complaint_types],
                    ['Roles', data.user_roles],
                  ] as const
                ).map(([label, options]) => (
                  <div
                    key={label}
                    className="rounded-field border border-line bg-field px-3 py-2"
                  >
                    <dt className="ccms-section-label">{label}</dt>
                    <dd className="mt-1 text-lg font-semibold text-ink-900">
                      {options.length}
                    </dd>
                  </div>
                ))}
              </dl>

              <p className="mt-4 text-xs text-ink-400">
                These counts come from Python enums in{' '}
                <code>backend/app/schemas/enums.py</code>. Nothing here is hard-coded
                in the frontend.
              </p>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
