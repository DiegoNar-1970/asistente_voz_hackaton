# Vocal Cognitivo — Agente de voz sobre datos abiertos de salud

Agente conversacional **por voz** que usa como **única fuente de verdad** la
«Relación de IPS públicas y privadas según el nivel de atención y capacidad
instalada» publicada en **datos.gov.co** (dataset `s2ru-bqt6`, 41.427
registros). Explica de qué trata, sugiere preguntas, escucha al usuario y
responde hablando con datos reales consultados **en vivo** a la API.

## Stack

| Capa | Tecnología |
|---|---|
| **Backend** | Python 3.14 · FastAPI · Uvicorn · `httpx` (keep-alive) · `python-dotenv` |
| **Modelo** | Google Gemini `gemini-3.5-flash-lite` (`temperature=0.3`) |
| **Documentos** | `pypdf` (PDF) · `python-docx` (Word) · txt/csv |
| **Frontend** | React 19 + Vite (JavaScript/JSX) · CSS a mano |
| **Voz** | Web Speech API del navegador: STT `es-CO` (dictado) y TTS `es-CO` (respuesta) |
| **Fuente de datos** | API SODA de datos.gov.co · `https://www.datos.gov.co/resource/s2ru-bqt6.json` con SoQL (`$select`, `$where`, `$group`, `$order`, `$limit`) |
| **Despliegue** | Backend en **Render** · Frontend en **Vercel** |

## Arquitectura

```
Navegador (Vercel)  ──fetch/stream──►  FastAPI (Render)  ──SoQL──►  datos.gov.co
  · STT es-CO (micrófono)               · intención + memoria        41.427 filas
  · TTS es-CO (voz)                     · Gemini redacta             (filtradas
  · chat, panel de emoción,             · respaldo local               en el
    transcripción diarizada,            · caché + whitelist            servidor)
    subida de documentos
```

**Decisión central:** el LLM **nunca recibe las 41.427 filas**. Recibe el
esquema en texto y, como mucho, **30 filas ya filtradas** por ciudad y
servicio. De ahí salen la baja latencia (~1–2 s), el costo bajo y que no
invente datos.

### Endpoints

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/health` | Estado, modelo y fuente (health check de Render). |
| GET | `/api/greeting` | Saludo + 3 sugerencias para arrancar. |
| GET | `/api/brief` | Briefing del dataset con agregados reales + 4–5 preguntas sugeridas. |
| GET | `/api/documento` | Estado del documento cargado. |
| POST | `/api/documento` | Sube PDF/DOCX/TXT/CSV (≤5 MB), lo extrae, lo resume y sugiere 4 preguntas. |
| DELETE | `/api/documento` | Elimina el documento. |
| POST | `/api/chat` | **Núcleo**: recibe `{pregunta, historial}` y responde en streaming. |
| POST | `/api/emotion` | Clasifica emoción/sentimiento para el panel. |

### Flujo de `POST /api/chat`

1. **Saludos/gracias** → respuesta local, sin red ni IA.
2. **Pregunta sobre el documento cargado** → ruta del documento.
3. **Memoria** → ciudad y servicio mencionados antes en el historial.
4. **Emergencia** → "llama al 123" + sede real de la API en ~0.02 s, **sin IA**.
5. **Varias ciudades** → una consulta SoQL por ciudad, resultados agrupados.
6. **Conteo puro** ("¿cuántas camas?") → `count(*)` agregado en ~0.3 s, **sin IA**.
7. **Consulta de filas** → `prompt_redaccion` → Gemini redacta con las filas.
8. **Sin ciudad** → `prompt_plan` devuelve JSON (`consultar` / `pedir_datos` / `fuera_de_alcance`).

Si Gemini tarda más de **5 s** o falla, se entrega un **respaldo local**
armado con las mismas filas reales: la demo nunca se congela.

### Características

- **Voz push-to-talk** con **interrupción**: si el usuario habla mientras la
  asistente habla, ésta se calla al instante.
- **Respuesta en streaming** (se pinta y se habla por trozos, sin esperar).
- **Transcripción por turnos** con hablante y marca de tiempo + indicador "En vivo".
- **Panel de sentimiento/emociones en vivo** (corre en segundo plano).
- **Memoria de conversación** (ciudad y servicio, con reglas para no heredar mal).
- **Documentos**: el jurado sube un archivo en vivo y se le puede preguntar.
- **Multi-ciudad** en una misma pregunta.
- **Cierres de continuidad** variados (pregunta siguiente o consejo corto),
  nunca la fórmula repetida de "¿hay algo más en que te puedo ayudar?".
- **Whitelist de parámetros SoQL**, tope de filas (1.000) y caché en memoria.

## Ejecución local

Backend:
```powershell
cd back
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload     # http://127.0.0.1:8000  ·  /docs
```
Frontend:
```powershell
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

- El backend necesita `back/.env` con `GEMINI_API_KEY` (**no versionar**).
- Variables opcionales: `GEMINI_MODEL`, `SOCRATA_APP_TOKEN`, `CORS_ORIGINS`, `DATASET_URL`.
- El frontend usa `VITE_API_URL` (por defecto `http://localhost:8000`).

Comprobación: `GET /api/health` →
`{"status":"ok","modelo":"gemini-3.5-flash-lite","fuente":"...s2ru-bqt6.json"}`

## Despliegue público

**Backend — Render** (Blueprint con `render.yaml`):
- Build: `pip install -r back/requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT --app-dir back`
- Health check: `/api/health`
- Env vars: `GEMINI_API_KEY` (obligatoria) y `CORS_ORIGINS` (por defecto `*`).

La raíz incluye un `requirements.txt` y un `main.py` puente para que el build
y el arranque funcionen también sin `--app-dir`.

**Frontend — Vercel:**
- Root Directory: `frontend`
- Env: `VITE_API_URL` = URL pública del backend.

> ⚠️ Si `VITE_API_URL` no está definida, el sitio le pega a
> `http://localhost:8000` del visitante y **solo funcionará en tu máquina**.

## Estructura del repositorio

```
back/main.py            1.530 líneas · todo el backend (endpoints, SoQL, prompts, memoria)
back/requirements.txt   dependencias
frontend/src/App.jsx      858 líneas · interfaz y toda la lógica de voz
frontend/src/App.css    1.606 líneas · estilos
render.yaml              blueprint de Render
main.py / requirements.txt (raíz) · puentes para el arranque en Render
```

## Uso de IA (declaración, regla M04)

Este proyecto se construyó con asistencia de **OpenCode** (agente de IA) para
redactar y refactorizar código. La aplicación en runtime usa **Google Gemini**
para redactar respuestas y clasificar emociones; las consultas a los datos se
construyen con reglas y SoQL, no con el modelo.

## Repositorio

Código y decisiones técnicas en este repositorio (público).
