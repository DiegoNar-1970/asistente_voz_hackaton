import io
import json
import os
import queue
import random
import re
import threading
import unicodedata

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
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

# El límite de filas que usamos en cualquier consulta.
MAX_FILAS = 1000
LIMITE_RESPUESTA = 6

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
Datos: "Relación de IPS públicas y privadas según nivel de atención y capacidad
instalada" (datos.gov.co). Cada fila es una capacidad instalada de una sede.
Campos:
- departamento (texto): "Antioquia", "Bogotá D.C", "Valle del cauca"...
- municipio (texto): "MEDELLÍN", "BOGOTÁ", "CALI"...
- nombre_prestador (texto), nom_sede_ips (texto)
- naturaleza: "Privada" | "Pública" | "Mixta"
- direcci_n (texto), tel_fono (texto)
- nom_grupo_capacidad: CONSULTORIOS | SALAS | CAMAS | AMBULANCIAS | CAMILLAS
- nom_descripcion_capacidad: "Urgencias", "Consulta Externa", "Partos"...
- num_cantidad_capacidad_instalada (num)
"""

SOQL_AYUDA = """
Operadores SoQL (Socrata):
- $select : columnas/agregados ("count(*) as total")
- $where  : filtro ("municipio='MEDELLÍN' AND nom_grupo_capacidad='CAMAS'")
- $group  : agrupación, $order : orden, $limit : máximo de filas
- $q      : búsqueda de texto libre
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


# ------------------------------------------------------------ documento cargado
# El documento no reemplaza la fuente de datos: se agrega como contenido sobre
# el que también se puede preguntar (reto, paso P2 y P3).
DOCUMENTO: dict = {}
TOPE_DOCUMENTO = 9000


def _leer_documento(nombre: str, datos: bytes) -> str:
    """Extrae el texto de PDF, DOCX, TXT o CSV."""
    bajo = (nombre or "").lower()
    if bajo.endswith(".pdf"):
        import pypdf

        lector = pypdf.PdfReader(io.BytesIO(datos))
        texto = "\n".join(
            (pagina.extract_text() or "") for pagina in lector.pages
        )
    elif bajo.endswith(".docx"):
        import docx

        archivo = docx.Document(io.BytesIO(datos))
        texto = "\n".join(p.text for p in archivo.paragraphs)
    else:
        texto = datos.decode("utf-8", errors="replace")

    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    if not texto:
        raise HTTPException(
            status_code=400,
            detail="No pude leer texto de ese archivo. Prueba con PDF, DOCX o TXT.",
        )
    return texto[:TOPE_DOCUMENTO]


def contexto_documento() -> str:
    """Bloque de texto para los prompts cuando hay un documento cargado."""
    if not DOCUMENTO.get("texto"):
        return ""
    return (
        f"\n\nDOCUMENTO CARGADO POR EL USUARIO ({DOCUMENTO['nombre']}):\n"
        f"{DOCUMENTO['texto'][:TOPE_DOCUMENTO]}\n"
    )


def resumen_documento() -> str:
    if not DOCUMENTO.get("texto"):
        return ""
    return DOCUMENTO.get("resumen") or ""


DOC_CLAVES = (
    "documento", "archivo", "pdf", "docx", "word", "informe", "texto",
    "pagina", "parrafo", "seccion", "resumen", "de que trata", "seg",
    "menciona", "encabeza", "conclusion", "capitulo", "anexo", "adjunto",
)


def _pregunta_del_documento(texto: str) -> bool:
    """Decide si la pregunta va dirigida al documento cargado (P4 del guion).

    El documento NO es la fuente de verdad: solo se usa cuando el usuario
    habla de él o cuando la pregunta comparte términos con su contenido.
    """
    if not DOCUMENTO.get("texto"):
        return False
    if any(clave in texto for clave in DOC_CLAVES):
        return True
    if len(texto) < 12:
        return False
    palabras_documento = set(
        re.findall(r"[a-z]{5,}", normalizar(DOCUMENTO["texto"])[:4000])
    )
    palabras_pregunta = set(re.findall(r"[a-z]{5,}", texto))
    return len(palabras_documento & palabras_pregunta) >= 2


def prompt_documento(pregunta: str, historial: str) -> str:
    return f"""Acompañas a un usuario que cargó un documento. Tu tarea es
responder preguntas sobre él.

REGLAS:
- Responde SOLO con información que esté en el DOCUMENTO.
- Si la respuesta no está en el documento, dilo con naturalidad. No inventes.
- Entre 2 y 4 frases. Sin markdown, sin asteriscos, sin emojis, en español.
  Sé breve: mejor una respuesta corta.
- NO saludes ni empieces con "Hola".
- Cierra con UNA frase que haga avanzar la conversación: una pregunta breve
  sobre el documento o un consejo práctico. NO uses "¿Hay algo más en que te
  pueda ayudar?". Ejemplos: "Si quieres, te resumo el punto 3.",
  "¿Te leo la sección de conclusiones?"

CONVERSACIÓN PREVIA:
{historial or "(sin turnos previos)"}

PREGUNTA DEL USUARIO: {pregunta}
{contexto_documento()}
"""


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9\s]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def limpiar_json(texto: str) -> str:
    return re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        texto.strip(),
        flags=re.IGNORECASE,
    ).strip()


