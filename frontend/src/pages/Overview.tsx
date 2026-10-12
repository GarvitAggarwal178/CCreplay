import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, pollExperiment, type ControllerSummary, type HealthInfo, type TraceSummary } from '../api'
import { badgeClassForVerdict } from '../lib/format'

interface StepState {
  label: string
  status: 'idle' | 'running' | 'done' | 'error'
  summary?: string
  experimentId?: string
  ok?: boolean
}

export default function Overview() {
  const navigate = useNavigate()
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [controllers, setControllers] = useState<ControllerSummary[]>([])
  const [steps, setSteps] = useState<StepState[]>([
    { label: '1. Negative control (cubic vs cubic) → NO DIVERGENCE', status: 'idle' },
    { label: '2. Seeded bug (cubic vs cubic_bug_ssthresh) → seq 1,705', status: 'idle' },
    { label: '3. Reproduce from checkpoint (interval 500) → 204-event suffix', status: 'idle' },
    { label: '4. Parameter variant β=0.8 (BETA=819) → divergence', status: 'idle' },
    { label: '5. Historical CoVegas regression (rep4) → seq 10,421', status: 'idle' },
  ])

  useEffect(() => {
    api.health().then(setHealth).catch(() => void 0)
    api.listTraces().then(setTraces).catch(() => void 0)
    api.listControllers().then(setControllers).catch(() => void 0)
  }, [])

  function setStep(i: number, patch: Partial<StepState>) {
    setSteps((prev) => prev.map((s, idx) => (idx === i ? { ...s, ...patch } : s)))
  }

  function findTrace(path: string): string | undefined {
    return traces.find((t) => t.path === path)?.id
  }

  async function runStep1() {
    const tid = findTrace('raw/cubic_replay/primary/rep1.ccr')
    if (!tid) return setStep(0, { status: 'error', summary: 'cubic rep1 trace not found' })
    setStep(0, { status: 'running' })
    try {
      const { id } = await api.createExperiment('diff', tid, 'cubic', 'cubic')
      const exp = await pollExperiment(id)
      const ok = exp.status === 'done' && exp.result?.result === 'NO DIVERGENCE'
      setStep(0, { status: ok ? 'done' : 'error', ok, experimentId: id, summary: exp.result?.result || exp.error || '' })
    } catch (e) {
      setStep(0, { status: 'error', summary: String(e) })
    }
  }

  async function runStep2() {
    const tid = findTrace('raw/cubic_replay/primary/rep1.ccr')
    if (!tid) return setStep(1, { status: 'error', summary: 'cubic rep1 trace not found' })
    setStep(1, { status: 'running' })
    try {
      const { id } = await api.createExperiment('diff', tid, 'cubic', 'cubic_bug_ssthresh')
      const exp = await pollExperiment(id)
      const seq = exp.result?.divergence?.first_divergent_event.seq
      const ok = seq === 1705
      setStep(1, {
        status: ok ? 'done' : 'error',
        ok,
        experimentId: id,
        summary: `seq=${seq}, callback=${exp.result?.divergence?.callback}`,
      })
    } catch (e) {
      setStep(1, { status: 'error', summary: String(e) })
    }
  }

  async function runStep3() {
    const tid = findTrace('raw/cubic_replay/primary/rep1.ccr')
    if (!tid) return setStep(2, { status: 'error', summary: 'cubic rep1 trace not found' })
    setStep(2, { status: 'running' })
    try {
      const { id } = await api.createExperiment('checkpoint', tid, 'cubic', 'cubic_bug_ssthresh', 500)
      const exp = await pollExperiment(id)
      const ok = exp.result?.suffix_length === 204 && exp.result?.reproduced_same_divergence === true
      setStep(2, {
        status: ok ? 'done' : 'error',
        ok,
        experimentId: id,
        summary: `checkpoint@${exp.result?.nearest_checkpoint?.event_index}, suffix=${exp.result?.suffix_length}, reproduced=${exp.result?.reproduced_same_divergence}`,
      })
    } catch (e) {
      setStep(2, { status: 'error', summary: String(e) })
    }
  }

  async function runStep4() {
    const tid = findTrace('raw/cubic_replay/primary/rep1.ccr')
    if (!tid) return setStep(3, { status: 'error', summary: 'cubic rep1 trace not found' })
    setStep(3, { status: 'running' })
    try {
      const { id: candId } = await api.createParamController('cubic', `beta_0_8_${Date.now()}`, { BETA: 819 })
      const { id } = await api.createExperiment('diff', tid, 'cubic', candId)
      const exp = await pollExperiment(id)
      const seq = exp.result?.divergence?.first_divergent_event.seq
      const ok = seq === 742
      setStep(3, {
        status: ok ? 'done' : 'error',
        ok,
        experimentId: id,
        summary: `candidate=${candId}, seq=${seq}, callback=${exp.result?.divergence?.callback}`,
      })
    } catch (e) {
      setStep(3, { status: 'error', summary: String(e) })
    }
  }

  async function runStep5() {
    const tid = findTrace('raw/covegas_campaign/rep4.ccr')
    if (!tid) return setStep(4, { status: 'error', summary: 'covegas_campaign rep4 trace not found' })
    setStep(4, { status: 'running' })
    try {
      const { id } = await api.createExperiment('diff', tid, 'covegas', 'covegas_v3_latch')
      const exp = await pollExperiment(id)
      const seq = exp.result?.divergence?.first_divergent_event.seq
      const modeDiff = exp.result?.divergence?.private_state_diff?.['priv_post_mode'] as
        | { reference: unknown; candidate: unknown }
        | undefined
      const MODE_NAME: Record<string, string> = { '0': 'DELAY', '1': 'COMPETE' }
      const ok = seq === 10421
      setStep(4, {
        status: ok ? 'done' : 'error',
        ok,
        experimentId: id,
        summary: modeDiff
          ? `seq=${seq}, priv_post_mode: ${MODE_NAME[String(modeDiff.reference)] ?? modeDiff.reference} <-> ${MODE_NAME[String(modeDiff.candidate)] ?? modeDiff.candidate}`
          : `seq=${seq}`,
      })
    } catch (e) {
      setStep(4, { status: 'error', summary: String(e) })
    }
  }

  const runners = [runStep1, runStep2, runStep3, runStep4, runStep5]

  async function openInWorkbench(experimentId: string) {
    const exp = await api.getExperiment(experimentId)
    const cfg = exp.config as { trace_id: string; reference: string; candidate: string }
    navigate(`/diff?trace=${cfg.trace_id}&reference=${cfg.reference}&candidate=${cfg.candidate}`)
  }

  return (
    <div>
      <h1>CCReplay Studio</h1>
      <p>
        CCReplay is a regression debugger for TCP congestion-control implementations. It records the
        congestion-control callback boundary of a live Linux TCP connection, then re-executes controller
        implementations against that recording to localize the exact transition where two implementations first
        diverge. This Studio browses recorded traces, builds controller variants, compares them on real recorded
        inputs, and reproduces the result — all through this one-command local app.
      </p>

      <div className="panel">
        <h2>Replay ABI validation status</h2>
        <table>
          <thead>
            <tr>
              <th>ABI</th>
              <th>Verdict</th>
              <th>Caveat</th>
            </tr>
          </thead>
          <tbody>
            {health?.abi_validation_table.map((row) => (
              <tr key={row.abi}>
                <td>{row.abi}</td>
                <td>
                  <span className={badgeClassForVerdict(row.verdict)}>{row.verdict}</span>
                </td>
                <td>{row.caveat}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hint">
          git {health?.git_commit} · python {health?.python} · library: {traces.length} traces, {controllers.length}{' '}
          controllers
        </p>
      </div>

      <div className="panel">
        <h2>Guided demo</h2>
        <p className="hint">Each button calls the real API and shows the real result inline — nothing here is hardcoded.</p>
        {steps.map((s, i) => (
          <div key={i} className="field-row" style={{ alignItems: 'flex-start' }}>
            <button className="btn btn-secondary" disabled={s.status === 'running'} onClick={() => runners[i]()}>
              {s.status === 'running' ? 'Running…' : 'Run'}
            </button>
            <div style={{ flex: 1 }}>
              <div>{s.label}</div>
              {s.status !== 'idle' && (
                <div>
                  <span
                    className={
                      s.status === 'done' && s.ok
                        ? 'badge badge-pass'
                        : s.status === 'running'
                          ? 'badge badge-neutral'
                          : 'badge badge-fail'
                    }
                  >
                    {s.status === 'running' ? 'running' : s.ok ? 'matches expected value' : 'unexpected result'}
                  </span>{' '}
                  <span className="mono hint">{s.summary}</span>
                  {s.experimentId && (
                    <button
                      className="btn btn-secondary"
                      style={{ marginLeft: '0.5rem' }}
                      onClick={() => void openInWorkbench(s.experimentId!)}
                    >
                      Open in Diff Workbench
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
