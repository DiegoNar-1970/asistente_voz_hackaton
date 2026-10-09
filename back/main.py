import json
import os
import re

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not API_KEY:
    raise RuntimeError("Falta GEMINI_API_KEY en el archivo .env")

cliente = genai.Client(api_key=API_KEY)

DATASET_URL = os.getenv(
    "DATASET_URL",
    "https://www.datos.gov.co/resource/s2ru-bqt6.json",
)
APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")

app = FastAPI(title="Agente Vocal Cognitivo - IPS Colombia")

origenes = os.getenv("CORS_ORIGINS", "*")
allow_origins = (
    ["*"] if origenes == "*"
    else [o.strip() for o in origenes.split(",") if o.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

ESQUEMA = """
Conjunto de datos: "Relación de IPS públicas y privadas según el nivel de atención
y capacidad instalada" (Ministerio de Salud, datos.gov.co). 41.427 registros.
Cada fila es una capacidad instalada de una sede de una IPS.

Campos (nombre SoQL | descripción):
- departamento (texto): "Antioquia", "Bogotá D.C", "Valle del cauca"...
- municipio (texto): "MEDELLÍN", "BOGOTÁ", "CALI"...
- nombre_prestador (texto): nombre de la IPS
- nit_ips (num), c_digo_prestador (num), c_digo_sede (num)
- naturaleza (texto): "Privada" | "Pública" | "Mixta"
- num_nivel_atencion (texto): "1" | "2" | "3" (solo públicas, puede ser nulo)
- nom_sede_ips (texto): nombre de la sede
- gerente (texto)
- direcci_n (texto), email (texto), tel_fono (texto)
- nom_grupo_capacidad (texto): CONSULTORIOS | SALAS | CAMAS | AMBULANCIAS |
  CAMILLAS | UNIDAD MOVIL | SILLAS
- nom_descripcion_capacidad (texto): detalle ("Urgencias", "Consulta Externa",
  "Partos", "UCI Adultos"...)
- num_cantidad_capacidad_instalada (num): cantidad de esa capacidad
- fecha_corte (texto), fuente (texto)
"""

SOQL_AYUDA = """
Operadores SoQL disponibles (Socrata):
- $select  : columnas y agregados, p.ej. "departamento, count(*) as total"
- $where   : filtro, p.ej. "naturaleza='Pública' AND departamento='Antioquia'"
- $group   : agrupación, p.ej. "departamento"
- $order   : orden, p.ej. "total desc"
- $limit   : máximo de filas (entero en texto)
- $offset  : desplazamiento (entero en texto)
- $q       : búsqueda de texto libre (p.ej. nombre de una IPS)

Ejemplos:
- "¿cuántas IPS hay?" -> {"$select":"count(*) as total"}
- "IPS por departamento" -> {"$select":"departamento, count(*) as total",
   "$group":"departamento","$order":"total desc","$limit":"10"}
- "IPS públicas en Antioquia" -> {"$select":"nombre_prestador, municipio",
   "$where":"naturaleza='Pública' AND departamento='Antioquia'","$limit":"20"}
- "camas en Bogotá" -> {"$select":"nombre_prestador, sum(num_cantidad_capacidad_instalada) as camas",
   "$where":"nom_grupo_capacidad='CAMAS' AND municipio='BOGOTÁ'","$group":"nombre_prestador",
   "$order":"camas desc","$limit":"10"}
"""

CAMPOS_PERMITIDOS = {
    "$select", "$where", "$group", "$order", "$limit", "$offset", "$q", "$having",
}


class PreguntaRequest(BaseModel):
    pregunta: str


class TextoRequest(BaseModel):
    texto: str


def limpiar_json(texto: str) -> str:
    return re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        texto.strip(),
        flags=re.IGNORECASE,
    ).strip()


def consultar_gemini(prompt: str) -> str:
    try:
        respuesta = cliente.models.generate_content(
            model=MODELO,
            contents=prompt,
        )
        if not respuesta.text:
            raise HTTPException(
                status_code=502,
                detail="Gemini no devolvió texto.",
            )
        return respuesta.text.strip()
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo consultar Gemini ({type(error).__name__}).",
        ) from error


def consultar_dataset(params: dict) -> list:
    limpios = {
        clave: valor
        for clave, valor in params.items()
        if clave in CAMPOS_PERMITIDOS and valor not in (None, "")
    }
    cabeceras = {"Accept": "application/json"}
    if APP_TOKEN:
        cabeceras["X-App-Token"] = APP_TOKEN

    try:
        respuesta = requests.get(
            DATASET_URL,
            params=limpios,
            headers=cabeceras,
            timeout=30,
        )
    except requests.RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="No se pudo consultar datos.gov.co.",
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"datos.gov.co respondió {respuesta.status_code}.",
        )

    return respuesta.json()


BRIEF_CACHE = {"data": None}


@app.get("/api/health")
def health():
    return {"status": "ok", "modelo": MODELO, "fuente": DATASET_URL}