def limpiar_markdown(texto: str, trim: bool = True) -> str:
    texto = texto.replace("**", "").replace("__", "").replace("`", "")
    texto = re.sub(r"^\s*[*•\-]\s+", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^#{1,6}\s*", "", texto, flags=re.MULTILINE)
    texto = texto.replace("*", "").replace("#", "")
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip() if trim else texto


# ------------------------------------------------------------- red (keep-alive)

_cabeceras = {"Accept": "application/json"}
if APP_TOKEN:
    _cabeceras["X-App-Token"] = APP_TOKEN

# Cliente reutilizado: la primera llamada cuesta ~0.9s y las siguientes ~0.2s.
_http = httpx.Client(timeout=httpx.Timeout(8.0), headers=_cabeceras)

_CACHE_DATOS: dict = {}


def _parametros_limpios(params: dict) -> dict:
    limpios = {
        clave: valor
        for clave, valor in params.items()
        if clave in CAMPOS_PERMITIDOS and valor not in (None, "")
    }

    if "$limit" in limpios:
        try:
            limpios["$limit"] = str(min(int(limpios["$limit"]), MAX_FILAS))
        except (TypeError, ValueError):
            limpios["$limit"] = str(LIMITE_RESPUESTA)

    return limpios


def consultar_dataset(params: dict) -> list:
    limpios = _parametros_limpios(params)
    clave = tuple(sorted(limpios.items()))

    if clave in _CACHE_DATOS:
        return _CACHE_DATOS[clave]

    try:
        respuesta = _http.get(DATASET_URL, params=limpios)
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail="No se pudo consultar datos.gov.co.",
        ) from error

    if respuesta.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"datos.gov.co respondió {respuesta.status_code}.",
        )

    datos = respuesta.json()
    if len(_CACHE_DATOS) > 200:
        _CACHE_DATOS.clear()
    _CACHE_DATOS[clave] = datos
    return datos


# --------------------------------------------------------------- Gemini

def _config(rapida: bool = True) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=0.3,
        max_output_tokens=220 if rapida else 320,
    )


