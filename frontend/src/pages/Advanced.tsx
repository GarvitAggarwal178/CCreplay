import { lazy,Suspense,useEffect,useState } from 'react'
import { Link } from 'react-router-dom'
import { api,pollExperiment } from '../api'
import type { TraceSummary,ControllerSummary,AllDecisionsResult } from '../api'
import { useResource } from '../hooks/useResource'
import { label,traceName } from '../workbench/api'
const SavedExperiments=lazy(()=>import('../workbench/SavedExperiments'))
const AllDecisions=lazy(()=>import('../components/AllDecisionsPanel'))
export default function Advanced(){
 const {data}=useResource<{abi_validation_table:{abi:string;verdict:string;caveat:string}[]}>('/health')
 const [traces,setTraces]=useState<TraceSummary[]>([]);const [controllers,setControllers]=useState<ControllerSummary[]>([])
 const [trace,setTrace]=useState('raw__cubic_replay__primary__rep1');const [candidate,setCandidate]=useState('cubic_bug_ssthresh');const [mode,setMode]=useState<'A'|'B'>('A')
 const [result,setResult]=useState<AllDecisionsResult|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('')
 useEffect(()=>{Promise.all([api.listTraces(),api.listControllers()]).then(([t,c])=>{setTraces(t);setControllers(c)}).catch(e=>setError(String(e)))},[])
 const abi=traces.find(t=>t.id===trace)?.abi??1;const base=['reno','cubic','covegas'][abi]
 async function run(){setBusy(true);setError('');try{const j=await api.createExperiment('all_decisions',trace,base,candidate,undefined,mode);const value=await pollExperiment(j.id);if(value.error)throw Error(value.error);setResult(value.result as AllDecisionsResult)}catch(e){setError(String(e))}finally{setBusy(false)}}
 return <><h1>Advanced tools & evidence</h1><section className="panel"><Link className="button" to="/algorithm-workbench">Independent Python Policy Sandbox · ABI v0 only</Link><p className="hint">Trusted local policies on recorded v0 or explicitly synthetic tutorial inputs; no kernel deployment.</p><Link className="button" to="/sweep">Parameter sweeps</Link><p>Checkpoint reproduction is available inside each saved stateful investigation.</p></section><section className="panel"><h2>All-decision statistics</h2><div className="controls"><label>Recording<select value={trace} onChange={e=>{setTrace(e.target.value);const a=traces.find(t=>t.id===e.target.value)?.abi??1;setCandidate(['reno','cubic','covegas'][a])}}>{traces.map(t=><option key={t.id} value={t.id}>{traceName(t.path)}</option>)}</select></label><label>Candidate<select value={candidate} onChange={e=>setCandidate(e.target.value)}>{controllers.filter(c=>c.abi===abi).map(c=><option key={c.id} value={c.id}>{label(c.id)}</option>)}</select></label><label>Mode<select value={mode} onChange={e=>setMode(e.target.value as 'A'|'B')}><option>A</option><option>B</option></select></label><button disabled={busy} onClick={()=>void run()}>{busy?'Computing all decisions…':'Compute statistics'}</button></div>{error&&<p role="alert" className="error">{error}</p>}{result&&<Suspense fallback={<p>Loading result plots…</p>}><AllDecisions result={result}/></Suspense>}</section><Suspense fallback={<p>Loading historical evidence…</p>}><SavedExperiments/></Suspense><section className="panel"><h2>Historical self-replay evidence</h2>{data?.abi_validation_table.map(r=><p key={r.abi}><b>{r.abi} · {r.verdict}</b> — {r.caveat}</p>)}<p>Recorder non-interference was not established; the historical Kali study failed. Native and instrumented measurements remain separate. CoVegas validates replay fidelity of the selected BPF implementation, with no independent kernel-native reference.</p></section></>
}
