# Demo: Gestor de Notas CLI

Proyecto de ejemplo que muestra el flujo completo del ecosistema better-project en **< 5 minutos**.

## Requisitos previos

- Python 3.10+
- Git
- Bash

## Flujo end-to-end (cronometrado)

### 1. Onboarding (30 seg)
```bash
cd /home/<usuario>/better-project
bash scripts/setup.sh --yes
```
Instala hook pre-commit, genera índice de conocimiento y ejecuta primera validación.

### 2. Crear requisito (30 seg)
```bash
cat > demo/.docs/requirements/REQ-004.md << 'EOF'
---
id: REQ-004
titulo: Exportar notas a Markdown
estado: Aprobado
prioridad: Media
version: 1.0
fecha_creacion: 2026-09-20
---
# REQ-004: Exportar notas a Markdown

Permitir exportar todas las notas a un archivo Markdown con formato:
- [ ] Texto de la nota
- [x] Nota completada
EOF
```

### 3. Implementar (1 min)
```bash
cat >> demo/src/notas.py << 'EOF'

def cmd_export() -> int:
    # REQ-004: exportar notas a Markdown
    notas = cargar_notas()
    if not notas:
        print("sin notas para exportar")
        return 0
    with open("notas_export.md", "w", encoding="utf-8") as f:
        for nota in notas:
            marca = "x" if nota["hecha"] else " "
            f.write(f"- [{marca}] {nota['texto']}\n")
    print("exportado a notas_export.md")
    return 0
EOF
```

Añadir el subcomando al parser:
```bash
sed -i '/p_done = sub.add_parser("done"/a\
    p_export = sub.add_parser("export", help="exportar a Markdown")' demo/src/notas.py
sed -i '/return cmd_done(args.id)/i\
    if args.comando == "export":\n        return cmd_export()' demo/src/notas.py
```

### 4. Validar trazabilidad (15 seg)
```bash
python3 scripts/doc_validator.py --root demo
# Debe salir: "Resultado: OK"
```

### 5. Ejecutar y probar (30 seg)
```bash
cd demo
python3 src/notas.py add "Probar exportación"
python3 src/notas.py add "Verificar REQ-004"
python3 src/notas.py done 1
python3 src/notas.py export
cat notas_export.md
```

### 6. Registrar lección (30 seg)
```bash
python3 scripts/lessons_extractor.py
# O vía MCP:
# python3 -c "from scripts.mcp_server import handle_call; handle_call('create_lesson', {'problema': 'Exportación requería añadir subcomando al parser', 'recomendacion': 'Documentar patrón de subcomandos en README demo', 'categoria': 'Proceso', 'fase': 'Implementacion', 'proyecto': 'demo'})"
```

### 7. Verificar todo (15 seg)
```bash
bash scripts/verificar-proyecto.sh --pre-commit
# Debe salir: "Resultado: X OK, 0 FALLOS"
```

---

## Estructura de la demo

```
demo/
├── src/notas.py              # Código con referencias # REQ-XXX
├── .docs/
│   ├── requirements/         # REQ-001 (Implementado), REQ-002 (Aprobado), REQ-003 (Deprecado), REQ-004 (Aprobado)
│   ├── knowledge/            # Arquitectura + glosario
│   └── lessons/              # Lección de ejemplo (LSN-001)
└── README.md                 # Este archivo
```

## Validación automática

El hook pre-commit ejecuta `verificar-proyecto.sh` que valida:
- Trazabilidad REQ (código ↔ `.docs/requirements/`)
- Frontmatter válido en todos los REQs
- No hay REQs `Deprecado` referenciados en código
- Índice de conocimiento generable
- Tests pasan
- ADRs válidos
- Auto-auditoría limpia

## Tiempo total estimado: **~3 minutos**

---

## Próximos pasos

1. Añadir más REQs y ver cómo la trazabilidad los detecta
2. Probar `python3 scripts/tui.py` para explorar el ecosistema visualmente
3. Ejecutar `python3 scripts/auto_audit.py all` para ver auditorías
4. Crear un ADR en `docs/decisions/ADR-001-...` y validar con `adr_validator.py`