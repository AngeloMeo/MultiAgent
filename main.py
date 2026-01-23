# ===========================================================================
#                       MAIN - Entry Point
# ===========================================================================
# Entry point del sistema multi-agente per code generation.
# Esegui con: python main.py "descrizione del programma"
# ===========================================================================

import sys
import argparse

from multiagent.graph.graph import run_graph


def main():
    """
    Entry point principale del sistema.
    
    Usage:
        python main.py "Scrivi un programma che calcola il fattoriale di 5"
        python main.py --interactive
    """
    parser = argparse.ArgumentParser(
        description="Multi-Agent Toy-Agent Code Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python main.py "Calcola la somma di due numeri"
  python main.py "Stampa i numeri da 1 a 10"
  python main.py --interactive
        """
    )
    
    parser.add_argument(
        "request",
        nargs="?",
        help="Descrizione del programma da generare"
    )
    
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Modalità interattiva (inserisci richieste una alla volta)"
    )
    
    args = parser.parse_args()
    
    if args.interactive:
        print("=" * 60)
        print("MULTI-AGENT TOY-AGENT CODE GENERATOR")
        print("Modalità Interattiva - Digita 'exit' per uscire")
        print("=" * 60)
        
        while True:
            try:
                request = input("\nRichiesta: ").strip()
                if request.lower() in ("exit", "quit", "q"):
                    print("Arrivederci!")
                    break
                if not request:
                    continue
                
                # Reset coder agent per evitare context confusion
                from multiagent.graph.nodes import _coder_agent
                import multiagent.graph.nodes as nodes_module
                nodes_module._coder_agent = None
                    
                result = run_graph(request)
                
            except KeyboardInterrupt:
                print("\n\nInterrotto. Arrivederci!")
                break
            except Exception as e:
                print(f"\nErrore: {e}")
                continue
            
    
    elif args.request:
        # Singola richiesta da linea di comando
        result = run_graph(args.request)
        
        sys.exit(0 if result.get("success") else 1)
    
    else:
        # Nessun argomento -> Menu Demo Tasks
        print("=" * 60)
        print("MULTI-AGENT TOY-AGENT CODE GENERATOR - DEMO MODE")
        print("=" * 60)
        
        DEMO_TASKS = [
            "Calcola il fattoriale di un numero N inserito dall'utente (es. 5 = 120)",
            "Leggi 3 numeri e stampa il maggiore",
            "Calcola la somma dei primi N numeri interi (es. N=5 -> Somma=15)",
            "Verifica se un numero N inserito dall'utente è pari (stampa 1) o dispari (stampa 0)",
            "Moltiplicazione tramite somme ripetute: leggi A e B, calcola A * B sommando A per B volte",
            "Calcolatrice: leggi la scelta operazione (1=somma, 2=sottrazione, 3=moltiplicazione, 4=divisione), poi leggi due numeri fract e stampa il risultato. Usa almeno 2 task ausiliari.",
            "COMPLESSO: Calcolatrice con Menu Interattivo. Richiede: menu scelta, gestione input ibridi, ciclo continuo, almeno 2 task, le 4 operazioni implementate."
        ]
        
        print("\nScegli un task demo da eseguire:")
        for i, task in enumerate(DEMO_TASKS, 1):
            print(f"{i}. {task}")
        print("0. Esci")
        
        try:
            choice = input("\nScelta [1-7]: ").strip()
            if choice == "0":
                print("Arrivederci!")
                sys.exit(0)
            
            if choice.isdigit() and 1 <= int(choice) <= len(DEMO_TASKS):
                idx = int(choice) - 1
                selected_task = DEMO_TASKS[idx]
                print(f"\nEsecuzione task: '{selected_task}'")
                result = run_graph(selected_task)
            else:
                print("Scelta non valida.")
                sys.exit(1)
                
        except KeyboardInterrupt:
            print("\nInterrotto.")
            sys.exit(0)


if __name__ == "__main__":
    main()
