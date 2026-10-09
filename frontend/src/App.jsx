import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SALUDO_POR_DEFECTO =
  'Hola, ¿cómo estás? Soy la asistente virtual de la IPS. ' +
  'Dime en qué te puedo ayudar y en qué ciudad estás.'

const EMOJI = {
  alegria: '😄',
  satisfaccion: '😊',
  serenidad: '😌',
  curiosidad: '🤔',
  confusion: '😕',
  preocupacion: '😟',
  ansiedad: '😰',
  frustracion: '😤',
  enojo: '😠',
  tristeza: '😢',
  neutral: '🙂',
}

function hora() {
  return new Date().toLocaleTimeString('es-CO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

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

function App() {
  const recognitionRef = useRef(null)

  const [brief, setBrief] = useState(null)
  const [cargandoBrief, setCargandoBrief] = useState(true)
  const [inicio, setInicio] = useState(false)
  const [saludo, setSaludo] = useState(SALUDO_POR_DEFECTO)
  const [sugerencias, setSugerencias] = useState([])
  const [preguntas, setPreguntas] = useState([])
  const [pregunta, setPregunta] = useState('')
  const [mensajes, setMensajes] = useState([])
  const [cargandoRespuesta, setCargandoRespuesta] = useState(false)
  const [escuchando, setEscuchando] = useState(false)
  const [error, setError] = useState('')
  const [analisis, setAnalisis] = useState([])
  const [vozActiva, setVozActiva] = useState(true)

  const cargarInicial = useCallback(async () => {
    try {
      const [rBrief, rSaludo] = await Promise.all([
        fetch(`${API_URL}/api/brief`),
        fetch(`${API_URL}/api/greeting`),
      ])
      const dBrief = await leerJson(rBrief)
      const dSaludo = await leerJson(rSaludo)

      setBrief(dBrief)
      setPreguntas(dBrief.preguntas_sugeridas || [])
      setSaludo(dSaludo.mensaje || SALUDO_POR_DEFECTO)
      setSugerencias(dSaludo.sugerencias || [])
    } catch (err) {
      setError(
        err.message ||
          'No se pudo conectar con la fuente de datos. Comprueba el backend.',
      )
    } finally {
      setCargandoBrief(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- carga inicial desde la API
    cargarInicial()
  }, [cargarInicial])

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
        body: JSON.stringify({ texto, rol: 'usuario' }),
      })
      return await leerJson(response)
    } catch {
      return null
    }
  }

  function iniciarAsistente() {
    setInicio(true)
    setMensajes([{ rol: 'asistente', texto: saludo, hora: hora() }])
    leerEnVozAlta(saludo)
  }

  async function enviarPregunta(texto = pregunta) {
    const textoPregunta = texto.trim()

    if (!textoPregunta || cargandoRespuesta || !inicio) return

    setPregunta('')
    setError('')

    const historial = mensajes.map((m) => ({ rol: m.rol, texto: m.texto }))
    const marcaHora = hora()

    setMensajes((actuales) => [
      ...actuales,
      { rol: 'usuario', texto: textoPregunta, hora: marcaHora },
    ])
    setCargandoRespuesta(true)

    clasificarEmocion(textoPregunta).then((analisisUsuario) => {
      if (!analisisUsuario) return
      setMensajes((actuales) =>
        actuales.map((m) =>
          m.hora === marcaHora && m.rol === 'usuario'
            ? { ...m, emocion: analisisUsuario }
            : m,
        ),
      )
      setAnalisis((actuales) => [
        ...actuales,
        {
          ...analisisUsuario,
          rol: 'usuario',
          texto: textoPregunta,
          hora: marcaHora,
        },
      ])
    })

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta: textoPregunta, historial }),
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
  const emocionActual = analisis[analisis.length - 1] || null
  const conteo = analisis.reduce((acc, item) => {
    acc[item.sentimiento] = (acc[item.sentimiento] || 0) + 1
    return acc
  }, {})
  const totalAnalisis = analisis.length || 1

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
        <span className="eyebrow">ASISTENTE DE SALUD POR VOZ · DATOS ABIERTOS</span>
        <h1>Habla con la red de IPS de Colombia.</h1>
        <p>
          Cuéntame tu necesidad de salud y tu ciudad. Con la «Relación de IPS»
          de datos.gov.co te oriento sobre instituciones y capacidad instalada,
          y analizo el tono de nuestra conversación en vivo.
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
              Cada consulta lee máximo 1.000 filas de datos.gov.co. No se
              almacena información personal.
            </p>
          </div>
        </aside>

        <div className="main-panel">
          <section className="chat-section">
            <div className="section-heading">
              <span className="step-number">02</span>
              <div>
                <h2>Conversa con la asistente</h2>
                <p>Responde por voz o por texto.</p>
              </div>
            </div>

            <div className="chat-history" aria-live="polite">
              {!inicio && (
                <div className="start-card">
                  <span className="chat-sparkle">✳</span>
                  <strong>Asistente virtual de la IPS</strong>
                  <p>
                    Pulsa para que la asistente te salude por voz y te pregunte
                    en qué te puede ayudar.
                  </p>
                  <button
                    type="button"
                    className="primary-button start-button"
                    onClick={iniciarAsistente}
                    disabled={cargandoBrief}
                  >
                    🔈 Iniciar asistente
                  </button>
                </div>
              )}

              {inicio &&
                mensajes.map((mensaje, index) => (
                  <div
                    className={`message ${mensaje.rol}`}
                    key={`${index}-${mensaje.hora}`}
                  >
                    <span className="message-label">
                      {mensaje.rol === 'usuario' ? 'Tú' : 'Asistente'}
                      <span className="message-time">{mensaje.hora}</span>
                      {mensaje.emocion && (
                        <span className="msg-emotion">
                          {EMOJI[mensaje.emocion.emocion] || '🙂'}{' '}
                          {mensaje.emocion.emocion}
                        </span>
                      )}
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
                  <span className="message-label">Asistente</span>
                  <p className="thinking">
                    Consultando datos y analizando la conversación…
                  </p>
                </div>
              )}
            </div>

            {inicio && sugerencias.length > 0 && mensajes.length <= 1 && (
              <div className="suggestion-list inline">
                {sugerencias.map((item) => (
                  <button
                    key={item}
                    className="suggestion-button"
                    onClick={() => enviarPregunta(item)}
                  >
                    <span>{item}</span>
                    <span className="suggestion-arrow">↗</span>
                  </button>
                ))}
              </div>
            )}

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
                disabled={cargandoRespuesta || !inicio}
                aria-label="Dictar mensaje"
              >
                🎙
              </button>
              <input
                type="text"
                value={pregunta}
                onChange={(event) => setPregunta(event.target.value)}
                placeholder={
                  !inicio
                    ? 'Inicia la asistente para hablar'
                    : escuchando
                      ? 'Escuchando…'
                      : 'Escribe o dicta tu necesidad y ciudad…'
                }
                disabled={cargandoRespuesta || !inicio}
                aria-label="Tu mensaje"
              />
              <button
                className="send-button"
                type="submit"
                disabled={!pregunta.trim() || cargandoRespuesta || !inicio}
                aria-label="Enviar"
              >
                ↑
              </button>
            </form>

            <p className="chat-footnote">
              La asistente orienta con datos abiertos y no reemplaza una
              valoración médica.
            </p>
          </section>

          <section className="summary-section">
            <div className="section-heading">
              <span className="step-number">03</span>
              <div>
                <h2>Sentimiento y emociones en vivo</h2>
                <p>Análisis del tono de cada turno mientras la conversación ocurre.</p>
              </div>
            </div>

            <div className="emotion-panel">
              <div className="emotion-current">
                <span className="emotion-emoji">
                  {emocionActual
                    ? EMOJI[emocionActual.emocion] || '🙂'
                    : '💬'}
                </span>
                <div className="emotion-headline">
                  <strong>
                    {emocionActual ? emocionActual.emocion : 'sin analizar'}
                  </strong>
                  <span className={`emotion-tag ${emocionActual?.sentimiento || 'neutral'}`}>
                    {emocionActual?.sentimiento || 'neutral'}
                  </span>
                </div>
                <span className="emotion-intensity">
                  Intensidad {Math.round((emocionActual?.intensidad || 0) * 100)}%
                </span>
              </div>

              <span className="emotion-bar">
                <i
                  style={{
                    width: `${Math.round((emocionActual?.intensidad || 0) * 100)}%`,
                  }}
                />
              </span>

              {emocionActual?.explicacion && (
                <p className="emotion-explication">{emocionActual.explicacion}</p>
              )}

              {analisis.length > 0 && (
                <div className="emotion-dist">
                  {['positivo', 'neutral', 'negativo'].map((clave) => (
                    <span
                      key={clave}
                      className={`emotion-seg ${clave}`}
                      style={{
                        width: `${((conteo[clave] || 0) / totalAnalisis) * 100}%`,
                      }}
                    />
                  ))}
                </div>
              )}

              {analisis.length > 0 && (
                <div className="emotion-legend">
                  {['positivo', 'neutral', 'negativo'].map((clave) => (
                    <span key={clave}>
                      <i className={`emotion-dot ${clave}`} /> {clave}:{' '}
                      {conteo[clave] || 0}
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="analysis-timeline">
              {analisis.length === 0 ? (
                <p className="transcript-empty">
                  El análisis emocional aparecerá aquí con cada mensaje.
                </p>
              ) : (
                analisis.map((item, index) => (
                  <div className="analysis-item" key={`a-${index}`}>
                    <span className="analysis-emoji">
                      {EMOJI[item.emocion] || '🙂'}
                    </span>
                    <div className="analysis-body">
                      <div className="analysis-meta">
                        <span className={`emotion-tag ${item.sentimiento}`}>
                          {item.emocion}
                        </span>
                        <span className="transcript-time">{item.hora}</span>
                      </div>
                      <p>{item.texto}</p>
                    </div>
                  </div>
                ))
              )}
            </div>

            {preguntas.length > 0 && (
              <div className="suggestions">
                <h3>Preguntas para explorar</h3>
                <p>Selecciona una si quieres una idea.</p>
                <div className="suggestion-list">
                  {preguntas.map((item, index) => (
                    <button
                      key={`${index}-${item}`}
                      className="suggestion-button"
                      onClick={() => enviarPregunta(item)}
                      disabled={cargandoRespuesta || !inicio}
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
        <span>Asistente de voz sobre datos abiertos de salud</span>
      </footer>
    </main>
  )
}

export default App
