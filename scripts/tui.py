#!/usr/bin/env python3
"""tui.py — Interfaz TUI minimalista para el ecosistema de gestion (REQ-006).

Vistas: Requisitos (1), Conocimiento (2), Lecciones (3), Verificar (4).
Navegacion: 1-4 pestañas, j/k/flechas mover, Enter detalle, Esc volver,
q salir (en detalle q vuelve a la lista).
curses stdlib: sin dependencias externas.
"""

import curses
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import doc_validator  # noqa: E402
import index_knowledge  # noqa: E402
import lessons_extractor  # noqa: E402

TABS = ["Requisitos", "Conocimiento", "Lecciones", "Verificar"]

CP_HEADER = 1
CP_OK = 2
CP_ERR = 3
CP_WARN = 4
CP_SEL = 5
CP_DIM = 6


def estado_color(estado: str) -> int:
    return {
        "Implementado": CP_OK,
        "Deprecado": CP_DIM,
        "Aprobado": CP_WARN,
        "Draft": CP_HEADER,
    }.get(estado, CP_HEADER)


def truncar(texto: str, ancho: int) -> str:
    return texto if len(texto) <= ancho else texto[: ancho - 1] + "…"


class Detalle:
    def __init__(self, titulo: str, lineas: list[str]) -> None:
        self.titulo = titulo
        self.lineas = lineas
        self.offset = 0


