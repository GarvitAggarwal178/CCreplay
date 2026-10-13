import type { Shape } from 'plotly.js-dist-min'
import type { AllDecisionsResult } from '../api'
import { fmtNum } from '../lib/format'
import Chart from './Chart'

export default function AllDecisionsPanel({ result }: { result: AllDecisionsResult }) {
  // The strip renders `disagree_runs` ([start, length] pairs, exact and
  // UNCAPPED server-side) as shaded rectangles, not as individual plotted
  // points -- a long Mode-B cascade can be a single run covering tens of
  // thousands of events, and expanding that back into one point per event
  // would defeat the entire purpose of run-length-encoding it.
  //
  // A run's data-space width is its real length, but an isolated length-1
  // run (the common Mode-A case: a seeded bug disagreeing only on isolated
  // recurrences of one callback) is then under a pixel wide on a chart
  // spanning tens of thousands of events and renders as literally nothing
  // (found by looking at the actual rendered chart, not assumed). Each run
  // gets a minimum visible width (a small fraction of the trace), centered
  // on the run, WITHOUT changing the length shown in the caption/table --
  // this only widens the drawn mark for narrow runs; a genuinely wide
  // cascade is already far past the minimum and is unaffected.
  const minVisibleWidth = Math.max(1, result.n_events * 0.003)
  const runShapes: Partial<Shape>[] = result.disagree_runs.map(([start, length]) => {
    const center = start + length / 2
    const drawWidth = Math.max(length, minVisibleWidth)
    return {
      type: 'rect',
      xref: 'x',
      yref: 'paper',
      x0: center - drawWidth / 2,
      x1: center + drawWidth / 2,
      y0: 0,
      y1: 1,
      fillcolor: 'rgba(180,35,24,0.55)',
      line: { width: 0 },
    }
  })

  const callbackNames = Array.from(
    new Set([...Object.keys(result.per_callback_checked), ...Object.keys(result.per_callback_disagree)])
  )

  return (
    <div>
      <div className="field-row">
        <span className="badge badge-neutral">Mode {result.mode}</span>
        <span data-testid="all-decisions-summary">
          {fmtNum(result.n_disagree)} / {fmtNum(result.n_events)} events disagree (
          {(result.disagreement_rate * 100).toFixed(3)}%)
        </span>
        {result.first_disagreement_index !== null && (
          <span className="hint" data-testid="all-decisions-first-seq">
            first at seq {result.first_disagreement_seq}
          </span>
        )}
      </div>
      <p className="hint">
        Every event compared independently (Mode A: both sides fed the same recorded private PRE state) or
        statefully with cascade labelling (Mode B) -- computed on identical recorded inputs, not a throughput or
        network-trajectory claim.
      </p>

      {result.disagree_runs.length > 0 ? (
        <Chart
          traces={[{ x: [0, result.n_events], y: [0, 0], name: '', mode: 'lines', color: 'rgba(0,0,0,0)' }]}
          shapes={runShapes}
          xLabel="event index"
          yLabel=""
          height={120}
          caption={`disagreement strip -- ${fmtNum(result.n_disagree)} disagreeing event(s) of ${fmtNum(result.n_events)} in ${fmtNum(result.disagree_runs.length)} run(s) (exact, not capped)`}
        />
      ) : (
        <p className="badge badge-pass">no disagreements across all {fmtNum(result.n_events)} events</p>
      )}

      <h3>Per-callback</h3>
      <table>
        <thead>
          <tr>
            <th>Callback</th>
            <th>Checked</th>
            <th>Disagree</th>
            <th>Rate</th>
          </tr>
        </thead>
        <tbody>
          {callbackNames.map((cb) => {
            const checked = result.per_callback_checked[cb] || 0
            const disagree = result.per_callback_disagree[cb] || 0
            return (
              <tr key={cb} data-testid={`all-decisions-callback-row-${cb}`}>
                <td className="mono">{cb}</td>
                <td data-testid={`all-decisions-callback-checked-${cb}`}>{fmtNum(checked)}</td>
                <td data-testid={`all-decisions-callback-disagree-${cb}`}>{fmtNum(disagree)}</td>
                <td data-testid={`all-decisions-callback-rate-${cb}`}>
                  {checked ? ((disagree / checked) * 100).toFixed(2) : '0.00'}%
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      {Object.keys(result.delta_stats).length > 0 && (
        <>
          <h3>Δ (candidate − reference) by field</h3>
          <p className="hint">Exact statistics over every disagreement, not only the capped sample below.</p>
          <table>
            <thead>
              <tr>
                <th>Field</th>
                <th>Count</th>
                <th>Median Δ</th>
                <th>Mean Δ</th>
                <th>Min Δ</th>
                <th>Max Δ</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.delta_stats).map(([field, stats]) => (
                <tr key={field}>
                  <td className="mono">{field}</td>
                  <td>{fmtNum(stats.count)}</td>
                  <td className="mono">{stats.median}</td>
                  <td className="mono">{stats.mean.toFixed(2)}</td>
                  <td className="mono">{stats.min}</td>
                  <td className="mono">{stats.max}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {result.disagreements.length > 0 && (
        <>
          <h3>
            Disagreements {result.disagreements_truncated && <span className="hint">(showing first {result.disagreements.length})</span>}
          </h3>
          <table>
            <thead>
              <tr>
                <th>seq</th>
                <th>callback</th>
                <th>fields</th>
                <th>cascaded</th>
              </tr>
            </thead>
            <tbody>
              {result.disagreements.slice(0, 100).map((d) => (
                <tr key={d.event_index}>
                  <td className="mono">{d.seq}</td>
                  <td className="mono">{d.callback}</td>
                  <td className="mono">{d.diff_fields.join(', ')}</td>
                  <td>{d.cascaded ? <span className="badge badge-partial">cascaded</span> : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.disagreements.length > 100 && (
            <p className="hint">showing first 100 of {result.disagreements.length} listed disagreements</p>
          )}
        </>
      )}
    </div>
  )
}