def consultar_gemini(prompt: str) -> str:
    try:
        respuesta = cliente.models.generate_content(
            model=MODELO,
            contents=prompt,
            config=_config(),
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


def _gemini_stream(prompt: str):
    """Genera trozos de texto a medida que los produce Gemini."""
    try:
        stream = cliente.models.generate_content_stream(
            model=MODELO,
            contents=prompt,
            config=_config(),
        )
        for trozo in stream:
            if trozo.text:
                yield trozo.text
    except Exception:
        # Ante un fallo del streaming devolvemos un mensaje de reserva.
        yield (
            "Ups, tuve un problema al preparar la respuesta. "
            "¿Me repites la ciudad y lo que necesitas?"
        )


def stream_con_recurso(prompt: str, respaldo: str, espera: float = 5.0):
    """Como _gemini_stream, pero si Gemini no responde a tiempo devuelve el
    texto de reserva para que el usuario nunca quede esperando."""
    cola: queue.Queue = queue.Queue(maxsize=64)

    def productor():
        try:
            for trozo in _gemini_stream(prompt):
                cola.put(("texto", trozo))
        except Exception:
            cola.put(("fallo", None))
        finally:
            cola.put(("fin", None))

    threading.Thread(target=productor, daemon=True).start()

    primero = True
    while True:
        try:
            tipo, valor = cola.get(timeout=espera if primero else 15.0)
        except queue.Empty:
            if primero:
                yield respaldo
            return
        if tipo == "fin":
            return
        if tipo == "fallo":
            if primero:
                yield respaldo
            return
        primero = False
        yield valor


def gemini_o_respaldo(prompt: str, respaldo: str, espera: float = 5.0) -> str:
    """Llamada bloqueante con tope de espera: nunca congela la respuesta."""
    resultado: dict = {}

    def ejecutar():
        try:
            resultado["texto"] = consultar_gemini(prompt)
        except Exception as error:
            resultado["error"] = error

    hilo = threading.Thread(target=ejecutar, daemon=True)
    hilo.start()
    hilo.join(espera)

    if "texto" in resultado:
        return resultado["texto"]
    return respaldo


# ------------------------------------------------------------- index de lugares

LUGARES: dict[str, dict] = {}


def _alias(valor: str) -> list[str]:
    base = normalizar(valor)
    if not base:
        return []
    palabras = [p for p in base.split() if len(p) > 3]
    recortado = " ".join(palabras)
    salidas = {base}
    if len(recortado) >= 4:
        salidas.add(recortado)
    return [a for a in salidas if len(a) >= 3]


def _cargar_lugares():
    global LUGARES
    nuevo: dict[str, dict] = {}

    def guardar(alias: str, valor: str, campo: str):
        actual = nuevo.get(alias)
        # Si un nombre es municipio y departamento, manda el municipio.
        if actual is None or (actual["campo"] == "departamento" and campo == "municipio"):
            nuevo[alias] = {"valor": valor, "campo": campo}

    for fila in consultar_dataset({"$select": "distinct municipio", "$limit": "1000"}):
        municipio = (fila.get("municipio") or "").strip()
        for a in _alias(municipio):
            guardar(a, municipio, "municipio")

    for fila in consultar_dataset({"$select": "distinct departamento", "$limit": "100"}):
        departamento = (fila.get("departamento") or "").strip()
        for a in _alias(departamento):
            guardar(a, departamento, "departamento")

    LUGARES = nuevo


def detectar_lugar(texto: str) -> dict | None:
    if not LUGARES:
        return None
    texto = f" {texto} "
    mejor = None
    for alias, info in LUGARES.items():
        if f" {alias} " in texto:
            if mejor is None or len(alias) > len(mejor[0]):
                mejor = (alias, info)
    return mejor[1] if mejor else None


def _calentar():
    """Precalienta Gemini y datos.gov.co para que el primer turno sea rápido."""
    try:
        consultar_dataset({"$select": "count(*) as total", "$limit": "1"})
    except Exception:
        pass
    try:
        cliente.models.generate_content(
            model=MODELO,
            contents="Responde solo: listo",
            config=_config(),
        )
    except Exception:
        pass


@app.on_event("startup")
def _startup():
    # Se cargan en segundo plano para no bloquear el arranque de la app.
    threading.Thread(target=_cargar_lugares, daemon=True).start()
    threading.Thread(target=_calentar, daemon=True).start()


# ------------------------------------------------------------ interpretación

SERVICIOS = [
    ("urgencias", ["urgencia", "urgencias"]),
    ("camas", ["cama", "camas", "hospitalizacion", "internacion"]),
    ("hospitales", ["hospital", "hospitales"]),
    ("partos", ["parto", "partos", "obstetricia", "embarazo", "natal"]),
    ("consulta externa", ["consulta externa", "consulta", "cita"]),
    ("cirugia", ["cirugia", "quirurgico"]),
    ("uci", ["uci", "unidad de cuidados intensivos"]),
    ("pediatria", ["pediatria", "nino", "infantil", "bebe"]),
    ("laboratorio", ["laboratorio", "muestra", "examenes"]),
    ("imagenologia", [
        "imagenologia", "radiografia", "rayos x", "ecografia", "tomografia",
    ]),
    ("odontologia", ["odontologia", "dental", "dentista"]),
    ("ambulancias", ["ambulancia", "ambulancias"]),
    ("vacunacion", ["vacunacion", "vacuna", "vacunas"]),
    ("teleconsulta", ["teleconsulta", "telemedicina"]),
]

SERVICIO_WHERE = {
    "urgencias": "UPPER(nom_descripcion_capacidad) LIKE '%URGENCIAS%'",
    "camas": "nom_grupo_capacidad='CAMAS'",
    "hospitales": "UPPER(nom_sede_ips) LIKE '%HOSPITAL%'",
    "partos": "UPPER(nom_descripcion_capacidad) LIKE '%PARTO%'",
    "consulta externa": "UPPER(nom_descripcion_capacidad) LIKE '%CONSULTA%'",
    "cirugia": "UPPER(nom_descripcion_capacidad) LIKE '%CIRUG%'",
    "uci": "UPPER(nom_descripcion_capacidad) LIKE '%UCI%'",
    "pediatria": "UPPER(nom_descripcion_capacidad) LIKE '%PEDI%'",
    "laboratorio": "UPPER(nom_descripcion_capacidad) LIKE '%LABORATORIO%'",
    "imagenologia": "UPPER(nom_descripcion_capacidad) LIKE '%IMAGEN%'",
    "odontologia": "UPPER(nom_descripcion_capacidad) LIKE '%ODONT%'",
    "ambulancias": "nom_grupo_capacidad='AMBULANCIAS'",
}


def detectar_servicio(texto: str) -> str | None:
    for nombre, claves in SERVICIOS:
        for clave in claves:
            if clave in texto:
                return nombre
    return None


SALUDOS = {
    "hola", "buenas", "buenos dias", "buenas tardes", "buenas noches",
    "que mas", "holi", "hey", "oye", "hola que tal",
}

REPLICAS_RAPIDAS = {
    "hola": (
        "Hola, ¿cómo estás? Soy la asistente virtual de la IPS. "
        "Dime en qué te puedo ayudar y en qué ciudad estás."
    ),
    "buenas": (
        "Hola, ¿cómo estás? Soy la asistente virtual de la IPS. "
        "Dime en qué te puedo ayudar y en qué ciudad estás."
    ),
    "buenos dias": (
        "Buenos días. Soy la asistente virtual de la IPS. "
        "Cuéntame en qué ciudad estás y qué necesitas."
    ),
    "buenas tardes": (
        "Buenas tardes. Soy la asistente virtual de la IPS. "
        "Cuéntame en qué ciudad estás y qué necesitas."
    ),
    "buenas noches": (
        "Buenas noches. Soy la asistente virtual de la IPS. "
        "Cuéntame en qué ciudad estás y qué necesitas."
    ),
    "gracias": (
        "¡Con gusto! Si necesitas otra cosa de salud, dime en qué ciudad estás."
    ),
    "grax": "¡Con gusto! Si necesitas otra cosa, dime en qué ciudad estás.",
    "chao": "Hasta pronto. Recuerda que estoy aquí cuando necesites orientación.",
    "adios": "Hasta pronto. Recuerda que estoy aquí cuando necesites orientación.",
    "hasta luego": "Hasta pronto. Estoy aquí cuando me necesites.",
    "si": "Perfecto. ¿En qué ciudad estás y qué necesitas de salud?",
    "ok": "Perfecto. ¿En qué ciudad estás y qué necesitas de salud?",
    "listo": "Perfecto. ¿En qué ciudad estás y qué necesitas de salud?",
}


PALABRAS_SALUDO = {
    "hola", "holi", "hey", "oye", "buenas", "buenos", "dias", "tardes",
    "noches", "que", "mas", "como", "estas", "todo", "bien", "saludos",
}


PEDIR_CIUDAD = re.compile(
    r"\s*[,;]?\s*(y|e)?\s*(dime en qu[ée] ciudad est[áa]s[^.]*\.|"
    r"cu[ée]ntame en qu[ée] ciudad est[áa]s[^.]*\.|"
    r"¿?en qu[ée] ciudad est[áa]s[^?]*¿?\?)",
    re.I,
)


def _sin_pedir_ciudad(texto: str) -> str:
    """Quita el pedir la ciudad cuando ya la sabemos."""
    limpio = PEDIR_CIUDAD.sub("", texto).strip()
    limpio = re.sub(r"\s+([.,;])", r"\1", limpio)
    limpio = re.sub(r"\s{2,}", " ", limpio).rstrip(" ,")
    if limpio and limpio[-1] not in ".!?":
        limpio += "."
    return limpio or texto


def respuesta_rapida(texto: str) -> str | None:
    texto = texto.strip().rstrip("!.¿¡")
    texto = normalizar(texto).strip()
    if texto in REPLICAS_RAPIDAS:
        return REPLICAS_RAPIDAS[texto]

    # Saludos pegados o con adornos: "Hola, buenas", "Buenas, ¿cómo estás?".
    # Solo cuando TODAS las palabras son de saludo, para no interferir con
    # preguntas reales ("hola, hospitales en Cali").
    palabras = texto.split()
    if (
        palabras
        and len(palabras) <= 5
        and all(palabra in PALABRAS_SALUDO for palabra in palabras)
    ):
        return REPLICAS_RAPIDAS.get(texto) or REPLICAS_RAPIDAS["hola"]

    return None


# ------------------------------------------------------------- redacción

def formato_ip(row: dict) -> str:
    nombre = row.get("nom_sede_ips") or row.get("nombre_prestador") or "IPS"
    direccion = (row.get("direcci_n") or "").strip()
    telefono = (row.get("tel_fono") or "").strip()
    partes = [nombre]
    if direccion:
        partes.append(f"en {direccion}")
    if telefono:
        partes.append(f"tel. {telefono}")
    return " ".join(partes)


def texto_con_servicios(filas: list, ciudad: str, servicio: str) -> str:
    sedes = []
    vistos = set()
    for row in filas:
        clave = (row.get("nom_sede_ips"), row.get("nombre_prestador"))
        if clave in vistos:
            continue
        vistos.add(clave)
        sedes.append(formato_ip(row))
        if len(sedes) >= 3:
            break

    if not sedes:
        return (
            f"No encontré opciones de {servicio} en {ciudad} con la información "
            "de la que dispongo. Puedes probarme con otra ciudad o con otro "
            "servicio."
        )

    if len(sedes) == 1:
        lista = sedes[0]
    else:
        lista = f"{', '.join(sedes[:-1])} y {sedes[-1]}"

    return f"En {ciudad} para {servicio} te puedo orientar hacia {lista}."


def texto_por_ciudad(filas: list, ciudad: str) -> str:
    if not filas:
        return (
            f"No encontré información de IPS en {ciudad} con lo que dispongo. "
            "Dime qué servicio necesitas para ayudarte mejor."
        )

    grupos = []
    for row in filas:
        grupo = (row.get("nom_grupo_capacidad") or "").strip()
        if grupo and grupo not in grupos:
            grupos.append(grupo)

    sedes = []
    for row in filas:
        clave = row.get("nom_sede_ips") or row.get("nombre_prestador")
        if clave and clave not in sedes:
            sedes.append(clave)

    if len(sedes) == 1:
        base = f"En {ciudad} encontré {sedes[0]}."
    else:
        base = f"En {ciudad} encontré {len(sedes)} sedes, entre ellas {sedes[0]}."

    if grupos:
        return (
            f"{base} Ofrecen atención como {', '.join(grupos[:5])}. "
            "Dime si necesitas urgencias, camas, partos o consulta externa "
            "y te oriento con precisión."
        )
    return f"{base} Dime qué servicio necesitas y te ayudo."


def texto_sin_datos() -> str:
    return (
        "Con la información que tengo no encuentro ese dato. "
        "Dime en qué ciudad estás y qué servicio necesitas y te ayudo."
    )


def texto_fuera_de_alcance() -> str:
    return (
        "Solo puedo orientarte sobre la ubicación y los servicios de las IPS de "
        "salud en Colombia. Dime en qué ciudad estás y qué necesitas de salud "
        "y con gusto te ayudo."
    )


CONSEJOS_CONTEO = [
    " ¿Quieres las direcciones?",
    " ¿Te muestro las dos más cercanas?",
    " ¿Te doy los teléfonos de contacto?",
    " ¿Comparo con las de tu aseguradora?",
    "",
]


def contar_respuesta(total: int, lugar: str, que: str, camas: bool = False) -> str:
    if total == 0:
        return (
            f"Con la información que tengo no encontré {que} en {lugar}. "
            "Prueba con otra ciudad o con otro servicio."
        )
    if camas:
        base = f"En {lugar} hay {total} camas registradas."
    elif que == "hospitales":
        base = f"En {lugar} hay {total} hospitales registrados."
    elif que == "sedes de IPS":
        base = f"En {lugar} encontré {total} sedes de IPS."
    else:
        base = f"En {lugar} hay {total} sedes que ofrecen {que}."
    # Los conteos responden con una consulta directa (sin LLM): aquí se
    # agrega el siguiente paso para que la conversación no quede en seco.
    return f"{base}{random.choice(CONSEJOS_CONTEO)}"


def _consultar_conteo(lugar: dict, servicio: str | None) -> tuple[int, str, bool]:
    """Devuelve (total, etiqueta, es_camas) con una sola consulta agregada."""
    where = f"{lugar['campo']}='{lugar['valor']}'"
    es_camas = servicio == "camas"

    if es_camas:
        where += " AND nom_grupo_capacidad='CAMAS'"
        select = "sum(num_cantidad_capacidad_instalada) as total"
        etiqueta = "camas"
    else:
        if servicio and servicio in SERVICIO_WHERE:
            where += " AND " + SERVICIO_WHERE[servicio]
            etiqueta = servicio
        else:
            etiqueta = "sedes de IPS"
        select = "count(distinct c_digo_sede) as total"

    filas = consultar_dataset({"$select": select, "$where": where, "$limit": "1"})

    if not filas:
        return 0, etiqueta, es_camas

    try:
        total = int(float(filas[0].get("total") or 0))
    except (TypeError, ValueError):
        total = 0

    return total, etiqueta, es_camas


# ---------------------------------------------------------------- prompts

def prompt_redaccion(
    pregunta, historial, filas, ciudad, servicio, recordada=False, extra=""
) -> str:
    memoria_aviso = (
        "\n- La ciudad es un dato de contexto para ti. Úsala para responder, "
        "pero NO la anuncies ni digas frases como 'recuerdo que estás en' ni "
        "'como indicaste'. Simplemente responde con normalidad."
        if recordada
        else ""
    )
    return f"""
Eres la asistente virtual de salud de una IPS en Colombia. Hablas en español,
cercana y humana, como si ayudaras a una persona por voz.

REGLAS ESTRICTAS:
- Solo puedes informar lo que aparece en los RESULTADOS. No inventes nombres,
  direcciones, teléfonos ni cantidades.
- No des diagnósticos ni medicamentos. Un consejo práctico (llamar antes de ir,
  verificar horarios, traer la cédula o la carnetización) sí está permitido.
- Si el dato no está en los RESULTADOS, dilo con naturalidad.
- Entre 2 y 4 frases en total y máximo 60 palabras. Da como mucho 2 o 3
  sedes de ejemplo: es mejor una respuesta corta que una larga. Sin markdown,
  sin asteriscos, sin viñetas, sin emojis.
- Responde SIEMPRE en español.
- IMPORTANTE: NO vuelvas a saludar. No empieces con "Hola", "Buenos días",
  "Claro que sí" ni frases de cortesía vacías. Ya hubo un saludo al inicio.
  Ve directo al contenido de la respuesta.
- Para cerrar, NO uses "¿Hay algo más en que te pueda ayudar?". Termina con
  UNA frase que haga avanzar la conversación: una pregunta breve sobre lo
  siguiente que le pueda servir, o un consejo práctico corto. Varía siempre.
  Ejemplos: "Si quieres te busco las que atiendan de noche.",
  "Te recomiendo llamar antes de ir para confirmar horario.",
  "¿Quieres que te compare con las de tu aseguradora?"
- Si la pregunta tiene varias partes (por ejemplo "¿cuántos hay? y dame la
  dirección"), responde TODAS las partes, no solo una. Si pide 1 o 2
  ejemplos, da exactamente esa cantidad.
{memoria_aviso}
CONVERSACIÓN PREVIA:
{historial or "(sin turnos previos)"}

PREGUNTA DEL USUARIO: {pregunta}
CIUDAD: {ciudad}
SERVICIO BUSCADO: {servicio or "no especificado"}

RESULTADOS ({len(filas)} filas):
{json.dumps(filas[:10], ensure_ascii=False)}
{extra}
"""


def prompt_plan(pregunta: str, historial: str, memoria: str = "") -> str:
    contexto = (
        f"CONTEXTO: el usuario ya indicó que está en {memoria}. Úsalo si hace "
        "falta, pero no lo menciones ni digas que lo recuerdas.\n"
        if memoria
        else ""
    )
    return f"""
Eres la asistente de salud de una IPS en Colombia. Usas EXCLUSIVAMENTE la
Relación de IPS de datos.gov.co. {ESQUEMA}{SOQL_AYUDA}

CONVERSACIÓN PREVIA:
{historial or "(sin turnos previos)"}

{contexto}
PREGUNTA ACTUAL: {pregunta}

REGLAS DE RESPUESTA (para las acciones pedir_datos y fuera_de_alcance):
- NO saludes ni empieces con "Hola" ni "Buenos días": el saludo ya ocurrió.
- Sé breve: 1 o 2 frases.
- Cierra con una cortesía como "¿Hay algo más en que te pueda ayudar?".
- Si ya conoces la ciudad, no vuelvas a preguntarla.

Devuelve SOLO JSON válido con UNA de estas acciones:
- {{"accion":"consultar","params":{{"$select":"...","$where":"...","$limit":"{LIMITE_RESPUESTA}"}}}}
  si ya tienes ciudad y necesidad para buscar en los datos.
- {{"accion":"pedir_datos","respuesta":"..."}} si falta la ciudad o la necesidad.
- {{"accion":"fuera_de_alcance","respuesta":"..."}} si no es sobre salud o IPS.
"""


# --------------------------------------------------------------- endpoints


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


BRIEF_CACHE = {"data": None}


@app.get("/api/documento")
def documento_estado():
    if not DOCUMENTO.get("texto"):
        return {"cargado": False}
    return {
        "cargado": True,
        "nombre": DOCUMENTO.get("nombre", ""),
        "resumen": DOCUMENTO.get("resumen", ""),
        "caracteres": len(DOCUMENTO.get("texto", "")),
    }


@app.post("/api/documento")
async def documento_subir(archivo: UploadFile = File(...)):
    """Paso P2 del guion: el jurado entrega un documento en ese momento."""
    datos = await archivo.read()
    if len(datos) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="El archivo supera 5 MB.")
    if not datos:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    texto = _leer_documento(archivo.filename or "", datos)
    previo = texto[:2500]

    def _reservado() -> str:
        return " ".join(previo.split()[:60]) + "…"

    resumen = gemini_o_respaldo(
        "Resume en máximo 3 frases de qué trata este documento. Luego sugiere "
        "4 preguntas que un jurado podría hacerle sobre él. Responde solo con "
        'JSON {"resumen":"...","preguntas":["...","..."]}. TEXTO:\n' + previo,
        json.dumps(
            {
                "resumen": _reservado(),
                "preguntas": [
                    "¿De qué trata el documento?",
                    "¿Cuáles son sus puntos principales?",
                    "¿Qué datos relevantes menciona?",
                    "¿Cuál es su conclusión?",
                ],
            },
            ensure_ascii=False,
        ),
    )

    try:
        datos_brief = json.loads(limpiar_json(resumen))
        resumen_texto = str(datos_brief.get("resumen") or _reservado())
        preguntas = [str(p) for p in (datos_brief.get("preguntas") or [])][:5]
    except (json.JSONDecodeError, ValueError):
        resumen_texto = _reservado()
        preguntas = []

    DOCUMENTO.clear()
    DOCUMENTO.update(
        {
            "nombre": archivo.filename or "documento",
            "texto": texto,
            "resumen": resumen_texto,
            "preguntas": preguntas,
        }
    )

    return {
        "cargado": True,
        "nombre": DOCUMENTO["nombre"],
        "resumen": resumen_texto,
        "preguntas": preguntas,
        "caracteres": len(texto),
    }


