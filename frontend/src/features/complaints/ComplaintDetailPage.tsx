import { ArrowLeft, CheckCircle2, Clock3, FileSearch, RefreshCw, Sparkles, Workflow } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { useGetMeQuery } from '@/features/auth/authApi'
import { useAssessComplaintMutation, useGetSavedAssessmentQuery } from '@/features/ai/aiApi'
import { AdvisoryNote, ErrorNotice, PageSpinner, StatusBadge, formatLabel, getErrorMessage } from '@/components/ui'
import { useGetComplaintQuery, useGetComplaintTimelineQuery, useGetWorkflowQuery, useTransitionComplaintMutation } from './complaintsApi'
import type { components } from '@/types/api'

type ComplaintStatus = components['schemas']['ComplaintStatus']
type Assessment = components['schemas']['AIAssessment']

export default function ComplaintDetailPage() {
  const params = useParams()
  const id = Number(params.complaintId)
  const { data: user } = useGetMeQuery()
  const complaintQuery = useGetComplaintQuery(id, { skip: !Number.isFinite(id) })
  const timelineQuery = useGetComplaintTimelineQuery(id, { skip: !Number.isFinite(id) })
  const workflowQuery = useGetWorkflowQuery()
  const assessmentQuery = useGetSavedAssessmentQuery(id, { skip: !Number.isFinite(id) })
  const [assessComplaint, assessState] = useAssessComplaintMutation()
  const [transitionComplaint, transitionState] = useTransitionComplaintMutation()
  const [selectedTransition, setSelectedTransition] = useState('')
  const [reason, setReason] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)

  if (complaintQuery.isLoading) return <PageSpinner label="Loading complaint workspace…" />
  if (complaintQuery.isError || !complaintQuery.data) return <ErrorNotice message="This complaint could not be loaded." onRetry={complaintQuery.refetch} />

  const complaint = complaintQuery.data
  const options = workflowQuery.data?.transitions[complaint.status] ?? []
  const allowedOptions = options.filter((option) => option.required_permissions.every((permission) => user?.permissions?.includes(permission)))
  const canAssess = user?.permissions?.includes('ai:assess') ?? false
  const assessment = assessmentQuery.data?.assessment

  async function runAssessment() {
    setActionError(null)
    try {
      await assessComplaint(id).unwrap()
      await assessmentQuery.refetch()
    } catch (error) {
      setActionError(getErrorMessage(error, 'The AI assessment could not be generated.'))
    }
  }

  async function moveComplaint() {
    const option = allowedOptions.find((candidate) => candidate.to_status === selectedTransition)
    if (!option) return
    if (option.requires_reason && !reason.trim()) {
      setActionError('A reason is required for this workflow transition.')
      return
    }
    setActionError(null)
    try {
      await transitionComplaint({ id, body: { to_status: selectedTransition as ComplaintStatus, reason: reason.trim() || undefined } }).unwrap()
      setSelectedTransition('')
      setReason('')
    } catch (error) {
      setActionError(getErrorMessage(error, 'The workflow transition could not be completed.'))
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link className="inline-flex items-center gap-2 text-sm font-semibold text-brand-700 hover:underline" to="/complaints"><ArrowLeft className="h-4 w-4" aria-hidden /> Back to complaints</Link>
          <div className="mt-4 flex flex-wrap items-center gap-3"><p className="ccms-section-label">Complaint workspace</p><StatusBadge value={complaint.status} />{complaint.is_overdue && <StatusBadge value="overdue" />}</div>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-ink-900">{complaint.reference_code}</h1>
          <p className="mt-1 text-sm text-ink-500">{complaint.product_name ?? 'Unspecified product'} · batch {complaint.batch_number ?? 'not provided'}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canAssess && <button type="button" className="ccms-button ccms-button--primary" onClick={runAssessment} disabled={assessState.isLoading}><Sparkles className="h-4 w-4" aria-hidden />{assessState.isLoading ? 'Assessing…' : assessment ? 'Refresh AI assessment' : 'Run AI assessment'}</button>}
        </div>
      </div>

      {actionError && <ErrorNotice message={actionError} />}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(380px,0.9fr)]">
        <div className="space-y-5">
          <section className="ccms-card p-5 sm:p-6">
            <div className="mb-5 flex items-center justify-between"><div><p className="ccms-section-label">Complaint record</p><h2 className="mt-1 text-lg font-bold text-ink-900">Reported details</h2></div><FileSearch className="h-5 w-5 text-brand-600" aria-hidden /></div>
            <div className="grid gap-4 sm:grid-cols-2">
              <DataPoint label="Customer" value={complaint.customer_name} />
              <DataPoint label="Source" value={formatLabel(complaint.source)} />
              <DataPoint label="Reporter" value={complaint.reporter_name} />
              <DataPoint label="Complaint type" value={formatLabel(complaint.complaint_type)} />
              <DataPoint label="Product strength" value={complaint.product_strength} />
              <DataPoint label="Quantity affected" value={complaint.quantity_affected ? `${complaint.quantity_affected} ${complaint.quantity_unit ?? ''}` : null} />
              <DataPoint label="Complaint date" value={complaint.complaint_date} />
              <DataPoint label="Due date" value={complaint.due_date} />
            </div>
            <div className="mt-5 border-t border-line pt-5"><p className="ccms-label">Detailed complaint description</p><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink-700">{complaint.description}</p></div>
          </section>

          <WorkflowCard options={allowedOptions} selected={selectedTransition} reason={reason} onSelect={setSelectedTransition} onReason={setReason} onMove={moveComplaint} isLoading={transitionState.isLoading} />
          <Timeline entries={timelineQuery.data ?? []} />
        </div>

        <div className="space-y-5">
          {assessmentQuery.isError && !canAssess ? <section className="ccms-card p-6"><div className="flex items-start gap-3"><Clock3 className="mt-0.5 h-5 w-5 text-pending-ink" aria-hidden /><div><h2 className="font-semibold text-ink-900">Assessment not run yet</h2><p className="mt-1 text-sm leading-6 text-ink-500">A user with AI assessment permission must generate the first recommendation for this complaint.</p></div></div></section> : assessment ? <AssessmentPanel assessment={assessment} duplicates={assessmentQuery.data?.duplicates ?? []} /> : <section className="ccms-card p-6"><div className="flex items-start gap-3"><Sparkles className="mt-0.5 h-5 w-5 text-brand-600" aria-hidden /><div><h2 className="font-semibold text-ink-900">AI triage is ready</h2><p className="mt-1 text-sm leading-6 text-ink-500">Run the advisory assessment to see completeness, risk classification, a factual summary, and possible duplicate complaints.</p>{canAssess && <button type="button" className="ccms-button ccms-button--secondary mt-4" onClick={runAssessment} disabled={assessState.isLoading}><RefreshCw className="h-4 w-4" aria-hidden /> Generate assessment</button>}</div></div></section>}
          {assessmentQuery.isFetching && <p className="text-center text-xs text-ink-400">Refreshing saved assessment…</p>}
        </div>
      </div>
    </div>
  )
}

