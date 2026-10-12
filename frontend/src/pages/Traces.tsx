import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type TraceSummary } from '../api'
import { fmtBytes, fmtDuration, fmtNum } from '../lib/format'

export default function Traces() {
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const metaRef = useRef<HTMLInputElement>(null)

  function refresh() {
    api.listTraces().then(setTraces).catch((e) => setError(String(e)))
  }

  useEffect(refresh, [])

  async function doUpload() {
    const file = fileRef.current?.files?.[0]
    if (!file) return
    const metaFile = metaRef.current?.files?.[0]
    setUploadMsg('uploading…')
    try {
      const info = await api.uploadTrace(file, metaFile)
      setUploadMsg(`uploaded: ${info.path} (${info.abi_name}, ${info.n_dominant_events} events)`)
      refresh()
    } catch (e) {
      setUploadMsg(`failed: ${String(e)}`)
    }
  }

  return (
    <div>
      <h1>Traces</h1>
      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <h2>Upload a trace</h2>
        <div className="field-row">
          <input ref={fileRef} type="file" accept=".ccr" />
          <input ref={metaRef} type="file" accept=".json" />
          <button className="btn btn-secondary" onClick={doUpload}>
            Upload
          </button>
        </div>
        <p className="hint">.ccr file required; optional sidecar .meta.json. {uploadMsg}</p>
      </div>

      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Path</th>
              <th>ABI</th>
              <th>Events</th>
              <th>Duration</th>
              <th>Drops</th>
              <th>Callbacks</th>
              <th>Size</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {traces.map((t) => (
              <tr key={t.id}>
                <td className="mono">{t.path}</td>
                <td>
                  <span className="badge badge-neutral">{t.abi_name}</span>
                </td>
                <td>{fmtNum(t.n_dominant_events)}</td>
                <td>{fmtDuration(t.duration_s)}</td>
                <td>{(t.meta as { drops?: number } | null)?.drops ?? '—'}</td>
                <td className="hint">
                  {Object.entries(t.callback_counts)
                    .map(([k, v]) => `${k}:${v}`)
                    .join(', ')}
                </td>
                <td>{fmtBytes(t.size_bytes)}</td>
                <td>
                  <Link className="btn btn-secondary" to={`/traces/${t.id}`}>
                    Explore
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
