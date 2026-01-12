# Specifiche Semantiche: Toy-Agent (The Puzzle Rules)

L'analisi semantica di Toy-Agent è progettata per essere rigorosa e "flat" (piatta). Non esistono scope annidati.

## 1. Regola dello SCOPE UNICO (Global Space)
Esiste una sola Tabella dei Simboli (Symbol Table) per l'intero programma.
* **Popolamento:** La tabella viene popolata esclusivamente durante il parsing del blocco `memory:`.
* **Collisioni:** È vietato avere due identificatori con lo stesso nome nell'intero file.
    * *Esempio Errato:* `keep i as whole;` e poi un task con parametro `[i as whole]`.
    * *Soluzione:* I parametri dei task devono avere nomi globalmente univoci (es. `task_sum_param_x`).

## 2. Gestione dei Parametri
I parametri definiti nella firma di un `task` non creano variabili locali.
* **Semantica:** Quando si definisce `task myJob [p1 as whole]`, l'identificatore `p1` deve essere univoco nel programma. Se `p1` esiste già in `memory`, è un errore di collisione.
* **Visibilità:** I parametri sono visibili ovunque (sono tecnicamente globali), ma semanticamente dovrebbero essere usati solo nel task proprietario. L'Agente Refiner deve segnalare warning se un task legge i parametri di un altro task.

## 3. Inferenza di Tipo: DISABILITATA
Non esiste inferenza. Ogni variabile e parametro deve avere un tipo esplicito.
* Assegnazione `x << 5` è valida solo se `x` è stato dichiarato `whole`.
* Assegnazione `x << 5.0` è valida solo se `x` è stato dichiarato `fract`.
* Non c'è casting implicito tra `whole` e `fract`.

## 4. Type Checking
Il controllo dei tipi è statico e rigido.
* **Operatori:**
    * `plus`, `minus`, `times`, `div`: Richiedono operandi omogenei (`whole op whole` -> `whole`, `fract op fract` -> `fract`).
    * `quote`: Supporta solo `plus` (concatenazione).
* **Condizioni:**
    * Le espressioni in `check` e `loop` devono valutare tassativamente a tipo `flag` (`yes`/`no`). Non sono ammessi interi come booleani (es. `if (1)` è errore).

## 5. Main Entry Point
Il programma deve contenere obbligatoriamente un task chiamato `entrypoint` che non accetta parametri. L'esecuzione inizia da lì.