class App:
    def __init__(self) -> None:
        self.tab = 0
        self.seleccion = [0] * len(TABS)
        self.offsets = [0] * len(TABS)
        self.detalle: Detalle | None = None
        self.mensaje = "Listo"
        self.requisitos: list[dict] = []
        self.validacion = {"errores": 0, "advertencias": 0}
        self.lecciones: list[dict] = []
        self.knowledge: list[dict] = []
        self.consulta = ""
        self.verificar: list[str] = []
        self.verificar_ok = False
        self.verificar_estado = ""

    # ---------- carga de datos ----------

    def cargar_requisitos(self) -> None:
        reqs = doc_validator.collect_req_files()
        refs = doc_validator.collect_code_refs()
        self.requisitos = [
            {
                "id": rid,
                "meta": entry["meta"],
                "path": entry["path"],
                "refs": len(refs.get(rid, [])),
            }
            for rid, entry in sorted(reqs.items())
        ]
        self.validacion = {
            "errores": len(doc_validator.errors),
            "advertencias": len(doc_validator.warnings),
        }

    def cargar_lecciones(self) -> None:
        lessons, _ = lessons_extractor.validate()
        self.lecciones = lessons

    def buscar_conocimiento(self, consulta: str) -> None:
        self.consulta = consulta
        if not consulta.strip():
            self.knowledge = []
            self.mensaje = "escribe una consulta y pulsa Enter"
            return
        if index_knowledge.JSON_INDEX.exists():
            self.knowledge = index_knowledge.search_json(consulta, 8)
        else:
            self.knowledge = self._busqueda_directa(consulta)
        if not self.knowledge:
            self.mensaje = "sin resultados (o falta indice: pulsa i para indexar)"
        else:
            self.mensaje = f"{len(self.knowledge)} resultados para: {consulta}"

    def _busqueda_directa(self, consulta: str) -> list[dict]:
        terms = set(index_knowledge._tokenize(consulta))
        if not terms or not index_knowledge.KNOWLEDGE_DIR.is_dir():
            return []
        resultados = []
        for path in sorted(index_knowledge.KNOWLEDGE_DIR.rglob("*.md")):
            texto = path.read_text(encoding="utf-8", errors="replace")
            for chunk in index_knowledge._chunks(texto):
                tokens = set(index_knowledge._tokenize(chunk))
                score = len(terms & tokens)
                if score > 0:
                    resultados.append(
                        {
                            "archivo": str(path.relative_to(ROOT)),
                            "contenido": chunk,
                            "score": score,
                        }
                    )
        resultados.sort(key=lambda r: r["score"], reverse=True)
        return resultados[:8]

    def indexar(self) -> None:
        index_knowledge.index_all(force=False)
        self.mensaje = "indice actualizado (i: indexar de nuevo)"

    def ejecutar_verificar(self) -> None:
        script = SCRIPTS / "verificar-proyecto.sh"
        if not script.exists():
            self.verificar = ["no existe scripts/verificar-proyecto.sh"]
            self.verificar_ok = False
            return
        try:
            proc = subprocess.run(
                ["bash", str(script), "--pre-commit"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(ROOT),
            )
            self.verificar = (proc.stdout + proc.stderr).splitlines()
            self.verificar_ok = proc.returncode == 0
            self.verificar_estado = f"exit {proc.returncode}"
        except subprocess.TimeoutExpired:
            self.verificar = ["verificacion agotada (60s)"]
            self.verificar_ok = False
        self.mensaje = f"verificacion terminada: {self.verificar_estado}"

    # ---------- bucle ----------

    def run(self, stdscr) -> None:
        self._init_colores()
        curses.curs_set(0)
        self.cargar_requisitos()
        self.cargar_lecciones()
        while True:
            self._draw(stdscr)
            tecla = stdscr.getch()
            if tecla == curses.KEY_RESIZE:
                continue
            if self.detalle is not None:
                if self._tecla_detalle(tecla):
                    self.detalle = None
                continue
            if tecla in (ord("q"), 27) or tecla == ord("Q"):
                break
            self._tecla_principal(tecla)

    def _init_colores(self) -> None:
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(CP_HEADER, curses.COLOR_CYAN, -1)
            curses.init_pair(CP_OK, curses.COLOR_GREEN, -1)
            curses.init_pair(CP_ERR, curses.COLOR_RED, -1)
            curses.init_pair(CP_WARN, curses.COLOR_YELLOW, -1)
            curses.init_pair(CP_SEL, curses.COLOR_BLACK, curses.COLOR_CYAN)
            curses.init_pair(CP_DIM, curses.COLOR_WHITE, -1)

    def _tecla_principal(self, tecla: int) -> None:
        if tecla in range(ord("1"), ord("1") + len(TABS)):
            self.tab = tecla - ord("1")
            self.mensaje = TABS[self.tab]
            return
        if tecla in (curses.KEY_UP, ord("k")) or tecla in (curses.KEY_DOWN, ord("j")):
            total = self._items_actuales()
            if not total:
                return
            paso = -1 if tecla in (curses.KEY_UP, ord("k")) else 1
            self.seleccion[self.tab] = max(0, min(total - 1, self.seleccion[self.tab] + paso))
            return
        if tecla in (ord("\n"), curses.KEY_ENTER, ord("l")):
            self._abrir_detalle()
            return
        if self.tab == 1:
            if tecla == ord("i"):
                self.indexar()
            elif tecla == 8 or tecla == 127 or tecla == curses.KEY_BACKSPACE:
                self.consulta = self.consulta[:-1]
                self.buscar_conocimiento(self.consulta)
            elif 32 <= tecla <= 126:
                self.consulta += chr(tecla)
                self.buscar_conocimiento(self.consulta)
        if self.tab == 3 and tecla in (ord("R"), ord(" ")):
            self.ejecutar_verificar()

    def _items_actuales(self) -> int:
        if self.tab == 0:
            return len(self.requisitos)
        if self.tab == 1:
            return len(self.knowledge)
        if self.tab == 2:
            return len(self.lecciones)
        return len(self.verificar)

    def _abrir_detalle(self) -> None:
        sel = self.seleccion[self.tab]
        if self.tab == 0 and sel < len(self.requisitos):
            req = self.requisitos[sel]
            self.detalle = Detalle(req["id"], req["path"].read_text(encoding="utf-8").splitlines())
        elif self.tab == 1 and sel < len(self.knowledge):
            hit = self.knowledge[sel]
            lineas = [f"{hit['archivo']}  (score {hit['score']})", ""] + textwrap.wrap(
                hit["contenido"], width=max(60, curses.COLS - 4)
            )
            self.detalle = Detalle("Conocimiento", lineas)
        elif self.tab == 2 and sel < len(self.lecciones):
            leccion = self.lecciones[sel]
            lineas = []
            for clave in ("id", "proyecto", "fase", "categoria", "estado", "fecha"):
                lineas.append(f"{clave}: {leccion.get(clave, '')}")
            lineas.append("")
            lineas.append("problema: " + str(leccion.get("problema", "")))
            lineas.append("")
            lineas.append("recomendacion: " + str(leccion.get("recomendacion", "")))
            self.detalle = Detalle(str(leccion.get("id", "Leccion")), lineas)

    def _tecla_detalle(self, tecla: int) -> bool:
        if tecla in (curses.KEY_UP, ord("k")) and self.detalle.offset > 0:
            self.detalle.offset -= 1
        elif tecla in (curses.KEY_DOWN, ord("j")):
            self.detalle.offset += 1
        return tecla in (ord("q"), 27, ord("Q"), ord("\n"), curses.KEY_ENTER)

    # ---------- dibujo ----------

    def _draw(self, stdscr) -> None:
        if self.detalle is not None:
            self._draw_detalle(stdscr)
            return
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        self._draw_header(stdscr, h, w)
        self._draw_tabs(stdscr, h, w)
        if self.tab == 0:
            self._draw_requisitos(stdscr, h, w)
        elif self.tab == 1:
            self._draw_conocimiento(stdscr, h, w)
        elif self.tab == 2:
            self._draw_lecciones(stdscr, h, w)
        else:
            self._draw_verificar(stdscr, h, w)
        self._draw_status(stdscr, h, w)
        stdscr.refresh()

    def _draw_header(self, stdscr, h, w) -> None:
        titulo = " better-project · ecosistema local de gestion "
        if curses.has_colors():
            stdscr.addstr(0, 0, truncar(titulo, w), curses.color_pair(CP_HEADER) | curses.A_BOLD)
        else:
            stdscr.addstr(0, 0, truncar(titulo, w))
        hint = "  q salir · 1-4 pestañas · j/k mover · Enter detalle"
        if w > 30:
            stdscr.addstr(0, max(0, w - len(hint)), truncar(hint, w))

    def _draw_tabs(self, stdscr, h, w) -> None:
        x = 0
        for i, nombre in enumerate(TABS):
            etiqueta = f" {i + 1}·{nombre} "
            if i == self.tab:
                stdscr.addstr(1, x, truncar(etiqueta, w - x), curses.color_pair(CP_SEL) | curses.A_BOLD)
            else:
                stdscr.addstr(1, x, truncar(etiqueta, w - x), curses.A_DIM)
            x += len(etiqueta)
            if x >= w:
                break

    def _rango_visible(self, h, w, inicio=3) -> tuple[int, int]:
        """Devuelve (offset, altura) validos para el area de contenido."""
        altura = max(1, h - inicio - 2)
        return self.offsets[self.tab], altura

    def _lista(self, stdscr, h, w, filas: list[tuple[str, int]], inicio=3) -> None:
        offset, altura = self._rango_visible(h, w, inicio)
        offset = max(0, min(offset, max(0, len(filas) - altura)))
        self.offsets[self.tab] = offset
        for i in range(altura):
            idx = offset + i
            if idx >= len(filas):
                break
            texto, color = filas[idx]
            if idx == self.seleccion[self.tab] and self.tab != 3:
                stdscr.addstr(inicio + i, 0, " " * (w - 1), curses.color_pair(CP_SEL))
                stdscr.addstr(inicio + i, 0, truncar(texto, w - 1), curses.color_pair(CP_SEL))
            else:
                stdscr.addstr(inicio + i, 0, truncar(texto, w - 1), color)
        if not filas:
            stdscr.addstr(inicio, 0, "(sin datos)", curses.A_DIM)

    def _draw_requisitos(self, stdscr, h, w) -> None:
        v = self.validacion
        color = CP_OK if v["errores"] == 0 else CP_ERR
        if v["errores"] == 0 and v["advertencias"] > 0:
            color = CP_WARN
        estado_txt = "OK" if v["errores"] == 0 and v["advertencias"] == 0 else f"{v['errores']}E/{v['advertencias']}W"
        stdscr.addstr(
            2,
            0,
            truncar(f" trazabilidad: {estado_txt}  ·  {len(self.requisitos)} requisitos  ·  Enter=detalle", w - 1),
            curses.color_pair(color),
        )
        filas = []
        for req in self.requisitos:
            meta = req["meta"]
            filas.append(
                (
                    f" {req['id']}  [{meta.get('estado', '?')}]  {meta.get('prioridad', ''):<6}  "
                    f"{meta.get('titulo', '')}  ({req['refs']} refs)",
                    curses.color_pair(estado_color(meta.get("estado", ""))),
                )
            )
        self._lista(stdscr, h, w, filas)

    def _draw_conocimiento(self, stdscr, h, w) -> None:
        consulta = f" consulta: {self.consulta or '(escribe y pulsa Enter)'}"
        stdscr.addstr(2, 0, truncar(consulta, w - 1), curses.color_pair(CP_HEADER))
        filas = []
        for hit in self.knowledge:
            primera = hit["contenido"].splitlines()[0] if hit["contenido"].splitlines() else ""
            filas.append(
                (f" [{hit['score']}] {hit['archivo']} — {truncar(primera, w - 30)}", 0)
            )
        self._lista(stdscr, h, w, filas, inicio=3)

    def _draw_lecciones(self, stdscr, h, w) -> None:
        stdscr.addstr(
            2, 0, truncar(f" {len(self.lecciones)} lecciones  ·  Enter=detalle", w - 1), curses.A_DIM
        )
        filas = []
        for leccion in sorted(self.lecciones, key=lambda l: str(l.get("id", ""))):
            color = CP_OK if leccion.get("estado") == "Resuelta" else CP_WARN
            filas.append(
                (
                    f" {leccion.get('id', '?')}  [{leccion.get('estado', '?')}]  "
                    f"{str(leccion.get('categoria', '')):<15} {truncar(str(leccion.get('problema', '')), w - 42)}",
                    curses.color_pair(color),
                )
            )
        self._lista(stdscr, h, w, filas)

    def _draw_verificar(self, stdscr, h, w) -> None:
        estado = self.verificar_estado or "pulsa R o espacio para ejecutar"
        color = CP_DIM if not self.verificar else (CP_OK if self.verificar_ok else CP_ERR)
        stdscr.addstr(2, 0, truncar(f" verificar-proyecto.sh — {estado}  ·  R=re-ejecutar", w - 1), curses.color_pair(color))
        filas = [(linea, 0) for linea in self.verificar]
        self._lista(stdscr, h, w, filas)

    def _draw_status(self, stdscr, h, w) -> None:
        if h < 2:
            return
        linea = truncar(self.mensaje, w - 1)
        if curses.has_colors():
            stdscr.addstr(h - 1, 0, " " * (w - 1), curses.color_pair(CP_HEADER))
            stdscr.addstr(h - 1, 0, linea, curses.color_pair(CP_HEADER))
        else:
            stdscr.addstr(h - 1, 0, linea)

    def _draw_detalle(self, stdscr) -> None:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        titulo = f" {self.detalle.titulo}  ·  Esc/Enter volver · j/k scroll "
        stdscr.addstr(0, 0, truncar(titulo, w), curses.color_pair(CP_HEADER) | curses.A_BOLD)
        lineas = self.detalle.lineas
        max_offset = max(0, len(lineas) - (h - 2))
        self.detalle.offset = max(0, min(self.detalle.offset, max_offset))
        for i in range(1, h):
            idx = self.detalle.offset + (i - 1)
            if idx >= len(lineas):
                break
            stdscr.addstr(i, 0, truncar(lineas[idx], w - 1))
        stdscr.refresh()


def main() -> int:
    return curses.wrapper(App().run)


if __name__ == "__main__":
    sys.exit(main())
