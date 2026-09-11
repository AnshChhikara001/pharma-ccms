import { Check, Info, LoaderCircle, Paperclip, RotateCcw, Send, Sparkles, UploadCloud } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { AdvisoryNote, ErrorNotice, SectionHeading, StatusBadge, SuccessNote, getErrorMessage } from '@/components/ui'
import { useGetMeQuery } from '@/features/auth/authApi'
import { useGetVocabularyQuery } from '@/features/meta/metaApi'
import { useCreateComplaintMutation } from './complaintsApi'
import { useExtractComplaintMutation } from '@/features/ai/aiApi'
import type { components } from '@/types/api'

type ComplaintCreate = components['schemas']['ComplaintCreate']
type FormKey = keyof ComplaintCreate
type FormState = Record<FormKey, string>

const INITIAL_FORM: FormState = {
  source: '', customer_name: '', customer_contact: '', reporter_name: '', product_name: '', product_strength: '',
  dosage_form: '', batch_number: '', manufacturing_date: '', expiry_date: '', quantity_affected: '', quantity_unit: '',
  complaint_type: '', complaint_date: '', description: '', severity: '', priority: '', assigned_investigator_id: '', due_date: '',
}

export default function IntakePage() {
  const navigate = useNavigate()
  const { data: user } = useGetMeQuery()
  const { data: vocabulary } = useGetVocabularyQuery()
  const [extractComplaint, extractionState] = useExtractComplaintMutation()
  const [createComplaint, createState] = useCreateComplaintMutation()
  const [form, setForm] = useState<FormState>(INITIAL_FORM)
  const [extractionText, setExtractionText] = useState('')
  const [aiFields, setAiFields] = useState<Set<string>>(new Set())
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(new Set())
  const [extractionResult, setExtractionResult] = useState<components['schemas']['ExtractedComplaint'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const canExtract = user?.permissions?.includes('ai:extract') ?? false
  const canCreate = user?.permissions?.includes('complaint:create') ?? false
  const missingRequired = form.description.trim().length < 10
  const sourceOptions = vocabulary?.complaint_sources ?? []
  const typeOptions = vocabulary?.complaint_types ?? []
  const dosageOptions = vocabulary?.dosage_forms ?? []
  const unitOptions = vocabulary?.quantity_units ?? []
  const severityOptions = vocabulary?.severities ?? []
  const priorityOptions = vocabulary?.priorities ?? []

  const extractedCount = useMemo(
    () => Object.values(extractionResult?.fields ?? {}).filter((value) => value !== null && value !== undefined && value !== '').length,
    [extractionResult],
  )

  function updateField(key: FormKey, value: string) {
    setForm((current) => ({ ...current, [key]: value }))
    setDirtyFields((current) => new Set(current).add(key))
    setSaved(false)
  }

  async function handleExtraction() {
    if (!extractionText.trim() || !canExtract) return
    setError(null)
    try {
      const result = await extractComplaint({ text: extractionText.trim() }).unwrap()
      setExtractionResult(result)
      const fields = result.fields ?? {}
      setForm((current) => {
        const next = { ...current }
        for (const [key, value] of Object.entries(fields)) {
          if (value !== null && value !== undefined && !dirtyFields.has(key)) next[key as FormKey] = String(value)
        }
        return next
      })
      setAiFields(new Set((result.provenance ?? []).map((item) => item.field)))
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'The AI assistant could not extract complaint details.'))
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (missingRequired || !canCreate) return
    setError(null)
    try {
      const payload = toPayload(form)
      const complaint = await createComplaint(payload).unwrap()
      setSaved(true)
      navigate(`/complaints/${complaint.id}`)
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'The complaint could not be saved.'))
    }
  }

  function resetForm() {
    setForm(INITIAL_FORM)
    setAiFields(new Set())
    setDirtyFields(new Set())
    setExtractionResult(null)
    setSaved(false)
    setError(null)
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
        <div>
          <p className="ccms-section-label">AI-assisted intake</p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-ink-900">Log Customer Complaint</h1>
          <p className="mt-1 text-sm text-ink-500">API &amp; FDF Quality Assurance Module</p>
        </div>
        <StatusBadge value="pending triage" />
      </div>

      {error && <ErrorNotice message={error} />}
      {saved && <SuccessNote>Complaint saved. Opening its triage workspace…</SuccessNote>}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.8fr)]">
        <form className="ccms-card p-5 sm:p-7" onSubmit={handleSubmit}>
          <SectionHeading number={1}>Product &amp; batch identification</SectionHeading>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Product name / API / FDF" value={form.product_name} ai={aiFields.has('product_name')} onChange={(value) => updateField('product_name', value)} placeholder="Awaiting AI extraction…" />
            <Field label="Product strength / grade" value={form.product_strength} ai={aiFields.has('product_strength')} onChange={(value) => updateField('product_strength', value)} placeholder="e.g. 500 mg" />
            <Field label="Batch / lot number" value={form.batch_number} ai={aiFields.has('batch_number')} onChange={(value) => updateField('batch_number', value)} placeholder="Awaiting AI extraction…" />
            <SelectField label="Dosage form" value={form.dosage_form} ai={aiFields.has('dosage_form')} options={dosageOptions} onChange={(value) => updateField('dosage_form', value)} />
            <Field label="Manufacturing date" type="date" value={form.manufacturing_date} ai={aiFields.has('manufacturing_date')} onChange={(value) => updateField('manufacturing_date', value)} />
            <Field label="Expiry date" type="date" value={form.expiry_date} ai={aiFields.has('expiry_date')} onChange={(value) => updateField('expiry_date', value)} />
          </div>

          <div className="mt-8"><SectionHeading number={2}>Origin &amp; customer details</SectionHeading></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Complaint source" value={form.source} ai={aiFields.has('source')} options={sourceOptions} onChange={(value) => updateField('source', value)} />
            <Field label="Customer name" value={form.customer_name} ai={aiFields.has('customer_name')} onChange={(value) => updateField('customer_name', value)} placeholder="Awaiting AI extraction…" />
            <Field label="Customer contact" value={form.customer_contact} ai={aiFields.has('customer_contact')} onChange={(value) => updateField('customer_contact', value)} />
            <Field label="Reporter name" value={form.reporter_name} ai={aiFields.has('reporter_name')} onChange={(value) => updateField('reporter_name', value)} />
          </div>

          <div className="mt-8"><SectionHeading number={3}>Complaint &amp; defect analysis</SectionHeading></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Complaint type" value={form.complaint_type} ai={aiFields.has('complaint_type')} options={typeOptions} onChange={(value) => updateField('complaint_type', value)} />
            <Field label="Complaint date" type="date" value={form.complaint_date} ai={aiFields.has('complaint_date')} onChange={(value) => updateField('complaint_date', value)} />
            <div className="sm:col-span-2">
              <Field label="Structured defect summary" textarea value={form.description} ai={aiFields.has('description')} onChange={(value) => updateField('description', value)} placeholder="AI will synthesize the complaint into a formal QMS description…" />
              <p className="mt-1 text-right text-[11px] text-ink-400">Minimum 10 characters</p>
            </div>
            <Field label="Quantity affected" type="number" value={form.quantity_affected} ai={aiFields.has('quantity_affected')} onChange={(value) => updateField('quantity_affected', value)} />
            <SelectField label="Quantity unit" value={form.quantity_unit} ai={aiFields.has('quantity_unit')} options={unitOptions} onChange={(value) => updateField('quantity_unit', value)} />
          </div>

          <div className="mt-8"><SectionHeading number={4}>Initial assessment &amp; priority</SectionHeading></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField label="Initial severity" value={form.severity} ai={aiFields.has('severity')} options={severityOptions} onChange={(value) => updateField('severity', value)} />
            <SelectField label="Priority" value={form.priority} ai={aiFields.has('priority')} options={priorityOptions} onChange={(value) => updateField('priority', value)} />
          </div>

          <div className="mt-8 flex flex-col-reverse justify-between gap-3 border-t border-line pt-5 sm:flex-row sm:items-center">
            <button type="button" className="ccms-button ccms-button--secondary" onClick={resetForm}><RotateCcw className="h-4 w-4" aria-hidden /> Reset form</button>
            <button type="submit" className="ccms-button ccms-button--primary" disabled={missingRequired || !canCreate || createState.isLoading}>
              {createState.isLoading ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Check className="h-4 w-4" aria-hidden />}
              {createState.isLoading ? 'Saving complaint…' : 'Save complaint'}
            </button>
          </div>
          {!canCreate && <p className="mt-3 text-right text-xs text-pending-ink">Your role can review complaints but cannot create new records.</p>}
        </form>

        <aside className="ccms-card overflow-hidden xl:sticky xl:top-5">
          <div className="border-b border-line p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-brand-600" aria-hidden /><div><h2 className="font-semibold text-ink-900">AI Complaint Intake Copilot</h2><p className="mt-1 text-xs text-ink-500">Paste a complaint narrative to extract structured fields.</p></div></div>
              <span className="rounded-full bg-brand-50 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-brand-700">Beta</span>
            </div>
          </div>
          <div className="space-y-4 p-5">
            <div className="rounded-field border border-dashed border-line-strong bg-field p-5 text-center text-sm text-ink-500">
              <UploadCloud className="mx-auto h-7 w-7 text-ink-400" aria-hidden />
              <p className="mt-2 font-semibold text-ink-700">Document upload planned</p>
              <p className="mt-1 text-xs">Text intake is available now; PDF and image parsing will arrive in a later phase.</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-ink-400"><span className="h-px flex-1 bg-line" /> OR <span className="h-px flex-1 bg-line" /></div>
            <textarea className="ccms-input min-h-36 resize-y" value={extractionText} onChange={(event) => setExtractionText(event.target.value)} placeholder="Paste complaint text or the customer email here…" maxLength={8000} />
            <div className="flex items-start gap-2 rounded-field border border-ok-line bg-ok-bg p-3 text-xs text-ok-ink"><Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /><span>Extraction is advisory. Review every value before saving the complaint.</span></div>
            <button type="button" className="ccms-button ccms-button--primary w-full" onClick={handleExtraction} disabled={!extractionText.trim() || !canExtract || extractionState.isLoading}>
              {extractionState.isLoading ? <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden /> : <Send className="h-4 w-4" aria-hidden />}
              {extractionState.isLoading ? 'Analyzing complaint…' : 'Extract complaint details'}
            </button>
            {extractionState.isLoading && <div><div className="mb-2 flex justify-between text-xs text-ink-500"><span>Extraction progress</span><span>Working</span></div><div className="h-2 overflow-hidden rounded-full bg-brand-100"><div className="h-full w-2/3 animate-pulse rounded-full bg-brand-600" /></div></div>}
            {!canExtract && <p className="text-xs text-pending-ink">Your role does not have permission to run AI extraction.</p>}
            {extractionResult && <ExtractionResult result={extractionResult} extractedCount={extractedCount} />}
            <AdvisoryNote>AI outputs are recommendations for qualified QA review, never confirmed root causes or regulatory decisions.</AdvisoryNote>
            <div className="flex items-center justify-center gap-2 border-t border-line pt-4 text-[11px] text-ink-400"><Paperclip className="h-3.5 w-3.5" aria-hidden /> Powered by the CCMS LangGraph AI layer</div>
          </div>
        </aside>
      </div>
    </div>
  )
}

