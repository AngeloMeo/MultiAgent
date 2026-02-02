# ===========================================================================
#                       CONFIG - API Configuration
# ===========================================================================


import os
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
#                           CARICAMENTO ENVIRONMENT
# ---------------------------------------------------------------------------
load_dotenv()


# ---------------------------------------------------------------------------
#                           API CONFIGURATION
# ---------------------------------------------------------------------------

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
TOY_AGENT_API_URL = os.getenv("TOY_AGENT_API_URL") # E.g. "https://toy-agent-func.azurewebsites.net/api"

# ---------------------------------------------------------------------------
#                           MODEL CONFIGURATION
# ---------------------------------------------------------------------------

MODEL_NAME = "gemini-2.5-flash-lite"


# ---------------------------------------------------------------------------
#                           RATE LIMITING
# ---------------------------------------------------------------------------


REQUEST_DELAY_SEC = 0     # Nessun delay (fatturazione attiva)


# ---------------------------------------------------------------------------
#                           GRAPH SETTINGS
# ---------------------------------------------------------------------------

MAX_SYNTAX_RETRIES = 3
MAX_TEST_RETRIES = 5
EXECUTION_TIMEOUT = 5  # Timeout per richieste HTTP e esecuzione test (secondi)


# ---------------------------------------------------------------------------
#                           HELPER FUNCTION
# ---------------------------------------------------------------------------

def get_llm_config() -> dict:
    """
    Restituisce la configurazione per inizializzare il modello LLM.
    
    Returns:
        dict: Configurazione con model name e temperature.
    
    Raises:
        ValueError: Se GOOGLE_API_KEY non è configurata.
    """
    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY non trovata! "
            "Crea un file .env con la tua API key."
        )
    
    return {
        "model": MODEL_NAME,
        "temperature": 0.2,
        "google_api_key": GOOGLE_API_KEY,
    }
