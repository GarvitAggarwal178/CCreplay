import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import type { Shape } from 'plotly.js-dist-min'
import { api, type EventsResponse, type SeriesResponse, type TraceDetail as TraceDetailT } from '../api'
import Chart from '../components/Chart'
import { fmtBytes, fmtDuration, fmtNum } from '../lib/format'

// "Infinite" ssthresh is recorded as INT32_MAX (2147483647) before the
// first loss -- observed directly in all three ABIs' raw trace data
// (max pre_snd_ssthresh in raw/r0/rep1.ccr and raw/cubic_replay/primary/rep1.ccr
// is exactly 2147483647, matching Linux's actual tcp_sock.snd_ssthresh init
// value of 0x7fffffff -- not the UINT32_MAX previously assumed here without
// checking). Clip anything at or above it.
const INFINITE_SSTHRESH = 2147483647

// tp->srtt_us (CoVegas's pre_srtt_us) is stored left-shifted by 3 in the
// kernel (see user/covegas_model.py: `srtt = srtt_us >> 3`); CUBIC's
// in_sample_rtt_us is a plain already-unshifted microsecond sample and
// needs no correction.
const SRTT_SHIFT = 3

function modeShapes(t: number[], mode: (number | null)[]) {
  const shapes: Partial<Shape>[] = []
  if (t.length === 0) return shapes
  let segStart = 0
  let segMode = mode[0]
  for (let i = 1; i <= mode.length; i++) {
    const m = i < mode.length ? mode[i] : null
    if (m !== segMode || i === mode.length) {
      shapes.push({
        type: 'rect',
        xref: 'x',
        yref: 'paper',
        x0: t[segStart],
        x1: t[Math.min(i, t.length - 1)],
        y0: 0,
        y1: 1,
        fillcolor: segMode === 1 ? 'rgba(180,35,24,0.12)' : 'rgba(37,99,235,0.08)',
        line: { width: 0 },
      })
      segStart = i
      segMode = m
    }
  }
  return shapes
}