@app.get("/api/brief")
def brief():
    if BRIEF_CACHE["data"] is not None:
        return BRIEF_CACHE["data"]

    total = consultar_dataset({"$select": "count(*) as total"})
    por_departamento = consultar_dataset({
        "$select": "departamento, count(*) as total",
        "$group": "departamento",
        "$order": "total desc",
        "$limit": "10",
    })
    por_naturaleza = consultar_dataset({
        "$select": "naturaleza, count(*) as total",
        "$group": "naturaleza",
        "$order": "total desc",
    })
    por_capacidad = consultar_dataset({
        "$select": (
            "nom_grupo_capacidad, "
            "sum(num_cantidad_capacidad_instalada) as cantidad"
        ),
        "$group": "nom_grupo_capacidad",
        "$order": "cantidad desc",
    })

    datos = {
        "total": total,
        "por_departamento": por_departamento,
        "por_naturaleza": por_naturaleza,
        "por_capacidad": por_capacidad,
    }

    prompt = f"""
Eres el presentador de un agente de voz sobre datos de salud de Colombia.
A partir de los agregados reales del conjunto de datos, escribe:
- "introduccion": 2 o 3 frases en español explicando de qué trata la fuente.
- "preguntas_sugeridas": entre 4 y 5 preguntas variadas y útiles que se puedan
  responder con estos datos (agregados, comparaciones, detalle de una IPS).

No inventes cifras: usa solo los números de los agregados.

Devuelve únicamente JSON válido:
{{"introduccion": "...", "preguntas_sugeridas": ["...", "..."]}}

AGREGADOS:
{json.dumps(datos, ensure_ascii=False)}
"""

    resultado = consultar_gemini(prompt)

    try:
        limpio = limpiar_json(resultado)
        contenido = json.loads(limpio)
        introduccion = contenido.get("introduccion", "")
        preguntas = [
            p for p in contenido.get("preguntas_sugeridas", [])
            if isinstance(p, str)
        ][:5]
    except (json.JSONDecodeError, ValueError):
        introduccion = resultado
        preguntas = []

    respuesta = {
        "fuente": "datos.gov.co · Relación de IPS (s2ru-bqt6)",
        "total_registros": datos["total"],
        "introduccion": introduccion,
        "preguntas_sugeridas": preguntas,
        "agregados": datos,
    }
    BRIEF_CACHE["data"] = respuesta
    return respuesta


@app.post("/api/chat")
def chat(datos: PreguntaRequest):
    pregunta = datos.pregunta.strip()
    if not pregunta:
        raise HTTPException(status_code=400, detail="Escribe una pregunta.")

    prompt_plan = f"""
Eres un traductor de preguntas a consultas SoQL sobre este conjunto de datos.
{ESQUEMA}
{SOQL_AYUDA}

Decide una acción:
- "consultar": si hace falta leer datos para responder. Devuelve "params".
- "fuera_de_alcance": si la pregunta no trata sobre estas IPS/datos de salud.

Devuelve únicamente JSON válido:
{{"accion": "consultar", "params": {{"$select": "...", "$where": "..."}},
  "razon": "..."}}
o
{{"accion": "fuera_de_alcance", "razon": "..."}}

PREGUNTA: {pregunta}
"""

    plan_texto = consultar_gemini(prompt_plan)

    try:
        plan = json.loads(limpiar_json(plan_texto))
    except (json.JSONDecodeError, ValueError):
        plan = {"accion": "fuera_de_alcance", "razon": "No se pudo interpretar."}

    if plan.get("accion") != "consultar" or not plan.get("params"):
        return {
            "pregunta": pregunta,
            "respuesta": (
                "Solo puedo responder sobre la Relación de IPS públicas y "
                "privadas de Colombia y su capacidad instalada. Esa pregunta "
                "queda fuera de la fuente de datos."
            ),
            "consulta": None,
            "filas": 0,
            "datos": [],
        }

    params = dict(plan["params"])
    params.setdefault("$limit", "25")
    filas = consultar_dataset(params)

    prompt_respuesta = f"""
Eres un asistente experto en salud en Colombia. Responde en español, breve y claro.
Usa EXCLUSIVAMENTE los datos devueltos por la consulta. No inventes cifras.
Si vienen 0 filas, dilo con naturalidad.
Puedes redondear o sumar cuando tenga sentido.

PREGUNTA: {pregunta}
CONSULTA SOQL: {json.dumps(params, ensure_ascii=False)}
RESULTADOS ({len(filas)} filas):
{json.dumps(filas[:30], ensure_ascii=False)}
"""

    respuesta = consultar_gemini(prompt_respuesta)

    return {
        "pregunta": pregunta,
        "respuesta": respuesta,
        "consulta": params,
        "filas": len(filas),
        "datos": filas[:10],
    }


@app.post("/api/emotion")
def emotion(datos: TextoRequest):
    texto = datos.texto.strip()
    if not texto:
        return {"sentimiento": "neutral", "emocion": "neutral", "intensidad": 0}

    prompt = f"""
Clasifica el tono emocional del siguiente texto de una conversación en español.
Devuelve únicamente JSON válido:
{{"sentimiento": "positivo|neutral|negativo",
  "emocion": "curiosidad|satisfaccion|alegria|confusion|frustracion|neutral",
  "intensidad": 0.0}}

TEXTO: {texto}
"""
    resultado = consultar_gemini(prompt)
    try:
        return json.loads(limpiar_json(resultado))
    except (json.JSONDecodeError, ValueError):
        return {"sentimiento": "neutral", "emocion": "neutral", "intensidad": 0.3}
