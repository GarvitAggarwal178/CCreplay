export default function ProvenanceTag({kind,text}:{kind:'measured'|'recorded'|'computed'|'example';text?:string}) {
 return <span className="provenance">{kind.toUpperCase()}{text&&` · ${text}`}</span>
}
