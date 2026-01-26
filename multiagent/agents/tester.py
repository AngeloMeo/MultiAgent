# ===========================================================================
#                       TESTER AGENT - Test Case Generation
# ===========================================================================
# Agente Black-Box per generazione di test cases.
# Non scrive codice Toy, ma produce specifiche JSON per l'Executor.
# ===========================================================================

import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from ..config import get_llm_config, REQUEST_DELAY_SEC
from ..models import TestSuite


# ---------------------------------------------------------------------------
#                           SYSTEM PROMPT
# ---------------------------------------------------------------------------

TESTER_SYSTEM_PROMPT = """Sei un QA engineer esperto. Il tuo compito è generare casi di test 
per programmi Toy-Agent usando un approccio BLACK-BOX.

NON devi scrivere codice Toy-Agent, ma solo specifiche di test in formato JSON.

Per ogni test case specifica:
1. description: breve descrizione del test
2. inputs: lista di stringhe da fornire come input (per istruzioni "grab")
3. expected_output: output atteso (da istruzioni "show")

REGOLE:
- Genera almeno 3 test cases con input/output diversi
- Includi casi edge (valori limite, casi speciali)
- L'expected_output deve corrispondere ESATTAMENTE all'output del programma

IMPORTANTE - FORMATO OUTPUT:
- Analizza il codice e le istruzioni 'show' per determinare l'output atteso, non inventarlo.
- Se ci sono più output, SARANNO SU RIGHE SEPARATE ("\n").


Rispondi SOLO con JSON valido nel formato:
{
  "test_cases": [
    {"description": "...", "inputs": ["..."], "expected_output": "..."},
    ...
  ]
}"""


# ---------------------------------------------------------------------------
#                           TESTER AGENT CLASS
# ---------------------------------------------------------------------------

class TesterAgent:
    """
    Agente per la generazione di test cases Black-Box.
    
    Analizza il codice e la richiesta per generare casi di test appropriati.
    Output in formato strutturato TestSuite (Pydantic).
    """
    
    def __init__(self):
        """Inizializza l'agente con il modello LLM."""
        config = get_llm_config()
        
        # LLM con structured output per TestSuite
        self.llm = ChatGoogleGenerativeAI(
            model=config["model"],
            temperature=config["temperature"],
            google_api_key=config["google_api_key"],
        )
        
        # Structured output per garantire formato JSON valido
        self.llm_structured = self.llm.with_structured_output(TestSuite)
    
    def generate_tests(self, user_request: str, toy_code: str) -> TestSuite:
        """
        Genera suite di test per il codice Toy-Agent.
        
        Args:
            user_request: Richiesta originale dell'utente
            toy_code: Codice Toy-Agent da testare
        
        Returns:
            TestSuite: Suite di test cases strutturata.
        """
        prompt = f"""Genera test cases per questo programma Toy-Agent.

RICHIESTA ORIGINALE:
{user_request}

CODICE:
```
{toy_code}
```

Analizza il codice e genera test cases appropriati.
Considera quali input sono richiesti (istruzioni "grab") e quali output prodotti (istruzioni "show").
Analizza bene il codice toy per far aderire perfettamente gli input e gli output attesi con quelli prodotti dal programma.
IMPORTANTE - TEST PER PROGRAMMI CON MENU/LOOP:
- Se il programma ha un menu CON LOOP, ogni test case DEVE terminare con l'input per USCIRE dal programma.
- Esempio: per testare la somma in un menu dove "5" = Esci, gli inputs saranno: ["1", "10", "5", "5"]
  (1=scelta somma, 10 e 5 = numeri, 5 = uscita dal menu)
- SENZA l'input di uscita, il test fallirà con EOF!
"""
        
        messages = [
            SystemMessage(content=TESTER_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]
        
        try:
            # Rate limiting
            print(f"[TESTER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
            
            # Genera con structured output
            result = self.llm_structured.invoke(messages)
            return result
        except Exception as e:
            # Fallback: restituisci suite vuota e logga warning
            print(f"[TESTER] WARNING: Generazione test fallita: {e}")
            return TestSuite(test_cases=[])


# ---------------------------------------------------------------------------
#                           FACTORY FUNCTION
# ---------------------------------------------------------------------------

def create_tester_agent() -> TesterAgent:
    """
    Factory function per creare un'istanza del Tester Agent.
    
    Returns:
        TesterAgent: Nuova istanza dell'agente.
    """
    return TesterAgent()
