Contexto técnico y estado del proyecto
Agente Vocal Cognitivo — transferencia de contexto para una IA local
Documento de transferencia basado en lo compartido en la conversación. Es una síntesis técnica, no una copia literal de cada mensaje ni una inspección directa del disco del usuario.
1. Instrucciones para la IA que recibe este contexto
•	Responder en español, de forma directa y paso a paso; el usuario prefiere que no se divague.
•	No afirmar que un cambio funciona hasta que el usuario lo pruebe y lo confirme.
•	Antes de editar, inspeccionar el código real. Preservar el diseño y las funciones que ya funcionan.
•	Indicar archivo y ubicación exacta de cada cambio. No inventar rutas, dependencias, endpoints ni resultados.
•	Desarrollo local primero. El usuario quiere publicar en internet más adelante y tiene presupuesto cero; no asumir que APIs, modelos o alojamiento son gratuitos sin verificar límites.
•	Nunca pedir ni publicar claves API. GEMINI_API_KEY está en .env; no compartirla ni versionarla.
•	El usuario expresó que las últimas indicaciones fueron incorrectas. Revisar JSX, formularios y CSS antes de proponer más cambios.
2. Objetivo del proyecto
Nombre: Agente Vocal Cognitivo; la interfaz muestra “Vocal Cognitivo”. Aplicación web para cargar documentos, extraer texto, dividirlo en fragmentos, generar resumen y preguntas sugeridas con Gemini, y responder preguntas usando fragmentos relevantes. Se está incorporando dictado por voz desde el navegador y lectura en voz alta de respuestas.
A futuro se contempla transcripción con marcas de tiempo, atribución de turnos y etiquetas aproximadas de emoción. No considerar esas funciones implementadas. Web Speech API no ofrece por sí sola diarización fiable de múltiples hablantes ni detección acústica fiable de emociones.
3. Especificaciones del computador
•	Sistema operativo: Windows.
•	CPU: Intel Core i5-12450H.
•	RAM: 16 GB.
•	GPU: Intel UHD integrada.
•	Almacenamiento: 477 GB total; aproximadamente 205 GB libres según lo informado.
•	Estrategia: desarrollar y probar localmente antes de desplegar.
4. Rutas y estructura conocida
Backend:
C:\Users\Diego\Desktop\agente-vocal-cognitivo\back
Frontend:
C:\Users\Diego\Desktop\agente-vocal-cognitivo\front\frontend
Árbol conocido del frontend:
agente-vocal-cognitivo/
├── back/
│   ├── .venv/
│   ├── main.py
│   ├── test_gemini.py
│   └── .env  (secreto: GEMINI_API_KEY; no versionar)
└── front/
    └── frontend/
        ├── node_modules/
        ├── public/
        ├── src/
        │   ├── assets/
        │   ├── App.css
        │   ├── index.css
        │   └── main.jsx
        ├── package.json
        └── pnpm-lock.yaml
