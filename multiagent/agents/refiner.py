# ===========================================================================
#                       REFINER AGENT - Error Analysis
# ===========================================================================
# Agente per analisi strutturata degli errori.
# Produce ErrorReport Pydantic per feedback mirato al Coder.
# Per customizzare: modifica REFINER_SYSTEM_PROMPT o ErrorReport.
# ===========================================================================

import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import get_llm_config, REQUEST_DELAY_SEC
from ..models import ErrorReport, ErrorType, TestResult


# ---------------------------------------------------------------------------
#                           SYSTEM PROMPT
# ---------------------------------------------------------------------------

REFINER_SYSTEM_PROMPT = """Sei un analista di errori esperto. Il tuo compito è analizzare 
i risultati dei test falliti e produrre un report strutturato per correggere il codice.

Devi produrre un ErrorReport con:
1. error_type: "Syntax" (errore di parsing), "Runtime" (errore in esecuzione), "Logical" (output errato)
2. details: descrizione chiara e concisa dell'errore
3. location: posizione nel codice se identificabile (es. "line 5", "task entrypoint")
4. suggestion: suggerimento SPECIFICO e AZIONABILE per correggere l'errore

REGOLE:
- Sii preciso e conciso
- Il suggestion deve essere implementabile direttamente
- Non suggerire riscritture complete, ma correzioni mirate
- Identifica la root cause, non solo il sintomo

IMPORTANTE - SINTASSI TOY:
- Il suggerimento DEVE rispettare la sintassi Toy-Agent.
- NON suggerire operatori inesistenti come `<=`, `>=`, `==`.
- Operatori validi: plus, minus, times, div, is, is_not, under (<), over (>), and, or, not
- Loop: NON esiste `for`. Usa sempre `loop condition do`.
- Per `<=`:
  - Su WHOLE: usa `x under (y plus 1)` (es: x <= 5 diventa x under 6)
  - Su FRACT: usa SOLO `not (x over y)` (NON usare plus 1, non funziona per decimali)"""


# ---------------------------------------------------------------------------
#                           REFINER AGENT CLASS
# ---------------------------------------------------------------------------

class RefinerAgent:
    """
    Agente per l'analisi degli errori e generazione di feedback strutturato.
    
    Riceve i risultati dei test falliti e produce ErrorReport
    con suggerimenti mirati per la correzione.
    """
    
    def __init__(self):
        """Inizializza l'agente con il modello LLM."""
        config = get_llm_config()
        
        self.llm = ChatGoogleGenerativeAI(
            model=config["model"],
            temperature=config["temperature"],
            google_api_key=config["google_api_key"],
        )
        
        # Structured output per ErrorReport
        self.llm_structured = self.llm.with_structured_output(ErrorReport)
    
    def analyze_failure(
        self, 
        user_request: str, 
        toy_code: str, 
        test_results: list[TestResult]
    ) -> ErrorReport:
        """
        Analizza i test falliti e produce un report di errore.
        
        Args:
            user_request: Richiesta originale dell'utente
            toy_code: Codice Toy-Agent che ha fallito
            test_results: Lista di risultati dei test (almeno uno fallito)
        
        Returns:
            ErrorReport: Report strutturato con analisi e suggerimenti.
        """
        # Prepara il riepilogo dei fallimenti
        failures = []
        for result in test_results:
            if not result.passed:
                failures.append(f"""
Test: {result.test_description}
Expected: {result.expected_output}
Actual: {result.actual_output}
Error: {result.error_message or 'Output mismatch'}""")
        
        failures_text = "\n".join(failures)
        
        prompt = f"""Analizza questo fallimento di test e produci un ErrorReport.

RICHIESTA ORIGINALE:
{user_request}

CODICE TOY-AGENT:
```
{toy_code}
```

TEST FALLITI:
{failures_text}

Identifica la causa dell'errore e suggerisci una correzione specifica."""
        
        messages = [
            SystemMessage(content=REFINER_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]
        
        try:
            # Rate limiting
            print(f"[REFINER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
            
            result = self.llm_structured.invoke(messages)
            return result
        except Exception as e:
            # Fallback: crea un report generico
            return ErrorReport(
                error_type=ErrorType.LOGICAL,
                details=f"Analisi fallita: {str(e)}",
                location=None,
                suggestion="Rivedere la logica del programma"
            )
    

# ---------------------------------------------------------------------------
#                           FACTORY FUNCTION
# ---------------------------------------------------------------------------

def create_refiner_agent() -> RefinerAgent:
    """
    Factory function per creare un'istanza del Refiner Agent.
    
    Returns:
        RefinerAgent: Nuova istanza dell'agente.
    """
    return RefinerAgent()
