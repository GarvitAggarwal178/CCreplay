import { Link } from 'react-router-dom'
export default function EmptyState({title,reason,to,action}:{title:string;reason:string;to:string;action:string}) {
 return <section className="panel empty-state"><h2>{title}</h2><p>{reason}</p><Link className="button" to={to}>{action}</Link></section>
}
