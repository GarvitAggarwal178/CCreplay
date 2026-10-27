import { lazy, Suspense, useEffect, useState } from 'react'
import { HashRouter, Routes, Route, NavLink, Navigate, Link } from 'react-router-dom'
import { useResource } from './hooks/useResource'
const AlgorithmWorkbench=lazy(()=>import('./pages/AlgorithmWorkbench'))
const Start=lazy(()=>import('./pages/Start'))
const Replay=lazy(()=>import('./pages/ReplayWorkspace'))
const Controllers=lazy(()=>import('./pages/ControllerWorkbench'))
const Recordings=lazy(()=>import('./pages/Recordings'))
const RecordingDetail=lazy(()=>import('./pages/TraceDetail'))
const Lab=lazy(()=>import('./pages/Lab'))
const Runs=lazy(()=>import('./pages/Runs'))
const Advanced=lazy(()=>import('./pages/Advanced'))
const Sweep=lazy(()=>import('./pages/Sweep'))
function Shell(){
 const [theme,setTheme]=useState(localStorage.getItem('ccr-theme')||'light')
 const {data:health,error}=useResource<{status:string}>('/health')
 useEffect(()=>{document.documentElement.dataset.theme=theme;localStorage.setItem('ccr-theme',theme)},[theme])
 return <><header className="app-topbar"><Link className="app-brand" to="/"><span className="brand-mark">CC</span> CCReplay Studio</Link><nav className="app-nav" aria-label="Main navigation">{[['/','Start'],['/lab','Network Lab'],['/recordings','Recordings'],['/controllers','Controllers'],['/replay','Replay'],['/runs','Runs & Compare']].map(([to,title])=><NavLink key={to} to={to} end={to==='/'}>{title}</NavLink>)}</nav><span className="connection">{health?'● Local backend':error?'Backend unavailable':'Connecting…'}</span><button className="theme-toggle" aria-label="Toggle color theme" onClick={()=>setTheme(theme==='light'?'dark':'light')}>{theme==='light'?'Dark':'Light'}</button><details className="help"><summary>Help</summary><div className="help-popover"><h2>Live → capture → replay</h2><p>Network Lab runs real Linux TCP through virtual links. Callback recording captures shared inputs and controller state. Replay compares compatible implementations on those fixed inputs.</p><p>Computed outputs do not predict an alternate connection's throughput or RTT.</p><Link to="/advanced">Validation and advanced tools</Link></div></details></header><main className="app-main"><Suspense fallback={<section className="panel">Loading workspace…</section>}><Routes><Route path="/" element={<Start/>}/><Route path="/lab" element={<Lab/>}/><Route path="/replay" element={<Replay/>}/><Route path="/algorithm-workbench" element={<AlgorithmWorkbench/>}/><Route path="/controllers" element={<Controllers/>}/><Route path="/recordings" element={<Recordings/>}/><Route path="/recordings/:id" element={<RecordingDetail/>}/><Route path="/runs" element={<Runs/>}/><Route path="/advanced" element={<Advanced/>}/><Route path="/sweep" element={<Sweep/>}/><Route path="/diff" element={<Navigate to="/replay" replace/>}/><Route path="/history" element={<Navigate to="/runs" replace/>}/><Route path="/traces" element={<Navigate to="/recordings" replace/>}/><Route path="/traces/:id" element={<RecordingDetail/>}/></Routes></Suspense></main><footer className="app-footer">Live measurements describe actual runs. Replay outputs describe controller computations on fixed recorded inputs.</footer></>
}
export default function App(){return <HashRouter><Shell/></HashRouter>}