function AssessmentPanel({ assessment, duplicates }: { assessment: Assessment; duplicates: components['schemas']['DuplicateMatch'][] }) {
  const completeness = assessment.completeness_score
  return (
    <section className="ccms-card overflow-hidden">
      <div className="border-b border-line bg-gradient-to-r from-ai-bg to-surface p-5"><div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-ai-ink" aria-hidden /><div><p className="ccms-section-label">AI triage recommendation</p><h2 className="mt-1 text-lg font-bold text-ink-900">Assessment snapshot</h2></div></div></div>
      <div className="space-y-5 p-5">
        <AdvisoryNote>{assessment.disclaimer}</AdvisoryNote>
        <div className="grid gap-3 sm:grid-cols-2"><AssessmentMetric label="Completeness" value={`${completeness}%`} detail={completeness === 100 ? 'Triage-critical fields present' : `${assessment.missing_critical_fields?.length ?? 0} fields still missing`} /><AssessmentMetric label="Recommended risk" value={formatLabel(assessment.recommended_severity)} detail={formatLabel(assessment.recommended_priority)} tone={assessment.recommended_severity === 'critical' ? 'risk' : 'normal'} /></div>
        <div><p className="ccms-section-label">Complaint summary</p><p className="mt-2 text-sm leading-6 text-ink-700">{assessment.summary}</p></div>
        {assessment.severity_rationale && <div className="rounded-field border border-line bg-field p-3 text-xs leading-5 text-ink-600"><span className="font-semibold text-ink-800">Risk rationale · </span>{assessment.severity_rationale}</div>}
        {assessment.missing_critical_fields && assessment.missing_critical_fields.length > 0 && <div className="rounded-field border border-pending-line bg-pending-bg p-3 text-xs text-pending-ink"><p className="font-semibold">Completeness gaps</p><p className="mt-1">{assessment.missing_critical_fields.map(formatLabel).join(' · ')}</p></div>}
        {assessment.risk_factors && assessment.risk_factors.length > 0 && <ListBlock title="Risk factors" items={assessment.risk_factors} tone="risk" />}
        <div><div className="mb-2 flex items-center justify-between"><p className="ccms-section-label">Possible duplicates</p><span className="text-xs text-ink-400">{duplicates.length} found</span></div>{duplicates.length === 0 ? <p className="rounded-field border border-ok-line bg-ok-bg p-3 text-xs text-ok-ink">No matching complaint candidates were found.</p> : <div className="space-y-2">{duplicates.map((duplicate) => <div key={duplicate.complaint_id} className="rounded-field border border-line bg-field p-3"><div className="flex items-center justify-between gap-3"><p className="font-semibold text-brand-700">{duplicate.reference_code}</p><span className="text-xs font-semibold text-ink-500">{Math.round(duplicate.similarity * 100)}% match</span></div><p className="mt-1 text-xs text-ink-500">Matched on {(duplicate.matched_on ?? []).map(formatLabel).join(', ')}</p>{duplicate.summary && <p className="mt-2 line-clamp-2 text-xs leading-5 text-ink-600">{duplicate.summary}</p>}</div>)}</div>}</div>
      </div>
    </section>
  )
}

