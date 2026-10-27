import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import './AlgorithmWorkbench.css'

type Output = { result: number; result_valid: number; post_snd_cwnd: number; post_snd_cwnd_cnt: number; decision?: { rule?: string; calculation?: string; meaning?: string } }
type Row = { index: number; seq: number; callback: string; input: Record<string, number | string>; a: Output; b: Output; different_fields: string[]; private_a?:{pre:unknown;post:unknown}; private_b?:{pre:unknown;post:unknown} }
type Result = { execution_mode?:string; initialization?:unknown; initialization_sha256?:string; rows: Row[]; compared_events: number; disagreements: number; first_difference: number | null; provenance: { kind: string; label: string; scope: string }; source_a_sha256: string; source_b_sha256: string }
type Trace = { id: string; abi: number; name?: string }
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new Error((await response.text()).slice(0, 1000))
  return response.json() as Promise<T>
}
function saveJson(result: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }))
  const link = document.createElement('a'); link.href = url; link.download = 'algorithm-comparison.json'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export default function AlgorithmWorkbench() {
  const [search, setSearch] = useSearchParams()
  const savedId = search.get('job') || ''
  const [starter, setStarter] = useState({ a: '', b: '' })
  const [sourceA, setSourceA] = useState('')
  const [sourceB, setSourceB] = useState('')
  const [scenario, setScenario] = useState('')
  const [executionMode,setExecutionMode] = useState('event_local')
  const [nameA,setNameA] = useState('Algorithm A')
  const [nameB,setNameB] = useState('Algorithm B')
  const [inputKind, setInputKind] = useState('scenario')
  const [traces, setTraces] = useState<Trace[]>([])
  const [traceId, setTraceId] = useState('')
  const [offset, setOffset] = useState(0)
  const [limit, setLimit] = useState(100)
  const [result, setResult] = useState<Result | null>(null)
  const [selected, setSelected] = useState(0)
  const [error, setError] = useState('')
  const [jobId, setJobId] = useState(savedId)
  const [busy, setBusy] = useState(!!savedId)
  const [field, setField] = useState<'post_snd_cwnd' | 'result'>('post_snd_cwnd')
  useEffect(() => {
    let active = true
    request<{ source_a: string; source_b: string; scenario: unknown }>('/api/algorithm-workbench/presets')
      .then(p => { if (active) { setStarter({ a: p.source_a, b: p.source_b }); if (!savedId) { setSourceA(p.source_a); setSourceB(p.source_b); setScenario(JSON.stringify(p.scenario, null, 2)) } } })
      .catch(e => { if (active) setError(String(e)) })
    request<Trace[]>('/api/traces').then(t => { if (active) { const compatible = t.filter(x => x.abi === 0); setTraces(compatible); if (!savedId) setTraceId(compatible[0]?.id || '') } }).catch(e => { if (active) setError(String(e)) })
    return () => { active = false }
  }, [savedId])
  useEffect(() => {
    if (!jobId) return
    let active = true
    let timer: ReturnType<typeof setTimeout>
    const poll = async () => {
      try {
        const job = await request<{ status: string; result: Result; error?: string; config: {execution_mode?:string; name_a?:string;name_b?:string;source_a:string; source_b:string; scenario:unknown; input_kind:string; trace_id:string; offset:number; limit:number} }>(`/api/experiments/${jobId}`)
        if (!active) return
        const c = job.config
        setExecutionMode(c.execution_mode || 'event_local'); setNameA(c.name_a || 'Algorithm A');setNameB(c.name_b || 'Algorithm B')
        setSourceA(c.source_a); setSourceB(c.source_b); setScenario(JSON.stringify(c.scenario, null, 2)); setInputKind(c.input_kind || 'scenario'); setTraceId(c.trace_id || ''); setOffset(c.offset || 0); setLimit(c.limit || 100)
        if (job.status === 'done') { setResult(job.result); setSelected(0); setBusy(false); setJobId('') }
        else if (['error','interrupted','cancelled'].includes(job.status)) { setError(job.error || `Execution ${job.status}`); setBusy(false); setJobId('') }
        else { setBusy(true); timer = setTimeout(poll, 500) }
      } catch (e) { if (active) { setError(String(e)); setBusy(false); setJobId('') } }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [jobId])
  function invalidate() { setResult(null); setError('') }
  async function importFile(file: File | undefined, target: 'a' | 'b' | 'scenario') {
    if (!file) return
    if (file.size > (target === 'scenario' ? 1_000_000 : 100_000)) { setError('File is too large'); return }
    try {
      const text = await file.text(); invalidate()
      if (target === 'a') {setSourceA(text);setNameA(file.name)}
      else if (target === 'b') {setSourceB(text);setNameB(file.name)}
      else { JSON.parse(text); setScenario(text); setInputKind('scenario') }
    } catch (e) { setError(String(e)) }
  }
  async function run() {
    setError(''); setResult(null); setBusy(true)
    try {
      const body = { source_a: sourceA, source_b: sourceB, input_kind: inputKind, execution_mode:executionMode,name_a:nameA,name_b:nameB,
        scenario: inputKind === 'scenario' ? JSON.parse(scenario) : null,
        trace_id: inputKind === 'recording' ? traceId : null, offset, limit }
      const job = await request<{ id: string }>('/api/algorithm-workbench/compare', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      setSearch({job:job.id}); setJobId(job.id)
    } catch (e) { setError(String(e)); setBusy(false) }
  }
  const row = result?.rows[selected]
  const chartRows = result?.rows.filter(r => field === 'post_snd_cwnd' || r.a.result_valid === 1) || []
  const max = Math.max(1, ...chartRows.flatMap(r => [r.a[field], r.b[field]]))
  return <div className="awb">
    <p><Link to="/controllers">Controllers</Link> · <Link to="/replay">Recorded debugger</Link> · <Link to="/runs">Saved runs</Link></p><div className="awb-title"><div><p className="awb-kicker">CCREPLAY STUDIO / ALGORITHM WORKBENCH</p><h1>Same input. Two decisions.</h1>
      <p>Write or import two independent congestion policies, execute them, and inspect how each decision was calculated.</p></div><span className="awb-chip">TCP callbacks · v0</span></div>
    <div className="awb-note">Each callback receives the same PRE values. Outputs are computed by your Python code. The next recorded input is supplied independently; this view does not predict a new network trajectory.</div>
    {error && <div className="error" role="alert">{error}</div>}
    <fieldset disabled={busy} className="awb-setup"><legend>1 · Choose inputs and algorithms</legend>
      <div className="awb-toolbar"><label>Execution mode <select aria-label="Execution mode" value={executionMode} onChange={e=>{invalidate();setExecutionMode(e.target.value)}}><option value="event_local">Event-local · no private history</option><option value="stateful">Stateful · initialized private history</option></select></label><label>Input source <select aria-label="Input source" value={inputKind} onChange={e => { invalidate(); setInputKind(e.target.value) }}><option value="scenario">Controlled input sequence (synthetic)</option><option value="recording">Captured recording · v0</option></select></label>
        {inputKind === 'scenario' ? <label className="awb-file">Import input JSON<input type="file" accept=".json" onChange={e => void importFile(e.target.files?.[0], 'scenario')} /></label> : <>
          <label>Recording <select aria-label="Recording" value={traceId} onChange={e => { invalidate(); setTraceId(e.target.value) }}>{traces.map(t => <option key={t.id} value={t.id}>{t.name || t.id}</option>)}</select></label>
          <label>Start index <input type="number" min={0} value={offset} onChange={e => { invalidate(); setOffset(Number(e.target.value)) }} /></label>
          <label>Events (1–1000) <input type="number" min={1} max={1000} value={limit} onChange={e => { invalidate(); setLimit(Number(e.target.value)) }} /></label></>}
      </div>
      <p className="awb-small">Stateful mode carries each implementation's own initialized JSON private state; shared TCP PRE still comes from each supplied event. Recorded stateful windows must start at index 0; prefix warmup is not supported.</p><details><summary>Import interface & blank template</summary><p>Trusted Python must expose transition(event, private_state), COMPARISON_FIELDS for v0, and unsigned 32-bit result_valid, result, post_snd_cwnd and post_snd_cwnd_cnt outputs. Return (output, next_state). Event-local mode returns None; stateful mode declares INITIAL_PRIVATE_STATE or NONE_PRIVATE_STATE and returns bounded finite JSON state. Each source can use different state keys. Optional decision annotations are plain text, not line-execution evidence.</p><a href="/api/algorithm-workbench/template.py" download>Download blank Python interface</a></details>
      {inputKind === 'scenario' && <details><summary>Inspect or edit the supplied callback inputs</summary><textarea aria-label="Callback input JSON" value={scenario} onChange={e => { invalidate(); setScenario(e.target.value) }} rows={12} /></details>}
      <div className="awb-grid">{(['a', 'b'] as const).map(side => <section className={`awb-source awb-${side}`} key={side}>
        <h2>Algorithm {side.toUpperCase()}</h2><label>Algorithm {side.toUpperCase()} name<input maxLength={160} value={side==='a'?nameA:nameB} onChange={e=>{invalidate();if(side==='a')setNameA(e.target.value);else setNameB(e.target.value)}}/></label>
        <p>{(side === 'a' ? sourceA : sourceB) !== starter[side] ? 'Loaded or edited source · inspect this implementation below.' : side === 'a' ? 'Starter example: grow by one per eligible callback; retain two-thirds on loss.' : 'Starter example: use ACK batch size, capped at four; subtract integer square root on loss.'}</p>
        <label className="awb-file">Import your own .py file<input type="file" accept=".py" onChange={e => void importFile(e.target.files?.[0], side)} /></label>
        <CodeMirror editable={!busy} aria-label={`Algorithm ${side.toUpperCase()} source editor`} value={side === 'a' ? sourceA : sourceB} height="300px" extensions={[python()]} onChange={value => { invalidate(); if (side === 'a') setSourceA(value); else setSourceB(value) }} />
      </section>)}</div>
      <p className="awb-small">Imported files must implement the displayed callback contract. Python runs locally under the application account; use trusted code. Explanations are supplied by the algorithm and displayed as text.</p>
      <button className="btn" disabled={!sourceA || !sourceB || (inputKind === 'recording' && !traceId)} onClick={() => void run()}>2 · Run both algorithms</button>
    </fieldset>
    <div className="awb-toolbar"><button onClick={() => saveJson({source_a:sourceA,source_b:sourceB,name_a:nameA,name_b:nameB,execution_mode:executionMode,input_kind:inputKind,scenario,trace_id:traceId,offset,limit})}>Export current source & inputs</button>{savedId && <><a href={`/api/experiments/${savedId}/export`}>Export saved run with sources</a><button disabled={busy} onClick={async () => { setError(''); setResult(null); try { const j = await request<{id:string}>(`/api/experiments/${savedId}/rerun`, {method:'POST'}); setSearch({job:j.id}); setJobId(j.id); setBusy(true) } catch(e) {setError(String(e))} }}>Rerun saved inputs</button></>}</div>
    {busy && <div className="awb-note" role="status">Executing both Python algorithms and repeating the full output check… {jobId&&<button onClick={async()=>{try{await request(`/api/algorithm-workbench/${jobId}/cancel`,{method:'POST'})}catch(e){setError(String(e))}}}>Cancel execution</button>}</div>}
    {result && row && <section aria-label="Computed comparison">
      <div className="awb-toolbar awb-results"><div><h2>3 · Investigate the computed decisions</h2><p><strong>{result.compared_events}</strong> callbacks compared · <strong>{result.disagreements}</strong> disagreements · {result.provenance.kind === 'synthetic' ? 'Synthetic inputs' : 'Captured recording'}<br />{result.provenance.scope}</p></div>
        <button className="btn" disabled={result.first_difference === null} onClick={() => setSelected(result.first_difference ?? 0)}>Jump to first difference</button>
        <button className="btn" onClick={() => saveJson(result)}>Export computed JSON</button></div>
      <p className="awb-note">Saved execution: {result.execution_mode==='stateful'?'Initialized private history per implementation':'Event-local independent callbacks'}. Only declared numeric outputs determine differences; private-state key shapes are not compared for correctness.</p>{result.execution_mode==='stateful'&&<details><summary>Saved initial private states and identity</summary><pre>{JSON.stringify(result.initialization,null,2)}</pre><p className="awb-small">Initialization SHA-256: {result.initialization_sha256}</p></details>}<div className="awb-chart"><label>Plot computed <select value={field} onChange={e => setField(e.target.value as typeof field)}><option value="post_snd_cwnd">post-callback cwnd</option><option value="result">returned threshold / undo value</option></select></label>
        <svg viewBox="0 0 960 225" role="img" aria-label="Scatter plot of computed callback outputs: blue A, orange B">
          {[0, .5, 1].map(f => <g key={f}><line x1="52" x2="935" y1={185 - f * 155} y2={185 - f * 155} stroke="currentColor" opacity=".15"/><text x="8" y={190 - f * 155} fill="currentColor" fontSize="13">{Math.round(max * f)}</text></g>)}
          {chartRows.map(r => { const x = 60 + r.index / Math.max(1, result.rows.length - 1) * 860; return <g key={r.index} opacity={selected === r.index ? 1 : .65}><circle cx={x - 3} cy={185 - r.a[field] / max * 155} r={selected === r.index ? 6 : 3} fill="#347fee"/><circle cx={x + 3} cy={185 - r.b[field] / max * 155} r={selected === r.index ? 6 : 3} fill="#e99b34"/></g> })}
          <text x="400" y="217" fill="currentColor" fontSize="13">Callback index · A blue / B orange</text></svg>
        <p className="awb-small">Points are separate callback decisions, not a simulated connection history. Return values are plotted only for callbacks that return a value.</p></div>
      <div className="awb-toolbar"><button className="btn" disabled={selected === 0} onClick={() => setSelected(i => i - 1)}>Previous</button>
        <label>Selected event <input aria-label="Selected event index" type="number" min={0} max={result.rows.length - 1} value={selected} onChange={e => setSelected(Math.max(0, Math.min(result.rows.length - 1, Number(e.target.value))))} /></label>
        <button className="btn" disabled={selected === result.rows.length - 1} onClick={() => setSelected(i => i + 1)}>Next</button>
        <strong>Index {selected} · seq {row.seq} · {row.callback}</strong><span className="awb-chip">{row.different_fields.length ? 'Different decisions' : 'Same compared outputs'}</span></div>
      <div className="awb-strip" aria-label="Select a callback">{result.rows.map(r => <button key={r.index} aria-label={`Index ${r.index}, ${r.callback}, ${r.different_fields.length ? 'different' : 'same'}`} aria-pressed={selected === r.index} className={r.different_fields.length ? 'awb-different' : ''} onClick={() => setSelected(r.index)}>{r.index}</button>)}</div>
      <section className="awb-input"><h3>Shared input → both algorithms</h3><div className="awb-values">{Object.entries(row.input).filter(([key]) => ['pre_snd_cwnd','in_acked','pre_snd_cwnd_clamp','pre_is_cwnd_limited','pre_prior_cwnd','pre_snd_cwnd_cnt'].includes(key)).map(([key, value]) => <div key={key}><span>{key}</span><strong>{value}</strong></div>)}</div></section>
      <div className="awb-grid">{(['a', 'b'] as const).map(side => <section className={`awb-decision awb-${side}`} key={side}><h3>Algorithm {side.toUpperCase()} → computed output</h3><p>{side==='a'?nameA:nameB}</p>
        <h2>{row[side].decision?.rule || 'Explanation not supplied'}</h2><pre>{row[side].decision?.calculation || 'Inspect output fields and source.'}</pre><p>{row[side].decision?.meaning}</p>
        <div className="awb-values"><div><span>post cwnd</span><strong>{row[side].post_snd_cwnd}</strong></div><div><span>{row.callback === 'ssthresh' ? 'returned ssthresh' : row.callback === 'undo_cwnd' ? 'returned undo' : 'return value'}</span><strong>{row[side].result_valid ? row[side].result : 'void'}</strong></div></div>
        {result.execution_mode==='stateful'&&<div className="awb-private"><h3>Initialized controller history · private PRE → POST</h3><pre>{JSON.stringify(side==='a'?row.private_a:row.private_b,null,2)}</pre><p className="awb-small">Controller-owned history; shared TCP PRE is always supplied independently.</p></div>}<p className="awb-small">Source snapshot: {side === 'a' ? result.source_a_sha256.slice(0, 12) : result.source_b_sha256.slice(0, 12)}</p></section>)}</div>
      <div className="awb-note">Compared fields that differ: <strong>{row.different_fields.join(', ') || 'none'}</strong>. A disagreement shows different policies, not necessarily a bug. These teaching samples are not production controllers.</div>
    </section>}
  </div>
}
