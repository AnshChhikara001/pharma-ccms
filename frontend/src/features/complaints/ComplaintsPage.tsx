import { ArrowRight, Clock3, Filter, Plus, Search, ShieldAlert, Siren } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useState } from 'react'

import { useGetComplaintsQuery } from './complaintsApi'
import { ErrorNotice, PageSpinner, StatusBadge, formatLabel } from '@/components/ui'

export default function ComplaintsPage() {
  const [search, setSearch] = useState('')
  const { data, isLoading, isError, refetch } = useGetComplaintsQuery({ q: search || undefined, page: 1, page_size: 50 })

  if (isLoading) return <PageSpinner label="Loading complaint queue…" />
  if (isError || !data) return <ErrorNotice message="The complaint queue could not be loaded." onRetry={refetch} />

  const items = data.items
  const overdue = items.filter((item) => item.is_overdue).length
  const urgent = items.filter((item) => item.priority === 'urgent' || item.severity === 'critical').length
  const underReview = items.filter((item) => item.status === 'under_review').length

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="ccms-section-label">Quality operations</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-ink-900">Complaint queue</h1>
          <p className="mt-1 text-sm text-ink-500">Triage, review, and move every complaint through a controlled workflow.</p>
        </div>
        <Link className="ccms-button ccms-button--primary" to="/complaints/new">
          <Plus className="h-4 w-4" aria-hidden /> New complaint
        </Link>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total complaints" value={data.total} icon={<Filter className="h-4 w-4" />} />
        <Metric label="Under review" value={underReview} icon={<Clock3 className="h-4 w-4" />} />
        <Metric label="Overdue" value={overdue} icon={<ShieldAlert className="h-4 w-4" />} tone="risk" />
        <Metric label="Critical / urgent" value={urgent} icon={<Siren className="h-4 w-4" />} tone="risk" />
      </div>

      <section className="ccms-card overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold text-ink-900">All complaints</h2>
            <p className="mt-1 text-xs text-ink-500">Select a record to open its triage workspace.</p>
          </div>
          <label className="relative block sm:w-72">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" aria-hidden />
            <input className="ccms-input pl-9" placeholder="Search complaints…" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
        </div>

        {items.length === 0 ? (
          <div className="p-10 text-center text-sm text-ink-500">No complaints match this search.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-field text-xs uppercase tracking-wide text-ink-500">
                <tr>
                  <th className="px-4 py-3 font-semibold">Reference</th>
                  <th className="px-4 py-3 font-semibold">Product / batch</th>
                  <th className="px-4 py-3 font-semibold">Type</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Risk</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {items.map((item) => (
                  <tr key={item.id} className="transition hover:bg-field">
                    <td className="px-4 py-4">
                      <Link className="font-semibold text-brand-700 hover:underline" to={`/complaints/${item.id}`}>{item.reference_code}</Link>
                      <p className="mt-1 text-xs text-ink-400">{item.complaint_date ?? 'Date not provided'}</p>
                    </td>
                    <td className="px-4 py-4">
                      <p className="font-medium text-ink-900">{item.product_name ?? 'Unspecified product'}</p>
                      <p className="mt-1 text-xs text-ink-500">Batch {item.batch_number ?? 'not provided'}</p>
                    </td>
                    <td className="px-4 py-4 text-ink-700">{formatLabel(item.complaint_type)}</td>
                    <td className="px-4 py-4"><StatusBadge value={item.status} /></td>
                    <td className="px-4 py-4">
                      {item.severity ? <StatusBadge value={item.severity} /> : <span className="text-xs text-ink-400">Pending</span>}
                      {item.is_overdue && <p className="mt-1 text-xs font-semibold text-risk-ink">Overdue</p>}
                    </td>
                    <td className="px-4 py-4 text-right"><Link className="inline-flex rounded-field p-2 text-ink-400 hover:bg-brand-50 hover:text-brand-700" to={`/complaints/${item.id}`} aria-label={`Open ${item.reference_code}`}><ArrowRight className="h-4 w-4" aria-hidden /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function Metric({ label, value, icon, tone = 'normal' }: { label: string; value: number; icon: React.ReactNode; tone?: 'normal' | 'risk' }) {
  return (
    <div className="ccms-card p-4">
      <div className="flex items-center justify-between text-ink-400"><span className="ccms-section-label">{label}</span><span className={tone === 'risk' ? 'text-risk-ink' : 'text-brand-600'}>{icon}</span></div>
      <p className="mt-3 text-2xl font-bold text-ink-900">{value}</p>
    </div>
  )
}
