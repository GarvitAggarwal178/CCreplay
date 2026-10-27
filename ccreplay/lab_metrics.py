"""Parse actual ss and tc outputs. Missing observations remain null."""
import re


def socket_samples(text, port=5201):
    rows=[]; current=None
    for line in text.splitlines():
        if line.startswith('State'):
            continue
        if line and not line[0].isspace() and not line.startswith(('reno ','cubic ','bbr ','ccr_')):
            columns=line.split()
            if len(columns)>=5:
                current={'local':columns[3],'peer':columns[4],'raw':''}
                rows.append(current)
        elif current is not None:
            current['raw']+=' '+line.strip()
    out=[]
    for row in rows:
        if not row['peer'].endswith(':'+str(port)):
            continue
        raw=row['raw']
        def number(name, cast=float):
            m=re.search(r'\b'+name+r':([0-9.]+)',raw)
            return cast(m.group(1)) if m else None
        cca=re.search(r'\b(ccr_reno|ccr_cubic|ccr_covegas|reno|cubic|bbr)\b',raw)
        row.update(cwnd_segments=number('cwnd',int),srtt_ms=number('rtt'),bytes_acked=number('bytes_acked',int),
                   retransmits=number('bytes_retrans',int),controller=cca.group(1) if cca else None)
        row['flow_id']=row['local']+'→'+row['peer']
        out.append(row)
    return out


def select_data_flow(rows, locked=None):
    if locked:
        return next((r for r in rows if r['flow_id']==locked),None)
    return max(rows,key=lambda r:r['bytes_acked'] or 0) if rows else None


def queue_sample(qdiscs):
    selected=next((q for q in qdiscs if q.get('kind')=='bfifo'),None)
    if selected is None:
        return {'queue_backlog_bytes':None,'qdisc_drops':None}
    return {'queue_backlog_bytes':selected.get('backlog'),'qdisc_drops':selected.get('drops')}


def receiver_summary(payload):
    try:
        data=payload['end']['sum_received']
        return {'receiver_throughput_bps':data['bits_per_second'],'receiver_bytes':data['bytes'],
                'receiver_duration_s':data['seconds'],
                'retransmits':payload['end'].get('sum_sent',{}).get('retransmits')}
    except (KeyError,TypeError):
        return {'receiver_throughput_bps':None,'receiver_bytes':None,'receiver_duration_s':None,'retransmits':None}
