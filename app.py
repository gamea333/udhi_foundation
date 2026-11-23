"""Part B web server.

GET  /                 -> the page
GET  /api/results      -> saved results.json (no model call)
POST /api/generate/{id} -> runs Part A live for one concept
"""
import json
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool

load_dotenv()

from concepts import get_concept  # noqa: E402
from pipeline import GenerationError, generate_one  # noqa: E402

BASE = Path(__file__).parent
app = FastAPI()


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/results")
def results():
    path = BASE / "results.json"
    return json.loads(path.read_text()) if path.exists() else []


@app.post("/api/generate/{concept_id}")
async def generate(concept_id: int):
    try:
        concept = get_concept(concept_id)
    except KeyError as e:
        return JSONResponse({"error": e.args[0]}, status_code=404)
    try:
        # generate_one blocks (network + sleep on backoff), so run it off the event loop
        return await run_in_threadpool(generate_one, concept)
    except GenerationError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    except Exception as e:  # never send the user a blank page
        return JSONResponse({"error": f"Unexpected error: {type(e).__name__}: {e}"}, status_code=500)
