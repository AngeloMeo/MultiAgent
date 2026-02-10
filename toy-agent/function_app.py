import azure.functions as func
import logging
import json
import dataclasses
from enum import Enum

# Ensure we can import toy_agent
from toy_agent import ToyExecutor, ToyParser, ASTNode

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if isinstance(o, Enum):
            return o.name
        return super().default(o)

@app.route(route="run")
def run_toy_agent(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Toy Agent RUN trigger function processed a request.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body.", status_code=400)

    script = req_body.get('script')
    inputs = req_body.get('inputs', [])

    if not script:
        return func.HttpResponse("Please pass a 'script'", status_code=400)

    output_buffer = []
    input_queue = list(inputs)
    input_queue.reverse()

    def custom_input(prompt: str = ""):
        if not input_queue:
            # Invece di RuntimeError (500), solleviamo un'eccezione che sarà
            # gestita per restituire un errore chiaro ma non un crash server.
            raise ValueError("Insufficient Inputs: Script requested input but queue is empty.")
        return input_queue.pop()

    def custom_output(text: str):
        output_buffer.append(text)

    try:
        executor = ToyExecutor(script=None, input_handler=custom_input, output_handler=custom_output)
        executor.load_script(script)
        
        return func.HttpResponse(
             json.dumps({"output": output_buffer, "status": "success"}),
             mimetype="application/json",
             status_code=200
        )
    except Exception as e:
        status = 500
        if isinstance(e, ValueError):
            status = 400 # Client error (input insufficient)
            
        return func.HttpResponse(
             json.dumps({"output": output_buffer, "status": "error", "error": str(e)}),
             mimetype="application/json",
             status_code=status
        )

@app.route(route="parse")
def parse_toy_agent(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Toy Agent PARSE trigger function processed a request.')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse("Invalid JSON body.", status_code=400)

    script = req_body.get('script')
    if not script:
        return func.HttpResponse("Please pass a 'script'", status_code=400)

    try:
        parser = ToyParser()
        ast = parser.parse(script)
        # Serialize AST to JSON
        ast_json = json.dumps(ast, cls=JSONEncoder)
        
        return func.HttpResponse(
             ast_json,
             mimetype="application/json",
             status_code=200
        )
    except Exception as e:
        return func.HttpResponse(
             json.dumps({"status": "error", "error": str(e)}),
             mimetype="application/json",
             status_code=400
        )

@app.route(route="grammar", methods=["GET"])
def get_grammar(req: func.HttpRequest) -> func.HttpResponse:
    """
    Restituisce la grammatica Lark usata dal parser Toy-Agent.
    Endpoint GET: /api/grammar
    """
    logging.info('Toy Agent GRAMMAR trigger function processed a request.')
    
    import os
    grammar_path = os.path.join(os.path.dirname(__file__), "grammar.lark")
    
    try:
        with open(grammar_path, 'r', encoding='utf-8') as f:
            grammar_content = f.read()
        
        return func.HttpResponse(
            grammar_content,
            mimetype="text/plain",
            status_code=200
        )
    except FileNotFoundError:
        return func.HttpResponse(
            "Grammar file not found",
            status_code=500
        )
