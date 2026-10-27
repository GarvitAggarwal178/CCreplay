import { useEffect, useState } from 'react'
import type { LabRun, LabSample } from './useLabRun'
import { request } from '../workbench/api'
export const nativeComplete = (r:LabRun) => r.status==='completed'&&r.instrumentation==='native-uninstrumented'&&!r.config.capture
export function matchedPair(runs:LabRun[]):[LabRun,LabRun]|null {
 const native=runs.filter(nativeComplete)
 for(const a of native.filter(r=>r.config.controller==='reno')) for(const b of native.filter(r=>r.config.controller==='cubic')) {
  if(Object.keys(a.config).every(k=>k==='controller'||a.config[k as keyof LabRun['config']]===b.config[k as keyof LabRun['config']])) return [a,b]
 }
 return null
}
export async function allSamples(id:string,signal:AbortSignal) {
 const values=new Map<number,LabSample>();let cursor=0;let cached=false
 while(!signal.aborted) {
  const page=await request<{items:LabSample[];cursor:number;agent_unavailable?:boolean}>(`/lab/runs/${encodeURIComponent(id)}/samples?after=${cursor}&limit=500`,{signal})
  cached ||= !!page.agent_unavailable
  for(const s of page.items) if(s.cursor>cursor) values.set(s.cursor,s)
  if(page.items.length && page.cursor<=cursor) throw Error('Sample cursor did not advance; coverage is incomplete')
  if(page.items.length<500) break
  cursor=page.cursor
 }
 return {samples:[...values.values()].sort((a,b)=>a.cursor-b.cursor),cached}
}
export function useComparisonSamples(id:string|null) {
 const [result,setResult]=useState<{id:string;samples:LabSample[];cached:boolean}|null>(null)
 const [failure,setFailure]=useState<{id:string;error:string}|null>(null)
 useEffect(()=>{
  if(!id)return
  const abort=new AbortController()
  allSamples(id,abort.signal).then(value=>{if(!abort.signal.aborted)setResult({id,...value})}).catch(e=>{if(!abort.signal.aborted)setFailure({id,error:String(e)})})
  return ()=>abort.abort()
 },[id])
 return {samples:result?.id===id?result.samples:[],cached:result?.id===id&&result.cached,loading:!!id&&result?.id!==id&&failure?.id!==id,error:failure?.id===id?failure.error:''}
}

// tc JSON represents netem delay in seconds and loss as a fraction:
// https://github.com/iproute2/iproute2/blob/main/tc/q_netem.c
export function readbackWarnings(r:LabRun):string[] {
 const issues:string[]=[]
 if(!r.observed_controllers?.length)issues.push('observed controller unknown')
 else if(r.observed_controllers.some(c=>c!==r.config.controller))issues.push('observed controller contradicts configuration')
 if(r.selected_controller&&r.selected_controller!==r.config.controller)issues.push('selected controller contradicts configuration')
 if(r.stopped_early)issues.push('execution stopped early; partial run')
 const raw=r.actual_readback as Record<string,unknown>|undefined
 if(!raw)return [...issues,'network readback unknown']
 for(const key of ['rate_mbit','delay_ms','queue_bytes','loss_percent'] as const)if(raw[key]!=null&&raw[key]!==r.config[key])issues.push(`${key} readback differs`)
 type Qdisc={kind:string;options?:{limit?:number;rate?:number;delay?:{delay?:number};'loss-random'?:{loss?:number};'loss-state'?:unknown;'loss-gemodel'?:unknown}}
 const list=(key:string):Qdisc[]=>Array.isArray(raw[key])?raw[key] as Qdisc[]:[]
 const fifo=list('router').find(q=>q.kind==='bfifo')?.options?.limit
 const rate=list('classes').find(q=>q.kind==='htb'&&typeof q.options?.rate==='number')?.options?.rate
 if(fifo==null)issues.push('FIFO readback unknown');else if(fifo!==r.config.queue_bytes)issues.push('FIFO readback differs')
 if(rate==null)issues.push('rate readback unknown');else if(Math.abs(rate*8/1e6-r.config.rate_mbit)>.001)issues.push('bottleneck rate readback differs')
 for(const side of ['sender','receiver']) {
  const options=list(side).find(q=>q.kind==='netem')?.options
  if(!options){issues.push(`${side} delay/loss readback unknown`);continue}
  const delay=options.delay?.delay
  if(delay!==undefined&&typeof delay!=='number')issues.push(`${side} delay encoding unknown`)
  else if(Math.abs((delay??0)*1000-r.config.delay_ms)>.001)issues.push(`${side} delay readback differs`)
  if(options['loss-state']||options['loss-gemodel'])issues.push(`${side} unexpected loss model`)
  const loss=options['loss-random']?.loss
  if(loss!==undefined&&typeof loss!=='number')issues.push(`${side} loss encoding unknown`)
  else if(Math.abs((loss??0)*100-(side==='sender'?r.config.loss_percent:0))>.0001)issues.push(`${side} loss readback differs`)
 }
 return issues
}
