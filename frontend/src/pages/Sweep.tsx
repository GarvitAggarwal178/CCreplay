import { useEffect, useMemo, useState } from 'react'
import { api, pollExperiment, type Experiment, type TraceSummary, type TunableSpec } from '../api'
import Chart from '../components/Chart'
import { fmtNum } from '../lib/format'

const ABI_BY_BASE: Record<string, number> = { reno: 0, cubic: 1 }

export default function Sweep() {
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [base, setBase] = useState<'cubic' | 'reno'>('cubic')
  const [tunables, setTunables] = useState<Record<string, TunableSpec>>({})
  const [param, setParam] = useState('BETA')
  const [valuesText, setValuesText] = useState('')
  const [selectedTraceIds, setSelectedTraceIds] = useState<string[]>([])
  const [running, setRunning] = useState(false)
  const [exp, setExp] = useState<Experiment | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listTraces().then(setTraces).catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    api
      .getTunables(base)
      .then((t) => {
        setTunables(t)
        const firstParam = Object.keys(t)[0]
        if (firstParam) setParam(firstParam)
      })
      .catch((e) => setError(String(e)))
  }, [base])

  const matchingTraces = useMemo(() => traces.filter((t) => t.abi === ABI_BY_BASE[base]), [traces, base])
  const spec = tunables[param]

  // Switching base or param (e.g. CUBIC BETA -> Reno num) previously left
  // the old value list in place, so Reno showed an immediate out-of-range
  // error with BETA-scale numbers still in the box. Reprefill a small list
  // around the new param's own default, always including the default
  // itself, whenever the active spec changes.
  useEffect(() => {
    if (!spec) return
    const span = spec.max - spec.min
    let candidates: number[]
    if (span <= 1) {
      candidates = [spec.min, spec.max]
    } else {
      candidates = [0.6, 0.8, 1.0, 1.2, 1.4]
        .map((m) => Math.round(spec.default * m))
        .map((v) => Math.min(spec.max, Math.max(spec.min, v)))
    }
    const unique = Array.from(new Set([...candidates, spec.default])).sort((a, b) => a - b)
    setValuesText(unique.join(','))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [param, spec?.default, spec?.min, spec?.max])

  function parseValues(): number[] {
    return valuesText
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
      .map((s) => Number(s))
      .filter((n) => !Number.isNaN(n))
  }

  function toggleTrace(id: string) {
    setSelectedTraceIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  async function runSweep() {
    setError(null)
    setExp(null)
    const values = parseValues()
    if (values.length === 0) {
      setError('enter at least one value')
      return
    }
    if (selectedTraceIds.length === 0) {
      setError('select at least one trace')
      return
    }
    if (spec) {
      const outOfRange = values.filter((v) => v < spec.min || v > spec.max)
      if (outOfRange.length > 0) {
        setError(`values out of range [${spec.min}, ${spec.max}]: ${outOfRange.join(', ')}`)
        return
      }
    }
    setRunning(true)
    try {
      const { id } = await api.createSweep(base, param, values, selectedTraceIds)
      const finished = await pollExperiment(id, setExp)
      setExp(finished)
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
  }

  const result = exp?.status === 'done' ? exp.result : null

  // One line per trace: disagreement rate (%) vs value, plus the default
  // value as a visible, explicitly-labelled zero point (verified to compute
  // 0 before this page was built -- see STUDIO_STATUS.md's M7 section).
  const traceIds = result ? Array.from(new Set(result.points.map((p) => p.trace_id))) : []

  return (
    <div>
      <h1>Sweep</h1>
      <p className="hint">
        Every point below is a real all-decisions comparison (Mode A) against the base reference, computed on
        identical recorded inputs -- never a throughput, RTT, or network-trajectory claim. Sweep variants are built
        in memory only; they are never saved to the Controllers registry.
      </p>

      <div className="panel">
        <h2>Setup</h2>
        <div className="field-row">
          <label>Base</label>
          <select value={base} onChange={(e) => setBase(e.target.value as 'cubic' | 'reno')}>
            <option value="cubic">CUBIC</option>
            <option value="reno">Reno</option>
          </select>
          <label>Parameter</label>
          <select value={param} onChange={(e) => setParam(e.target.value)}>
            {Object.keys(tunables).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          {spec && (
            <span className="hint">
              default {spec.default}, range [{spec.min}, {spec.max}] -- {spec.note}
            </span>
          )}
        </div>
        <div className="field-row">
          <label>Values (comma-separated)</label>
          <input type="text" value={valuesText} onChange={(e) => setValuesText(e.target.value)} style={{ width: 280 }} />
        </div>
        <div className="field-row" style={{ alignItems: 'flex-start' }}>
          <label>Traces</label>
          <div>
            {matchingTraces.map((t) => (
              <div key={t.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={selectedTraceIds.includes(t.id)}
                    onChange={() => toggleTrace(t.id)}
                  />{' '}
                  <span className="mono">{t.path}</span> ({fmtNum(t.n_dominant_events)} ev)
                </label>
              </div>
            ))}
            {matchingTraces.length === 0 && <p className="hint">no traces available for this ABI</p>}
          </div>
        </div>
        <button className="btn" disabled={running} onClick={runSweep}>
          {running ? 'Running…' : 'Run sweep'}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}
      {exp?.status === 'error' && <div className="error-box">Sweep failed: {exp.error}</div>}

      {result && (
        <div className="panel">
          <h2>Results</h2>
          <Chart
            traces={traceIds.map((tid) => ({
              x: result.points.filter((p) => p.trace_id === tid).map((p) => p.value),
              y: result.points.filter((p) => p.trace_id === tid).map((p) => (p.disagreement_rate ?? 0) * 100),
              name: tid,
              color: undefined,
              mode: 'lines+markers',
            }))}
            xLabel={param}
            yLabel="disagreement rate (%)"
            caption={`${result.base}/${result.param} sweep, reference=${result.reference_id} -- computed on identical recorded inputs (not a throughput/trajectory claim); default value ${result.default_value} shown as a visible zero point`}
          />
          <h3>Table</h3>
          <table>
            <thead>
              <tr>
                <th>{param}</th>
                <th>Trace</th>
                <th>Events</th>
                <th>Disagree</th>
                <th>Rate</th>
                <th>Median Δ result</th>
                <th>Median Δ post_snd_cwnd</th>
                <th>First seq</th>
              </tr>
            </thead>
            <tbody>
              {result.points.map((p, i) => (
                <tr
                  key={i}
                  data-testid={`sweep-row-${p.value}-${p.trace_id}`}
                  style={{ fontWeight: p.value === result.default_value ? 700 : 400 }}
                >
                  <td className="mono">
                    {p.value}
                    {p.value === result.default_value ? ' (default)' : ''}
                  </td>
                  <td className="mono">{p.trace_id}</td>
                  {p.error ? (
                    <td colSpan={6} className="error-box">
                      {p.error}
                    </td>
                  ) : (
                    <>
                      <td>{fmtNum(p.n_events)}</td>
                      <td data-testid={`sweep-n-disagree-${p.value}-${p.trace_id}`}>{fmtNum(p.n_disagree)}</td>
                      <td data-testid={`sweep-rate-${p.value}-${p.trace_id}`}>
                        {((p.disagreement_rate ?? 0) * 100).toFixed(3)}%
                      </td>
                      <td className="mono">{p.result_median_delta ?? '—'}</td>
                      <td className="mono">{p.post_snd_cwnd_median_delta ?? '—'}</td>
                      <td className="mono" data-testid={`sweep-first-seq-${p.value}-${p.trace_id}`}>
                        {p.first_disagreement_seq ?? '—'}
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
