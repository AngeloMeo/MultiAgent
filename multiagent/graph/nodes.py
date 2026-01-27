# ===========================================================================
#                       NODES - Graph Node Functions
# ===========================================================================
# Funzioni per gestire la chiamata di ogni nodo del grafo LangGraph.
# Ogni funzione riceve lo stato, lo modifica e lo restituisce.
# ===========================================================================

import requests

from ..agents.coder import get_coder_agent
from ..agents.tester import create_tester_agent
from ..agents.refiner import create_refiner_agent
from ..models import TestResult
from ..config import MAX_SYNTAX_RETRIES, MAX_TEST_RETRIES, TOY_AGENT_API_URL, EXECUTION_TIMEOUT

from .state import AgentState

# Import opzionale del modulo di esecuzione locale
try:
    from .local_executor import local_parse, local_execute
    LOCAL_EXECUTOR_AVAILABLE = True
except ImportError:
    LOCAL_EXECUTOR_AVAILABLE = False
    local_parse = None
    local_execute = None


# ---------------------------------------------------------------------------
#                           HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def _strict_or_numeric_equal(s1: str, s2: str) -> bool:
    """Confronta due stringhe, con tolleranza numerica."""
    if s1 == s2:
        return True
    try:
        return abs(float(s1) - float(s2)) < 1e-9
    except ValueError:
        return False


def _verify_output(actual: str, expected: str) -> bool:
    """
    Verifica se l'output atteso è contenuto nell'output effettivo.
    
    Usa matching permissivo: cerca ogni riga expected come sottosequenza
    NON CONTIGUA nell'actual. Questo permette al programma di stampare
    "rumore" (menu, prompt) tra i valori che ci interessano.
    
    Esempio:
        expected: "15\\n0"
        actual: "1\\n2\\n3\\n4\\n15\\n1\\n2\\n3\\n4\\n0"
        -> True (15 e 0 appaiono in ordine, anche se non adiacenti)
    """
    expected_lines = [l.strip() for l in expected.strip().splitlines() if l.strip()]
    actual_lines = [l.strip() for l in actual.splitlines() if l.strip()]
    
    if not expected_lines:
        return not actual_lines
    
    # Cerca ogni expected line come sottosequenza (non contigua) nell'actual
    actual_idx = 0
    for expected_line in expected_lines:
        found = False
        while actual_idx < len(actual_lines):
            if _strict_or_numeric_equal(actual_lines[actual_idx], expected_line):
                found = True
                actual_idx += 1  # Avanza per cercare la prossima expected
                break
            actual_idx += 1
        
        if not found:
            # Fallback: cerca ovunque (non in ordine) per valori critici
            if not any(_strict_or_numeric_equal(al, expected_line) for al in actual_lines):
                return False
    
    return True


def _parse_code(script: str) -> tuple[bool, str | None]:
    """
    Valida il codice: prova remoto, fallback a locale se necessario.
    
    Returns:
        Tuple (success, error_msg): success=True se sintassi valida, 
        altrimenti error_msg contiene l'errore.
    """
    # Prova remoto
    if TOY_AGENT_API_URL:
        try:
            print(f"[PARSE] 🚀 Parsing remoto")
            response = requests.post(
                f"{TOY_AGENT_API_URL}/parse",
                json={"script": script},
                timeout=EXECUTION_TIMEOUT
            )
            
            # Server error (5xx) -> fallback
            if response.status_code >= 500:
                print(f"[PARSE] ⚠ Server error ({response.status_code}), fallback a locale...")
            # HTML response (Azure sleeping) -> fallback
            elif "<html" in response.text.lower():
                print("[PARSE] ⚠ API risponde con HTML, fallback a locale...")
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
            print(f"[PARSE] ⚠ Connessione fallita ({e}), fallback a locale...")
    
    # Fallback locale
    if not LOCAL_EXECUTOR_AVAILABLE:
        return False, "API non disponibile e modulo locale non presente"
    
    return local_parse(script)


def _execute_code(script: str, inputs: list) -> tuple[str, str | None]:
    """
    Esegue il codice: prova remoto, fallback a locale se necessario.
    
    Returns:
        Tuple (output, error): output è l'output del programma,
        error è None se esecuzione OK, altrimenti contiene l'errore.
    """
    # Prova remoto
    if TOY_AGENT_API_URL:
        try:
            print(f"[EXECUTE] 🚀 Esecuzione remota")
            response = requests.post(
                f"{TOY_AGENT_API_URL}/run",
                json={"script": script, "inputs": inputs},
                timeout=EXECUTION_TIMEOUT
            )
            
            if response.status_code >= 500:
                print(f"[EXECUTE] ⚠ Server error ({response.status_code}), fallback a locale...")
            else:
                try:
                    resp_data = response.json()
                except ValueError:
                    if "<html" in response.text.lower():
                        print("[EXECUTE] ⚠ API risponde con HTML, fallback a locale...")
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
            print(f"[EXECUTE] ⚠ Connessione fallita ({e}), fallback a locale...")
    
    # Fallback locale
    if not LOCAL_EXECUTOR_AVAILABLE:
        return "", "API non disponibile e modulo locale non presente"
    
    return local_execute(script, inputs)


# ---------------------------------------------------------------------------
#                           CODER NODE
# ---------------------------------------------------------------------------

def coder_node(state: AgentState) -> dict:
    """Nodo Coder: genera o corregge codice Toy-Agent."""
    print("[CODER] Generazione codice...")
    
    coder = get_coder_agent()
    
    if state.get("error_report"):
        code, reasoning = coder.generate_with_error_report(
            state["user_request"], 
            state["error_report"]
        )
    elif state.get("syntax_error"):
        code, reasoning = coder.generate(
            state["user_request"],
            syntax_error=state["syntax_error"]
        )
    else:
        code, reasoning = coder.generate(state["user_request"])
    
    print(f"[CODER] Codice generato ({len(code)} chars)")
    
    return {
        "generated_code": code,
        "reasoning": reasoning,
        "syntax_error": None,
        "error_report": None,
        **({"syntax_retry_count": 0} if state.get("error_report") else {})
    }


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
            "syntax_error": None,
            "syntax_retry_count": state["syntax_retry_count"]
        }
    else:
        retry_count = state["syntax_retry_count"] + 1
        print(f"[SYNTAX GATE] ✗ Errore: {error_msg}")
        print(f"[SYNTAX GATE] Tentativo {retry_count}/{MAX_SYNTAX_RETRIES}")
        return {
            "syntax_error": error_msg,
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
        error_details = getattr(error_report, 'details', None) or error_report.get('details', 'N/A')
    elif failed_tests:
        ft = failed_tests[0]
        error_details = f"Test Failed: {ft.test_description}\nExpected: {ft.expected_output}\nActual: {ft.actual_output or 'N/A'}"
    else:
        error_details = state.get('syntax_error') or 'N/A'
    
    return {
        "success": False,
        "final_output": f"""✗ Generazione fallita: {reason}

Ultimo codice tentato:
{state['generated_code']}

Ultimo errore:
{error_details}
"""
    }
