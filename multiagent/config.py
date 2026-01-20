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

if not GOOGLE_API_KEY:
    import warnings
    warnings.warn(
        "GOOGLE_API_KEY non trovata! "
        "Crea un file .env con la tua API key. Vedi .env.example"
    )


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

MAX_SYNTAX_RETRIES = 10
MAX_TEST_RETRIES = 5


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
            "Crea un file .env con la tua API key. Vedi .env.example"
        )
    
    return {
        "model": MODEL_NAME,
        "temperature": 0.2,
        "google_api_key": GOOGLE_API_KEY,
    }
