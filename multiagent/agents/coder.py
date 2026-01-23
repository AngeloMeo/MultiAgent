# ===========================================================================
#                       CODER AGENT - Code Generation
# ===========================================================================
# Agente responsabile della generazione di codice Toy-Agent.
# Utilizza tools per consultare la documentazione on-demand.
# ===========================================================================

import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from ..config import get_llm_config, REQUEST_DELAY_SEC
from ..tools import CODER_TOOLS
from ..models import CoderOutput


# ---------------------------------------------------------------------------
#                           SYSTEM PROMPT
# ---------------------------------------------------------------------------

CODER_SYSTEM_PROMPT = """Sei un esperto programmatore nel linguaggio Toy-Agent.

REGOLA GENERALE:
- NON USARE MAI IL CARATTERE "ի".

REGOLE CRITICHE - LEGGI ATTENTAMENTE:

1. STRUTTURA OBBLIGATORIA:
   - Ogni variabile nel blocco memory: inizia con `keep`
   - Ogni programma ha un task "entrypoint" senza parametri
   - Commenti usano `%` (NON `#`)

2. TIPIZZAZIONE STRETTA - NESSUNA CONVERSIONE:
   - NON esiste conversione tra tipi (whole, fract, quote, flag)
   - NON puoi assegnare un whole a una variabile quote
   - NON puoi concatenare quote + whole

3. OUTPUT DI NUMERI E DATI:
   - FORMATO: SOLO VALORI GREZZI. Niente frasi.
   - VIETATO: `show "Il risultato è";`
   - VIETATO: `show "Input:";`
   - VIETATO: `show "Ecco il numero:";`
   - CONSENTITO: `show result;` (dove result è una variabile)
   - CONSENTITO: `show "Errore";` (solo se è un dato di errore)

   Esempio corretto:
   ```toy
   grab n;
   ... calcolo ...
   show result;
   ```

4. LOOP invece di RICORSIONE:
   La ricorsione NON funziona (scope unico). Usa sempre loop.

5. OPERATORI:
   plus, minus, times, div, is, is_not, under, over, and, or, not

6. FORMATO OUTPUT OBBLIGATORIO:
   - Restituisci il codice SEMPRE all'interno di blocchi markdown:
   ```toy
   memory:
       ...
   end_memory
   ...
   ```
   - Sii conciso. Meno testo, più codice.

7. NESSUN PROMPT DI INPUT:
   - NON STAMPARE MESSAGGI DI INPUT (es. NO `show "Inserisci numero";`)
   - Usa SOLO `grab variabile;`
   - Questo è fondamentale per i test automatici.

8. STRINGHE - NO ESCAPE:
   - Le stringhe usano SOLO doppi apici: "testo"
   - NON usare MAI backslash: NO `\"`, NO `\\`
   - ERRATO: `show "Ciao \"mondo\"";`
   - CORRETTO: `show "Ciao mondo";`

9. CHIAMATA TASK:
   - Sintassi: `nome_task run [arg1, arg2];`
   - NON usare: `call nome_task(arg1, arg2);` (ERRATO!)
   - Esempio: `result << add run [5, 3];`

10. SIGNATURE TASK:
    - OGNI task DEVE avere `-> tipo:` (anche se non ritorna nulla usa `-> whole:`)
    - ERRATO: `task entrypoint [] :`
    - CORRETTO: `task entrypoint [] -> whole:`

11. CONDIZIONALI (check/alt_check):
    - `alt_check` fa parte dello STESSO blocco `check`
    - UN SOLO `close;` alla fine dell'intera catena
    - ERRATO: `check x is 1 then ... close; alt_check x is 2 then`
    - CORRETTO:
      ```
      check x is 1 then
          ...
      alt_check x is 2 then
          ...
      close;
      ```

12. LOOP - NO BREAK:
    - NON esiste l'istruzione `break`.
    - Per uscire da un loop, devi cambiare la condizione del loop stesso (usa un flag).
    - ERRATO: `loop yes do ... if exit break; ... close;`
    - CORRETTO:
      ```toy
      running << yes;
      loop running is yes do
          ...
          check choice is 5 then
              running << no;  % Esce al prossimo controllo
          close;
      close;
      ```

Consulta get_syntax_help("control_flow") per strutture condizionali complesse."""


# ---------------------------------------------------------------------------
#                           CODER AGENT CLASS
# ---------------------------------------------------------------------------

