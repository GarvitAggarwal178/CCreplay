export const finite = (v:unknown):v is number => typeof v==='number' && Number.isFinite(v)
export const display = (v:unknown,unit='') => v==null ? 'Unavailable' : typeof v==='number' ? (finite(v)?v.toLocaleString(undefined,{maximumFractionDigits:3})+(unit?' '+unit:''):'Unavailable') : String(v)
export const percent = (n:number,d:number) => d>0 ? (100*n/d).toFixed(2)+'%' : 'Not exercised'
export const renoFormula = (p:Record<string,number>) => `max((snd_cwnd × ${p.num}) // ${p.den}, ${p.min_ssthresh}) segments; // is integer floor`
export const localDate = (s:string) => new Date(s).toLocaleString()+' (local time)'
