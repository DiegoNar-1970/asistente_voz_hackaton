
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError(
        "No se encontró GEMINI_API_KEY en el archivo .env"
    )

client = genai.Client(api_key=api_key)

try:
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=(
            "Responde en español en una sola frase: "
            "¿Qué es un agente de inteligencia artificial?"
        ),
    )

    print("\nRespuesta de Gemini:")
    print(response.text)

except Exception as error:
    print("\nNo se pudo consultar Gemini.")
    print(f"Tipo de error: {type(error).__name__}")
    print(error)