@app.delete("/api/documento")
def documento_quitar():
    DOCUMENTO.clear()
    return {"cargado": False}


@app.get("/api/brief")
def brief():
    # Documento cargado: el jurado pide que explique de qué trata (P3).
    if DOCUMENTO.get("texto"):
        preguntas = DOCUMENTO.get("preguntas") or []
        if len(preguntas) < 3:
            preguntas = [
                "¿De qué trata el documento?",
                "¿Qué información principal contiene?",
                "¿Qué datos o cifras menciona?",
                "¿Cuáles son sus conclusiones?",
            ]
        return {
            "introduccion": (
                f"Listo, ya indexé «{DOCUMENTO.get('nombre', 'el documento')}». "
                f"{DOCUMENTO.get('resumen', '')}"
            ),
            "preguntas_sugeridas": preguntas[:5],
            "documento": DOCUMENTO.get("nombre", ""),
        }

    if BRIEF_CACHE["data"] is None:
        BRIEF_CACHE["data"] = {
            "introduccion": (
                "Soy tu asistente de salud. Cuéntame qué necesitas y en qué ciudad "
                "estás para ayudarte a encontrar dónde atenderte."
            ),
            "preguntas_sugeridas": [
                "¿Cuál es la clínica más cercana según mi ciudad?",
                "¿Dónde hay urgencias en Medellín?",
                "¿En qué lugar puedo tener un parto en Bogotá?",
                "¿Dónde puedo agendar una cita médica general en Cali?",
            ],
        }
    return BRIEF_CACHE["data"]


