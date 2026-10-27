// Small contract checks using the locked TypeScript compiler, no new test framework.
import ts from '../frontend/node_modules/typescript/lib/typescript.js'
import {readFileSync} from 'node:fs'
import {pathToFileURL} from 'node:url'
import {resolve,dirname} from 'node:path'
import assert from 'node:assert/strict'
const root=resolve(import.meta.dirname,'..')
function moduleURL(file){
 let code=ts.transpileModule(readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
 code=code.replace(/from ['"]([^'"]+)['"]/g,(_,name)=>`from ${JSON.stringify(name==='react'?pathToFileURL(resolve(root,'frontend/node_modules/react/index.js')).href:moduleURL(resolve(dirname(file),name+'.ts')))}`)
 return 'data:text/javascript;base64,'+Buffer.from(code).toString('base64')
}
const {allSamples,nativeComplete,matchedPair,readbackWarnings}=await import(moduleURL(resolve(root,'frontend/src/hooks/useComparisonSamples.ts')))
const pages=[]
globalThis.fetch=async(url,opts)=>{
 assert.equal(opts.signal.aborted,false)
 const cursor=Number(new URL(url,'http://test').searchParams.get('after'));pages.push(cursor)
 return {ok:true,json:async()=>({items:Array.from({length:Math.min(500,1201-cursor)},(_,i)=>({cursor:cursor+i+1,t_s:(cursor+i)/10})),cursor:Math.min(cursor+500,1201),agent_unavailable:true})}
}
let result=await allSamples('test',new AbortController().signal)
assert.deepEqual(pages,[0,500,1000]);assert.equal(result.samples.length,1201);assert.equal(result.samples.at(-1).cursor,1201);assert.equal(result.cached,true)
globalThis.fetch=async()=>({ok:true,json:async()=>({items:[{cursor:1}],cursor:0})})
await assert.rejects(allSamples('bad',new AbortController().signal),/did not advance/)
const config={controller:'reno',capture:false,rate_mbit:10,delay_ms:20,queue_bytes:50000,loss_percent:1,duration_s:30,workload_revision:'continuous'}
const run={id:'a',status:'completed',instrumentation:'native-uninstrumented',config,observed_controllers:['reno'],actual_readback:{sender:[{kind:'netem',options:{delay:{delay:.020},'loss-random':{loss:.01}}}],receiver:[{kind:'netem',options:{delay:{delay:.020}}}],router:[{kind:'bfifo',options:{limit:50000}}],classes:[{kind:'htb',options:{rate:1250000}}]}}
assert.deepEqual(readbackWarnings(run),[])
assert(readbackWarnings({...run,actual_readback:{...run.actual_readback,sender:[{kind:'netem',options:{delay:{delay:.2}}}]}}).some(s=>s.includes('delay readback differs')))
assert(readbackWarnings({...run,actual_readback:null}).includes('network readback unknown'))
const cubic={...run,id:'b',config:{...config,controller:'cubic'}}
assert.equal(nativeComplete({...run,status:'running'}),false)
assert.equal(nativeComplete({...run,config:{...config,capture:true}}),false)
assert.deepEqual(matchedPair([run,cubic]),[run,cubic])
assert.equal(matchedPair([run,{...cubic,config:{...cubic.config,duration_s:20}}]),null)
console.log('PASS frontend contracts: all 1,201 test samples paged, stalled cursor rejected, native eligibility, matched controls, actual readback conversion/mismatch/unknown')
