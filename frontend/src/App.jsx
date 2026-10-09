import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SALUDO_POR_DEFECTO =
  'Hola, ¿cómo estás? Soy la asistente virtual de la IPS. ' +
  'Dime en qué te puedo ayudar y en qué ciudad estás.'

function hora() {
  return new Date().toLocaleTimeString('es-CO', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function limpiarTexto(texto) {
  return texto
    .replace(/\*\*/g, '')
    .replace(/__/g, '')
    .replace(/`/g, '')
    .replace(/^\s*[*•-]\s+/gm, '')
    .replace(/^#{1,6}\s*/gm, '')
    .replace(/[*#]/g, '')
    .trim()
}

function App() {
  const reconocimientoRef = useRef(null)
  const transcripcionRef = useRef('')
  const enviarAlSoltarRef = useRef(false)

  const [brief, setBrief] = useState(null)
  const [inicio, setInicio] = useState(false)
  const [saludo, setSaludo] = useState(SALUDO_POR_DEFECTO)
  const [sugerencias, setSugerencias] = useState([])
  const [preguntas, setPreguntas] = useState([])
  const [pregunta, setPregunta] = useState('')
  const [mensajes, setMensajes] = useState([])
  const [cargandoRespuesta, setCargandoRespuesta] = useState(false)
  const [pensando, setPensando] = useState(false)
  const [escuchando, setEscuchando] = useState(false)
  const [error, setError] = useState('')
  const [vozActiva, setVozActiva] = useState(true)

  const cargarInicial = useCallback(async () => {
    try {
      const [rBrief, rSaludo] = await Promise.all([
        fetch(`${API_URL}/api/brief`),
        fetch(`${API_URL}/api/greeting`),
      ])
      const dBrief = await rBrief.json().catch(() => ({}))
      const dSaludo = await rSaludo.json().catch(() => ({}))

      setBrief(dBrief)
      setPreguntas(dBrief.preguntas_sugeridas || [])
      setSaludo(dSaludo.mensaje || SALUDO_POR_DEFECTO)
      setSugerencias(dSaludo.sugerencias || [])
    } catch {
      // La asistente arranca igualmente con los textos de reserva.
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- la carga inicial vive en la API
    cargarInicial()
  }, [cargarInicial])

  function decir(texto) {
    if (!('speechSynthesis' in window) || !vozActiva) return
    const voz = new SpeechSynthesisUtterance(texto)
    voz.lang = 'es-CO'
    voz.rate = 1.05
    voz.pitch = 1
    window.speechSynthesis.speak(voz)
  }

  function leerEnVozAlta(texto) {
    if (!('speechSynthesis' in window) || !vozActiva) return
    window.speechSynthesis.cancel()
    decir(texto)
  }

  function iniciarAsistente() {
    setInicio(true)
    setMensajes([{ rol: 'asistente', texto: limpiarTexto(saludo), hora: hora() }])
    leerEnVozAlta(saludo)
  }

  function hablarIncremental(texto, estado) {
    if (!vozActiva) {
      estado.hablado = texto.length
      return
    }
    while (estado.hablado < texto.length) {
      const resto = texto.slice(estado.hablado)
      const corte = resto.match(/^[^.!?…\n]*[.!?…]+(\s+|$)/)
      if (!corte) break
      const trozo = corte[0].trim()
      if (trozo) decir(trozo)
      estado.hablado += corte[0].length
    }
  }

  async function enviarPregunta(texto = pregunta) {
    const textoPregunta = texto.trim()

    if (!textoPregunta || cargandoRespuesta) return

    setPregunta('')
    setError('')

    const historial = mensajes
      .filter((m) => m.texto && m.texto.trim() !== '')
      .map((m) => ({ rol: m.rol, texto: m.texto }))
    const indiceAsistente = mensajes.length + 1

    setMensajes((actuales) => [
      ...actuales,
      { rol: 'usuario', texto: textoPregunta, hora: hora() },
      { rol: 'asistente', texto: '', hora: hora() },
    ])
    setCargandoRespuesta(true)
    setPensando(true)
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()

    try {
      const response = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pregunta: textoPregunta, historial }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'No se pudo obtener una respuesta.',
        )
      }

      const estado = { hablado: 0 }
      let acumulado = ''

      const actualizar = (textoActual) => {
        setMensajes((actuales) => {
          if (actuales.length <= indiceAsistente) return actuales
          const copia = [...actuales]
          copia[indiceAsistente] = {
            ...copia[indiceAsistente],
            texto: textoActual,
          }
          return copia
        })
      }

      if (response.body && response.body.getReader) {
        const reader = response.body.getReader()
        const decoder = new TextDecoder()

        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          acumulado += decoder.decode(value, { stream: true })
          const limpio = limpiarTexto(acumulado)
          setPensando(false)
          actualizar(limpio)
          hablarIncremental(limpio, estado)
        }
      } else {
        acumulado = await response.text()
      }

      const final = limpiarTexto(acumulado)
      actualizar(final)
      setPensando(false)

      if (estado.hablado < final.length) {
        const resto = final.slice(estado.hablado).trim()
        if (resto && vozActiva) decir(resto)
      }
    } catch (err) {
      setError(err.message || 'No se pudo obtener una respuesta.')
    } finally {
      setPensando(false)
      setCargandoRespuesta(false)
    }
  }

  function usarSugerencia(texto) {
    if (cargandoRespuesta) return
    if (!inicio) {
      setInicio(true)
      setMensajes([
        { rol: 'asistente', texto: limpiarTexto(saludo), hora: hora() },
      ])
    }
    enviarPregunta(texto)
  }

  function iniciarDictado() {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition

    if (!SpeechRecognition) {
      setError(
        'Tu navegador no admite reconocimiento de voz. Usa una versión actualizada de Chrome o Edge.',
      )
      return
    }

    if (cargandoRespuesta || !inicio || escuchando) return

    const reconocimiento = new SpeechRecognition()
    reconocimiento.lang = 'es-CO'
    reconocimiento.continuous = true
    reconocimiento.interimResults = true
    reconocimiento.maxAlternatives = 1

    transcripcionRef.current = ''
    enviarAlSoltarRef.current = false

    reconocimiento.onstart = () => {
      setEscuchando(true)
      setError('')
    }

    reconocimiento.onresult = (event) => {
      let texto = ''
      for (let i = 0; i < event.results.length; i++) {
        texto += event.results[i][0].transcript
      }
      transcripcionRef.current = texto.trim()
      setPregunta(transcripcionRef.current)
    }

    reconocimiento.onerror = (event) => {
      if (event.error !== 'no-speech' && event.error !== 'aborted') {
        setError(`Error de voz: ${event.error}`)
      }
    }

    reconocimiento.onend = () => {
      setEscuchando(false)
      if (enviarAlSoltarRef.current) {
        enviarAlSoltarRef.current = false
        const texto = transcripcionRef.current.trim()
        if (texto) {
          enviarPregunta(texto)
        } else {
          setPregunta('')
        }
      }
    }

    reconocimientoRef.current = reconocimiento

    try {
      reconocimiento.start()
    } catch {
      setEscuchando(false)
      setError('No se pudo iniciar el micrófono. Inténtalo de nuevo.')
    }
  }

  function soltarDictado() {
    if (!escuchando) return
    enviarAlSoltarRef.current = true
    reconocimientoRef.current?.stop()
  }

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
            En línea
          </span>
        </div>
      </header>

      <section className="hero">
        <span className="eyebrow">ASISTENTE DE SALUD POR VOZ</span>
        <h1>Tu asistente de salud, siempre disponible.</h1>
        <p>
          Háblale con naturalidad, cuéntale qué necesitas y en qué ciudad
          estás, y te ayudará a encontrar dónde atenderte.
        </p>
      </section>

      <section className="workspace">
        <aside className="sidebar">
          <div className="section-heading">
            <span className="step-number">01</span>
            <div>
              <h2>¿Cómo te ayudo?</h2>
              <p>Habla conmigo como con una persona.</p>
            </div>
          </div>

          <div className="summary-card brief-card">
            <p className="summary-text">
              {brief?.introduccion ||
                'Soy tu asistente de salud. Cuéntame qué necesitas y en qué ciudad estás para ayudarte a encontrar dónde atenderte.'}
            </p>
          </div>

          <ul className="help-list">
            <li>Encontrar clínicas y hospitales en tu ciudad.</li>
            <li>Buscar urgencias, camas, partos o consulta externa.</li>
            <li>Conocer los datos de contacto de cada lugar.</li>
          </ul>

          <div className="privacy-note">
            <span>ⓘ</span>
            <p>
              Te oriento con información oficial de salud. No reemplaza una
              valoración médica.
            </p>
          </div>
        </aside>

        <div className="main-panel">
          <section className="chat-section">
            <div className="section-heading">
              <span className="step-number">02</span>
              <div>
                <h2>Conversa con la asistente</h2>
                <p>Mantén pulsado el micrófono, habla y suéltalo al terminar.</p>
              </div>
            </div>

            <div className="chat-history" aria-live="polite">
              {!inicio && (
                <div className="start-card">
                  <span className="chat-sparkle">✳</span>
                  <strong>Asistente virtual de la IPS</strong>
                  <p>
                    Pulsa para que te salude por voz y te pregunte en qué te
                    puede ayudar.
                  </p>
                  <button
                    type="button"
                    className="primary-button start-button"
                    onClick={iniciarAsistente}
                  >
                    🔈 Iniciar asistente
                  </button>
                </div>
              )}

              {inicio &&
                mensajes
                  .filter((mensaje) => mensaje.texto !== '')
                  .map((mensaje, index) => (
                    <div
                      className={`message ${mensaje.rol}`}
                      key={`${index}-${mensaje.hora}`}
                    >
                      <span className="message-label">
                        {mensaje.rol === 'usuario' ? 'Tú' : 'Asistente'}
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
                    </div>
                  ))}

              {pensando && (
                <div className="message asistente">
                  <span className="message-label">Asistente</span>
                  <p className="thinking">Pensando…</p>
                </div>
              )}
            </div>

            {inicio && sugerencias.length > 0 && mensajes.length <= 1 && (
              <div className="suggestion-list inline">
                {sugerencias.map((item) => (
                  <button
                    key={item}
                    className="suggestion-button"
                    onClick={() => usarSugerencia(item)}
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
                onPointerDown={(event) => {
                  event.preventDefault()
                  iniciarDictado()
                }}
                onPointerUp={soltarDictado}
                onPointerLeave={soltarDictado}
                onPointerCancel={soltarDictado}
                disabled={cargandoRespuesta || !inicio}
                aria-label="Mantén pulsado para hablar"
                title="Mantén pulsado para hablar"
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
                      ? 'Escuchando… habla y suelta el botón'
                      : 'Mantén pulsado el micrófono y habla…'
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
              La asistente orienta con información de salud y no reemplaza una
              valoración médica.
            </p>
          </section>

          <section className="summary-section">
            <div className="section-heading">
              <span className="step-number">03</span>
              <div>
                <h2>Preguntas frecuentes</h2>
                <p>Toca una para preguntármela.</p>
              </div>
            </div>

            <div className="suggestion-list">
              {(preguntas.length > 0 ? preguntas : sugerencias).map(
                (item, index) => (
                  <button
                    key={`${index}-${item}`}
                    className="suggestion-button"
                    onClick={() => usarSugerencia(item)}
                    disabled={cargandoRespuesta}
                  >
                    <span>{item}</span>
                    <span className="suggestion-arrow">↗</span>
                  </button>
                ),
              )}
            </div>
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
        <span>Asistente de salud por voz</span>
      </footer>
    </main>
  )
}

export default App