def _historial_texto(historial: list[dict]) -> str:
    ultimo = historial[-6:] if historial else []
    return "\n".join(
        f"{'Usuario' if m.get('rol') == 'usuario' else 'Asistente'}: "
        f"{m.get('texto', '')}"
        for m in ultimo
    )


def _detectar_lugar_ultimo(texto: str) -> dict | None:
    """Devuelve el último lugar mencionado en el texto (la ciudad más reciente
    gana, por si el usuario se corrige: 'no, soy de Bogotá')."""
    if not LUGARES:
        return None
    texto = f" {texto} "
    mejor = None
    for alias, info in LUGARES.items():
        posicion = texto.find(f" {alias} ")
        if posicion >= 0 and (mejor is None or posicion > mejor[0]):
            mejor = (posicion, info)
    return mejor[1] if mejor else None


def extraer_memoria(historial: list[dict]) -> dict:
    """Recuerda la ciudad y el servicio que el usuario ya mencionó."""
    memoria = {"lugar": None, "servicio": None, "servicios": []}

    for mensaje in historial:
        if mensaje.get("rol") != "usuario":
            continue
        texto = normalizar(mensaje.get("texto") or "")
        if not texto:
            continue

        lugar = _detectar_lugar_ultimo(texto)
        if lugar:
            memoria["lugar"] = lugar

        servicio = detectar_servicio(texto)
        if servicio:
            memoria["servicio"] = servicio
            if servicio not in memoria["servicios"]:
                memoria["servicios"].append(servicio)

    return memoria


