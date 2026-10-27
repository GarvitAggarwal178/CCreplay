import { useEffect, useState } from 'react'
import { request } from '../workbench/api'
export interface LabSample { cursor:number;t_s:number;flow_id:string|null;cwnd_segments:number|null;srtt_ms:number|null;bytes_acked:number|null;acked_rate_bps:number|null;retransmits:number|null;queue_backlog_bytes:number|null;qdisc_drops:number|null;controller:string|null }
export interface LabLog {cursor:number;t_s:number;kind:string;message:string}
export function useRunStream<T extends {cursor:number}>(id:string|null,kind:'samples'|'log',poll:boolean) {
 const [items,setItems]=useState<{id:string;items:T[]}|null>(null)
 const [error,setError]=useState('')
 useEffect(()=>{
  if(!id)return
  const abort=new AbortController();let cursor=0;let timer:ReturnType<typeof setTimeout>;let collected:T[]=[]
  async function load(){
   try{const r=await request<{items:T[];cursor:number;agent_unavailable?:boolean}>(`/lab/runs/${id}/${kind}?after=${cursor}&limit=500`,{signal:abort.signal});if(abort.signal.aborted)return;cursor=r.cursor;collected=[...collected,...r.items].slice(-4000);setItems({id:id!,items:collected});setError(r.agent_unavailable?'Agent unavailable; displaying only telemetry already saved by Studio':'');if(poll||r.items.length===500)timer=setTimeout(load,r.items.length===500?20:500)}catch(e){if(!abort.signal.aborted)setError(String(e))}
  }
  void load();return()=>{abort.abort();clearTimeout(timer)}
 },[id,kind,poll])
 return {items:items?.id===id?items.items:[],error}
}
export interface LabRun {id:string;status:string;phase:string;created_at:string;started_at?:string;finished_at?:string;error?:string;config:{controller:string;capture:boolean;duration_s:number;rate_mbit:number;delay_ms:number;queue_bytes:number;loss_percent:number;workload_revision:string};selected_controller?:string;observed_controllers?:string[];instrumentation:string;samples_count:number;recording_id?:string;recording?:{integrity:string;replayable:boolean;n_events?:number;sha256?:string;self_replay?:{verdict:string};reason?:string};summary:{receiver_throughput_bps?:number|null;receiver_bytes?:number|null;receiver_duration_s?:number|null;retransmits?:number|null};actual_readback?:unknown;cleanup?:{completed:boolean;errors:string[]};artifacts?:Record<string,{bytes:number;sha256:string}>;workload?:{name:string;sha256:string};stopped_early?:boolean}
