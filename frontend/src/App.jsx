import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const SALUDO_POR_DEFECTO =
  'Hola, ¿cómo estás? Soy la asistente virtual de la IPS. ' +
  'Dime en qué te puedo ayudar y en qué ciudad estás.'

const EMOJI = {
  alegria: '😊',
  satisfaccion: '😌',
  serenidad: '🧘',
  curiosidad: '🤔',
  confusion: '😕',
  preocupacion: '😟',
  ansiedad: '😰',
  frustracion: '😖',
  enojo: '😠',
  tristeza: '😢',
  neutral: '😐',
}

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
  const interrumpidoRef = useRef(false)
  const escuchandoRef = useRef(false)
  const seguridadRef = useRef(null)

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
  const [analisis, setAnalisis] = useState(null)
  const [emociones, setEmociones] = useState([])
  const [horaEscucha, setHoraEscucha] = useState('')
  const [documento, setDocumento] = useState(null)
  const [subiendoDoc, setSubiendoDoc] = useState(false)
  const archivoRef = useRef(null)

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
    // Si el usuario sale del botón o el navegador no reporta el `pointerup`
    // dentro de él, la sesión se cierra igual: nunca queda escuchando sola.
    const alSoltar = () => {
      const sesion = reconocimientoRef.current
      if (!sesion) return
      enviarAlSoltarRef.current = true
      try {
        sesion.stop()
      } catch {
        try {
          sesion.abort()
        } catch {
          // Sesión ya cerrada.
        }
      }
    }
    window.addEventListener('pointerup', alSoltar)
    window.addEventListener('pointercancel', alSoltar)
    return () => {
      window.removeEventListener('pointerup', alSoltar)
      window.removeEventListener('pointercancel', alSoltar)
      if (seguridadRef.current) clearTimeout(seguridadRef.current)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- la carga inicial vive en la API
    cargarInicial()
  }, [cargarInicial])

  function decir(texto) {
    if (!('speechSynthesis' in window) || !vozActiva) return
    if (interrumpidoRef.current) return
    const voz = new SpeechSynthesisUtterance(texto)
    voz.lang = 'es-CO'
    voz.rate = 1.05
    voz.pitch = 1
    window.speechSynthesis.speak(voz)
  }

  function callarVoz() {
    // El usuario pulsó el micrófono: la asistente se queda callada.
    interrumpidoRef.current = true
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
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
    if (!vozActiva || interrumpidoRef.current) {
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

  async function subirDocumento(archivo) {
    if (!archivo) return
    setSubiendoDoc(true)
    setError('')
    try {
      const datos = new FormData()
      datos.append('archivo', archivo)
      const response = await fetch(`${API_URL}/api/documento`, {
        method: 'POST',
        body: datos,
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(
          typeof data.detail === 'string'
            ? data.detail
            : 'No pude leer ese archivo.',
        )
      }
      setDocumento(data)
      if (data.preguntas && data.preguntas.length) setPreguntas(data.preguntas)
      if (data.resumen) {
        setBrief({
          introduccion: `Ya indexé «${data.nombre}». ${data.resumen}`,
        })
      }
    } catch (err) {
      setError(err.message || 'No se pudo cargar el documento.')
    } finally {
      setSubiendoDoc(false)
      if (archivoRef.current) archivoRef.current.value = ''
    }
  }

  async function analizarEmocion(texto) {    // No bloquea la respuesta: corre en segundo plano.
    try {
      const response = await fetch(`${API_URL}/api/emotion`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ texto, rol: 'usuario' }),
      })
      if (!response.ok) return
      const data = await response.json()
      setAnalisis(data)
      setEmociones((prev) => [
        ...prev.slice(-6),
        { ...data, hora: hora(), texto: texto.slice(0, 60) },
      ])
    } catch {
      // El análisis es informativo: un fallo no interrumpe la conversación.
    }
  }

  async function enviarPregunta(texto = pregunta) {
    const textoPregunta = texto.trim()

    if (!textoPregunta) return

    // Una nueva pregunta corta lo anterior (interrupción del usuario).
    interrumpidoRef.current = false
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()

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

    analizarEmocion(textoPregunta)

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

    if (!inicio) return

    // Interrupción: el usuario habla mientras la asistente habla y la calla.
    callarVoz()

    // Siempre se parte de una sesión limpia. Antes una sesión que no llegaba
    // a emitir onstart dejaba `escuchando` en true y el botón quedaba pegado
    // en la siguiente pregunta.
    limpiarSesion()

    const reconocimiento = new SpeechRecognition()
    reconocimiento.lang = 'es-CO'
    reconocimiento.continuous = true
    reconocimiento.interimResults = true
    reconocimiento.maxAlternatives = 1

    transcripcionRef.current = ''
    enviarAlSoltarRef.current = false

    reconocimiento.onstart = () => {
      escuchandoRef.current = true
      setEscuchando(true)
      setHoraEscucha(hora())
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
      escuchandoRef.current = false
      setEscuchando(false)
      if (seguridadRef.current) {
        clearTimeout(seguridadRef.current)
        seguridadRef.current = null
      }
      if (reconocimientoRef.current === reconocimiento) {
        reconocimientoRef.current = null
      }
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
      escuchandoRef.current = false
      setEscuchando(false)
      reconocimientoRef.current = null
      setError('No se pudo iniciar el micrófono. Inténtalo de nuevo.')
      return
    }

    // Red de seguridad: si el navegador no emite `onend`, se corta solo.
    seguridadRef.current = setTimeout(() => {
      if (reconocimientoRef.current === reconocimiento) {
        try {
          reconocimiento.abort()
        } catch {
          // Si ya no existe, no hay nada que limpiar.
        }
      }
    }, 20000)
  }

  function limpiarSesion() {
    const previo = reconocimientoRef.current
    if (!previo) return
    // Se anulan los callbacks para que la sesión vieja no dispare eventos.
    previo.onstart = null
    previo.onresult = null
    previo.onerror = null
    previo.onend = null
    try {
      previo.abort()
    } catch {
      // Sesión ya cerrada.
    }
    reconocimientoRef.current = null
    escuchandoRef.current = false
    setEscuchando(false)
    if (seguridadRef.current) {
      clearTimeout(seguridadRef.current)
      seguridadRef.current = null
    }
  }

  function soltarDictado() {
    if (!escuchandoRef.current && !reconocimientoRef.current) return
    enviarAlSoltarRef.current = true
    const sesion = reconocimientoRef.current
    if (!sesion) {
      enviarAlSoltarRef.current = false
      return
    }
    try {
      sesion.stop()
    } catch {
      try {
        sesion.abort()
      } catch {
        // Sesión ya cerrada.
      }
    }
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
          <div className="doc-card">
            <div className="doc-head">
              <span className="doc-icon">📄</span>
              <div>
                <strong>Documento</strong>
                <p>Carga un PDF, DOCX o TXT y pregúntale.</p>
              </div>
            </div>

            <input
              ref={archivoRef}
              type="file"
              accept=".pdf,.docx,.txt,.csv,.md"
              onChange={(event) => subirDocumento(event.target.files?.[0])}
              hidden
            />

            {documento?.cargado ? (
              <div className="doc-ok">
                <span className="doc-ok-name">✓ {documento.nombre}</span>
                <span className="doc-ok-meta">
                  {documento.caracteres?.toLocaleString('es-CO')} caracteres
                </span>
              </div>
            ) : (
              <button
                type="button"
                className="primary-button doc-button"
                onClick={() => archivoRef.current?.click()}
                disabled={subiendoDoc}
              >
                {subiendoDoc ? 'Indexando…' : 'Cargar documento'}
              </button>
            )}
          </div>

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

              {escuchando && (
                <div className="message usuario en-vivo">
                  <span className="message-label">
                    Tú · transcribiendo
                    <span className="message-time">{horaEscucha}</span>
                  </span>
                  <p className="transcripcion-viva">
                    {pregunta || 'Escuchando…'}
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
                disabled={!inicio}
                aria-label="Mantén pulsado para hablar"
                title="Mantén pulsado para hablar (corta a la asistente)"
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
                disabled={!inicio}
                aria-label="Tu mensaje"
              />
              <button
                className="send-button"
                type="submit"
                disabled={!pregunta.trim() || !inicio}
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

          <section className="summary-section">
            <div className="section-heading">
              <span className="step-number">04</span>
              <div>
                <h2>Sentimiento de la conversación</h2>
                <p>Cómo te sientes mientras hablamos.</p>
              </div>
            </div>

            {!analisis ? (
              <div className="empty-state compact">
                <span className="spinner" />
                <strong>Esperando tu primer mensaje</strong>
              </div>
            ) : (
              <>
                <div className="analysis-card">
                  <div className="analysis-top">
                    <span className="analysis-emoji">
                      {EMOJI[analisis.emocion] || '😐'}
                    </span>
                    <div>
                      <strong className="analysis-emotion">
                        {analisis.emocion}
                      </strong>
                      <span className={`analysis-mood ${analisis.sentimiento}`}>
                        {analisis.sentimiento}
                      </span>
                    </div>
                  </div>

                  <div className="analysis-gauge">
                    <div
                      className={`analysis-gauge-fill ${analisis.sentimiento}`}
                      style={{
                        width: `${Math.round(
                          (analisis.intensidad || 0) * 100,
                        )}%`,
                      }}
                    />
                  </div>

                  <p className="analysis-detail">
                    {analisis.explicacion || 'Sin observaciones.'}
                  </p>
                </div>

                {emociones.length > 0 && (
                  <ul className="emotion-timeline">
                    {emociones
                      .slice()
                      .reverse()
                      .map((item, index) => (
                        <li key={`${index}-${item.hora}`}>
                          <span className="timeline-emoji">
                            {EMOJI[item.emocion] || '😐'}
                          </span>
                          <span className="timeline-text">{item.texto}</span>
                          <span className="timeline-time">{item.hora}</span>
                        </li>
                      ))}
                  </ul>
                )}
              </>
            )}
          </section>

          <section className="summary-section">
            <div className="section-heading">
              <span className="step-number">05</span>
              <div>
                <h2>Transcripción diarizada</h2>
                <p>Hablante y marca de tiempo de cada turno.</p>
              </div>
            </div>

            {mensajes.filter((m) => m.texto).length === 0 ? (
              <div className="empty-state compact">
                <strong>Aún no hay turnos</strong>
              </div>
            ) : (
              <div className="diarized-wrap">
                <div className="diarized-head">
                  <span>Hablante</span>
                  <span>Hora</span>
                </div>
                <ul className="diarized-list">
                  {mensajes
                    .filter((m) => m.texto)
                    .slice(-8)
                    .map((m, index) => (
                      <li key={`d-${index}-${m.hora}`}>
                        <span className={`speaker-tag ${m.rol}`}>
                          {m.rol === 'usuario' ? 'Tú' : 'Asistente'}
                        </span>
                        <span className="diarized-time">{m.hora}</span>
                        <p className="diarized-text">
                          {m.texto.slice(0, 110)}
                          {m.texto.length > 110 ? '…' : ''}
                        </p>
                      </li>
                    ))}
                </ul>
                {escuchando && (
                  <div className="diarized-live">
                    <span className="rec-dot" /> En vivo · {horaEscucha}
                  </div>
                )}
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
        <span>Asistente de salud por voz</span>
      </footer>
    </main>
  )
}

export default App
