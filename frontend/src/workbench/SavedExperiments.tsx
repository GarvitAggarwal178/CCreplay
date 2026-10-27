import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useResource } from '../hooks/useResource'
import { post } from './api'
interface Experiment {id:string;type:string;status:string;config:Record<string,unknown>;result:unknown;error:string|null;created_at:number}
export default function SavedExperiments(){
 const {data:jobs}=useResource<Experiment[]>('/experiments')
 const [selected,setSelected]=useState('')
 const {data:detail,error}=useResource<Experiment>(selected?'/experiments/'+selected:null,!!selected)
 const [actionError,setActionError]=useState('')
 const items=(jobs||[]).filter(j=>!['replay','session_checkpoint'].includes(j.type))
 return <section className="panel"><h2>Advanced & legacy experiments</h2><p className="hint">Older rows without source capsules are marked legacy. Their stored results can be opened, but are not silently rerun against today's code.</p>{items.slice(0,30).map(j=><div className="run-row" key={j.id}><span>{j.type==='algorithm_workbench'?'Independent algorithms':j.type} · {j.id} <span className="pill">{j.status}</span>{!j.config._capsule&&j.type!=='algorithm_workbench'&&<small>Legacy/current-source identity only</small>}</span>{j.type==='algorithm_workbench'?<Link className="button" to={'/algorithm-workbench?job='+j.id}>Open computed decisions</Link>:<button onClick={()=>setSelected(j.id)}>Open saved result</button>}</div>)}{error&&<p className="error">{error}</p>}{detail?.id===selected&&<div><h3>{detail.type} · {detail.status}</h3><div className="controls"><a className="button" href={`/api/experiments/${selected}/export?format=json`}>Export JSON</a><a className="button" href={`/api/experiments/${selected}/export?format=md`}>Export Markdown</a>{!!detail.config._capsule&&<button onClick={()=>post<{id:string}>(`/experiments/${selected}/rerun`).then(r=>setSelected(r.id)).catch(e=>setActionError(String(e)))}>Rerun saved inputs</button>}</div>{actionError&&<p className="error">{actionError}</p>}<pre>{JSON.stringify(detail.result||detail.error||detail.status,null,2)}</pre></div>}</section>
}