CIERRES = [
    "",
    " ¿Quieres que te busque las que atiendan de noche?",
    " Te recomiendo llamar antes de ir para confirmar el horario.",
    " ¿Te muestro otras opciones en la misma ciudad?",
    " Si quieres, te doy los teléfonos de esas sedes.",
    " ¿Comparo con las de tu aseguradora?",
    " Recuerda llevar tu cédula y la carnetización.",
    " ¿Te parece si buscamos algo más cercano a ti?",
    " Puedo filtrar por las que estén abiertas ahora.",
    "",
]


def _cierre(texto: str) -> str:
    """Cierre de continuidad: sugiere el siguiente paso o da un consejo.

    A veces se omite para no repetir la misma fórmula en cada respuesta.
    """
    texto = texto.strip()
    if re.search(
        r"ay algo m[áa]s|en que te pueda ayudar|en qu[ée] m[áa]s|"
        r"te puedo ayudar con algo m[áa]s|necesitas algo m[áa]s|"
        r"quiere que te busque|quiere que te muestre|te busco|te muestro|"
        r"quieres las direcciones|te muestro las dos|te doy los tel[ée]fonos",
        texto,
        re.I,
    ):
        return texto
    if texto and texto[-1] not in ".!?":
        texto += "."
    # Cortesía de longitud: nadie quiere escuchar una respuesta interminable.
    if len(texto) > 430:
        trozo = texto[:430]
        corte = max(trozo.rfind(". "), trozo.rfind(", "))
        texto = (trozo[:corte] if corte > 220 else trozo).rstrip() + "…"
    return f"{texto}{random.choice(CIERRES)}"


