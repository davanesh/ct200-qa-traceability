from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from .service import ingest, list_nodes, get_node, search_nodes, create_selection, generate_cases, get_generations, db_init

app = FastAPI(title="CT-200 QA Traceability API", version="1.0.0")
db_init()

class SelectionIn(BaseModel):
    name: str
    node_ids: list[str]
    version: Optional[int] = None

class GenerateIn(BaseModel):
    provider: Optional[str] = None

@app.get('/health')
def health(): return {'status':'ok'}

@app.post('/documents/ingest')
def ingest_api(path: str, version: Optional[int] = None):
    try: return ingest(path, version)
    except Exception as e: raise HTTPException(400, str(e))

@app.get('/documents/{doc_id}/sections')
def sections(doc_id: str, version: Optional[int] = None): return list_nodes(doc_id, version, roots_only=True)

@app.get('/nodes/{node_id}')
def node(node_id: str, version: Optional[int] = None):
    result=get_node(node_id,version)
    if not result: raise HTTPException(404,'Node/version not found')
    return result

@app.get('/documents/{doc_id}/search')
def search(doc_id: str, q: str, version: Optional[int] = None): return search_nodes(doc_id,q,version)

@app.get('/nodes/{node_id}/changes')
def changes(node_id: str):
    from .service import node_changes
    return node_changes(node_id)

@app.post('/selections')
def selection(data: SelectionIn):
    try: return create_selection(data.name,data.node_ids,data.version)
    except ValueError as e: raise HTTPException(400,str(e))

@app.post('/selections/{selection_id}/generate')
def generate(selection_id: str, data: GenerateIn):
    try: return generate_cases(selection_id,data.provider)
    except ValueError as e: raise HTTPException(404,str(e))
    except RuntimeError as e: raise HTTPException(502,str(e))

@app.get('/generations')
def generations(selection_id: Optional[str] = None, node_id: Optional[str] = None): return get_generations(selection_id,node_id)