La estructura del backend es parcial y reconstruida a partir de la conversación. Verificar el árbol real antes de asumir que solo existen esos archivos.
5. Backend: tecnologías y ejecución
•	Python + FastAPI.
•	Uvicorn para servir el backend.
•	python-docx para DOCX; pypdf para PDF.
•	python-dotenv para variables de entorno.
•	google-genai para Gemini.
•	scikit-learn para TF-IDF y similitud coseno.
•	Entorno virtual conocido: back\.venv.
Comandos conocidos desde la carpeta back en PowerShell:
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
•	Backend: http://localhost:8000
•	Documentación FastAPI: http://localhost:8000/docs
•	Health check: GET http://localhost:8000/api/health
•	Frontend Vite: http://localhost:5173
6. Endpoints y comportamiento conocido
GET /api/health
Comprobación de estado del backend.
POST /api/documents
Recibe multipart en el campo “archivo”; límite informado de 10 MB; acepta TXT, PDF y DOCX; extrae texto, lo fragmenta y reemplaza el documento actual en memoria.
POST /api/documents/summary
Envía hasta unos 24.000 caracteres iniciales a Gemini y solicita resumen y 3–5 preguntas sugeridas en JSON. Existe una alternativa si no se interpreta la respuesta JSON.
POST /api/chat
Recibe JSON con “pregunta”; recupera fragmentos por TF-IDF/similitud coseno y pide a Gemini responder usando el contexto, indicando si falta información.
Estado global conocido: documento_actual = {"nombre": None, "fragmentos": []}. El documento está en memoria y puede perderse al reiniciar el servidor; el flujo actual contempla un documento activo.
Fragmentación conocida: aproximadamente 1000 caracteres por fragmento y 150 de solapamiento. La búsqueda usa TF-IDF y similitud coseno y devuelve hasta cinco fragmentos.
El usuario informó que los endpoints funcionaban y que test_gemini.py recibió una respuesta en español.
7. Gemini y secretos
main.py lee GEMINI_API_KEY desde .env. El modelo predeterminado observado era GEMINI_MODEL o, si no existe, “gemini-3.5-flash-lite”. Verificar que ese identificador siga vigente antes de cambiarlo o desplegar; no asumir cuota gratuita permanente.
No subir .env a Git ni pegar su contenido en chats o logs. En despliegue, guardar la clave como secreto. Las cuotas gratuitas y límites pueden cambiar.
8. Frontend: stack, estado y funciones
Vite + React con JavaScript/JSX, no TypeScript según los archivos compartidos. El usuario dijo que la interfaz general funcionaba bien antes del problema actual. Archivos principales: src/App.jsx, src/App.css, src/index.css. main.jsx importa index.css y App.jsx y renderiza App con createRoot.
•	Estados: archivo, documento, resumen, preguntas, pregunta, mensajes, cargandoArchivo, cargandoRespuesta, error, escuchando.
•	Refs: inputRef para input file y recognitionRef para SpeechRecognition.
•	leerRespuesta(response): interpreta JSON y lanza error si response.ok es falso.
•	cargarDocumento(event): POST /api/documents y luego POST /api/documents/summary; actualiza documento, resumen y preguntas.
•	enviarPregunta(texto = pregunta): añade mensaje del usuario, POST /api/chat, añade respuesta y fuentes.
•	manejarArchivo(event): obtiene el primer archivo y actualiza estado archivo.
•	iniciarMicrofono(): usa SpeechRecognition o webkitSpeechRecognition, idioma es-CO; coloca transcripción en pregunta.
•	detenerMicrofono(): detiene recognitionRef.current; no se usa directamente en el JSX compartido.
•	leerEnVozAlta(texto): usa SpeechSynthesisUtterance con idioma es-CO.
9. Problema actual: selector/carga de archivos
Síntoma reportado: al intentar cargar/seleccionar un archivo, el cursor muestra el símbolo de bloqueo/prohibido.
Hallazgos concretos en el App.jsx pegado
•	Después de <form onSubmit={cargarDocumento}> en el sidebar “Tu documento”, se insertaron los botones de micrófono y enviar pregunta, que pertenecen al chat.
•	El botón del micrófono usa disabled={!documento || cargandoRespuesta}; como documento empieza en null, queda deshabilitado al inicio. El botón de enviar también depende de documento y pregunta y empieza deshabilitado. Esto explica el cursor de bloqueo sobre esos botones, pero no demuestra que sea la única causa del problema con el selector.
•	El input file tiene hidden y ref={inputRef}, pero no aparece un botón de selección que invoque inputRef.current.click(). manejarArchivo solo corre cuando el selector ya fue abierto.
•	El botón “Cargar y analizar” se deshabilita si !archivo || cargandoArchivo.
Corrección propuesta anteriormente, todavía no confirmada
1.	Crear abrirSelectorArchivo() que ejecute inputRef.current?.click() si no se está cargando.
2.	Dentro del formulario de carga, mantener el input file oculto y añadir un botón type="button" con onClick={abrirSelectorArchivo}, texto “Seleccionar archivo”.
3.	Eliminar los botones de micrófono y enviar pregunta del formulario de carga.
4.	Dejar micrófono y enviar solo dentro de <form className="chat-form"> al final del componente.
5.	Guardar, recargar http://localhost:5173, pulsar “Seleccionar archivo”, elegir PDF/DOCX/TXT y después “Cargar y analizar”.
6.	Si persiste el cursor de prohibido, inspeccionar App.css por overlays, pointer-events: none, z-index, disabled y estilos que tapen el control.
No afirmar que el problema está resuelto hasta que el usuario lo confirme. Si falla, pedir App.css actual y aclarar sobre qué elemento aparece el cursor bloqueado.
10. Código de referencia para seleccionar archivo
function abrirSelectorArchivo() {
  if (!cargandoArchivo) {
    inputRef.current?.click()
  }
}

// Dentro del formulario de carga:
<input
  ref={inputRef}
  type="file"
  accept=".pdf,.docx,.txt"
  onChange={manejarArchivo}
  hidden
/>

<button
  type="button"
  className="primary-button full-width"
  onClick={abrirSelectorArchivo}
  disabled={cargandoArchivo}
>
  Seleccionar archivo
</button>
11. Diseño actual descrito
•	Header con “Vocal Cognitivo” y estado “Asistente documental”.
•	Hero: “Entiende cualquier documento.”
•	Sidebar “01 Tu documento”: selección, archivo seleccionado, botón de carga y nota de privacidad.
•	Panel “02 Resumen inteligente”: carga, resumen y preguntas sugeridas.
•	Sección “03 Conversa con tu documento”: historial, fuentes/contexto, input y botón de enviar.
•	Mensajes del asistente pueden mostrar botón “Escuchar respuesta”.
•	Banda de errores y footer.
12. Limitaciones y precauciones futuras
•	El reconocimiento de voz puede requerir permisos y depender de servicios externos; no prometer procesamiento completamente local.
•	La lectura en voz alta usa speech synthesis del navegador.
•	Los turnos usuario/asistente no equivalen a diarización real de múltiples hablantes.
•	Las etiquetas emocionales deben describirse como estimaciones inciertas; clasificación textual no equivale a detección acústica ni diagnóstico.
•	Antes de desplegar: revisar CORS, secretos, límites de archivos, privacidad, autenticación, persistencia y cuotas de Gemini.
13. Datos pendientes de verificar
•	App.css completo y actual.
•	main.py completo y actual.
•	package.json y versiones de dependencias.
•	Si ya se añadió y probó “Seleccionar archivo”.
•	Sobre qué elemento aparece el cursor de prohibido.
•	Errores de consola del navegador y terminales de Vite/FastAPI.
•	Tamaño y formato del archivo que intenta subir.
14. Estado resumido para continuar
Backend: el usuario reportó que funciona. Frontend: la interfaz general funcionaba antes de los últimos cambios. Voz: funciones añadidas, funcionamiento completo no confirmado. Problema activo: selector/carga de archivos con cursor de bloqueo; el JSX compartido contiene botones de chat dentro del formulario de carga y un input file oculto sin disparador visible explícito. Prioridad: corregir y verificar selección de archivo sin romper el diseño.
