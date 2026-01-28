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
"""


# ---------------------------------------------------------------------------
#                           CODER AGENT CLASS
# ---------------------------------------------------------------------------

class CoderAgent:
    """
    Agente per la generazione di codice Toy-Agent.
    
    Utilizza LangChain per il tool binding e la gestione dei messaggi.
    I messaggi vengono passati dall'esterno (AgentState) e restituiti aggiornati.
    
    Attributes:
        llm: Modello LLM base
        llm_with_tools: LLM con tools bindati per exploration
        llm_structured: LLM con structured output per generazione finale
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
    
    def _execute_generation_loop(
        self, 
        messages: list, 
        final_prompt_text: str
    ) -> tuple[str, str, list]:
        """
        Gestisce il loop di tool execution e la generazione finale.
        
        Args:
            messages: Lista messaggi corrente
            final_prompt_text: Prompt per generazione strutturata finale
            
        Returns:
            Tuple (code, reasoning, updated_messages)
        """
        while True:
            print(f"[CODER] Attendo {REQUEST_DELAY_SEC}s per rate limit...")
            time.sleep(REQUEST_DELAY_SEC)
            
            response = self.llm_with_tools.invoke(messages)
            
            if response.tool_calls:
                messages.append(response)
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"[CODER] CALLING TOOL: {tool_name} with args: {tool_args}")
                    
                    tool_found = False
                    for tool in CODER_TOOLS:
                        if tool.name == tool_name:
                            result = tool.invoke(tool_args)
                            messages.append(
                                ToolMessage(content=result, tool_call_id=tool_call["id"])
                            )
                            tool_found = True
                            break
                    
                    if not tool_found:
                        available_tools = ", ".join(t.name for t in CODER_TOOLS)
                        error_msg = f"Tool '{tool_name}' non esiste. Tools disponibili: {available_tools}"
                        print(f"[CODER] ⚠ {error_msg}")
                        messages.append(
                            ToolMessage(content=error_msg, tool_call_id=tool_call["id"])
                        )
            else:
                if response.content:
                    messages.append(response)
                break
        
        print("[CODER] Generazione output strutturato finale...")
        
        final_prompt = HumanMessage(content=final_prompt_text)
        messages.append(final_prompt)
        
        try:
            structured_response = self.llm_structured.invoke(messages)
            return structured_response.toy_code, structured_response.reasoning, messages
        except Exception as e:
            print(f"[CODER] ERROR in structured generation: {e}")
            return "", f"Errore generazione strutturata: {e}", messages

    def generate(
        self, 
        messages: list,
        user_request: str, 
        syntax_error: str = None
    ) -> tuple[str, str, list]:
        """
        Genera codice Toy-Agent per la richiesta utente.
        
        Args:
            messages: Lista messaggi corrente (da AgentState)
            user_request: Descrizione del programma da generare
            syntax_error: Errore di sintassi dalla iterazione precedente (opzionale)
        
        Returns:
            Tuple (codice_toy, reasoning, updated_messages)
        """
        # Aggiungi SystemMessage se non presente
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + messages
        
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
        
        messages.append(HumanMessage(content=prompt))
        
        return self._execute_generation_loop(
            messages, 
            "Ora genera il codice finale e la spiegazione usando lo schema richiesto."
        )
    
    def generate_with_error_report(
        self, 
        messages: list,
        user_request: str, 
        error_report
    ) -> tuple[str, str, list]:
        """
        Genera codice correggendo errori runtime/logici dal Refiner.
        
        Args:
            messages: Lista messaggi corrente (da AgentState)
            user_request: Richiesta originale
            error_report: ErrorReport dal Refiner agent
        
        Returns:
            Tuple (codice_toy, reasoning, updated_messages)
        """
        # Aggiungi SystemMessage se non presente
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + messages
            
        prompt = f"""La richiesta originale era: {user_request}

Il codice precedente ha fallito i test con questo errore:

TIPO: {error_report.error_type}
DETTAGLI: {error_report.details}
POSIZIONE: {error_report.location or "N/A"}
SUGGERIMENTO: {error_report.suggestion}

Correggi il codice per risolvere questo problema."""
        
        messages.append(HumanMessage(content=prompt))
        
        return self._execute_generation_loop(
            messages, 
            "Ora genera il codice corretto finale e la spiegazione usando lo schema richiesto."
        )


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
