from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app  # Asegúrate de que esta importación apunte a tu app de FastAPI
from schemas.parser import LexicalEntry, MDFField

client = TestClient(app)

# Define la ruta específica donde tienes tu archivo de prueba
# Puede ser relativa al directorio desde donde corres pytest o absoluta
PDF_TEST_PATH = Path("C:/Users/jmanu/Downloads/Diccionario Náhuatl Zongolica.pdf")


# ----------------------------------------------------------------------
# Mocks del Agente (Para no gastar tokens de IA durante el test)
# ----------------------------------------------------------------------
@pytest.fixture
def mock_ai_agent(monkeypatch):
    """Intercepta el agente de IA para devolver una respuesta controlada."""

    def mock_agent_run(*args, **kwargs):
        class MockResult:
            ok = True
            detected_language = "maya"
            entries = [
                LexicalEntry(
                    lexeme=MDFField.literal("balam"),
                    part_of_speech=MDFField.literal("n"),
                    definition_es=MDFField.literal("jaguar"),
                    source_page=1,
                )
            ]

        return MockResult()

    monkeypatch.setattr("services.mdf_agent.MDFPageAgent.run", mock_agent_run)


# ----------------------------------------------------------------------
# Test de Integración con Ruta Específica
# ----------------------------------------------------------------------
def test_extract_from_specific_path(mock_ai_agent):
    """
    Lee un PDF desde una ruta específica en el disco, lo envía a la API
    y valida la respuesta estructurada.
    """

    # 1. Validación de seguridad (falla rápido si olvidaste colocar el archivo)
    assert PDF_TEST_PATH.exists(), f"El archivo de prueba no existe en: {PDF_TEST_PATH}"
    assert PDF_TEST_PATH.is_file(), "La ruta especificada no es un archivo válido"

    # 2. Abrir el archivo real y enviarlo al endpoint
    with open(PDF_TEST_PATH, "rb") as f:
        response = client.post(
            "/api/extract",  # Asegúrate de que coincida con tu router de FastAPI
            files={"file": (PDF_TEST_PATH.name, f, "application/pdf")},
            data={"allow_ai_generation": "false"},
        )

    # 3. Validar la respuesta HTTP
    assert response.status_code == 200, f"Error en la API: {response.text}"
    json_data = response.json()

    # 4. Validaciones del esquema devuelto
    assert json_data["metadata"]["source_file"] == PDF_TEST_PATH.name

    # Validamos los datos procesados por nuestro Mock del Agente y Pydantic
    assert len(json_data["entries"]) > 0
    primera_entrada = json_data["entries"][0]

    assert primera_entrada["lexeme"]["value"] == "balam"
    assert primera_entrada["definition_es"]["value"] == "jaguar"