export default function TraceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [detail, setDetail] = useState<TraceDetailT | null>(null)
  const [series, setSeries] = useState<SeriesResponse | null>(null)
  const [events, setEvents] = useState<EventsResponse | null>(null)
  const [page, setPage] = useState(0)
  const [callbackFilter, setCallbackFilter] = useState<string>('')
  const [drawer, setDrawer] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 25

  useEffect(() => {
    if (!id) return
    setDetail(null)
    setSeries(null)
    api.getTrace(id).then(setDetail).catch((e) => setError(String(e)))
  }, [id])

  const fields = useMemo(() => {
    if (!detail) return []
    const base = ['pre_snd_cwnd', 'pre_snd_ssthresh']
    if (detail.abi === 1) return [...base, 'in_sample_rtt_us', 'priv_pre_last_max_cwnd', 'priv_pre_bic_K']
    if (detail.abi === 2) return [...base, 'pre_srtt_us', 'priv_pre_mode']
    return base
  }, [detail])

  useEffect(() => {
    if (!id || fields.length === 0) return
    api.getSeries(id, fields, 4000).then(setSeries).catch((e) => setError(String(e)))
  }, [id, fields])

  useEffect(() => {
    if (!id) return
    api.getEvents(id, page * pageSize, pageSize, callbackFilter || undefined).then(setEvents).catch((e) => setError(String(e)))
  }, [id, page, callbackFilter])

  if (error) return <div className="error-box">{error}</div>
  if (!detail) return <p>Loading…</p>

  const ssthreshClipped = series?.series['pre_snd_ssthresh']?.map((v) =>
    v !== null && v >= INFINITE_SSTHRESH ? null : v
  )
  const hasInfinite = series?.series['pre_snd_ssthresh']?.some((v) => v !== null && v >= INFINITE_SSTHRESH)

  return (
    <div>
      <h1 className="mono">{detail.path}</h1>
      <div className="grid-2">
        <div className="panel">
          <h2>Trace metadata</h2>
          <table>
            <tbody>
              <tr>
                <td>ABI</td>
                <td>
                  <span className="badge badge-neutral">{detail.abi_name}</span>
                </td>
              </tr>
              <tr>
                <td>Kernel</td>
                <td className="mono">{detail.kernel_release}</td>
              </tr>
              <tr>
                <td>Dominant events</td>
                <td>{fmtNum(detail.n_dominant_events)}</td>
              </tr>
              <tr>
                <td>Other (non-dominant) events</td>
                <td>{fmtNum(detail.n_other_events)}</td>
              </tr>
              <tr>
                <td>Duration</td>
                <td>{fmtDuration(detail.duration_s)}</td>
              </tr>
              <tr>
                <td>Size</td>
                <td>{fmtBytes(detail.size_bytes)}</td>
              </tr>
              <tr>
                <td>sha256</td>
                <td className="mono">{detail.sha256?.slice(0, 16)}…</td>
              </tr>
            </tbody>
          </table>
          <p className="hint">{detail.other_connections?.note}</p>
        </div>
        <div className="panel">
          <h2>meta.json</h2>
          <pre className="mono" style={{ fontSize: '0.78rem', overflow: 'auto', maxHeight: 260 }}>
            {JSON.stringify(detail.meta, null, 2)}
          </pre>
        </div>
      </div>

      <div className="panel">
        <h2>Callback mix</h2>
        <Chart
          traces={[
            {
              x: Object.keys(detail.callback_counts),
              y: Object.values(detail.callback_counts),
              name: 'events',
            },
          ]}
          chartType="bar"
          xType="category"
          yLabel="events"
          height={240}
          caption={`trace ${detail.id} · recorded data`}
        />
        <table>
          <thead>
            <tr>
              {Object.keys(detail.callback_counts).map((k) => (
                <th key={k}>{k}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {Object.values(detail.callback_counts).map((v, i) => (
                <td key={i}>{fmtNum(v)}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {series && (
        <div className="panel">
          <h2>cwnd / ssthresh vs time</h2>
          <Chart
            traces={[
              { x: series.t, y: series.series['pre_snd_cwnd'], name: 'snd_cwnd' },
              { x: series.t, y: ssthreshClipped || [], name: 'snd_ssthresh (clipped)' },
            ]}
            shapes={detail.abi === 2 ? modeShapes(series.t, series.series['priv_pre_mode'] || []) : undefined}
            xLabel="t (s)"
            yLabel="segments"
            caption={`trace ${detail.id} · sha ${detail.sha256?.slice(0, 8)} · recorded data${hasInfinite ? ' · ssthresh shown as "∞" clipped to null before first loss' : ''}${detail.abi === 2 ? ' · shaded bands: DELAY (blue) / COMPETE (red)' : ''}`}
          />
          {detail.abi === 1 && (
            <>
              <h2>CUBIC W_max / bic_K</h2>
              <Chart
                traces={[
                  { x: series.t, y: series.series['priv_pre_last_max_cwnd'] || [], name: 'last_max_cwnd (W_max)' },
                  { x: series.t, y: series.series['priv_pre_bic_K'] || [], name: 'bic_K', yaxis: 'y2' },
                ]}
                xLabel="t (s)"
                yLabel="W_max"
                y2Label="bic_K"
                caption={`trace ${detail.id} · recorded data`}
              />
            </>
          )}
          {(detail.abi === 1 || detail.abi === 2) && (
            <>
              <h2>RTT samples</h2>
              <Chart
                traces={[
                  {
                    x: series.t,
                    y:
                      detail.abi === 1
                        ? series.series['in_sample_rtt_us'] || []
                        : (series.series['pre_srtt_us'] || []).map((v) => (v === null ? null : v >> SRTT_SHIFT)),
                    name: detail.abi === 1 ? 'sample_rtt_us' : 'srtt_us (>>3)',
                    mode: detail.abi === 1 ? 'markers' : 'lines',
                  },
                ]}
                xLabel="t (s)"
                yLabel="µs"
                caption={`trace ${detail.id} · recorded data${detail.abi === 1 ? ' · only present on pkts_acked events with a real sample' : ' · raw tp->srtt_us is stored <<3; shown here right-shifted back to microseconds'}`}
              />
            </>
          )}
        </div>
      )}

      <div className="panel">
        <h2>Events</h2>
        <div className="field-row">
          <label>Callback filter</label>
          <select value={callbackFilter} onChange={(e) => { setCallbackFilter(e.target.value); setPage(0) }}>
            <option value="">all</option>
            {Object.keys(detail.callback_counts).map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
          <button className="btn btn-secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            ← prev
          </button>
          <button
            className="btn btn-secondary"
            disabled={!events || (page + 1) * pageSize >= events.total}
            onClick={() => setPage((p) => p + 1)}
          >
            next →
          </button>
          <span className="hint">
            {events ? `${page * pageSize + 1}-${Math.min((page + 1) * pageSize, events.total)} of ${events.total}` : ''}
          </span>
        </div>
        <table>
          <thead>
            <tr>
              <th>seq</th>
              <th>callback</th>
              <th>pre_snd_cwnd</th>
              <th>result</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {events?.events.map((e) => (
              <tr key={String(e.seq)}>
                <td className="mono">{String(e.seq)}</td>
                <td className="mono">{String(e.callback_id)}</td>
                <td className="mono">{String(e.pre_snd_cwnd)}</td>
                <td className="mono">{String(e.result)}</td>
                <td>
                  <button className="btn btn-secondary" onClick={() => setDrawer(e)}>
                    JSON
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {drawer && (
        <div className="panel" style={{ position: 'fixed', right: 20, bottom: 20, maxWidth: 420, maxHeight: '60vh', overflow: 'auto', zIndex: 20 }}>
          <div className="field-row">
            <b>Event JSON</b>
            <button className="btn btn-secondary" onClick={() => setDrawer(null)}>
              close
            </button>
          </div>
          <pre className="mono" style={{ fontSize: '0.75rem' }}>{JSON.stringify(drawer, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}