function ExtractionResult({ result, extractedCount }: { result: components['schemas']['ExtractedComplaint']; extractedCount: number }) {
  return (
    <div className="space-y-3 border-t border-line pt-4">
      <div className="flex items-center justify-between"><p className="ccms-section-label">Extraction result</p><span className="text-xs font-semibold text-ai-ink">{extractedCount} fields found</span></div>
      {result.missing_fields && result.missing_fields.length > 0 && <div className="rounded-field border border-pending-line bg-pending-bg p-3 text-xs text-pending-ink"><p className="font-semibold">Still needed</p><p className="mt-1">{result.missing_fields.map((field) => field.replaceAll('_', ' ')).join(' · ')}</p></div>}
      {result.clarifying_questions && result.clarifying_questions.length > 0 && <div className="rounded-field border border-line bg-field p-3 text-xs text-ink-700"><p className="font-semibold">Clarifying questions</p><ul className="mt-1 list-disc space-y-1 pl-4">{result.clarifying_questions.map((question) => <li key={question}>{question}</li>)}</ul></div>}
      {result.extraction_notes && <p className="text-xs leading-5 text-ink-500">{result.extraction_notes}</p>}
    </div>
  )
}

function Field({ label, value, onChange, ai, type = 'text', placeholder, textarea = false }: { label: string; value: string; onChange: (value: string) => void; ai: boolean; type?: string; placeholder?: string; textarea?: boolean }) {
  const className = `ccms-input mt-2 ${ai ? 'ccms-input--ai' : ''}`
  return <label className="block"><span className="ccms-label">{label}{ai && <span className="ml-1 text-ai-ink" title="Populated by AI">✦</span>}</span>{textarea ? <textarea className={`${className} min-h-28 resize-y`} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /> : <input className={className} type={type} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />}</label>
}

function SelectField({ label, value, onChange, ai, options }: { label: string; value: string; onChange: (value: string) => void; ai: boolean; options: { value: string; label: string }[] }) {
  return <label className="block"><span className="ccms-label">{label}{ai && <span className="ml-1 text-ai-ink" title="Populated by AI">✦</span>}</span><select className={`ccms-input mt-2 ${ai ? 'ccms-input--ai' : ''}`} value={value} onChange={(event) => onChange(event.target.value)}><option value="">Select {label.toLowerCase()}</option>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
}

function toPayload(form: FormState): ComplaintCreate {
  const payload: Record<string, string> = {}
  for (const [key, value] of Object.entries(form)) if (value.trim()) payload[key] = value.trim()
  return payload as unknown as ComplaintCreate
}
