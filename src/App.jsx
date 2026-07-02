import { useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import { requestCodeAction } from './api/client'
import './App.css'

const DEFAULT_PYTHON = `def greet(name):
    return f"Hello, {name}!"

print(greet("world"))
print("2 + 2 =", 2 + 2)
`

function App() {
  const [code, setCode] = useState(DEFAULT_PYTHON)
  const [instruction, setInstruction] = useState('Refactor this script to use a helper function and greet the user warmly.')
  const [usePatchMode, setUsePatchMode] = useState(true)
  const [output, setOutput] = useState('Click Run to execute the current Python buffer.')
  const [status, setStatus] = useState('Loading Pyodide...')
  const [agentSteps, setAgentSteps] = useState([])
  const [isRunning, setIsRunning] = useState(false)
  const [isAsking, setIsAsking] = useState(false)
  const [ready, setReady] = useState(false)
  const [sessionId, setSessionId] = useState('')
  const pyodideRef = useRef(null)

  useEffect(() => {
    let cancelled = false

    async function initPyodide() {
      try {
        const pyodideModule = await import('pyodide/pyodide.mjs')
        const pyodide = await pyodideModule.loadPyodide({
          indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.2/full/',
        })

        if (cancelled) {
          return
        }

        pyodide.setStdout({
          batched: (text) => {
            setOutput((prev) => `${prev}${text}`)
          },
        })

        pyodide.setStderr({
          batched: (text) => {
            setOutput((prev) => `${prev}${text}`)
          },
        })

        pyodideRef.current = pyodide
        setReady(true)
        setStatus('Pyodide ready. Run your Python code instantly.')
      } catch (error) {
        console.error(error)
        try {
          const { loadPyodide } = await import('https://cdn.jsdelivr.net/pyodide/v0.26.2/full/pyodide.mjs')
          const pyodide = await loadPyodide({
            indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.26.2/full/',
          })

          if (cancelled) {
            return
          }

          pyodide.setStdout({
            batched: (text) => {
              setOutput((prev) => `${prev}${text}`)
            },
          })

          pyodide.setStderr({
            batched: (text) => {
              setOutput((prev) => `${prev}${text}`)
            },
          })

          pyodideRef.current = pyodide
          setReady(true)
          setStatus('Pyodide ready. Run your Python code instantly.')
        } catch (fallbackError) {
          console.error(fallbackError)
          setStatus(`Pyodide failed to load: ${fallbackError.message}`)
        }
      }
    }

    initPyodide()

    return () => {
      cancelled = true
    }
  }, [])

  const handleRun = async () => {
    if (!pyodideRef.current) {
      setOutput('Pyodide is still loading. Please wait a moment and try again.')
      return
    }

    setIsRunning(true)
    setOutput('')
    setStatus('Running Python...')

    try {
      await pyodideRef.current.runPythonAsync(code)
      setStatus('Execution complete.')
    } catch (error) {
      setOutput((prev) => `${prev}${error.message}\n`)
      setStatus('Execution failed.')
    } finally {
      setIsRunning(false)
    }
  }

  const handleAskAi = async () => {
    if (!instruction.trim()) {
      setStatus('Please enter an instruction before asking the AI.')
      return
    }

    setIsAsking(true)
    setAgentSteps([])
    setStatus('Planning the rewrite...')

    try {
      const data = await requestCodeAction({
        file_content: code,
        instruction,
        use_patch_mode: usePatchMode,
        session_id: sessionId || undefined,
      })
      setCode(data.rewritten_code)
      setAgentSteps(data.steps || [])
      setSessionId(data.session_id)
      setOutput('Phase 5 pipeline completed. Planner, developer, validator, and memory steps finished.')
      setStatus('Rewrite complete.')
    } catch (error) {
      console.error(error)
      setOutput(`AI request failed: ${error.message}`)
      setStatus('Rewrite failed.')
    } finally {
      setIsAsking(false)
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">AgentCode · Phase 5</p>
          <h1>Browser-based Python playground</h1>
          <p className="subtitle">
            Type Python in the editor, run it locally with Pyodide, or ask the backend to rewrite the current file.
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="secondary-button" onClick={handleAskAi} disabled={isAsking}>
            {isAsking ? 'Thinking…' : 'Ask AI'}
          </button>
          <button type="button" className="run-button" onClick={handleRun} disabled={!ready || isRunning}>
            {isRunning ? 'Running…' : 'Run'}
          </button>
        </div>
      </header>

      <section className="prompt-panel">
        <label htmlFor="instruction">Instruction</label>
        <textarea
          id="instruction"
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          placeholder="Describe the change you want the AI to make"
        />
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={usePatchMode}
            onChange={(event) => setUsePatchMode(event.target.checked)}
          />
          <span>Use patch-based mode (libcst fallback)</span>
        </label>
      </section>

      <section className="status-bar" aria-live="polite">
        <span>{status}</span>
        <span>{ready ? 'Client-side runtime ready' : 'Waiting for runtime'}</span>
        <span>{sessionId ? `Session ID: ${sessionId}` : 'No session yet'}</span>
      </section>

      <section className="editor-panel">
        <Editor
          height="60vh"
          defaultLanguage="python"
          value={code}
          theme="vs-dark"
          onChange={(value) => setCode(value ?? '')}
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            lineNumbersMinChars: 3,
            scrollBeyondLastLine: false,
          }}
        />
      </section>

      <section className="output-panel">
        <div className="output-header">
          <h2>Output</h2>
          <span>stdout / stderr / AI</span>
        </div>
        <pre>{output}</pre>
      </section>

      <section className="agent-panel">
        <div className="output-header">
          <h2>Agent steps</h2>
          <span>Planner → Developer → Validator</span>
        </div>
        <ul>
          {agentSteps.length === 0 ? (
            <li className="empty-state">No agent steps recorded yet.</li>
          ) : (
            agentSteps.map((step) => (
              <li key={step.name}>
                <strong>{step.name}</strong>
                <span>{step.status}</span>
                <p>{step.detail}</p>
              </li>
            ))
          )}
        </ul>
      </section>
    </main>
  )
}

export default App
