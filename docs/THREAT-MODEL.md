# Threat model (MCP local + agente)

Alcance: el ecosistema funciona como **herramienta local**. No expone servicios
de red por defecto; el único canal con el agente es `scripts/mcp_server.py` por
**stdio** (JSON-RPC). Este modelo sigue el enfoque de OWASP GenAI (LLM Top 10
2026) y MITRE ATLAS, y referencia las reglas del proyecto (`AGENTS.md`).

## Activos

| Activo | Dónde | Sensibilidad |
|---|---|---|
| Requisitos y ADRs | `.docs/requirements/`, `docs/decisions/` | interna |
| Conocimiento y lecciones | `.docs/knowledge/`, `.docs/lessons/` | interna |
| Código y configuración | `scripts/`, `opencode.json`/`kilo.json` | interna |
| Claves/credenciales | **fuera del repo** (`.env`, `~/.ssh`) | crítica (P0.6) |
| Modelo GGUF local | `~/.cache/better-project/jev/` | no sensible |

## Fronteras de confianza

1. **Programador → agente**: única fuente de órdenes. El contenido que procesa
   el agente (webs, docs, salidas, terceros) es **dato**, no orden (P0.13).
2. **Agente → sistema**: mediada por los 304 patrones de permiso (218 `deny`,
   85 `ask`, 1 `allow`) y por `sudo` prohibido siempre (P0.5).
3. **Agente → MCP local**: stdio, con límites de entrada en servidor (REQ-007) y
   auditoría JSONL sin contenidos (P0.9).
4. **Red**: opcional y explícita (descarga del GGUF, `pip-audit`/OSV, verificación
   de URLs). El backend por defecto (stdlib) no usa red.

## Amenazas y mitigaciones

| Amenaza (LLM/ATLAS) | Vector | Mitigación |
|---|---|---|
| Prompt injection (LLM01) | instrucciones en contenido procesado | P0.13 (dato≠orden), delimitadores `<untrusted_data>`, guardarraíles deterministas |
| Fuga de secretos (LLM02/LLM07) | leer `.env`/claves; system prompt como boundary | `read`/`edit` deny de claves y `.env`; `.gitignore`; P0.6 |
| Abuso de herramientas (LLM06) | comandos destructivos vía agente | deny deterministas (`rm -rf`, `DROP`, `git reset --hard`, `git push --force`); P0.3/P0.4 |
| Ejecución no confiable (LLM05) | pipes `curl|bash`, `eval` | `analyze_shell.py`, P0.8; `eval`/`exec` prohibidos en scripts |
| Fuga de datos personales (LLM02) | commits con PII/IPs/claves | checks del verificador (P0.9/P0.10), hook `Assisted-by` (P1.14) |
| Cadena de suministro (LLM03) | dependencias opcionales | SBOM + lock con hashes (REQ-020), `pip-audit`/OSV, backend stdlib por defecto |
| Consumo no acotado (LLM10) | bucles de herramientas/prompts | límites de entrada MCP (REQ-007), timeouts, P0.19 |
| Saturación/DoS local | ejecución repetida del modelo | `--max-mutantes`, timeouts; Jev fuera del pre-commit |

## Riesgos residuales (declarados)

- El matcher de permisos de opencode compara tokens posicionales: formas no
  cubiertas (pipes `|`, `sed -i`, varios comandos con `;`) pueden eludir deny;
  la defensa primaria sigue siendo la regla de texto (ver `docs/PRUEBAS.md`).
- `ask` no es 100 % determinista en algunas versiones (issue upstream); la
  protección real son los `deny`.
- El motor Jev es **experimental** (accuracy 0.646); no decide sin humano.
- Sin auditoría externa ni SLSA >= 2: ver `docs/ALCANCE.md`.

## Referencias

- OWASP GenAI LLM Top 10 2026 (LLM01–LLM10); MITRE ATLAS.
- Reglas del proyecto: `AGENTS.md`, `docs/REGLAS-COMPLETAS.md`.
- Evidencia: `docs/PRUEBAS.md`, `docs/SBOM-2026-09-20.cdx.json`, `.docs/lessons/`.
