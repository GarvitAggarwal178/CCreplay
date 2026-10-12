import { useEffect, useState } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { api, type ControllerSummary, type ValidationReport } from '../api'

const ABI_NAME: Record<number, string> = { 0: 'Reno', 1: 'CUBIC', 2: 'CoVegas' }

function ValidationPanel({ v }: { v: ValidationReport }) {
  return (
    <div className="panel" style={{ background: 'var(--bg-raised)' }}>
      <h2>
        Validation:{' '}
        <span className={v.ok ? 'badge badge-pass' : 'badge badge-fail'}>{v.ok ? 'PASS' : 'FAIL'}</span>
      </h2>
      <table>
        <tbody>
          {v.checks?.map((c) => (
            <tr key={c.name}>
              <td>{c.ok ? '✓' : '✗'}</td>
              <td className="mono">{c.name}</td>
              <td className="hint">{c.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {v.error && <div className="error-box">{v.error}</div>}
    </div>
  )
}

export default function Controllers() {
  const [controllers, setControllers] = useState<ControllerSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  // Parameter variant form
  const [paramBase, setParamBase] = useState<'cubic' | 'reno'>('cubic')
  const [paramName, setParamName] = useState('')
  const [beta, setBeta] = useState(717)
  const [bicScale, setBicScale] = useState(41)
  const [num, setNum] = useState(1)
  const [den, setDen] = useState(2)
  const [paramValidation, setParamValidation] = useState<ValidationReport | null>(null)
  const [paramBusy, setParamBusy] = useState(false)

  // Code editor
  const [editorBase, setEditorBase] = useState<'cubic' | 'reno'>('cubic')
  const [code, setCode] = useState('')
  const [codeName, setCodeName] = useState('')
  const [codeValidation, setCodeValidation] = useState<ValidationReport | null>(null)
  const [codeBusy, setCodeBusy] = useState(false)

  function refresh() {
    api.listControllers().then(setControllers).catch((e) => setError(String(e)))
  }
  useEffect(refresh, [])

  useEffect(() => {
    api.getTemplate(editorBase).then(setCode).catch(() => void 0)
  }, [editorBase])

  // Mirrors ccreplay.controllers._recompute_cubic_derived exactly (Python //
  // truncates toward -infinity same as Math.floor for these non-negative
  // operands) -- a preview that doesn't match what Create actually computes
  // would mislead the user before they commit to a variant.
  const betaScale = Math.floor(Math.floor((8 * (1024 + beta)) / 3) / (1024 - beta))
  const cubeRttScale = bicScale * 10
  const cubeFactor = Math.floor(Math.pow(2, 10 + 3 * 10) / (bicScale * 10))

  async function createParam() {
    setParamBusy(true)
    setParamValidation(null)
    try {
      const params: Record<string, number> = paramBase === 'cubic' ? { BETA: beta, BIC_SCALE: bicScale } : { num, den }
      const name = paramName || `${paramBase}_${Date.now()}`
      const { validation } = await api.createParamController(paramBase, name, params)
      setParamValidation(validation)
      refresh()
    } catch (e) {
      setError(String(e))
    } finally {
      setParamBusy(false)
    }
  }

  async function saveAndValidateCode() {
    setCodeBusy(true)
    setCodeValidation(null)
    try {
      const name = codeName || `code_${Date.now()}`
      const { validation } = await api.createUserController(name, editorBase, code)
      setCodeValidation(validation)
      refresh()
    } catch (e) {
      setError(String(e))
    } finally {
      setCodeBusy(false)
    }
  }

  const grouped = controllers.reduce<Record<string, ControllerSummary[]>>((acc, c) => {
    acc[c.kind] = acc[c.kind] || []
    acc[c.kind].push(c)
    return acc
  }, {})

  return (
    <div>
      <h1>Controllers</h1>
      {error && <div className="error-box">{error}</div>}

      <div className="panel">
        <h2>Registry</h2>
        {Object.entries(grouped).map(([kind, list]) => (
          <div key={kind} style={{ marginBottom: '1rem' }}>
            <h3 style={{ textTransform: 'capitalize' }}>{kind.replace('-', ' ')}</h3>
            <table>
              <thead>
                <tr>
                  <th>id</th>
                  <th>abi</th>
                  <th>description</th>
                </tr>
              </thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.id}</td>
                    <td>{c.abi !== null ? <span className="badge badge-neutral">{ABI_NAME[c.abi]}</span> : '?'}</td>
                    <td className="hint">{c.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>

      <div className="grid-2">
        <div className="panel">
          <h2>Create a parameter variant</h2>
          <div className="field-row">
            <label>Base</label>
            <select value={paramBase} onChange={(e) => setParamBase(e.target.value as 'cubic' | 'reno')}>
              <option value="cubic">CUBIC</option>
              <option value="reno">Reno</option>
            </select>
            <label>Name</label>
            <input type="text" value={paramName} onChange={(e) => setParamName(e.target.value)} placeholder="my_variant" />
          </div>
          {paramBase === 'cubic' ? (
            <>
              <div className="field-row">
                <label>β = {beta} (BETA/1024 = {(beta / 1024).toFixed(3)})</label>
                <input
                  type="number"
                  min={1}
                  max={1023}
                  value={beta}
                  onChange={(e) => setBeta(Number(e.target.value))}
                  style={{ width: 90 }}
                />
              </div>
              <div className="field-row">
                <label>BIC_SCALE</label>
                <input
                  type="number"
                  min={1}
                  max={400}
                  value={bicScale}
                  onChange={(e) => setBicScale(Number(e.target.value))}
                  style={{ width: 90 }}
                />
              </div>
              <p className="hint">
                derived: BETA_SCALE≈{betaScale.toFixed(2)}, CUBE_RTT_SCALE={cubeRttScale}, CUBE_FACTOR≈
                {cubeFactor.toFixed(2)}
              </p>
            </>
          ) : (
            <div className="field-row">
              <label>retention = num/den</label>
              <input type="number" min={1} value={num} onChange={(e) => setNum(Number(e.target.value))} style={{ width: 60 }} />
              /
              <input type="number" min={1} value={den} onChange={(e) => setDen(Number(e.target.value))} style={{ width: 60 }} />
              <span className="hint">({(num / den).toFixed(2)} of cwnd retained on loss)</span>
            </div>
          )}
          <button className="btn" disabled={paramBusy} onClick={createParam}>
            {paramBusy ? 'Creating…' : 'Create → auto-validate'}
          </button>
          {paramValidation && <ValidationPanel v={paramValidation} />}
        </div>

        <div className="panel">
          <h2>Write a controller</h2>
          <div className="field-row">
            <label>Start from template</label>
            <select value={editorBase} onChange={(e) => setEditorBase(e.target.value as 'cubic' | 'reno')}>
              <option value="cubic">CUBIC</option>
              <option value="reno">Reno</option>
            </select>
            <label>Name</label>
            <input type="text" value={codeName} onChange={(e) => setCodeName(e.target.value)} placeholder="my_controller" />
          </div>
          <p className="hint">This runs Python code on your machine (in a child process with a timeout), for responsiveness, not isolation.</p>
          <CodeMirror value={code} height="320px" extensions={[python()]} onChange={setCode} theme="dark" />
          <div className="field-row" style={{ marginTop: '0.5rem' }}>
            <button className="btn" disabled={codeBusy} onClick={saveAndValidateCode}>
              {codeBusy ? 'Saving…' : 'Save → Validate'}
            </button>
          </div>
          {codeValidation && <ValidationPanel v={codeValidation} />}
        </div>
      </div>
    </div>
  )
}
