import { useEffect, useState } from 'react'

interface LabCapabilities {
  is_root: boolean
  can_run_lab: boolean
  reason: string
  result_files: string[]
}

export default function Lab() {
  const [caps, setCaps] = useState<LabCapabilities | null>(null)
  const [capsError, setCapsError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/lab/capabilities')
      .then((res) => {
        if (!res.ok) throw new Error(res.statusText)
        return res.json()
      })
      .then(setCaps)
      .catch((e) => setCapsError(String(e)))
  }, [])

  return (
    <div>
      <h1>Network Lab</h1>
      <p className="hint">
        Network Lab experiments require privileged network operations (netns, tc, ethtool) that are
        unavailable to this unprivileged part of Studio. This page never runs, claims to run, or
        simulates those operations -- it only reports capability status and lists any JSON result
        files already produced by a human operator running the scripts manually.
      </p>

      <div className="panel">
        <h2>Capabilities</h2>
        {capsError && <div className="error-box">{capsError}</div>}
        {!caps && !capsError && <p className="hint">loading…</p>}
        {caps && (
          <>
            <div className="field-row">
              <label>Root in this process</label>
              <span className="mono">{String(caps.is_root)}</span>
            </div>
            <div className="field-row">
              <label>Can run lab here</label>
              <span className="mono" data-testid="lab-can-run">
                {String(caps.can_run_lab)}
              </span>
            </div>
            <div className="error-box" data-testid="lab-disabled-reason">
              Lab is disabled: {caps.reason}
            </div>
            <p className="hint">
              Needs root -- see <span className="mono">.autorun/SUDO_RUNBOOK.md</span> for the exact
              commands a human owner can run manually, outside of this app, to set up the validated
              topology and execute one lab experiment.
            </p>
          </>
        )}
      </div>

      <div className="panel">
        <h2>Results</h2>
        <p className="hint">
          Any JSON result files already present under <span className="mono">results/lab/</span>,
          produced by a human running <span className="mono">scripts/lab/lab_run.sh</span> outside this
          app.
        </p>
        {!caps && !capsError && <p className="hint">checking results/lab/…</p>}
        {caps && caps.result_files.length === 0 && <p className="hint">no lab results yet</p>}
        {caps && caps.result_files.length > 0 && (
          <ul>
            {caps.result_files.map((f) => (
              <li key={f} className="mono">
                {f}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
