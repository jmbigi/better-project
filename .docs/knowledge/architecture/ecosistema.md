# Arquitectura del ecosistema

## Pilar 1: requisitos como contrato

Los requisitos son la fuente de verdad del alcance. Viven en
`.docs/requirements/REQ-XXX.md` con frontmatter YAML y estados de ciclo de
vida. El validador `scripts/doc_validator.py` conecta el contrato con el
codigo: cada referencia `REQ-XXX` en el codigo debe tener su archivo, y el
estado debe ser coherente con el uso.

## Pilar 2: conocimiento indexado

`.docs/knowledge/` es el cerebro del proyecto: arquitectura, reglas de
negocio y glosario en Markdown con una idea principal por seccion H2.
`scripts/index_knowledge.py` lo convierte en chunks y lo indexa para
busqueda por los agentes, con ChromaDB (vectorial) o indice JSON TF-IDF.

## Pilar 3: memoria de lecciones

`.docs/lessons/` guarda lecciones aprendidas en YAML por anio. El extractor
las exporta a un archivo plano que los agentes consultan antes de depurar,
para no repetir errores pasados.

## Integracion con agentes

Los agentes consumen el ecosistema por dos vias: las directivas de
`AGENTS.md` (flujo de trabajo) y el servidor MCP `scripts/mcp_server.py`
(herramientas reales: busqueda, lectura de requisitos, validacion, alta de
lecciones). Todo corre local, sin servicios externos.