def _datos_lugar(lugar: dict, servicio: str | None) -> tuple[list, str]:
    campo = lugar["campo"]
    valor = lugar["valor"]

    if servicio and servicio in SERVICIO_WHERE:
        where = f"{campo}='{valor}' AND {SERVICIO_WHERE[servicio]}"
        select = "nombre_prestador, nom_sede_ips, direcci_n, tel_fono, municipio"
    else:
        where = f"{campo}='{valor}'"
        select = (
            "nombre_prestador, nom_sede_ips, direcci_n, tel_fono, "
            "nom_grupo_capacidad, nom_descripcion_capacidad, municipio"
        )

    filas = consultar_dataset({
        "$select": select,
        "$where": where,
        "$limit": str(LIMITE_RESPUESTA),
    })
    return filas, where


@app.post("/api/chat")
def chat(datos: PreguntaRequest):
    pregunta = datos.pregunta.strip()
    if not pregunta:
        raise HTTPException(status_code=400, detail="Escribe una pregunta.")

    historial = datos.historial or []
    historial_texto = _historial_texto(historial)
    entrada = normalizar(pregunta)

    # Memoria: qué ciudad y qué servicio mencionó antes el usuario.
    memoria = extraer_memoria(historial)

    # 1) Respuestas inmediatas sin red ni Gemini (saludos, gracias...).
    rapida = respuesta_rapida(entrada)
    if rapida and memoria["lugar"]:
        # Ya conoce la ciudad: no volver a pedirla.
        rapida = _sin_pedir_ciudad(rapida)
    if rapida:
        return StreamingResponse(
            iter([limpiar_markdown(rapida)]),
            media_type="text/plain; charset=utf-8",
        )

    # 2) Documento cargado: si la pregunta va por él, respondemos con él.
    if _pregunta_del_documento(entrada):
        respaldo_doc = _cierre(
            f"Según «{DOCUMENTO.get('nombre', 'el documento')}»: "
            f"{DOCUMENTO.get('resumen', 'no pude resumirlo.')}"
        )
        return StreamingResponse(
            (
                limpiar_markdown(t, trim=False)
                for t in stream_con_recurso(
                    prompt_documento(pregunta, historial_texto),
                    respaldo_doc,
                    espera=5.0,
                )
            ),
            media_type="text/plain; charset=utf-8",
        )

    lugar = detectar_lugar(entrada)
    recordada = False
    if lugar is None and memoria["lugar"]:
        # El usuario no repitió la ciudad: la tomamos de la memoria.
        lugar = memoria["lugar"]
        recordada = True

    servicio = detectar_servicio(entrada)
    # Solo se hereda el servicio de un turno anterior si la nueva pregunta no
    # habla de otra cosa (si pregunta por IPS, no debe responder con camas).
    menciona_entidad = bool(
        re.search(
            r"\bips+|\bsedes?\b|\bhospitales?\b|\binstituciones?\b|"
            r"\bclinicas?\b|\bestablecimientos?\b|\bproveedores?\b",
            entrada,
        )
    )
    if servicio is None and memoria["servicio"] and recordada and not menciona_entidad:
        # Seguimiento ("¿cuántas camas hay?") sin repetir el servicio.
        servicio = memoria["servicio"]

    pide_conteo = bool(re.search(r"\bcu[ánta]nt[oa]s?\b|\btotal\b", entrada))
    # Conteo compuesto: pide además direcciones, nombres o listado.
    # En ese caso el atajo solo con el número no alcanza.
    solo_conteo = pide_conteo and not bool(
        re.search(
            r"\bd[áa]me\b|\bdirecci|\bmu[ée]str|\blist[ao]|\bcu[áa]l(?:es)?\b|"
            r"\bnombre|\bc[óo]mo llego\b|\bd[óo]nde\b|\by dame\b|\btambi[ée]n\b|"
            r"\binclu(?:ye|ya)\b|\bpara ver\b|\bde ellas\b|\bde ellos\b",
            entrada,
        )
    )

    # 2) Camino directo: ya sabemos la ciudad, consultamos y redactamos.
    if lugar:
        ciudad = lugar["valor"].title()

        # Conteos puros: una sola consulta agregada y respuesta inmediata.
        if solo_conteo:
            try:
                total, etiqueta, es_camas = _consultar_conteo(lugar, servicio)
            except HTTPException as error:
                return StreamingResponse(
                    iter([error.detail]),
                    media_type="text/plain; charset=utf-8",
                )
            texto = contar_respuesta(total, ciudad, etiqueta, es_camas)
            return StreamingResponse(
                iter([texto]),
                media_type="text/plain; charset=utf-8",
            )

        try:
            filas, where = _datos_lugar(lugar, servicio)
        except HTTPException as error:
            return StreamingResponse(
                iter([error.detail]),
                media_type="text/plain; charset=utf-8",
            )

        # Conteo compuesto: damos a Gemini las filas Y el número exacto.
        extra_conteo = ""
        if pide_conteo:
            try:
                total, etiqueta, es_camas = _consultar_conteo(lugar, servicio)
                if total:
                    extra_conteo = f"\nTOTAL EXACTO de {etiqueta}: {total}."
            except HTTPException:
                extra_conteo = ""

        if not filas:
            texto = (
                f"No encontré información de {servicio or 'IPS'} en {ciudad} "
                "con lo que tengo disponible. Prueba con otra ciudad o con "
                "otro servicio."
            )
            return StreamingResponse(
                iter([_cierre(texto)]),
                media_type="text/plain; charset=utf-8",
            )

        prompt = prompt_redaccion(
            pregunta, historial_texto, filas, ciudad, servicio, recordada,
            extra_conteo,
        )
        respaldo = _cierre(texto_con_servicios(
            filas, ciudad, servicio or "atención médica"
        ))
        return StreamingResponse(
            (limpiar_markdown(t, trim=False) for t in stream_con_recurso(prompt, respaldo)),
            media_type="text/plain; charset=utf-8",
        )

    # 3) Sin ciudad conocida: una sola llamada a Gemini para decidir.
    plan_texto = gemini_o_respaldo(
        prompt_plan(
            pregunta,
            historial_texto,
            memoria["lugar"]["valor"].title() if memoria["lugar"] else "",
        ),
        '{"accion":"pedir_datos","respuesta":'
        '"Cuéntame en qué ciudad estás y qué necesitas de salud."}',
    )
    try:
        plan = json.loads(limpiar_json(plan_texto))
    except (json.JSONDecodeError, ValueError):
        plan = {
            "accion": "pedir_datos",
            "respuesta": "¿Me cuentas en qué ciudad estás y qué necesitas de salud?",
        }

    accion = plan.get("accion")

    if accion == "fuera_de_alcance":
        texto = plan.get("respuesta") or texto_fuera_de_alcance()
        return StreamingResponse(
            iter([limpiar_markdown(_cierre(texto))]),
            media_type="text/plain; charset=utf-8",
        )

    if accion != "consultar" or not plan.get("params"):
        texto = plan.get("respuesta") or (
            "Cuéntame en qué ciudad estás y qué necesitas de salud para ayudarte."
        )
        return StreamingResponse(
            iter([limpiar_markdown(_cierre(texto))]),
            media_type="text/plain; charset=utf-8",
        )

    params = dict(plan["params"])
    params.setdefault("$limit", str(LIMITE_RESPUESTA))

    try:
        filas = consultar_dataset(params)
    except HTTPException as error:
        return StreamingResponse(
            iter([error.detail]),
            media_type="text/plain; charset=utf-8",
        )

    if not filas:
        return StreamingResponse(
            iter([_cierre(texto_sin_datos())]),
            media_type="text/plain; charset=utf-8",
        )

    donde = params.get("$where") or ""
    match = re.search(r"(?:municipio|departamento)='([^']+)'", donde)
    ciudad = match.group(1).title() if match else "tu ciudad"

    # Conteo: repetimos la consulta como agregado para no depender de un límite.
    if pide_conteo:
        try:
            conteo = dict(params)
            conteo["$select"] = (
                "sum(num_cantidad_capacidad_instalada) as total"
                if servicio == "camas"
                else "count(distinct c_digo_sede) as total"
            )
            conteo.pop("$group", None)
            conteo.pop("$order", None)
            filas_conteo = consultar_dataset(conteo)
            total = int(float(filas_conteo[0].get("total") or 0)) if filas_conteo else 0
        except (HTTPException, TypeError, ValueError):
            total = len(filas)
        es_camas = servicio == "camas"
        etiqueta = "camas" if es_camas else (servicio or "sedes de IPS")
        texto = contar_respuesta(total, ciudad, etiqueta, es_camas)
        return StreamingResponse(
            iter([texto]),
            media_type="text/plain; charset=utf-8",
        )

    texto = texto_con_servicios(filas, ciudad, servicio or "atención médica")
    return StreamingResponse(
        iter([_cierre(texto)]),
        media_type="text/plain; charset=utf-8",
    )


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