class CoderAgent:
    """
    Agente per la generazione di codice Toy-Agent.
    
    Utilizza LangChain per il tool binding e la gestione dei messaggi.
    Mantiene la history delle conversazioni per il feedback loop.
    
    Attributes:
        llm: Modello LLM con tools bindati
        messages: Storia dei messaggi per contesto
    """
    
    def __init__(self):
        """Inizializza l'agente con il modello e i tools."""
        config = get_llm_config()
        
        self.llm = ChatGoogleGenerativeAI(
            model=config["model"],
            temperature=config["temperature"],
            google_api_key=config["google_api_key"],
        )
        
        self.llm_with_tools = self.llm.bind_tools(CODER_TOOLS)
        
        self.llm_structured = self.llm.with_structured_output(CoderOutput)
        
        self.messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)]
    
    def generate(self, user_request: str, syntax_error: str = None) -> tuple[str, str]:
        """
        Genera codice Toy-Agent per la richiesta utente.
        
        Args:
            user_request: Descrizione del programma da generare
            syntax_error: Errore di sintassi dalla iterazione precedente (opzionale)
        
        Returns:
            Tuple (codice_toy, reasoning) con il codice generato e spiegazione.
        """
        # Costruisci il messaggio utente
        if syntax_error:
            prompt = f"""Il codice precedente ha un errore di sintassi:

                        ERRORE: {syntax_error}

                        Correggi il codice per risolvere questo errore."""
        else:
            prompt = f"""Genera un programma Toy-Agent che: {user_request}

                        Ricorda di:
                        1. Consultare la documentazione con get_syntax_help prima di scrivere
                        2. Includere il task entrypoint obbligatorio
                        3. Dichiarare le variabili nel blocco memory:
                        4. Terminare ogni statement con ;"""
        
        self.messages.append(HumanMessage(content=prompt))
        
        # FASE 1: Loop per gestire tool calls (Esplorazione)
        while True:
            print(f"[CODER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
            
            # Invoca modello con tools
            response = self.llm_with_tools.invoke(self.messages)
            
            # Se ci sono tool calls, eseguile e continua il loop
            if response.tool_calls:
                self.messages.append(response) # Aggiungi l'intenzione di chiamare tool alla history
                
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"[CODER] CALLING TOOL: {tool_name} with args: {tool_args}")
                    
                    # Esegui il tool appropriato
                    for tool in CODER_TOOLS:
                        if tool.name == tool_name:
                            result = tool.invoke(tool_args)
                            self.messages.append(
                                ToolMessage(content=result, tool_call_id=tool_call["id"])
                            )
                            break
                            
            else:
                # Nessun tool call, l'LLM ha finito di esplorare
                # Aggiungiamo la risposta testuale (se c'è) alla history come "pensiero"
                if response.content:
                     self.messages.append(response)
                break
        
        # FASE 2: Generazione Strutturata Finale
        print("[CODER] Generazione output strutturato finale...")
        
        # Chiediamo esplicitamente l'output finale usando lo schema
        final_prompt = HumanMessage(content="Ora genera il codice finale e la spiegazione usando lo schema richiesto.")
        self.messages.append(final_prompt)
        
        try:
            structured_response = self.llm_structured.invoke(self.messages)
            
            return structured_response.toy_code, structured_response.reasoning
            
        except Exception as e:
            print(f"[CODER] ERROR in structured generation: {e}")
            return "", f"Errore generazione strutturata: {e}"
    
    def generate_with_error_report(self, user_request: str, error_report) -> tuple[str, str]:
        """
        Genera codice correggendo errori runtime/logici dal Refiner.
        
        Args:
            user_request: Richiesta originale
            error_report: ErrorReport dal Refiner agent
        
        Returns:
            Tuple (codice_toy, reasoning) con il codice corretto.
        """
        prompt = f"""La richiesta originale era: {user_request}

Il codice precedente ha fallito i test con questo errore:

TIPO: {error_report.error_type}
DETTAGLI: {error_report.details}
POSIZIONE: {error_report.location or "N/A"}
SUGGERIMENTO: {error_report.suggestion}

Correggi il codice per risolvere questo problema."""
        
        self.messages.append(HumanMessage(content=prompt))
        
        # FASE 1: Loop per gestire tool calls (Esplorazione)
        while True:
            # Rate limiting
            print(f"[CODER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
            
            response = self.llm_with_tools.invoke(self.messages)
            
            if response.tool_calls:
                self.messages.append(response)
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"[CODER] CALLING TOOL: {tool_name} with args: {tool_args}")
                    
                    for tool in CODER_TOOLS:
                        if tool.name == tool_name:
                            result = tool.invoke(tool_args)
                            self.messages.append(
                                ToolMessage(content=result, tool_call_id=tool_call["id"])
                            )
                            break
            else:
                if response.content:
                    self.messages.append(response)
                break
        
        # FASE 2: Generazione Strutturata Finale
        print("[CODER] Generazione output strutturato finale (Error Loop)...")
        
        final_prompt = HumanMessage(content="Ora genera il codice corretto finale e la spiegazione usando lo schema richiesto.")
        self.messages.append(final_prompt)
        
        try:
            structured_response = self.llm_structured.invoke(self.messages)
            return structured_response.toy_code, structured_response.reasoning
        except Exception as e:
            print(f"[CODER] ERROR in structured generation: {e}")
            return "", f"Errore generazione strutturata: {e}"
    



# ---------------------------------------------------------------------------
#                           FACTORY FUNCTION
# ---------------------------------------------------------------------------

def create_coder_agent() -> CoderAgent:
    """
    Factory function per creare un'istanza del Coder Agent.
    
    Returns:
        CoderAgent: Nuova istanza dell'agente.
    """
    return CoderAgent()