function AssessmentMetric({ label, value, detail, tone = 'normal' }: { label: string; value: string; detail: string; tone?: 'normal' | 'risk' }) {
  return <div className="rounded-field border border-line bg-field p-3"><p className="ccms-section-label">{label}</p><p className={`mt-2 text-xl font-bold ${tone === 'risk' ? 'text-risk-ink' : 'text-ink-900'}`}>{value}</p><p className="mt-1 text-xs text-ink-500">{detail}</p></div>
}

function ListBlock({ title, items, tone }: { title: string; items: string[]; tone?: 'risk' }) {
  return <div><p className="ccms-section-label">{title}</p><ul className={`mt-2 space-y-2 text-sm leading-5 ${tone === 'risk' ? 'text-risk-ink' : 'text-ink-700'}`}>{items.map((item) => <li key={item} className="flex gap-2"><span>•</span><span>{item}</span></li>)}</ul></div>
}

function WorkflowCard({ options, selected, reason, onSelect, onReason, onMove, isLoading }: { options: components['schemas']['TransitionOptionResponse'][]; selected: string; reason: string; onSelect: (value: string) => void; onReason: (value: string) => void; onMove: () => void; isLoading: boolean }) {
  return <section className="ccms-card p-5"><div className="flex items-center gap-2"><Workflow className="h-5 w-5 text-brand-600" aria-hidden /><div><p className="ccms-section-label">Workflow</p><h2 className="mt-1 font-bold text-ink-900">Move complaint forward</h2></div></div>{options.length === 0 ? <p className="mt-4 text-sm text-ink-500">No workflow actions are available for your role at this stage.</p> : <div className="mt-4 space-y-3"><select className="ccms-input" value={selected} onChange={(event) => onSelect(event.target.value)}><option value="">Select next status</option>{options.map((option) => <option key={option.to_status} value={option.to_status}>{option.label}{option.is_backward ? ' · return' : ''}</option>)}</select>{selected && options.find((option) => option.to_status === selected)?.requires_reason && <textarea className="ccms-input min-h-20 resize-y" value={reason} onChange={(event) => onReason(event.target.value)} placeholder="Reason for this workflow move…" />}{selected && <button type="button" className="ccms-button ccms-button--secondary" onClick={onMove} disabled={isLoading}><CheckCircle2 className="h-4 w-4" aria-hidden />{isLoading ? 'Updating…' : 'Apply transition'}</button>}</div>}</section>
}

function Timeline({ entries }: { entries: components['schemas']['StatusTransitionRead'][] }) {
  return <section className="ccms-card p-5"><div className="flex items-center gap-2"><Clock3 className="h-5 w-5 text-brand-600" aria-hidden /><div><p className="ccms-section-label">Audit timeline</p><h2 className="mt-1 font-bold text-ink-900">Complaint history</h2></div></div><div className="mt-5 space-y-4">{entries.map((entry) => <div key={entry.id} className="relative border-l border-line pl-5"><span className="absolute -left-1.5 top-1 h-3 w-3 rounded-full border-2 border-surface bg-brand-600" /><p className="text-sm font-semibold text-ink-900">{entry.from_status ? `${formatLabel(entry.from_status)} → ` : ''}{formatLabel(entry.to_status)}</p><p className="mt-1 text-xs text-ink-500">{new Date(entry.created_at).toLocaleString()} · {entry.changed_by_name ?? 'System'}</p>{entry.reason && <p className="mt-1 text-xs text-ink-600">{entry.reason}</p>}</div>)}{entries.length === 0 && <p className="text-sm text-ink-500">No timeline entries yet.</p>}</div></section>
}

function DataPoint({ label, value }: { label: string; value: string | null | undefined }) {
  return <div><p className="ccms-section-label">{label}</p><p className="mt-1 text-sm font-medium text-ink-800">{value || 'Not provided'}</p></div>
}
