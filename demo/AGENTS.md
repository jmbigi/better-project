# AGENTS.md — demo del ecosistema

Mini-proyecto de ejemplo para better-project. Aplica el ruleset completo del
proyecto (20 P0 / 36 P1); reglas detalladas, justificaciones y checklist en la
raíz del repo y en `docs/`.

Directivas aplicables a esta demo:

1. Toda función que implemente un requisito lleva `# REQ-XXX` en su
   encabezado (directiva del proyecto).
2. Antes de implementar algo nuevo: revisar `.docs/requirements/`.
3. Antes de depurar: revisar `.docs/lessons/`.
4. Validar la demo de forma autónoma:
   `python3 scripts/doc_validator.py --root demo`
