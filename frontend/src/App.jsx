import { useEffect, useRef, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function hora() {
  return new Date().toLocaleTimeString('es-CO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function App() {
  const recognitionRef = useRef(null)

  const [brief, setBrief] = useState(null)
  const [cargandoBrief, setCargandoBrief] = useState(true)
  const [preguntas, setPreguntas] = useState([])
  const [pregunta, setPregunta] = useState('')
  const [mensajes, setMensajes] = useState([])
  const [cargandoRespuesta, setCargandoRespuesta] = useState(false)
  const [escuchando, setEscuchando] = useState(false)
  const [error, setError] = useState('')
  const [emocion, setEmocion] = useState(null)
  const [vozActiva, setVozActiva] = useState(true)

  useEffect(() => {
    cargarBrief()
  }, [])

  async function leerJson(response) {
    const data = await response.json().catch(() => ({}))

    if (!response.ok) {
      throw new Error(
        typeof data.detail === 'string'
          ? data.detail
          : 'No se pudo completar la operación.',
      )
    }

    return data
  }

  async function cargarBrief() {
    setCargandoBrief(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/brief`)
      const data = await leerJson(response)
      setBrief(data)
      setPreguntas(data.preguntas_sugeridas || [])
    } catch (err) {
      setError(
        err.message ||
          'No se pudo conectar con la fuente de datos. Comprueba el backend.',
      )
    } finally {
      setCargandoBrief(false)
    }
  }

  function leerEnVozAlta(texto) {
    if (!('speechSynthesis' in window) || !vozActiva) return

    window.speechSynthesis.cancel()
    const voz = new SpeechSynthesisUtterance(texto)
    voz.lang = 'es-CO'
    voz.rate = 1.05
    voz.pitch = 1
    window.speechSynthesis.speak(voz)
  }

  async function clasificarEmocion(texto) {
    try {
      const response = await fetch(`${API_URL}/api/emotion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto }),
      })
      const data = await leerJson(response)
      setEmocion(data)
    } catch {
      /* el panel de emoción es opcional */
    }
  }

  async function enviarPregunta(texto = pregunta) {
    const textoPregunta = texto.trim()

    if (!textoPregunta || cargandoRespuesta) return

    setPregunta('')
    setError('')
    setMensajes((actuales) => [
      ...actuales,
      { rol: 'usuario', texto: textoPregunta, hora: hora() },
    ])
    setCargandoRespuesta(true)
    clasificarEmocion(textoPregunta)

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta: textoPregunta }),
      })

      const data = await leerJson(response)

      setMensajes((actuales) => [
        ...actuales,
        {
          rol: 'asistente',
          texto: data.respuesta,
          hora: hora(),
          consulta: data.consulta,
          filas: data.filas,
        },
      ])

      leerEnVozAlta(data.respuesta)
    } catch (err) {
      setError(err.message || 'No se pudo obtener una respuesta.')
    } finally {
      setCargandoRespuesta(false)
    }
  }

  function iniciarMicrofono() {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition

    if (!SpeechRecognition) {
      setError(
        'Tu navegador no admite reconocimiento de voz. Usa una versión actualizada de Chrome o Edge.',
      )
      return
    }

    if (escuchando) {
      recognitionRef.current?.stop()
      return
    }

    const reconocimiento = new SpeechRecognition()
    reconocimiento.lang = 'es-CO'
    reconocimiento.continuous = false
    reconocimiento.interimResults = true
    reconocimiento.maxAlternatives = 1

    reconocimiento.onstart = () => {
      setEscuchando(true)
      setError('')
    }

    reconocimiento.onresult = (event) => {
      let texto = ''
      for (let i = 0; i < event.results.length; i++) {
        texto += event.results[i][0].transcript
      }
      setPregunta(texto.trim())
    }

    reconocimiento.onerror = (event) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(`Error de reconocimiento de voz: ${event.error}`)
      }
    }

    reconocimiento.onend = () => setEscuchando(false)

    recognitionRef.current = reconocimiento

    try {
      reconocimiento.start()
    } catch {
      setEscuchando(false)
      setError('No se pudo iniciar el micrófono. Inténtalo de nuevo.')
    }
  }

  const totalRegistros = brief?.total_registros?.[0]?.total

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#">
          <span className="brand-icon">✳</span>
          <span>
            Vocal<span className="brand-light"> Cognitivo</span>
          </span>
        </a>
        <div className="topbar-right">
          <button
            type="button"
            className="voice-toggle"
            onClick={() => setVozActiva((valor) => !valor)}
            aria-label="Activar o desactivar la voz"
          >
            {vozActiva ? '🔊 Voz activa' : '🔇 Voz silenciada'}
          </button>
          <span className="status">
            <span className="status-dot" />
            Datos.gov.co en vivo
          </span>
        </div>
      </header>

      <section className="hero">
        <span className="eyebrow">DATOS ABIERTOS DE SALUD, UNA CONVERSACIÓN</span>
        <h1>Habla con las IPS de Colombia.</h1>
        <p>
          Pregunta por voz o por texto sobre la red de Instituciones
          Prestadoras de Servicios de Salud y su capacidad instalada. Las
          respuestas se construyen con datos reales de datos.gov.co.
        </p>
      </section>

      <section className="workspace">
        <aside className="sidebar">
          <div className="section-heading">
            <span className="step-number">01</span>
            <div>
              <h2>Fuente de datos</h2>
              <p>Índice abierto consultado en vivo.</p>
            </div>
          </div>

          {cargandoBrief ? (
            <div className="empty-state compact">
              <span className="spinner" />
              <strong>Conectando con datos.gov.co</strong>
            </div>
          ) : (
            <>
              {brief && (
                <div className="document-info">
                  <span className="success-label">✓ Fuente conectada</span>
                  <p>{brief.fuente}</p>
                  <span>
                    {totalRegistros
                      ? `${Number(totalRegistros).toLocaleString('es-CO')} registros`
                      : 'Datos abiertos'}{' '}
                    · Ministerio de Salud
                  </span>
                </div>
              )}

              {brief?.introduccion && (
                <div className="summary-card brief-card">
                  <p className="summary-text">{brief.introduccion}</p>
                </div>
              )}
            </>
          )}

          <div className="privacy-note">
            <span>ⓘ</span>
            <p>
              La fuente es la «Relación de IPS públicas y privadas según el
              nivel de atención y capacidad instalada» publicada en
              datos.gov.co.
            </p>
          </div>
        </aside>

        <div className="main-panel">
          <section className="chat-section">
            <div className="section-heading">
              <span className="step-number">02</span>
              <div>
                <h2>Conversa con los datos</h2>
                <p>Pregunta por voz o por texto.</p>
              </div>
            </div>

            <div className="chat-history" aria-live="polite">
              {mensajes.length === 0 && (
                <div className="chat-welcome">
                  <span className="chat-sparkle">✳</span>
                  <p>Pulsa el micrófono y pregunta, por ejemplo:</p>
                  <p className="chat-example">
                    «¿Cuántas camas hay en Medellín?»
                  </p>
                </div>
              )}

              {mensajes.map((mensaje, index) => (
                <div
                  className={`message ${mensaje.rol}`}
                  key={`${index}-${mensaje.hora}`}
                >
                  <span className="message-label">
                    {mensaje.rol === 'usuario' ? 'Tú' : 'Vocal'}
                    <span className="message-time">{mensaje.hora}</span>
                  </span>
                  <p>{mensaje.texto}</p>

                  {mensaje.rol === 'asistente' && (
                    <button
                      className="speak-button"
                      type="button"
                      onClick={() => leerEnVozAlta(mensaje.texto)}
                    >
                      🔈 Escuchar respuesta
                    </button>
                  )}

                  {mensaje.consulta && (
                    <span className="query-chip">
                      Consulta: {JSON.stringify(mensaje.consulta)} ·{' '}
                      {mensaje.filas} filas
                    </span>
                  )}
                </div>
              ))}

              {cargandoRespuesta && (
                <div className="message asistente">
                  <span className="message-label">Vocal</span>
                  <p className="thinking">Consultando los datos…</p>
                </div>
              )}
            </div>

            <form
              className="chat-form"
              onSubmit={(event) => {
                event.preventDefault()
                enviarPregunta()
              }}
            >
              <button
                className={`mic-button ${escuchando ? 'mic-active' : ''}`}
                type="button"
                onClick={iniciarMicrofono}
                disabled={cargandoRespuesta}
                aria-label="Dictar pregunta"
              >
                🎙
              </button>
              <input
                type="text"
                value={pregunta}
                onChange={(event) => setPregunta(event.target.value)}
                placeholder={
                  escuchando ? 'Escuchando…' : 'Escribe o dicta tu pregunta…'
                }
                disabled={cargandoRespuesta}
                aria-label="Tu pregunta"
              />
              <button
                className="send-button"
                type="submit"
                disabled={!pregunta.trim() || cargandoRespuesta}
                aria-label="Enviar pregunta"
              >
                ↑
              </button>
            </form>

            <p className="chat-footnote">
              La IA puede cometer errores. Verifica las respuestas importantes.
            </p>
          </section>

          <section className="summary-section">
            <div className="section-heading">
              <span className="step-number">03</span>
              <div>
                <h2>Transcripción y emociones</h2>
                <p>Habla identificado por turno y análisis en vivo.</p>
              </div>
            </div>

            <div className="emotion-panel">
              <span className="emotion-panel-label">Tono de la conversación</span>
              <div className="emotion-current">
                <span
                  className={`emotion-dot ${
                    emocion?.sentimiento || 'neutral'
                  }`}
                />
                <strong>{emocion?.emocion || 'neutral'}</strong>
                <span className="emotion-sent">
                  {emocion?.sentimiento || 'neutral'}
                </span>
              </div>
              <span className="emotion-bar">
                <i
                  style={{
                    width: `${Math.round((emocion?.intensidad || 0) * 100)}%`,
                  }}
                />
              </span>
            </div>

            <div className="transcript-box">
              {mensajes.length === 0 ? (
                <p className="transcript-empty">
                  La transcripción aparecerá aquí a medida que hablen.
                </p>
              ) : (
                mensajes.map((mensaje, index) => (
                  <div className="transcript-item" key={`t-${index}`}>
                    <div className="transcript-meta">
                      <span
                        className={`transcript-speaker ${
                          mensaje.rol === 'usuario' ? 'spk-a' : 'spk-b'
                        }`}
                      >
                        {mensaje.rol === 'usuario' ? 'Hablante 1 · Tú' : 'Hablante 2 · Vocal'}
                      </span>
                      <span className="transcript-time">{mensaje.hora}</span>
                    </div>
                    <p>{mensaje.texto}</p>
                  </div>
                ))
              )}
            </div>

            {preguntas.length > 0 && (
              <div className="suggestions">
                <h3>Preguntas para explorar</h3>
                <p>Selecciona una para iniciar la conversación.</p>
                <div className="suggestion-list">
                  {preguntas.map((item, index) => (
                    <button
                      key={`${index}-${item}`}
                      className="suggestion-button"
                      onClick={() => enviarPregunta(item)}
                      disabled={cargandoRespuesta}
                    >
                      <span>{item}</span>
                      <span className="suggestion-arrow">↗</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      </section>

      {error && (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button onClick={() => setError('')} aria-label="Cerrar error">
            ×
          </button>
        </div>
      )}

      <footer className="footer">
        <span>Vocal Cognitivo · Kognia Labs</span>
        <span>Agente de voz sobre datos abiertos de salud</span>
      </footer>
    </main>
  )
}

export default App
