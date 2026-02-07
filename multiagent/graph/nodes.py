# ===========================================================================
#                       NODES - Graph Node Functions
# ===========================================================================
# Funzioni nodo per il grafo LangGraph.
# Ogni funzione riceve lo stato, lo modifica e lo restituisce.
# Include nodi per: Coder (subgraph), Syntax Gate, Tester, Executor, 
# Refiner, Success, Failure.
# ===========================================================================

from typing import Literal

import requests
from langchain_core.messages import SystemMessage

from ..agents.coder import create_coder_agent, CODER_SYSTEM_PROMPT
from ..agents.tester import create_tester_agent
from ..agents.refiner import create_refiner_agent
from ..models import TestResult, ErrorReport, ErrorType
from ..config import (
    MAX_SYNTAX_RETRIES, MAX_TEST_RETRIES, 
    TOY_AGENT_API_URL, EXECUTION_TIMEOUT
)

from .state import AgentState




# ---------------------------------------------------------------------------
#                           HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def _strict_or_numeric_equal(s1: str, s2: str) -> bool:
    """Confronta due stringhe, con tolleranza numerica."""
    if s1 == s2:
        return True
    try:
        return abs(float(s1) - float(s2)) < 1e-5
    except ValueError:
        return False


def _verify_output(actual: str, expected: str) -> bool:
    """
    Verifica se l'output atteso è contenuto nell'output effettivo.
    
    Supporta "Newline Magic String" Strategy:
    Poiché Toy-Agent non può concatenare stringhe e numeri facilmente e aggiunge
    sempre newline, la strategia è:
    1. Stampare il token ">>>" su una riga
    2. Stampare il risultato sulla riga successiva
    
    Il verificatore cerca ">>>" e prende la riga DOPO come valore da testare.
    """
    # 1. Pulizia e Normalizzazione: Rimuove spazi e righe vuote
    actual_lines_raw = [l.strip() for l in actual.splitlines() if l.strip()]
    expected_lines = [l.strip() for l in expected.strip().splitlines() if l.strip()]

    # 2. Estrazione "Magic Values" (>>>)
    #    Se troviamo ">>>", consideriamo valida solo la riga successiva.
    magic_values = []
    i = 0
    while i < len(actual_lines_raw):
        line = actual_lines_raw[i]
        
        # Se la riga è il magic token
        if line.startswith(">>>"):
            # Prendi il valore alla riga successiva (se esiste)
            if i + 1 < len(actual_lines_raw):
                magic_values.append(actual_lines_raw[i+1])
                i += 1 # Salta la riga del valore appena consumata
        i += 1
            
    # Usa solo i valori magici se presenti, altrimenti usa tutto l'output (fallback)
    lines_to_verify = magic_values if magic_values else actual_lines_raw
        
    # Caso base: se non ci aspettiamo nulla, controlliamo se l'output è vuoto
    if not expected_lines:
        return not lines_to_verify
    
    # 3. Verifica Semplificata (Unordered)
    #    Controlliamo semplicemente se tutte le righe attese sono presenti nell'output.
    for expected_line in expected_lines:
        found = False
        for line in lines_to_verify:
            if _strict_or_numeric_equal(line, expected_line):
                found = True
                break
        
        if not found:
            return False
            
    return True


def _parse_code(script: str) -> tuple[bool, str | None]:
    """
    Valida il codice: prova remoto, fallback a locale se necessario.
    
    Returns:
        Tuple (success, error_msg): success=True se sintassi valida, 
        altrimenti error_msg contiene l'errore.
    """
    
    if not TOY_AGENT_API_URL:
        return False, "API URL not configured (TOY_AGENT_API_URL missing)"

    try:
        print(f"[PARSE] 🚀 Parsing remoto")
        response = requests.post(
            f"{TOY_AGENT_API_URL}/parse",
            json={"script": script},
            timeout=EXECUTION_TIMEOUT
        )
        
        # Server error (5xx)
        if response.status_code >= 500:
            return False, f"Server error ({response.status_code})"
            
        # HTML response (Azure sleeping or error page)
        elif "<html" in response.text.lower():
            return False, "API returned HTML (possibly Azure starting up or error page)"
            
        elif response.status_code == 200:
            return True, None
        else:
            # Errore di sintassi (4xx)
            try:
                error_msg = response.json().get("error", "Unknown syntax error")
            except ValueError:
                error_msg = response.text[:200]
            return False, error_msg
            
    except requests.exceptions.RequestException as e:
        return False, f"Connection failed: {e}"


