import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, pollExperiment, type ControllerSummary, type Experiment, type TraceSummary } from '../api'
import DivergenceCard from '../components/DivergenceCard'
import ExportButtons from '../components/ExportButtons'
import AllDecisionsPanel from '../components/AllDecisionsPanel'

export default function Diff() {
  const [params] = useSearchParams()
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [controllers, setControllers] = useState<ControllerSummary[]>([])
  const [traceId, setTraceId] = useState(params.get('trace') || '')
  const [refId, setRefId] = useState(params.get('reference') || '')
  const [candId, setCandId] = useState(params.get('candidate') || '')
  const [interval, setInterval_] = useState(500)
  const [running, setRunning] = useState(false)
  const [exp, setExp] = useState<Experiment | null>(null)
  const [ckptExp, setCkptExp] = useState<Experiment | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [compareAll, setCompareAll] = useState(false)
  const [allMode, setAllMode] = useState<'A' | 'B'>('A')
  const [allExp, setAllExp] = useState<Experiment | null>(null)
  const [allRunning, setAllRunning] = useState(false)

  useEffect(() => {
    api.listTraces().then(setTraces).catch((e) => setError(String(e)))
    api.listControllers().then(setControllers).catch((e) => setError(String(e)))
  }, [])

  const traceAbi = useMemo(() => traces.find((t) => t.id === traceId)?.abi, [traces, traceId])
  const compatibleControllers = useMemo(
    () => controllers.filter((c) => c.abi === traceAbi || traceAbi === undefined),
    [controllers, traceAbi]
  )

  useEffect(() => {
    if (params.get('trace') && params.get('reference') && params.get('candidate')) {
      void runDiff(params.get('trace')!, params.get('reference')!, params.get('candidate')!)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function runDiff(t = traceId, r = refId, c = candId) {
    setError(null)
    setExp(null)
    setCkptExp(null)
    setAllExp(null)
    if (!t || !r || !c) {
      setError('select a trace, reference, and candidate first')
      return
    }
    setRunning(true)
    try {
      const { id } = await api.createExperiment('diff', t, r, c)
      const finished = await pollExperiment(id, setExp)
      setExp(finished)
    } catch (e) {
      setError(String(e))
    } finally {
      setRunning(false)
    }
    if (compareAll) {
      void runAllDecisions(t, r, c)
    }
  }

  async function runAllDecisions(t = traceId, r = refId, c = candId) {
    if (!t || !r || !c) return
    setAllRunning(true)
    try {
      const { id } = await api.createExperiment('all_decisions', t, r, c, undefined, allMode)
      const finished = await pollExperiment(id, setAllExp)
      setAllExp(finished)
    } catch (e) {
      setError(String(e))
    } finally {
      setAllRunning(false)
    }
  }

  async function runCheckpoint() {
    if (!exp || exp.status !== 'done') return
    setError(null)
    try {
      const { id } = await api.createExperiment('checkpoint', traceId, refId, candId, interval)
      const finished = await pollExperiment(id, setCkptExp)
      setCkptExp(finished)
    } catch (e) {
      setError(String(e))
    }
  }

  const abiIncompatible =
    traceId && refId && candId && (traces.find((t) => t.id === traceId)?.abi !== controllers.find((c) => c.id === refId)?.abi ||
      traces.find((t) => t.id === traceId)?.abi !== controllers.find((c) => c.id === candId)?.abi)

  return (
    <div>
      <h1>Diff Workbench</h1>
      <div className="panel">
        <h2>Setup</h2>
        <div className="field-row">
          <label>Trace</label>
          <select value={traceId} onChange={(e) => setTraceId(e.target.value)}>
            <option value="">— select —</option>
            {traces.map((t) => (
              <option key={t.id} value={t.id}>
                {t.path} ({t.abi_name}, {t.n_dominant_events.toLocaleString()} ev)
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label>Reference</label>
          <select value={refId} onChange={(e) => setRefId(e.target.value)}>
            <option value="">— select —</option>
            {controllers.map((c) => (
              <option key={c.id} value={c.id} disabled={traceAbi !== undefined && c.abi !== traceAbi}>
                {c.name} [{c.kind}] {c.abi !== traceAbi ? '(incompatible ABI)' : ''}
              </option>
            ))}
          </select>
          <label>Candidate</label>
          <select value={candId} onChange={(e) => setCandId(e.target.value)}>
            <option value="">— select —</option>
            {controllers.map((c) => (
              <option key={c.id} value={c.id} disabled={traceAbi !== undefined && c.abi !== traceAbi}>
                {c.name} [{c.kind}] {c.abi !== traceAbi ? '(incompatible ABI)' : ''}
              </option>
            ))}
          </select>
        </div>
        {abiIncompatible && (
          <div className="error-box">
            Reference/candidate ABI does not match the selected trace&apos;s Replay ABI — pick controllers built for
            the same ABI as the trace.
          </div>
        )}
        <button className="btn" disabled={running || !!abiIncompatible} onClick={() => runDiff()}>
          {running ? 'Running…' : 'Run diff'}
        </button>
        <p className="hint">{compatibleControllers.length} ABI-compatible controller(s) available for this trace.</p>
        <div className="field-row">
          <label>
            <input type="checkbox" checked={compareAll} onChange={(e) => setCompareAll(e.target.checked)} />
            {' '}Compare all decisions
          </label>
          <select value={allMode} onChange={(e) => setAllMode(e.target.value as 'A' | 'B')} disabled={!compareAll}>
            <option value="A">Mode A (event-local)</option>
            <option value="B">Mode B (stateful, cascaded)</option>
          </select>
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}

      {exp?.status === 'error' && <div className="error-box">Experiment failed: {exp.error}</div>}

      {exp?.status === 'done' && exp.result && (
        <div className="panel">
          <DivergenceCard result={exp.result} />
          <ExportButtons experimentId={exp.id} />

          {exp.result.divergence && (
            <div style={{ marginTop: '1rem' }}>
              <h2>Reproduce from checkpoint</h2>
              <div className="field-row">
                <label>Interval</label>
                <select value={interval} onChange={(e) => setInterval_(Number(e.target.value))}>
                  {[50, 100, 250, 500, 1000, 2500, 5000].map((i) => (
                    <option key={i} value={i}>
                      {i}
                    </option>
                  ))}
                </select>
                <button className="btn btn-secondary" onClick={runCheckpoint}>
                  Run checkpoint reproducer
                </button>
              </div>
              {ckptExp?.status === 'done' && ckptExp.result && (
                <div>
                  <p>
                    Nearest checkpoint @ event <b className="mono">{ckptExp.result.nearest_checkpoint?.event_index}</b>,
                    suffix length <b className="mono">{ckptExp.result.suffix_length}</b> events.{' '}
                    {ckptExp.result.reproduced_same_divergence ? (
                      <span className="badge badge-pass">reproduced identical divergence</span>
                    ) : (
                      <span className="badge badge-fail">did not reproduce identical divergence</span>
                    )}
                  </p>
                  <ExportButtons experimentId={ckptExp.id} />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {compareAll && allRunning && <p className="hint">Running all-decisions comparison…</p>}
      {allExp?.status === 'error' && <div className="error-box">All-decisions comparison failed: {allExp.error}</div>}
      {allExp?.status === 'done' && allExp.result && (
        <div className="panel" data-testid="all-decisions-panel">
          <h2>Compare all decisions</h2>
          <AllDecisionsPanel result={allExp.result} />
          <ExportButtons experimentId={allExp.id} />
        </div>
      )}
    </div>
  )
}
