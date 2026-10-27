import { useEffect, useRef, useState } from 'react'

import type { Data, Layout, Shape } from 'plotly.js-dist-min'

export interface ChartTrace {
  x: (number | string | null)[]
  y: (number | null)[]
  name: string
  color?: string
  yaxis?: 'y' | 'y2'
  fill?: 'tozeroy' | 'none'
  mode?: 'lines' | 'markers' | 'lines+markers'
}

interface ChartProps {
  traces: ChartTrace[]
  title?: string
  xLabel?: string
  yLabel?: string
  y2Label?: string
  height?: number
  shapes?: Partial<Shape>[]
  caption?: string
  chartType?: 'scatter' | 'bar'
  onSelectX?: (x:number)=>void
  xType?: 'category'
}

function isDark(): boolean {
  return document.documentElement.getAttribute('data-theme') !== 'light'
}

export default function Chart({
  traces,
  title,
  xLabel,
  yLabel,
  y2Label,
  height = 320,
  shapes,
  caption,
  chartType = 'scatter',
  xType,
  onSelectX,
}: ChartProps) {
  const ref = useRef<HTMLDivElement>(null)

  const [themeVersion, setThemeVersion] = useState(0)
  useEffect(() => {
    const observer = new MutationObserver(() => setThemeVersion(v => v + 1))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    if (!ref.current) return
    const element = ref.current
    let cancelled = false
    let dispose: (() => void) | undefined
    const dark = isDark()
    const fg = dark ? '#e7eaee' : '#15181c'
    const grid = dark ? '#2c333c' : '#e3e7eb'
    const bg = dark ? '#171b21' : '#ffffff'
    const palette = ['#2563eb', '#d1872f', '#1a7f37', '#b42318', '#7b5ce0', '#0e8a8a']

    // This plotly build chokes on an own key whose value is `undefined`
    // (e.g. `{ yaxis2: undefined }`) -- it throws "Cannot read properties of
    // undefined (reading 'anchor')" while walking layout keys, even though
    // the key is simply absent from the rendered plot otherwise. Every
    // conditional field below is added with a spread so the key is omitted
    // entirely rather than present-with-undefined.
    const data = traces.map((t, i) => ({
      x: t.x as number[],
      y: t.y as number[],
      type: chartType,
      ...(chartType === 'scatter' ? { mode: t.mode || 'lines' } : {}),
      name: t.name,
      yaxis: t.yaxis === 'y2' ? 'y2' : 'y',
      ...(t.fill ? { fill: t.fill } : {}),
      ...(chartType === 'scatter'
        ? {
            line: { color: t.color || palette[i % palette.length], width: 1.6 },
            marker: { color: t.color || palette[i % palette.length], size: 4 },
          }
        : { marker: { color: t.color || palette[i % palette.length] } }),
    })) as Partial<Data>[]

    const layout: Partial<Layout> = {
      ...(title ? { title: { text: title, font: { size: 13, color: fg } } } : {}),
      height,
      margin: { l: 55, r: y2Label ? 55 : 20, t: title ? 36 : 12, b: 40 },
      paper_bgcolor: bg,
      plot_bgcolor: bg,
      font: { color: fg, size: 11 },
      xaxis: { title: { text: xLabel }, gridcolor: grid, zerolinecolor: grid, color: fg, ...(xType ? { type: xType } : {}) },
      yaxis: { title: { text: yLabel }, gridcolor: grid, zerolinecolor: grid, color: fg },
      ...(y2Label
        ? { yaxis2: { title: { text: y2Label }, overlaying: 'y', side: 'right', color: fg, gridcolor: 'transparent' } }
        : {}),
      legend: { orientation: 'h', y: -0.2, font: { color: fg, size: 10 } },
      ...(shapes ? { shapes } : {}),
      showlegend: traces.length > 1,
    }

    import('plotly.js-dist-min').then(({ default: Plotly }) => {
      if (cancelled) return
      Plotly.react(element, data, layout, { responsive: true, displayModeBar: false }).then(()=>{
        if(!cancelled&&onSelectX)(element as unknown as {on:(event:string,cb:(e:{points:{x:number}[]})=>void)=>void}).on('plotly_click',e=>{const x=e.points[0]?.x;if(typeof x==='number')onSelectX(x)})
      })
      const observer = new ResizeObserver(() => {
        // Collapsed Details panes and unmounted plots have no display box.
        if (!cancelled && element.isConnected && element.offsetWidth > 0 && element.offsetHeight > 0) {
          Plotly.Plots.resize(element)
        }
      })
      observer.observe(element)
      dispose = () => { observer.disconnect(); Plotly.purge(element) }
    })
    return () => { cancelled = true; dispose?.() }
  }, [traces, title, xLabel, yLabel, y2Label, height, shapes, chartType, xType, themeVersion, onSelectX])

  return (
    <div className="plot-wrapper">
      <div ref={ref} />
      {caption && <div className="hint">{caption}</div>}
    </div>
  )
}