def _execute_code(script: str, inputs: list) -> tuple[str, str | None]:
    """
    Esegue il codice: prova remoto, fallback a locale se necessario.
    
    Returns:
        Tuple (output, error): output è l'output del programma,
        error è None se esecuzione OK, altrimenti contiene l'errore.
    """
    
    if not TOY_AGENT_API_URL:
        return "", "API URL not configured (TOY_AGENT_API_URL missing)"

    try:
        print(f"[EXECUTE] 🚀 Esecuzione remota")
        response = requests.post(
            f"{TOY_AGENT_API_URL}/run",
            json={"script": script, "inputs": inputs},
            timeout=EXECUTION_TIMEOUT
        )
        
        if response.status_code >= 500:
            # Prova a estrarre il messaggio di errore dal JSON
            try:
                err_data = response.json()
                error_msg = err_data.get("error", f"Server error ({response.status_code})")
                output_list = err_data.get("output", [])
                output = "\n".join(output_list) if isinstance(output_list, list) else ""
                return output, error_msg
            except ValueError:
                return "", f"Server error ({response.status_code})"
        
        try:
            resp_data = response.json()
        except ValueError:
            if "<html" in response.text.lower():
                 return "", "API returned HTML (possibly Azure starting up or error page)"
            else:
                return "", f"Invalid response: {response.text[:200]}"
        else:
            output_list = resp_data.get("output", [])
            output = "\n".join(output_list) if isinstance(output_list, list) else str(output_list)
            
            if response.status_code == 200:
                return output, None
            else:
                return output, resp_data.get("error", "Unknown execution error")
                    
    except requests.exceptions.RequestException as e:
        return "", f"Connection failed: {e}"


# ---------------------------------------------------------------------------
#                           CODER SUBGRAPH NODES
# ---------------------------------------------------------------------------

def coder_reasoning_node(state: AgentState) -> dict:
    """
    Nodo di ragionamento del Coder: chiama coder.reason() per tool exploration.
    
    Adapter tra AgentState e CoderAgent.
    """
    coder = create_coder_agent()
    messages = list(state.get("messages", []))
    
    # Inizializza con SystemMessage se vuoto
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + messages
    
    response = coder.reason(messages, state)
    messages.append(response)
    
    return {"messages": messages}


def coder_structuring_node(state: AgentState) -> dict:
    """
    Nodo di strutturazione del Coder: chiama coder.structure() per output JSON.
    
    Adapter tra AgentState e CoderAgent.
    """
    coder = create_coder_agent()
    messages = list(state.get("messages", []))
    
    result = coder.structure(messages)
    
    return {
        "generated_code": result.toy_code,
        "reasoning": result.reasoning,
        "error_report": None,
    }


def after_reasoning(state: AgentState) -> Literal["tools", "structure"]:
    """
    Routing dopo reasoning: se ci sono tool calls -> tools, altrimenti -> structure.
    """
    messages = state.get("messages", [])
    if not messages:
        return "structure"
    
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    return "structure"


# ---------------------------------------------------------------------------
#                           SYNTAX GATE NODE
# ---------------------------------------------------------------------------


def syntax_gate_node(state: AgentState) -> dict:
    """Nodo Syntax Gate: valida il codice con ToyParser."""
    print("[SYNTAX GATE] Validazione sintassi...")
    
    success, error_msg = _parse_code(state["generated_code"])
    
    if success:
        print("[SYNTAX GATE] ✓ Sintassi valida!")
        return {
            "error_report": None,
            "syntax_retry_count": 0
        }
    else:
        retry_count = state["syntax_retry_count"] + 1
        print(f"[SYNTAX GATE] ✗ Errore: {error_msg}")
        print(f"[SYNTAX GATE] Tentativo {retry_count}/{MAX_SYNTAX_RETRIES}")
        return {
            "error_report": ErrorReport(
                error_type=ErrorType.SYNTAX,
                details=error_msg,
                location=None,
                suggestion="Correggi la sintassi del codice."
            ),
            "syntax_retry_count": retry_count
        }


