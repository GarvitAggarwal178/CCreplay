import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Experiment } from '../api'
import DivergenceCard from '../components/DivergenceCard'
import AllDecisionsPanel from '../components/AllDecisionsPanel'
import ExportButtons from '../components/ExportButtons'
import { fmtNum } from '../lib/format'

function fmtTime(t: number | null): string {
  if (!t) return '—'
  return new Date(t * 1000).toLocaleString()
}

// diff/checkpoint configs have trace_id/reference/candidate; all_decisions
// adds mode; sweep has a completely different shape (base/param/values/
// trace_ids) with no single trace/reference/candidate -- rendering it
// through the diff/checkpoint column logic produced literal "undefined"
// cells (found by review, not by the e2e suite, which only checked
// "history has rows").
function traceCell(e: Experiment): string {
  if (e.type === 'sweep') return String(e.config.trace_ids ?? '—')
  return String(e.config.trace_id ?? '—')
}
function referenceCell(e: Experiment): string {
  if (e.type === 'sweep') return `${e.config.base} (${e.config.reference_id || e.config.base})`
  return String(e.config.reference ?? '—')
}
function candidateCell(e: Experiment): string {
  if (e.type === 'sweep') {
    const values = e.config.values as number[] | undefined
    return `${e.config.param} in {${values?.join(', ') ?? '?'}}`
  }
  return String(e.config.candidate ?? '—')
}

function verdictBadge(e: Experiment): { cls: string; text: string } {
  if (e.status !== 'done') return { cls: 'badge badge-neutral', text: e.status }
  if (e.type === 'sweep') {
    const n = e.result?.points?.length ?? 0
    return { cls: 'badge badge-neutral', text: `${n} point${n === 1 ? '' : 's'}` }
  }
  if (e.type === 'all_decisions') {
    const n = e.result?.n_disagree ?? 0
    return { cls: n === 0 ? 'badge badge-pass' : 'badge badge-fail', text: `${fmtNum(n)} disagree` }
  }
  // diff / checkpoint
  return {
    cls: e.result?.result === 'NO DIVERGENCE' ? 'badge badge-pass' : 'badge badge-fail',
    text: e.result?.result ?? e.status,
  }
}

export default function History() {
  const navigate = useNavigate()
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [open, setOpen] = useState<Experiment | null>(null)
  const [rerunMsg, setRerunMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function refresh() {
    api.listExperiments().then(setExperiments).catch((e) => setError(String(e)))
  }
  useEffect(refresh, [])

  async function rerun(id: string) {
    setRerunMsg('rerunning…')
    try {
      const r = await api.rerunExperiment(id)
      // A rerun that didn't finish is not the same thing as a rerun that
      // finished and produced a different result -- conflating them would
      // show "result differs" for e.g. a controller deleted since the
      // original run, which is misleading, not a real behavioral finding.
      if (r.status !== 'done') {
        setRerunMsg(`rerun ${r.id}: failed (${r.status}) -- ${r.error || 'no error detail'}`)
      } else {
        setRerunMsg(r.same_as_original ? `rerun ${r.id}: identical to original ✓` : `rerun ${r.id}: result differs from original`)
      }
      refresh()
    } catch (e) {
      setRerunMsg(String(e))
    }
  }

  return (
    <div>
      <h1>History</h1>
      {error && <div className="error-box">{error}</div>}
      {rerunMsg && <p className="hint">{rerunMsg}</p>}
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Type</th>
              <th>Trace</th>
              <th>Reference</th>
              <th>Candidate</th>
              <th>Verdict</th>
              <th>Duration</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {experiments.map((e) => {
              const verdict = verdictBadge(e)
              return (
                <tr key={e.id}>
                  <td className="mono">{fmtTime(e.created_at)}</td>
                  <td>{e.type}</td>
                  <td className="mono">{traceCell(e)}</td>
                  <td className="mono">{referenceCell(e)}</td>
                  <td className="mono">{candidateCell(e)}</td>
                  <td>
                    <span className={verdict.cls}>{verdict.text}</span>
                  </td>
                  <td>{e.started_at && e.finished_at ? `${(e.finished_at - e.started_at).toFixed(2)} s` : '—'}</td>
                  <td className="field-row">
                    <button className="btn btn-secondary" onClick={() => setOpen(e)}>
                      Open
                    </button>
                    <button className="btn btn-secondary" onClick={() => rerun(e.id)}>
                      Rerun
                    </button>
                    {e.type === 'diff' && (
                      <button
                        className="btn btn-secondary"
                        onClick={() =>
                          navigate(
                            `/diff?trace=${e.config.trace_id}&reference=${e.config.reference}&candidate=${e.config.candidate}`
                          )
                        }
                      >
                        Diff Workbench
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="panel">
          <div className="field-row">
            <h2>Experiment {open.id}</h2>
            <button className="btn btn-secondary" onClick={() => setOpen(null)}>
              close
            </button>
          </div>
          {open.type === 'diff' && open.result && <DivergenceCard result={open.result} />}
          {open.type === 'all_decisions' && open.result && <AllDecisionsPanel result={open.result} />}
          {(open.type === 'checkpoint' || open.type === 'sweep') && open.result && (
            <pre className="mono" style={{ fontSize: '0.8rem', overflow: 'auto', maxHeight: 400 }}>
              {JSON.stringify(open.result, null, 2)}
            </pre>
          )}
          {!open.result && open.status !== 'done' && (
            <p className="hint">
              {open.status === 'error' ? `failed: ${open.error}` : `status: ${open.status}`}
            </p>
          )}
          <ExportButtons experimentId={open.id} />
        </div>
      )}
    </div>
  )
}
