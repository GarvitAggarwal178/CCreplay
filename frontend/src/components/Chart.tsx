import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'
import type { Data, Layout, Shape } from 'plotly.js-dist-min'

export interface ChartTrace {
  x: (number | null)[]
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
}

function isDark(): boolean {
  return document.documentElement.getAttribute('data-theme') !== 'light'
}

export default function Chart({ traces, title, xLabel, yLabel, y2Label, height = 320, shapes, caption }: ChartProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
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
    const data: Partial<Data>[] = traces.map((t, i) => ({
      x: t.x as number[],
      y: t.y as number[],
      type: 'scatter',
      mode: t.mode || 'lines',
      name: t.name,
      yaxis: t.yaxis === 'y2' ? 'y2' : 'y',
      ...(t.fill ? { fill: t.fill } : {}),
      line: { color: t.color || palette[i % palette.length], width: 1.6 },
      marker: { color: t.color || palette[i % palette.length], size: 4 },
    }))

    const layout: Partial<Layout> = {
      ...(title ? { title: { text: title, font: { size: 13, color: fg } } } : {}),
      height,
      margin: { l: 55, r: y2Label ? 55 : 20, t: title ? 36 : 12, b: 40 },
      paper_bgcolor: bg,
      plot_bgcolor: bg,
      font: { color: fg, size: 11 },
      xaxis: { title: { text: xLabel }, gridcolor: grid, zerolinecolor: grid, color: fg },
      yaxis: { title: { text: yLabel }, gridcolor: grid, zerolinecolor: grid, color: fg },
      ...(y2Label
        ? { yaxis2: { title: { text: y2Label }, overlaying: 'y', side: 'right', color: fg, gridcolor: 'transparent' } }
        : {}),
      legend: { orientation: 'h', y: -0.2, font: { color: fg, size: 10 } },
      ...(shapes ? { shapes } : {}),
      showlegend: traces.length > 1,
    }

    Plotly.react(ref.current, data, layout, { responsive: true, displayModeBar: false })
  }, [traces, title, xLabel, yLabel, y2Label, height, shapes])

  return (
    <div>
      <div ref={ref} />
      {caption && <div className="hint">{caption}</div>}
    </div>
  )
}
