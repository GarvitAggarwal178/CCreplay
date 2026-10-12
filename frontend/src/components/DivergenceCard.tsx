import { useEffect, useState } from 'react'
import type { Shape } from 'plotly.js-dist-min'
import { api, type DiffResult, type SeriesResponse } from '../api'
import { fmtNum } from '../lib/format'
import Chart from './Chart'

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ marginTop: '0.75rem' }}>
      <button className="btn btn-secondary" onClick={() => setOpen((o) => !o)}>
        {open ? '▾' : '▸'} {title}
      </button>
      {open && <div style={{ marginTop: '0.5rem' }}>{children}</div>}
    </div>
  )
}

function KVTable({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (entries.length === 0) return <p className="hint">none</p>
  return (
    <table>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td className="mono">{k}</td>
            <td className="mono">{String(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function DivergenceCard({ result }: { result: DiffResult }) {
  const d = result.divergence
  const [series, setSeries] = useState<SeriesResponse | null>(null)

  useEffect(() => {
    setSeries(null)
    api
      .getSeries(result.trace_id, ['pre_snd_cwnd', 'seq'], 2000)
      .then(setSeries)
      .catch(() => void 0)
  }, [result.trace_id])

  const divergenceShape: Partial<Shape>[] | undefined = d
    ? [
        {
          type: 'line',
          xref: 'x',
          yref: 'paper',
          x0: d.first_divergent_event.seq,
          x1: d.first_divergent_event.seq,
          y0: 0,
          y1: 1,
          line: { color: '#b42318', width: 2, dash: 'dash' },
        },
      ]
    : undefined

  return (
    <div>
      <div className={`verdict-banner ${d ? 'verdict-divergence' : 'verdict-none'}`}>
        {result.result} — {result.reference_id} vs {result.candidate_id} on {result.trace_id}
      </div>
      <p className="hint">
        {fmtNum(result.n_events_dominant)} dominant-connection events replayed · matched{' '}
        {fmtNum(result.matched_event_count_before_divergence)} before{' '}
        {d ? 'divergence' : 'the end (no divergence)'}.
      </p>

      {series && (
        <Chart
          traces={[{ x: series.series['seq'] || [], y: series.series['pre_snd_cwnd'] || [], name: 'snd_cwnd' }]}
          xLabel="seq"
          yLabel="snd_cwnd"
          shapes={divergenceShape}
          height={220}
          caption={
            d
              ? `trace ${result.trace_id} · recorded data · dashed line marks first divergence at seq ${d.first_divergent_event.seq}`
              : `trace ${result.trace_id} · recorded data`
          }
        />
      )}

      {d && (
        <>
          <div className="panel" style={{ background: 'var(--bg-raised)' }}>
            <h2>First divergence</h2>
            <table>
              <tbody>
                <tr>
                  <td>Event seq</td>
                  <td className="mono">{d.first_divergent_event.seq}</td>
                </tr>
                <tr>
                  <td>Event index</td>
                  <td className="mono">{d.first_divergent_event.event_index}</td>
                </tr>
                <tr>
                  <td>Callback</td>
                  <td className="mono">{d.callback}</td>
                </tr>
                <tr>
                  <td>Kind</td>
                  <td>
                    <span className={result.kind === 'result' ? 'badge badge-fail' : 'badge badge-partial'}>
                      {result.kind === 'result'
                        ? 'callback result / cwnd differs'
                        : 'only internal controller state differs'}
                    </span>
                  </td>
                </tr>
                <tr>
                  <td>Matched events before</td>
                  <td className="mono">{fmtNum(d.matched_event_count_before_divergence)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h3>Differing fields</h3>
          <table>
            <thead>
              <tr>
                <th>Field</th>
                <th>Reference</th>
                <th>Candidate</th>
              </tr>
            </thead>
            <tbody>
              {d.all_diff_fields.map((f) => {
                const group = f.startsWith('priv_post_')
                  ? d.private_state_diff
                  : f.startsWith('post_')
                    ? d.controller_owned_state_diff
                    : d.callback_result_diff
                const vals = group[f]
                return (
                  <tr key={f}>
                    <td className="mono">{f}</td>
                    <td className="mono diff-val-ref">{vals ? String(vals.reference) : '—'}</td>
                    <td className="mono diff-val-cand">{vals ? String(vals.candidate) : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          <Collapsible title="Shared PRE state">
            <KVTable data={d.shared_pre} />
          </Collapsible>
          <Collapsible title="Callback inputs & time">
            <KVTable data={d.inputs_and_time} />
          </Collapsible>
          {result.event_context && (
            <Collapsible title="Event context (±5)">
              <table>
                <thead>
                  <tr>
                    <th>seq</th>
                    <th>callback</th>
                  </tr>
                </thead>
                <tbody>
                  {result.event_context.map((e) => (
                    <tr key={e.seq} style={{ fontWeight: e.seq === d.first_divergent_event.seq ? 700 : 400 }}>
                      <td className="mono">{e.seq}</td>
                      <td className="mono">{e.callback}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Collapsible>
          )}
        </>
      )}
    </div>
  )
}
