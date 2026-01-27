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

AZIONE OBBLIGATORIA:
Prima di scrivere QUALSIASI codice, DEVI consultare la documentazione:
1. get_syntax_help("limitations") - Leggi SEMPRE questo per primo!
2. get_syntax_help("general") - Per la struttura base del programma

=== REGOLA CRITICA SULL'OUTPUT ===

I programmi Toy-Agent vengono testati automaticamente confrontando l'output.
DEVI stampare SOLO i valori risultanti, MAI testo descrittivo.

VIETATO (causa SEMPRE fallimento dei test):
- show "Menu:";
- show "Inserisci un numero:";
- show "Risultato:";
- show "Scelta:";
- show "Errore:";
- QUALSIASI show con testo che descrive cosa sta per succedere

PERMESSO (solo questi pattern):
- show result;              % Stampa il valore numerico
- show 0;                   % Stampa un letterale
- grab choice;              % Leggi input SENZA prompt prima

ESEMPIO MENU/CALCOLATRICE:
```
% SBAGLIATO - Fallirà SEMPRE i test:
show "1. Somma";
show "2. Sottrai";
grab choice;

% CORRETTO - Solo valori:
grab choice;
grab num1;
grab num2;
show result;
```

=== ALTRE REGOLE ===
- NO carattere armeno "ի"
- NO escape nelle stringhe (\\', \\", \\\\)
- NO ricorsione (i parametri sono globali)
- Commenti con % (NON #)

FORMATO RISPOSTA:
Restituisci il codice in blocchi markdown ```toy ... ```"""


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
    
    def _execute_generation_loop(self, final_prompt_text: str) -> tuple[str, str]:
        """
        Helper method che gestisce il loop di tool execution e la generazione finale.
        """
        while True:
            print(f"[CODER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
            
            response = self.llm_with_tools.invoke(self.messages)
            
            if response.tool_calls:
                self.messages.append(response)
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"[CODER] CALLING TOOL: {tool_name} with args: {tool_args}")
                    
                    tool_found = False
                    for tool in CODER_TOOLS:
                        if tool.name == tool_name:
                            result = tool.invoke(tool_args)
                            self.messages.append(
                                ToolMessage(content=result, tool_call_id=tool_call["id"])
                            )
                            tool_found = True
                            break
                    
                    if not tool_found:
                        available_tools = ", ".join(t.name for t in CODER_TOOLS)
                        error_msg = f"Tool '{tool_name}' non esiste. Tools disponibili: {available_tools}"
                        print(f"[CODER] ⚠ {error_msg}")
                        self.messages.append(
                            ToolMessage(content=error_msg, tool_call_id=tool_call["id"])
                        )
            else:
                if response.content:
                     self.messages.append(response)
                break
        
        print("[CODER] Generazione output strutturato finale...")
        
        final_prompt = HumanMessage(content=final_prompt_text)
        self.messages.append(final_prompt)
        
        try:
            structured_response = self.llm_structured.invoke(self.messages)
            return structured_response.toy_code, structured_response.reasoning
        except Exception as e:
            print(f"[CODER] ERROR in structured generation: {e}")
            return "", f"Errore generazione strutturata: {e}"

    def generate(self, user_request: str, syntax_error: str = None) -> tuple[str, str]:
        """
        Genera codice Toy-Agent per la richiesta utente.
        
        Args:
            user_request: Descrizione del programma da generare
            syntax_error: Errore di sintassi dalla iterazione precedente (opzionale)
        
        Returns:
            Tuple (codice_toy, reasoning) con il codice generato e spiegazione.
        """
        
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
        
        return self._execute_generation_loop("Ora genera il codice finale e la spiegazione usando lo schema richiesto.")
    
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
        
        return self._execute_generation_loop("Ora genera il codice corretto finale e la spiegazione usando lo schema richiesto.")


# ---------------------------------------------------------------------------
#                           FACTORY FUNCTION
# ---------------------------------------------------------------------------

_CODER_INSTANCE = None

def get_coder_agent() -> CoderAgent:
    """
    Factory function per creare un'istanza Singleton del Coder Agent.
    
    Returns:
        CoderAgent: L'istanza condivisa dell'agente.
    """
    global _CODER_INSTANCE
    if _CODER_INSTANCE is None:
        _CODER_INSTANCE = CoderAgent()
    return _CODER_INSTANCE
