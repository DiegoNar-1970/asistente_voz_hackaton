# Vocal Cognitivo — Agente de voz sobre datos abiertos de salud

Agente conversacional por voz que indexa como **única fuente de verdad** la
«Relación de IPS públicas y privadas según el nivel de atención y capacidad
instalada» publicada en **datos.gov.co** (dataset `s2ru-bqt6`, 41.427 registros),
explica de qué trata, sugiere preguntas y responde preguntas por voz con datos
reales obtenidos en vivo desde la API.

## Stack
- **Backend:** Python 3.13, FastAPI, Uvicorn, `google-genai` (Gemini), `requests`.
- **Modelo:** Gemini (`gemini-3.5-flash-lite`) para traducir preguntas a SoQL y redactar respuestas.
- **Frontend:** React 19 + Vite (JavaScript/JSX).
- **Voz:** Web Speech API del navegador (STT `es-CO` para dictar y TTS `es-CO` para leer respuestas).
- **Fuente de datos:** API SODA de datos.gov.co (`https://www.datos.gov.co/resource/s2ru-bqt6.json`), soporta SoQL (`$select`, `$where`, `$group`, `$order`, `$limit`).

## Arquitectura
1. `GET /api/brief`: consulta agregados reales (total, por departamento, por
   naturaleza, por capacidad) y pide a Gemini la introducción y 4–5 preguntas.
2. `POST /api/chat`: Gemini traduce la pregunta a una consulta SoQL; el backend
   la ejecuta contra datos.gov.co; Gemini redacta la respuesta usando **solo**
   las filas devueltas. Si la pregunta no es sobre la fuente, lo dice.
3. `POST /api/emotion`: clasifica el tono del texto (sentimiento/emoción) para el panel.
4. El frontend muestra la conversación, la transcripción por turnos
   (hablante + marca de tiempo) y el panel de sentimiento/emociones.

El LLM **nunca recibe las 41.427 filas**: recibe el esquema y opera por
consultas agregadas, lo que mantiene baja la latencia y el costo.

## Ejecución local
Backend:
```
cd back
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```
Frontend:
```
cd frontend
npm install
npm run dev
```
El backend necesita un archivo `back/.env` con `GEMINI_API_KEY` (no versionar).
Variables opcionales: `GEMINI_MODEL`, `SOCRATA_APP_TOKEN`, `CORS_ORIGINS`, `DATASET_URL`.
El frontend usa `VITE_API_URL` (por defecto `http://localhost:8000`).

## Despliegue público
- **Backend** (Render/HF Spaces): variable de entorno `GEMINI_API_KEY` y
  `CORS_ORIGINS` = dominio del frontend. Arranque:
  `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- **Frontend** (Vercel): variable `VITE_API_URL` = URL pública del backend.

## Uso de IA (declaración, regla M04)
Este proyecto se construyó con asistencia de **OpenCode** (agente de IA) para
redactar y refactorizar código. La aplicación en runtime usa **Google Gemini**
para traducir preguntas a consultas y generar respuestas en lenguaje natural.

## Repositorio
Código y decisiones técnicas en este repositorio (público).
