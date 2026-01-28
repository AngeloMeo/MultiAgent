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

=== REGOLA CRITICA: ANALIZZA IL FLUSSO DI ESECUZIONE ===

Prima di generare test, simula mentalmente l'esecuzione del programma:
1. Quali istruzioni "show" verranno eseguite?
2. Quali "grab" richiedono input?
3. Cosa stamperà il programma per ogni percorso di input?

=== EXPECTED OUTPUT: MATCHING PERMISSIVO ===

L'output atteso viene verificato con matching PERMISSIVO:
- Il sistema cerca i valori expected come SOTTOSEQUENZA nell'output reale
- Se expected è "15", passa anche se l'output è "Menu\\n15\\nFine"
- Quindi l'expected deve contenere i VALORI CHIAVE che ci aspettiamo

REGOLA FONDAMENTALE:
- L'expected_output deve contenere i RISULTATI delle operazioni
- NON includere testo di menu, prompt, o messaggi informativi
- Se il programma stampa un menu e poi un risultato, l'expected è SOLO il risultato

ESEMPIO:
- Programma somma: expected = "15" (il risultato)
- Programma con menu che fa 10+5: expected = "15" (solo il risultato)
- Programma che stampa menu e poi esce: expected = "" (nessun risultato, il menu viene ignorato)

=== ATTENZIONE AI PROGRAMMI CON MENU ===

Se il codice ha un menu con loop:
1. Il menu viene SEMPRE stampato PRIMA di leggere la scelta
2. NON creare test "uscita immediata senza operazioni" - sono inutili
3. Ogni test DEVE fare almeno UNA operazione (somma, sottrazione, etc.)
4. L'ULTIMO input deve essere quello che esce dal loop

=== FORMATO TEST CASE ===

Per ogni test case specifica:
1. description: breve descrizione del test
2. inputs: lista di stringhe da fornire come input (per istruzioni "grab")
3. expected_output: SOLO i valori risultanti delle operazioni

REGOLE INPUTS:
- Conta quanti "grab" ci sono nel PERCORSO di esecuzione
- Se c'è loop con menu: scelta + parametri operazione + scelta uscita

ESEMPIO MENU CALCOLATRICE (0=esci):
- Test somma 10+5: inputs = ["1", "10", "5", "0"], expected = "15"
- Test sottrazione 20-8: inputs = ["2", "20", "8", "0"], expected = "12"

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
        
        self.llm = ChatGoogleGenerativeAI(
            model=config["model"],
            temperature=config["temperature"],
            google_api_key=config["google_api_key"],
        )
        
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

ANALISI RICHIESTA:
1. Identifica le operazioni disponibili (es. somma, sottrazione, etc.)
2. Conta i "grab" per ogni percorso di esecuzione
3. Determina quale input fa uscire dal programma

REGOLE CRITICHE:
- NON creare test "uscita immediata senza operazioni" - sono inutili!
- Ogni test DEVE eseguire almeno UNA operazione significativa
- L'expected_output deve contenere SOLO i risultati numerici, NON il testo del menu
- Se c'è un loop/menu, l'ULTIMO input deve far uscire dal programma


Genera 5-10 test cases che coprono le principali funzionalità."""
        
        messages = [
            SystemMessage(content=TESTER_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]
        
        try:
            print(f"[TESTER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
            
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
