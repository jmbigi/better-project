#!/usr/bin/env python3
"""mcp_server.py — Servidor MCP (Model Context Protocol) local para agentes (REQ-004).

Expone las herramientas del ecosistema a opencode y otros agentes via stdio:
- search_knowledge(query, k): busqueda en .docs/knowledge/ (indice JSON o directa).
- read_requirement(id): lee una especificacion REQ-XXX.
- validate_requirements(): valida trazabilidad REQ (doc_validator).
- create_lesson(...): anade una leccion a .docs/lessons/<anio>.yaml.

Sin dependencias externas. Framing stdio: JSON por linea (espec MCP 2025-06-18)
con soporte retrocompatible de cabeceras Content-Length.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
KNOWLEDGE_DIR = ROOT / ".docs" / "knowledge"
JSON_INDEX = ROOT / ".docs" / ".storage" / "index.json"
LESSONS_DIR = ROOT / ".docs" / "lessons"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import doc_validator  # noqa: E402
import index_knowledge  # noqa: E402

TOOLS = [
    {
        "name": "search_knowledge",
        "description": "Busca en la base de conocimiento (.docs/knowledge/) y devuelve los fragmentos mas relevantes. Fundamenta respuestas en los resultados.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Consulta en lenguaje natural"},
                "k": {"type": "number", "description": "Numero de resultados (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_requirement",
        "description": "Lee una especificacion de requisito completa de .docs/requirements/.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Formato REQ-XXX"}},
            "required": ["id"],
        },
    },
    {
        "name": "validate_requirements",
        "description": "Valida la trazabilidad entre codigo y requisitos (doc_validator).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_lesson",
        "description": "Registra una leccion aprendida en .docs/lessons/ tras un fallo o hallazgo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "problema": {"type": "string", "description": "Que fallo o que se encontro"},
                "recomendacion": {"type": "string", "description": "Como evitarlo"},
                "categoria": {"type": "string", "description": "p.ej. Riesgo_Tecnico, Seguridad, Proceso"},
                "fase": {"type": "string", "description": "p.ej. Testing, Implementacion, Deploy"},
                "proyecto": {"type": "string", "description": "Modulo o proyecto afectado"},
            },
            "required": ["problema", "recomendacion"],
        },
    },
]


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _next_lesson_id(existing_ids: set) -> str:
    nums = [
        int(match.group(1))
        for item in existing_ids
        if (match := re.fullmatch(r"LSN-(\d+)", item))
    ]
    return f"LSN-{max(nums, default=0) + 1:03d}"


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def handle_call(name: str, arguments: dict) -> tuple[list[dict], bool]:
    try:
        if name == "search_knowledge":
            return search_knowledge(arguments), False
        if name == "read_requirement":
            return read_requirement(arguments), False
        if name == "validate_requirements":
            return validate_requirements(), False
        if name == "create_lesson":
            return create_lesson(arguments), False
        return [{"type": "text", "text": f"tool desconocida: {name}"}], True
    except Exception as exc:  # noqa: BLE001 - el protocolo exige respuesta
        return [{"type": "text", "text": f"error: {exc}"}], True


def search_knowledge(args: dict) -> list[dict]:
    query = str(args.get("query", "")).strip()
    k = int(args.get("k", 5))
    if not query:
        return [{"type": "text", "text": "error: query vacia"}]
    if JSON_INDEX.exists():
        results = index_knowledge.search_json(query, k)
    else:
        results = _direct_search(query, k)
    if not results:
        return [{"type": "text", "text": "sin resultados. Ejecuta: python scripts/index_knowledge.py"}]
    payload = json.dumps(results, ensure_ascii=False, indent=2)
    return [{"type": "text", "text": payload}]


def _direct_search(query: str, k: int) -> list[dict]:
    """Fallback sin indice: escaneo directo con scoring de terminos."""
    terms = set(index_knowledge._tokenize(query))
    if not terms or not KNOWLEDGE_DIR.is_dir():
        return []
    results = []
    for path in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for chunk in index_knowledge._chunks(text):
            tokens = set(index_knowledge._tokenize(chunk))
            score = len(terms & tokens)
            if score > 0:
                results.append(
                    {
                        "archivo": str(path.relative_to(ROOT)),
                        "contenido": chunk[:1200],
                        "score": score,
                    }
                )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:k]


def read_requirement(args: dict) -> list[dict]:
    req_id = str(args.get("id", "")).strip()
    if not re.fullmatch(r"REQ-\d{3}", req_id):
        return [{"type": "text", "text": "error: id debe ser REQ-XXX"}]
    path = ROOT / ".docs" / "requirements" / f"{req_id}.md"
    if not path.exists():
        return [{"type": "text", "text": f"error: no existe .docs/requirements/{req_id}.md"}]
    return [{"type": "text", "text": path.read_text(encoding="utf-8")}]


def validate_requirements() -> list[dict]:
    reqs = doc_validator.collect_req_files()
    refs = doc_validator.collect_code_refs()
    report = {"requisitos": len(reqs), "referencias_codigo": len(refs)}
    if doc_validator.errors:
        report["errores"] = doc_validator.errors
        report["estado"] = "con errores"
    elif doc_validator.warnings:
        report["advertencias"] = doc_validator.warnings
        report["estado"] = "con advertencias"
    else:
        report["estado"] = "OK"
    return [{"type": "text", "text": json.dumps(report, ensure_ascii=False, indent=2)}]


def create_lesson(args: dict) -> list[dict]:
    problema = str(args.get("problema", "")).strip()
    recomendacion = str(args.get("recomendacion", "")).strip()
    if not problema or not recomendacion:
        return [{"type": "text", "text": "error: problema y recomendacion son obligatorias"}]
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    year_file = LESSONS_DIR / f"{date.today().year}.yaml"
    existing: set = set()
    if year_file.exists():
        for line in year_file.read_text(encoding="utf-8").splitlines():
            m = re.match(r"- id:\s*(\S+)", line)
            if m:
                existing.add(m.group(1))
    entry = {
        "id": _next_lesson_id(existing),
        "proyecto": str(args.get("proyecto", "")).strip() or "general",
        "fase": str(args.get("fase", "")).strip() or "General",
        "categoria": str(args.get("categoria", "")).strip() or "Proceso",
        "problema": problema,
        "recomendacion": recomendacion,
        "estado": "Abierta",
        "fecha": date.today().isoformat(),
    }
    lines = [
        "- id: " + entry["id"],
        "  proyecto: " + _quote(entry["proyecto"]),
        "  fase: " + _quote(entry["fase"]),
        "  categoria: " + _quote(entry["categoria"]),
        "  problema: " + _quote(entry["problema"]),
        "  recomendacion: " + _quote(entry["recomendacion"]),
        "  estado: " + entry["estado"],
        "  fecha: " + entry["fecha"],
    ]
    text = year_file.read_text(encoding="utf-8") if year_file.exists() else ""
    with year_file.open("a", encoding="utf-8") as fh:
        if text and not text.endswith("\n"):
            fh.write("\n")
        fh.write("\n".join(lines) + "\n")
    return [{"type": "text", "text": f"leccion {entry['id']} anadida a {year_file.name}"}]


class StdioServer:
    def __init__(self) -> None:
        self.buffer = b""

    def _messages(self) -> list[dict]:
        """Extrae mensajes completos del buffer (JSONL o Content-Length)."""
        messages = []
        while True:
            text = self.buffer.decode("utf-8", errors="replace")
            if text.lstrip().startswith("Content-Length:"):
                header_end = text.find("\r\n\r\n")
                if header_end == -1:
                    return messages
                header = text[:header_end]
                match = re.search(r"Content-Length:\s*(\d+)", header)
                if not match:
                    self.buffer = b""
                    return messages
                length = int(match.group(1))
                body_start = header_end + 4
                if len(self.buffer) < body_start + length:
                    return messages
                raw = self.buffer[body_start : body_start + length]
                self.buffer = self.buffer[body_start + length :]
                try:
                    messages.append(json.loads(raw))
                except json.JSONDecodeError:
                    log("mensaje JSON invalido")
                continue
            newline = self.buffer.find(b"\n")
            if newline == -1:
                return messages
            raw = self.buffer[:newline]
            self.buffer = self.buffer[newline + 1 :]
            if not raw.strip():
                continue
            try:
                messages.append(json.loads(raw))
            except json.JSONDecodeError:
                log("linea JSON invalida ignorada")
        return messages

    def send(self, payload: dict) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    def run(self) -> None:
        for chunk in sys.stdin.buffer:
            self.buffer += chunk
            for message in self._messages():
                self._dispatch(message)

    def _dispatch(self, message: dict) -> None:
        method = message.get("method")
        msg_id = message.get("id")
        if method == "initialize":
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": message.get("params", {}).get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "better-project", "version": "0.1.0"},
                    },
                }
            )
        elif method == "notifications/initialized":
            pass
        elif method == "ping":
            self.send({"jsonrpc": "2.0", "id": msg_id, "result": {}})
        elif method == "tools/list":
            self.send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            params = message.get("params", {})
            content, is_error = handle_call(params.get("name", ""), params.get("arguments", {}) or {})
            self.send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {"content": content, "isError": is_error},
                }
            )
        elif method == "notifications/cancelled":
            pass
        else:
            log(f"metodo no soportado: {method}")


if __name__ == "__main__":
    StdioServer().run()
