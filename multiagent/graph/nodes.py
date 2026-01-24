# ===========================================================================
#                       NODES - Graph Node Functions
# ===========================================================================
# Funzioni per ogni nodo del grafo LangGraph.
# Ogni funzione riceve lo stato, lo modifica e lo restituisce.
# ===========================================================================

import sys
import os
import requests

from ..agents.coder import create_coder_agent
from ..agents.tester import create_tester_agent
from ..agents.refiner import create_refiner_agent
from ..models import ErrorReport, TestResult
from ..config import MAX_SYNTAX_RETRIES, MAX_TEST_RETRIES, TOY_AGENT_API_URL

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
    Usa matching permissivo (sottosequenza) con tolleranza numerica.
    """
    expected_lines = [l.strip() for l in expected.strip().splitlines() if l.strip()]
    actual_lines = [l.strip() for l in actual.splitlines() if l.strip()]
    
    if not expected_lines:
        return not actual_lines
    
    # Cerca sequenza expected dentro actual
    for i in range(len(actual_lines) - len(expected_lines) + 1):
        match = True
        for j in range(len(expected_lines)):
            if not _strict_or_numeric_equal(actual_lines[i + j], expected_lines[j]):
                match = False
                break
        if match:
            return True
    
    # Fallback: exact match
    return actual == expected.strip()


# ---------------------------------------------------------------------------
#                           CODER NODE
# ---------------------------------------------------------------------------

_coder_agent = None

def get_coder_agent():
    """Singleton per il Coder Agent."""
    global _coder_agent
    if _coder_agent is None:
        _coder_agent = create_coder_agent()
    return _coder_agent


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
        "error_report": None
    }


# ---------------------------------------------------------------------------
#                           SYNTAX GATE NODE
# ---------------------------------------------------------------------------

def syntax_gate_node(state: AgentState) -> dict:
    """Nodo Syntax Gate: valida il codice con ToyParser."""
    print("[SYNTAX GATE] Validazione sintassi...")

    if TOY_AGENT_API_URL:
        print(f"[SYNTAX GATE] Validazione REMOTA su {TOY_AGENT_API_URL}...")
        try:
            response = requests.post(
                f"{TOY_AGENT_API_URL}/parse",
                json={"script": state["generated_code"]},
                timeout=10
            )
            
            if response.status_code == 200:
                print("[SYNTAX GATE] ✓ Sintassi valida (Remota)!")
                return {
                    "syntax_error": None,
                    "syntax_retry_count": state["syntax_retry_count"]
                }
            else:
                try:
                    err_data = response.json()
                    error_msg = err_data.get("error", "Unknown remote syntax error")
                except (ValueError, KeyError):
                    error_msg = response.text
                raise Exception(error_msg)

        except Exception as e:
            error_msg = str(e)
            retry_count = state["syntax_retry_count"] + 1
            
            print(f"[SYNTAX GATE] ✗ Errore Remoto: {error_msg}")
            print(f"[SYNTAX GATE] Tentativo {retry_count}/{MAX_SYNTAX_RETRIES}")
            
            return {
                "syntax_error": error_msg,
                "syntax_retry_count": retry_count
            }

    # Fallback: esecuzione locale
    if not LOCAL_EXECUTOR_AVAILABLE:
        error_msg = "TOY_AGENT_API_URL non configurato e modulo locale non disponibile"
        print(f"[SYNTAX GATE] ✗ {error_msg}")
        return {
            "syntax_error": error_msg,
            "syntax_retry_count": state["syntax_retry_count"] + 1
        }
    
    print("[SYNTAX GATE] Validazione LOCALE...")
    success, error_msg = local_parse(state["generated_code"])
    
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

    if TOY_AGENT_API_URL:
        print(f"[EXECUTOR] Esecuzione REMOTA su {TOY_AGENT_API_URL}...")
        results = []
        
        for tc in state["test_cases"]:
            description = tc.description
            inputs = tc.inputs
            expected = tc.expected_output
            
            print(f"[EXECUTOR] Remote Running: {description}")
            
            try:
                response = requests.post(
                    f"{TOY_AGENT_API_URL}/run",
                    json={
                        "script": state["generated_code"],
                        "inputs": inputs
                    },
                    timeout=10
                )
                
                resp_data = response.json()
                
                if response.status_code == 200:
                    actual_output_list = resp_data.get("output", [])
                    actual_output = "\n".join(actual_output_list) if isinstance(actual_output_list, list) else str(actual_output_list)
                    
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

                else:
                    error_msg = resp_data.get("error", "Unknown remote error")
                    output_list = resp_data.get("output", [])
                    partial_output = "\n".join(output_list)
                    
                    results.append(TestResult(
                        test_description=description,
                        passed=False,
                        actual_output=partial_output,
                        expected_output=expected,
                        error_message=error_msg
                    ))
                    print(f"[EXECUTOR] ✗ ERROR: {error_msg}")

            except Exception as e:
                results.append(TestResult(
                    test_description=description,
                    passed=False,
                    actual_output="",
                    expected_output=expected,
                    error_message=str(e)
                ))
                print(f"[EXECUTOR] ✗ CONNECTION ERROR: {str(e)}")
        
        return {"test_results": results}

    # Fallback: esecuzione locale
    if not LOCAL_EXECUTOR_AVAILABLE:
        error_msg = "TOY_AGENT_API_URL non configurato e modulo locale non disponibile"
        print(f"[EXECUTOR] ✗ {error_msg}")
        return {
            "test_results": [TestResult(
                test_description="Setup Error",
                passed=False,
                actual_output="",
                expected_output="",
                error_message=error_msg
            )]
        }
    
    print("[EXECUTOR] Esecuzione LOCALE...")
    results = []
    
    for tc in state["test_cases"]:
        description = tc.description
        inputs = tc.inputs
        expected = tc.expected_output
        
        print(f"[EXECUTOR] Running: {description}")
        
        actual_output, error = local_execute(state["generated_code"], inputs)
        
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
    
    error_report = state.get('error_report')
    if error_report and isinstance(error_report, ErrorReport):
        error_details = error_report.details
    elif isinstance(error_report, dict):
        error_details = error_report.get('details', 'N/A')
    elif state.get("test_results"):
        failed_tests = [res for res in state["test_results"] if not res.passed]
        if failed_tests:
            ft = failed_tests[0]
            error_details = f"Test Failed: {ft.test_description}\nMessaggio: {ft.error_message or 'Output mismatch'}\nExpected: {ft.expected_output}\nActual: {ft.actual_output or 'N/A'}"
        else:
            error_details = "Test logic failed without specific error message"
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
