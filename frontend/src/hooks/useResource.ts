import { useEffect, useState } from 'react'
import { request } from '../workbench/api'
export function useResource<T>(path: string | null, poll = false) {
  const [data, setData] = useState<{ path: string; value: T } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!path) return
    const abort = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function load() {
      let keepPolling = poll
      try { const value = await request<T>(path!, { signal: abort.signal }); if (!abort.signal.aborted) { setData({ path: path!, value }); setError(''); if (value && typeof value === 'object' && 'status' in value && ['done','error','failed','cancelled','completed','interrupted'].includes(String(value.status))) keepPolling = false } }
      catch (e) { if (!abort.signal.aborted) setError(String(e)) }
      if (keepPolling && !abort.signal.aborted) timer = setTimeout(load, 500)
    }
    void load()
    return () => { abort.abort(); clearTimeout(timer) }
  }, [path, poll])
  return { data: data?.path === path ? data.value : null, error }
}
