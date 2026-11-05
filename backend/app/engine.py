"""Small, deterministic workbook processing graph."""

from __future__ import annotations

import hashlib
import math
from io import BytesIO
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from openpyxl import Workbook, load_workbook


REGIONS = ("EU", "NA", "APAC")
ALIASES = {
    "EU": {
        "sku": ("article", "sku", "product code"),
        "quantity": ("units", "stock", "quantity"),
        "unit_price": ("net price", "unit price", "price"),
    },
    "NA": {
        "sku": ("item", "sku", "product code"),
        "quantity": ("qty", "on hand", "quantity"),
        "unit_price": ("unit price", "price"),
    },
    "APAC": {
        "sku": ("product code", "sku", "item"),
        "quantity": ("units sold", "available", "quantity"),
        "unit_price": ("price", "unit price"),
    },
}


class SheetState(TypedDict, total=False):
    region: str
    kind: str
    headers: list[str]
    rows: list[list[Any]]
    cached_mapping: dict[str, int] | None
    mapping: dict[str, int]
    output: list[list[Any]]
    errors: list[str]
    trace: list[dict[str, str]]
    reused: bool


def normalized(value: Any) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def identify_kind(sheet_name: str, headers: list[str]) -> str | None:
    name = sheet_name.lower()
    if "inventory" in name or "stock" in name:
        return "inventory"
    if "sales" in name:
        return "sales"
    names = {normalized(header) for header in headers}
    if names & {"stock", "onhand", "available"}:
        return "inventory"
    if names & {"netprice", "unitprice", "price"}:
        return "sales"
    return None


def fingerprint(region: str, kind: str, headers: list[str]) -> str:
    value = "|".join((region, kind, *(normalized(item) for item in headers)))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def suggest_mapping(region: str, kind: str, headers: list[str]) -> dict[str, int]:
    aliases = ALIASES[region]
    fields = ("sku", "quantity", "unit_price") if kind == "sales" else ("sku", "quantity")
    index = {normalized(header): i for i, header in enumerate(headers)}
    mapping: dict[str, int] = {}
    for field in fields:
        for alias in aliases[field]:
            if normalized(alias) in index:
                mapping[field] = index[normalized(alias)]
                break
    return mapping


def _trace(state: SheetState, step: str, status: str, detail: str) -> list[dict[str, str]]:
    return [*state.get("trace", []), {"step": step, "status": status, "detail": detail}]


def inspect_node(state: SheetState) -> SheetState:
    return {"trace": _trace(state, "inspect", "success", f"{len(state['rows'])} data rows")}


def plan_node(state: SheetState) -> SheetState:
    cached = state.get("cached_mapping")
    mapping = cached if cached is not None else suggest_mapping(state["region"], state["kind"], state["headers"])
    required = {"sku", "quantity", "unit_price"} if state["kind"] == "sales" else {"sku", "quantity"}
    missing = sorted(required - set(mapping))
    if missing:
        return {
            "mapping": mapping,
            "errors": [f"Missing required columns: {', '.join(missing)}"],
            "reused": cached is not None,
            "trace": _trace(state, "plan", "failed", f"Missing: {', '.join(missing)}"),
        }
    return {
        "mapping": mapping,
        "reused": cached is not None,
        "trace": _trace(state, "plan", "success", "Reused saved mapping" if cached is not None else "Mapped columns"),
    }


def _number(value: Any) -> float:
    number = float(str(value).replace(",", "").strip())
    if not math.isfinite(number):
        raise ValueError("non-finite number")
    return number


def execute_node(state: SheetState) -> SheetState:
    if state.get("errors"):
        return {"output": [], "trace": _trace(state, "execute", "skipped", "No valid mapping")}
    mapping = state["mapping"]
    output: list[list[Any]] = []
    skipped = 0
    for row in state["rows"]:
        try:
            sku = str(row[mapping["sku"]] or "").strip()
            if not sku:
                raise ValueError("empty SKU")
            quantity = _number(row[mapping["quantity"]])
            if quantity < 0:
                raise ValueError("negative quantity")
            if state["kind"] == "sales":
                price = _number(row[mapping["unit_price"]])
                if price < 0:
                    raise ValueError("negative price")
                output.append([sku, quantity, price, round(quantity * price, 2)])
            else:
                output.append([sku, quantity])
        except (IndexError, TypeError, ValueError):
            skipped += 1
    return {
        "output": output,
        "trace": _trace(state, "execute", "success", f"{len(output)} cleaned rows; {skipped} skipped"),
    }


def validate_node(state: SheetState) -> SheetState:
    errors = list(state.get("errors", []))
    if not errors and not state.get("output"):
        errors.append("No valid data rows")
    return {
        "errors": errors,
        "trace": _trace(state, "validate", "failed" if errors else "success", "; ".join(errors) if errors else "Output ready"),
    }


def build_graph():
    graph = StateGraph(SheetState)
    graph.add_node("inspect", inspect_node)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("validate", validate_node)
    graph.add_edge(START, "inspect")
    graph.add_edge("inspect", "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


WORKFLOW = build_graph()


def read_sheets(data: bytes) -> list[dict[str, Any]]:
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    sheets: list[dict[str, Any]] = []
    try:
        for worksheet in workbook.worksheets:
            iterator = worksheet.values
            first = next(iterator, None)
            if first is None:
                continue
            headers = [str(value or "").strip() for value in first]
            rows = [list(row) for row in iterator if any(value is not None for value in row)]
            sheets.append({"name": worksheet.title, "headers": headers, "rows": rows})
    finally:
        workbook.close()
    return sheets


def create_output(results: list[dict[str, Any]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for i, result in enumerate(results, 1):
        worksheet = workbook.create_sheet(f"{result['kind'].title()} Cleaned {i}")
        worksheet.append(["SKU", "Quantity", "Unit Price", "Amount"] if result["kind"] == "sales" else ["SKU", "Quantity"])
        for values in result["output"]:
            worksheet.append(values)
            worksheet.cell(worksheet.max_row, 1).data_type = "s"
        worksheet.freeze_panes = "A2"
        worksheet.column_dimensions["A"].width = 22
        worksheet.column_dimensions["B"].width = 14
        if result["kind"] == "sales":
            worksheet.column_dimensions["C"].width = 16
            worksheet.column_dimensions["D"].width = 16
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def create_sample(region: str) -> bytes:
    names = {
        "EU": ("Article", "Units", "Net Price", "Stock"),
        "NA": ("Item", "Qty", "Unit Price", "On Hand"),
        "APAC": ("Product Code", "Units Sold", "Price", "Available"),
    }
    sku, quantity, price, stock = names[region]
    workbook = Workbook()
    sales = workbook.active
    sales.title = f"{region} Sales"
    sales.append([sku, quantity, price])
    sales.append(["SAMPLE-001", 12, 19.9])
    sales.append(["SAMPLE-002", 8, 24.5])
    inventory = workbook.create_sheet(f"{region} Inventory")
    inventory.append([sku, stock])
    inventory.append(["SAMPLE-001", 40])
    inventory.append(["SAMPLE-002", 25])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
