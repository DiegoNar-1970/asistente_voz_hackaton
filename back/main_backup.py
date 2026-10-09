
from io import BytesIO
from pathlib import Path
import re

from docx import Document
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf import PdfReader

app = FastAPI(title="Agente Vocal Cognitivo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prototipo local: el documento se conserva en memoria.
# Si reinicias el backend, tendrás que cargarlo otra vez.
documento_actual = {
    "nombre": None,
    "fragmentos": [],
}


def extraer_texto(nombre: str, contenido: bytes) -> str:
    extension = Path(nombre).suffix.lower()

    try:
        if extension == ".txt":
            texto = contenido.decode("utf-8-sig")

        elif extension == ".pdf":
            lector = PdfReader(BytesIO(contenido))

            if lector.is_encrypted:
                raise HTTPException(
                    status_code=400,
                    detail="El PDF está protegido con contraseña."
                )

            texto = "\n".join(
                pagina.extract_text() or ""
                for pagina in lector.pages
            )

        elif extension == ".docx":
            documento = Document(BytesIO(contenido))
            texto = "\n".join(
                parrafo.text for parrafo in documento.paragraphs
            )

        else:
            raise HTTPException(
                status_code=400,
                detail="Formato no admitido. Usa PDF, DOCX o TXT."
            )

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail="No se pudo leer el documento."
        ) from error

    texto = re.sub(r"\s+", " ", texto).strip()

    if not texto:
        raise HTTPException(
            status_code=400,
            detail="El documento no contiene texto extraíble."
        )

    return texto


def dividir_en_fragmentos(
    texto: str,
    tamano: int = 1000,
    solapamiento: int = 150,
) -> list[str]:
    fragmentos = []
    inicio = 0

    while inicio < len(texto):
        fin = min(inicio + tamano, len(texto))
        fragmentos.append(texto[inicio:fin])

        if fin == len(texto):
            break

        inicio = fin - solapamiento

    return fragmentos


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/documents")
async def cargar_documento(
    archivo: UploadFile = File(...)
):
    contenido = await archivo.read()

    # Límite inicial de seguridad: 10 MB.
    if len(contenido) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="El documento supera el límite de 10 MB."
        )

    nombre = archivo.filename or "documento"

    texto = extraer_texto(nombre, contenido)
    fragmentos = dividir_en_fragmentos(texto)

    # Se reemplaza el documento anterior.
    documento_actual["nombre"] = nombre
    documento_actual["fragmentos"] = fragmentos

    return {
        "mensaje": "Documento cargado e indexado.",
        "nombre": nombre,
        "caracteres": len(texto),
        "cantidad_fragmentos": len(fragmentos),
        "vista_previa": texto[:500],
    }