# ---------------------------------------------------------------------------
#                           TESTER NODE
# ---------------------------------------------------------------------------

def tester_node(state: AgentState) -> dict:
    """Nodo Tester: genera test cases black-box."""
    print("[TESTER] Generazione test cases...")
    
    tester = create_tester_agent()
    test_suite = tester.generate_tests(
        state["user_request"],
        state["generated_code"]
    )
    
    test_cases = test_suite.test_cases
    print(f"[TESTER] Generati {len(test_cases)} test cases")
    
    return {"test_cases": test_cases}


# ---------------------------------------------------------------------------
#                           EXECUTOR NODE
# ---------------------------------------------------------------------------

def executor_node(state: AgentState) -> dict:
    """Nodo Executor: esegue i test cases con ToyExecutor."""
    print("[EXECUTOR] Esecuzione test cases...")
    
    results = []
    
    for tc in state["test_cases"]:
        description = tc.description
        inputs = tc.inputs
        expected = tc.expected_output
        
        print(f"[EXECUTOR] Running: {description}")
        
        actual_output, error = _execute_code(state["generated_code"], inputs)
        
        if error:
            results.append(TestResult(
                test_description=description,
                passed=False,
                actual_output=actual_output,
                expected_output=expected,
                error_message=error
            ))
            print(f"[EXECUTOR] ✗ ERROR: {error}")
        else:
            passed = _verify_output(actual_output, expected)
            
            results.append(TestResult(
                test_description=description,
                passed=passed,
                actual_output=actual_output,
                expected_output=expected,
                error_message=None if passed else "Output mismatch"
            ))
            
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"[EXECUTOR] {status}")
            
            if not passed:
                print(f"  [EXPECTED]: {repr(expected)}")
                print(f"  [ACTUAL]  : {repr(actual_output)}")
    
    return {"test_results": results}


# ---------------------------------------------------------------------------
#                           REFINER NODE
# ---------------------------------------------------------------------------

def refiner_node(state: AgentState) -> dict:
    """Nodo Refiner: analizza test falliti e produce error report."""
    print("[REFINER] Analisi errori...")
    
    refiner = create_refiner_agent()
    test_results = state["test_results"]
    
    error_report = refiner.analyze_failure(
        state["user_request"],
        state["generated_code"],
        test_results
    )
    
    retry_count = state["test_retry_count"] + 1
    print(f"[REFINER] Errore: {error_report.error_type}")
    print(f"[REFINER] Suggerimento: {error_report.suggestion}")
    print(f"[REFINER] Tentativo {retry_count}/{MAX_TEST_RETRIES}")
    
    return {
        "error_report": error_report,
        "test_retry_count": retry_count
    }


# ---------------------------------------------------------------------------
#                           FINAL NODES
# ---------------------------------------------------------------------------

def success_node(state: AgentState) -> dict:
    """Nodo Success: tutti i test sono passati."""
    print("[SUCCESS] ✓ Tutti i test passati!")
    
    return {
        "success": True,
        "final_output": f"""✓ Codice generato con successo!

CODICE TOY-AGENT:
{state['generated_code']}

REASONING:
{state['reasoning']}
"""
    }


def failure_node(state: AgentState) -> dict:
    """Nodo Failure: superato il limite di tentativi."""
    if state["syntax_retry_count"] >= MAX_SYNTAX_RETRIES:
        reason = "Troppi errori di sintassi"
    else:
        reason = "Troppi fallimenti nei test"
    
    print(f"[FAILURE] ✗ {reason}")
    
    # Estrai dettagli errore (priorità: error_report > test_results > syntax_error)
    error_report = state.get('error_report')
    failed_tests = [r for r in state.get("test_results", []) if not r.passed]
    
    if error_report:
        error_details = error_report.details or 'N/A'
    elif failed_tests:
        ft = failed_tests[0]
        error_details = f"Test Failed: {ft.test_description}\nExpected: {ft.expected_output}\nActual: {ft.actual_output or 'N/A'}"
    else:
        error_details = 'N/A'
    
    return {
        "success": False,
        "final_output": f"""✗ Generazione fallita: {reason}

Ultimo codice tentato:
{state['generated_code']}

Ultimo errore:
{error_details}
"""
    }
