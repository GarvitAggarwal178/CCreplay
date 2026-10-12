export function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (Number.isInteger(n)) return n.toLocaleString()
  return n.toLocaleString(undefined, { maximumFractionDigits: 3 })
}

export function fmtDuration(s: number | null | undefined): string {
  if (s === null || s === undefined) return '—'
  return `${s.toFixed(1)} s`
}

export function fmtBytes(b: number | null | undefined): string {
  if (b === null || b === undefined) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

export function badgeClassForVerdict(verdict: string): string {
  if (verdict === 'PASS') return 'badge badge-pass'
  if (verdict === 'PARTIAL') return 'badge badge-partial'
  return 'badge badge-fail'
}
