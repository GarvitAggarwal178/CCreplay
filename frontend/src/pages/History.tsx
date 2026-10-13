import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Experiment } from '../api'
import DivergenceCard from '../components/DivergenceCard'
import ExportButtons from '../components/ExportButtons'

function fmtTime(t: number | null): string {
  if (!t) return '—'
  return new Date(t * 1000).toLocaleString()
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
            {experiments.map((e) => (
              <tr key={e.id}>
                <td className="mono">{fmtTime(e.created_at)}</td>
                <td>{e.type}</td>
                <td className="mono">{String(e.config.trace_id)}</td>
                <td className="mono">{String(e.config.reference)}</td>
                <td className="mono">{String(e.config.candidate)}</td>
                <td>
                  <span
                    className={
                      e.status !== 'done'
                        ? 'badge badge-neutral'
                        : e.result?.result === 'NO DIVERGENCE'
                          ? 'badge badge-pass'
                          : 'badge badge-fail'
                    }
                  >
                    {e.status === 'done' ? e.result?.result : e.status}
                  </span>
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
            ))}
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
          {open.type === 'checkpoint' && open.result && (
            <pre className="mono" style={{ fontSize: '0.8rem', overflow: 'auto' }}>
              {JSON.stringify(open.result, null, 2)}
            </pre>
          )}
          <ExportButtons experimentId={open.id} />
        </div>
      )}
    </div>
  )
}
