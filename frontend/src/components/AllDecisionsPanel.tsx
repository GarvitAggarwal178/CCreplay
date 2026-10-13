import type { AllDecisionsResult } from '../api'
import { fmtNum } from '../lib/format'
import Chart from './Chart'

export default function AllDecisionsPanel({ result }: { result: AllDecisionsResult }) {
  // The strip plots the sparse `disagreements` list (event_index for each
  // disagreement, already capped server-side) -- never a dense per-event
  // mask, which would be up to ~236k points for a single trace.
  const disagreeIndices = result.disagreements.map((d) => d.event_index)

  const callbackNames = Array.from(
    new Set([...Object.keys(result.per_callback_checked), ...Object.keys(result.per_callback_disagree)])
  )

  return (
    <div>
      <div className="field-row">
        <span className="badge badge-neutral">Mode {result.mode}</span>
        <span>
          {fmtNum(result.n_disagree)} / {fmtNum(result.n_events)} events disagree (
          {(result.disagreement_rate * 100).toFixed(3)}%)
        </span>
        {result.first_disagreement_index !== null && (
          <span className="hint">first at seq {result.first_disagreement_seq}</span>
        )}
      </div>
      <p className="hint">
        Every event compared independently (Mode A: both sides fed the same recorded private PRE state) or
        statefully with cascade labelling (Mode B) -- computed on identical recorded inputs, not a throughput or
        network-trajectory claim.
      </p>

      {disagreeIndices.length > 0 ? (
        <Chart
          traces={[{ x: disagreeIndices, y: disagreeIndices.map(() => 1), name: 'disagreement', mode: 'markers' }]}
          xLabel="event index"
          yLabel=""
          height={120}
          caption={`disagreement strip -- ${fmtNum(result.n_disagree)} disagreeing event(s) of ${fmtNum(result.n_events)}${result.disagreements_truncated ? ` (plotting first ${fmtNum(disagreeIndices.length)})` : ''}`}
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
              <tr key={cb}>
                <td className="mono">{cb}</td>
                <td>{fmtNum(checked)}</td>
                <td>{fmtNum(disagree)}</td>
                <td>{checked ? ((disagree / checked) * 100).toFixed(2) : '0.00'}%</td>
              </tr>
            )
          })}
        </tbody>
      </table>

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
