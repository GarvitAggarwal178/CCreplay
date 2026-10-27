import { useEffect,useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { post,request } from './api'
export default function TrafficEditor({onSaved}:{onSaved:(id:string)=>void}) {
 const [name,setName]=useState('my_bursty_workload');const [source,setSource]=useState('');const [error,setError]=useState('');const [revision,setRevision]=useState('')
 useEffect(()=>{request<{source:string}>('/workloads/bursty_template').then(w=>setSource(w.source)).catch(e=>setError(String(e)))},[])
 async function save(){try{const r=await post<{id:string;sha256:string}>('/workloads',{name,source});setRevision(r.sha256);onSaved(r.id);setError('')}catch(e){setError(String(e))}}
 return <><p className="hint">One Python TCP workload, one local receiver, one data socket. It runs at the normal user's uid after namespace entry. This generates traffic; it does not implement a kernel congestion controller.</p><label>Workload name<input value={name} onChange={e=>setName(e.target.value)}/></label><label>Import local .py file<input type="file" accept=".py" onChange={e=>{const f=e.target.files?.[0];if(f)f.text().then(setSource)}}/></label><CodeMirror aria-label="Traffic source editor" value={source} extensions={[python()]} height="350px" onChange={setSource}/><button onClick={()=>void save()}>Save workload revision</button>{revision&&<p className="mono hint">Source SHA-256 {revision}</p>}{error&&<p role="alert" className="error">{error}</p>}</>
}
