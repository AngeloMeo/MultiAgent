# ===========================================================================
#                       CODER AGENT - Code Generation
# ===========================================================================
# Agente responsabile della generazione di codice Toy-Agent.
# Utilizza tools per consultare la documentazione on-demand.
# Espone metodi reason() e structure() per il sottografo LangGraph.
# ===========================================================================

import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage

from ..config import get_llm_config, REQUEST_DELAY_SEC
from ..tools import CODER_TOOLS
from ..models import CoderOutput, ErrorType


# ---------------------------------------------------------------------------
#                           SYSTEM PROMPT
# ---------------------------------------------------------------------------

CODER_SYSTEM_PROMPT = """Sei un esperto programmatore nel linguaggio Toy-Agent.

AZIONE OBBLIGATORIA:
Prima di scrivere QUALSIASI codice, DEVI consultare la documentazione:
1. get_syntax_help("limitations") - Leggi SEMPRE questo per primo!
2. get_syntax_help("general") - Per la struttura base del programma

=== REGOLA CRITICA SULL'OUTPUT (MAGIC STRING) ===

Il sistema di test cerca una "Magic String" per identificare l'output corretto.
Poiché Toy-Agent non supporta concatenazione tra stringhe e numeri, DEVI usare questo pattern su DUE RIGHE:

PATTERN OBBLIGATORIO:
show ">>>";     % Magic string su una riga
show result;    % Valore sulla riga successiva

ESEMPI CORRETTI:
```
% Stampa intero
show ">>>";
show 120;

% Stampa da variabile
show ">>>";
show result;

% Stampa calcolo
show ">>>";
show (a plus b);
```

VIETATO (Causa Errore di Sintassi o Runtime):
- show ">>> " + result;    (ERRORE: Non puoi sommare stringa e numero)
- show ">>> " plus result; (ERRORE: Sintassi non valida)
- show result;             (ERRORE: Manca la magic string prima)

PUOI stampare testo descrittivo (Menu, Prompt) liberamente, ma il risultato deve seguire il pattern.

ESEMPIO MENU/CALCOLATRICE:
```
show "1. Somma";
show "2. Sottrai";
grab choice;
...
% Calcolo risultato in 'res'
show "Risultato finale:";
show ">>>";
show res;        % QUESTO è quello che il test legge!
```

=== STRUMENTI DISPONIBILI (IMPORTANTISSIMO) ===
HAI SOLO QUESTI DUE TOOL:
1. `get_syntax_help(topic)`: Per leggere la documentazione
2. `get_full_grammar()`: Per la grammatica formale

NON ESISTE NESSUN TOOL PER ESEGUIRE IL CODICE!
- NON provare a chiamare `run_code`, `execute`, `test_code` o simili.
- NON provare a verificare se il codice funziona eseguendolo.
- L'esecuzione viene fatta esternamente DOPO che hai generato il codice strutturato.

=== ALTRE REGOLE ===
- NO carattere armeno "ի"
- NO escape nelle stringhe (\\', \\", \\\\)
- NO ricorsione (i parametri sono globali)
- Commenti con % (NON #)
"""


# ---------------------------------------------------------------------------
#                           CODER AGENT CLASS
# ---------------------------------------------------------------------------

class CoderAgent:
    """
    Agente per la generazione di codice Toy-Agent.
    
    Utilizza LangChain per il tool binding e la gestione dei messaggi.
    Espone due metodi principali per il sottografo:
    - reason(): Invoca LLM con tools per esplorazione
    - structure(): Genera output strutturato finale
    
    Attributes:
        llm_with_tools: LLM con tools bindati per esplorazione
        llm_structured: LLM con structured output per generazione finale
    """
    
    def __init__(self):
        """Inizializza l'agente con il modello e i tools."""
        config = get_llm_config()
        
        base_llm = ChatGoogleGenerativeAI(
            model=config["model"],
            temperature=config["temperature"],
            google_api_key=config["google_api_key"],
        )
        
        self.llm_with_tools = base_llm.bind_tools(CODER_TOOLS)
        
        self.llm_structured = base_llm.with_structured_output(CoderOutput)
    
    def build_prompt(self, state: dict) -> str | None:
        """
        Costruisce il prompt appropriato in base allo stato.
        
        Args:
            state: AgentState corrente (dizionario)
        
        Returns:
            Stringa prompt da inviare all'LLM, o None se non serve nuovo prompt.
        """
        messages = state.get("messages", [])
        err = state.get("error_report")
        
        # Caso 1: C'è un errore da correggere (SYNTAX, RUNTIME, o LOGICAL)
        if err is not None:
            error_intro = {
                ErrorType.SYNTAX: "Il codice precedente ha un errore di sintassi",
                ErrorType.RUNTIME: "Il codice precedente ha causato un errore di esecuzione",
                ErrorType.LOGICAL: "Il codice precedente ha fallito i test",
            }.get(err.error_type, "Il codice precedente ha un errore")
            
            return f"""La richiesta originale era: {state['user_request']}

{error_intro}:

TIPO: {err.error_type.value}
DETTAGLI: {err.details}
POSIZIONE: {err.location or "N/A"}
SUGGERIMENTO: {err.suggestion}

Correggi il codice per risolvere questo problema."""
        
        # Caso 2: Prima generazione (no errori)
        if len(messages) <= 1:
            return f"""Genera un programma Toy-Agent che: {state['user_request']}

Ricorda di:
1. Consultare la documentazione con get_syntax_help prima di scrivere
2. Includere il task entrypoint obbligatorio
3. Dichiarare le variabili nel blocco memory:
4. Terminare ogni statement con ;"""
        # Caso 3: Dopo tool call
        return None
    
    def reason(self, messages: list, state: dict) -> AIMessage:
        """
        Esegue un passo di ragionamento con tool calls.
        
        Args:
            messages: Lista messaggi corrente
            state: AgentState per costruire prompt
        
        Returns:
            AIMessage: Risposta dell'LLM (può contenere tool_calls)
        """
        if REQUEST_DELAY_SEC != 0:
            print(f"[CODER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
        
        prompt_text = self.build_prompt(state)
        if prompt_text:
            messages.append(HumanMessage(content=prompt_text))
        
        response = self.llm_with_tools.invoke(messages)
        
        if response.tool_calls:
            for tc in response.tool_calls:
                print(f"[CODER] CALLING TOOL: {tc['name']} with args: {tc['args']}")
        
        return response
    
    def structure(self, messages: list) -> CoderOutput:
        """
        Genera output strutturato finale.
        
        Args:
            messages: Lista messaggi della conversazione
        
        Returns:
            CoderOutput: Output strutturato con toy_code e reasoning
        """
        print("[CODER] Generazione output strutturato finale...")
        if REQUEST_DELAY_SEC != 0:
            print(f"[CODER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
        
        final_prompt = HumanMessage(
            content="Ora genera il codice finale e la spiegazione usando lo schema JSON richiesto."
        )
        
        try:
            response = self.llm_structured.invoke(messages + [final_prompt])
            print(f"[CODER] Codice generato ({len(response.toy_code)} chars)")
            return response
        except Exception as e:
            print(f"[CODER] ERROR in structured generation: {e}")
            return CoderOutput(toy_code="", reasoning=f"Errore generazione strutturata: {e}")


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


# ---------------------------------------------------------------------------
#                           EXPORTS
# ---------------------------------------------------------------------------

__all__ = ["CODER_SYSTEM_PROMPT", "CoderAgent", "create_coder_agent"]
