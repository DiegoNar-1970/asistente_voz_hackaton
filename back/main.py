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

# La API de datos.gov.co devuelve 1000 filas por defecto: no pedimos más.
MAX_FILAS = 1000

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
    historial: list[dict] = []


class TextoRequest(BaseModel):
    texto: str
    rol: str = "usuario"


def limpiar_json(texto: str) -> str:
    return re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        texto.strip(),
        flags=re.IGNORECASE,
    ).strip()


def limpiar_markdown(texto: str) -> str:
    """Deja texto natural para mostrar y leer en voz alta (sin markdown)."""
    texto = texto.replace("**", "").replace("__", "").replace("`", "")
    texto = re.sub(r"^\s*[*•\-]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^#{1,6}\s*", "", texto, flags=re.MULTILINE)
    texto = texto.replace("*", "").replace("#", "")
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


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

    if "$limit" in limpios:
        try:
            limpios["$limit"] = str(min(int(limpios["$limit"]), MAX_FILAS))
        except (TypeError, ValueError):
            limpios["$limit"] = str(MAX_FILAS)

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


@app.get("/api/greeting")
def greeting():
    return {
        "mensaje": (
            "Hola, ¿cómo estás? Soy la asistente virtual de la IPS. "
            "Dime en qué te puedo ayudar y en qué ciudad estás."
        ),
        "sugerencias": [
            "¿Cuál es la clínica más cercana donde estoy?",
            "Estoy en Medellín y necesito urgencias.",
            "¿Dónde puedo encontrar atención de partos en Bogotá?",
        ],
    }


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
Eres la asistente virtual de una red de salud en Colombia. Escribe contenido
cercano y útil para una persona que busca atención médica, sin tecnicismos y sin
mencionar "datos", "registros", "API", "filas" ni cifras técnicas.
- "introduccion": 2 frases que expliquen para qué sirve esta asistente
  (ayudarlo a encontrar dónde atenderte según su ciudad y su necesidad).
- "preguntas_sugeridas": entre 4 y 5 preguntas que haría un paciente y que
  orienten a encontrar ayuda. Ejemplos: "¿Cuál es la clínica más cercana según
  mi ciudad?", "¿Dónde hay urgencias en Medellín?", "¿Dónde puedo tener un parto
  en Bogotá?".

Devuelve únicamente JSON válido:
{{"introduccion": "...", "preguntas_sugeridas": ["...", "..."]}}

AGREGADOS (referencia interna, no los menciones):
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

    historial = datos.historial[-8:] if datos.historial else []
    historial_texto = "\n".join(
        f"{'Usuario' if m.get('rol') == 'usuario' else 'Asistente'}: "
        f"{m.get('texto', '')}"
        for m in historial
    )

    prompt_plan = f"""
Eres la asistente virtual de una red de IPS (Instituciones Prestadoras de
Servicios de Salud) en Colombia. Ayudas a un usuario con su necesidad de salud
usando exclusivamente la Relación de IPS de datos.gov.co.
{ESQUEMA}
{SOQL_AYUDA}

CONVERSACIÓN PREVIA:
{historial_texto or "(sin turnos previos)"}

PREGUNTA ACTUAL DEL USUARIO: {pregunta}

Decide una acción y devuelve SOLO JSON válido:
- "consultar": necesitas leer datos. Incluye "params".
  Si el usuario mencionó ciudad/municipio, filtra por municipio o departamento.
  Si menciona un servicio, filtra por nom_grupo_capacidad o
  nom_descripcion_capacidad (ej. "Urgencias", "Consulta Externa", "Partos").
  {{"accion":"consultar","params":{{"$select":"...","$where":"...","$limit":"20"}}}}
- "pedir_datos": aún no sabes la ciudad o la necesidad. Incluye "respuesta"
  con una pregunta breve y amable.
  {{"accion":"pedir_datos","respuesta":"..."}}
- "fuera_de_alcance": no trata sobre salud/IPS.
  {{"accion":"fuera_de_alcance","respuesta":"..."}}
"""

    try:
        plan = json.loads(limpiar_json(consultar_gemini(prompt_plan)))
    except (json.JSONDecodeError, ValueError):
        plan = {"accion": "pedir_datos", "respuesta": (
            "¿Me cuentas en qué ciudad estás y qué necesitas de salud?"
        )}

    accion = plan.get("accion")

    if accion != "consultar" or not plan.get("params"):
        respuesta = plan.get("respuesta") or (
            "Cuéntame en qué ciudad estás y qué necesitas de salud para poder "
            "ayudarte."
        )
        return {
            "pregunta": pregunta,
            "respuesta": limpiar_markdown(respuesta),
            "accion": accion or "pedir_datos",
            "consulta": None,
            "filas": 0,
            "datos": [],
        }

    params = dict(plan["params"])
    params.setdefault("$limit", "10")
    filas = consultar_dataset(params)

    prompt_respuesta = f"""
Eres la asistente virtual de una red de IPS en Colombia. Hablas en español,
cercana y humana, como si estuvieras ayudando a una persona por voz.
Ayúdala con su necesidad de salud usando EXCLUSIVAMENTE los datos de la consulta.
No das diagnósticos médicos: orientas sobre instituciones y su capacidad.
IMPORTANTE: no uses markdown ni símbolos (nada de asteriscos, almohadillas,
barras, viñetas con símbolos). Escribe frases naturales.
- Responde en 2 a 4 frases.
- Si mencionas opciones, sepáralas con comas o punto y coma, no con viñetas.
- Si no hay resultados, dilo con naturalidad y propón ampliar la búsqueda.

CONVERSACIÓN PREVIA:
{historial_texto or "(sin turnos previos)"}

PREGUNTA DEL USUARIO: {pregunta}
RESULTADOS ({len(filas)} filas):
{json.dumps(filas[:20], ensure_ascii=False)}
"""

    respuesta = limpiar_markdown(consultar_gemini(prompt_respuesta))

    return {
        "pregunta": pregunta,
        "respuesta": respuesta,
        "accion": "consultar",
        "consulta": params,
        "filas": len(filas),
        "datos": filas[:10],
    }


@app.post("/api/emotion")
def emotion(datos: TextoRequest):
    texto = datos.texto.strip()
    if not texto:
        return {
            "sentimiento": "neutral",
            "emocion": "neutral",
            "intensidad": 0.0,
            "explicacion": "",
        }

    prompt = f"""
Eres un analista experto en sentimiento y emociones. Analiza el siguiente
turno de una conversación en español ("{datos.rol}") entre un usuario y la
asistente virtual de una IPS (búsqueda de ayuda de salud).
Devuelve SOLO JSON válido:
{{
  "sentimiento": "positivo|neutral|negativo",
  "emocion": "alegria|satisfaccion|serenidad|curiosidad|confusion|preocupacion|ansiedad|frustracion|enojo|tristeza|neutral",
  "intensidad": 0.0,
  "explicacion": "frase muy corta en español que justifique"
}}
La intensidad va de 0.0 (nula) a 1.0 (muy intensa).

TEXTO: {texto}
"""
    resultado = consultar_gemini(prompt)

    try:
        analisis = json.loads(limpiar_json(resultado))
        analisis.setdefault("sentimiento", "neutral")
        analisis.setdefault("emocion", "neutral")
        analisis.setdefault("intensidad", 0.3)
        analisis.setdefault("explicacion", "")
        return analisis
    except (json.JSONDecodeError, ValueError):
        return {
            "sentimiento": "neutral",
            "emocion": "neutral",
            "intensidad": 0.3,
            "explicacion": "",
        }
