"""Public Excel processing API."""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4
from zipfile import BadZipFile

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl.utils.exceptions import InvalidFileException

from app.engine import REGIONS, WORKFLOW, create_output, create_sample, fingerprint, identify_kind, read_sheets, suggest_mapping


MAX_UPLOAD_BYTES = 2 * 1024 * 1024
app = FastAPI(title="AutoProcess", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# This small server keeps results and recognized mappings for its current process lifetime.
RUNS: dict[str, bytes] = {}
RECIPES: dict[str, dict[str, int]] = {}


def selected_region(region: str) -> str:
    value = region.upper()
    if value not in REGIONS:
        raise HTTPException(status_code=422, detail="Region must be EU, NA, or APAC")
    return value


async def uploaded_sheets(file: UploadFile):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Choose an .xlsx workbook")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Workbook exceeds 2 MB")
    try:
        return read_sheets(data)
    except (BadZipFile, InvalidFileException, ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="Workbook could not be read") from exc


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/sample")
def sample(region: str = Query("EU")):
    region = selected_region(region)
    return StreamingResponse(
        BytesIO(create_sample(region)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{region.lower()}-sample.xlsx"'},
    )


@app.post("/api/inspect")
async def inspect(file: UploadFile = File(...), region: str = Form("EU")):
    region = selected_region(region)
    sheets = await uploaded_sheets(file)
    return {
        "sheets": [
            {
                "name": sheet["name"],
                "kind": identify_kind(sheet["name"], sheet["headers"]),
                "headers": sheet["headers"],
                "rows": len(sheet["rows"]),
                "mapping": suggest_mapping(region, kind, sheet["headers"]) if (kind := identify_kind(sheet["name"], sheet["headers"])) else {},
            }
            for sheet in sheets
        ]
    }


@app.post("/api/process")
async def process(file: UploadFile = File(...), region: str = Form("EU")):
    region = selected_region(region)
    sheets = await uploaded_sheets(file)
    results = []
    ignored = []
    for sheet in sheets:
        kind = identify_kind(sheet["name"], sheet["headers"])
        if kind is None:
            ignored.append(sheet["name"])
            continue
        recipe_id = fingerprint(region, kind, sheet["headers"])
        state = WORKFLOW.invoke(
            {
                "region": region,
                "kind": kind,
                "headers": sheet["headers"],
                "rows": sheet["rows"],
                "cached_mapping": RECIPES.get(recipe_id),
                "trace": [],
                "errors": [],
            }
        )
        if state.get("errors"):
            raise HTTPException(status_code=422, detail=f"{sheet['name']}: {'; '.join(state['errors'])}")
        RECIPES[recipe_id] = state["mapping"]
        results.append(
            {
                "source_sheet": sheet["name"],
                "kind": kind,
                "rows_in": len(sheet["rows"]),
                "rows_out": len(state["output"]),
                "recipe_id": recipe_id,
                "reused": state["reused"],
                "mapping": {name: sheet["headers"][index] for name, index in state["mapping"].items()},
                "trace": state["trace"],
                "preview": state["output"][:10],
                "output": state["output"],
            }
        )
    if not results:
        raise HTTPException(status_code=422, detail="No sales or inventory sheet found")
    run_id = uuid4().hex
    if len(RUNS) >= 20:
        RUNS.pop(next(iter(RUNS)))
    RUNS[run_id] = create_output(results)
    return {
        "run_id": run_id,
        "region": region,
        "ignored_sheets": ignored,
        "sheets": [{key: value for key, value in result.items() if key != "output"} for result in results],
    }


@app.get("/api/download/{run_id}")
def download(run_id: str):
    content = RUNS.get(run_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="autoprocess-{run_id[:8]}.xlsx"'},
    )
