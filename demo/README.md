# Demo: gestor de notas CLI

Proyecto de ejemplo que muestra cómo usar el ecosistema de better-project en
un proyecto real. Reproduce los tres pilares en miniatura:

- `.docs/requirements/REQ-001..003.md` — ciclo de vida completo: uno
  Implementado (con código), uno Aprobado (pendiente) y uno Deprecado.
- `.docs/knowledge/` — arquitectura y glosario en Markdown.
- `.docs/lessons/` — una lección aprendida.
- `src/notas.py` — CLI funcional con comentarios `# REQ-XXX`.

## Validar la trazabilidad de la demo

La demo no se mezcla con el proyecto principal: el validador la excluye del
escaneo por defecto. Para validarla de forma autónoma:

```bash
python3 scripts/doc_validator.py --root demo
```

Esperado: `3 REQs, 1 referencia en código, Resultado: OK` (REQ-002 Aprobado
sin código genera advertencia, no error).

## Probar el código

```bash
python3 demo/src/notas.py add "aprender MCP"
python3 demo/src/notas.py list
python3 demo/src/notas.py done 1
```

## Ciclo de vida de los requisitos en la demo

1. **REQ-001** (Implementado): gestor de notas en JSON local — `src/notas.py`
   lo implementa y lo referencia.
2. **REQ-002** (Aprobado): sincronización remota — aprobado, pendiente de
   implementar, sin código.
3. **REQ-003** (Deprecado): interfaz ncurses — deprecado antes de
   implementar; el código no debe referenciarlo.
