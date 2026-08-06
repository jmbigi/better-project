# Glosario

## REQ

Identificador de requisito, formato `REQ-XXX`. Archivo Markdown con
frontmatter YAML en `.docs/requirements/`.

## Chunk

Fragmento de conocimiento indexable, obtenido al dividir un Markdown por sus
secciones H2. Una idea principal por chunk.

## Trazabilidad

Conexion verificable entre codigo y requisito: el codigo cita `REQ-XXX` y el
validador comprueba que la referencia es coherente con el archivo.

## MCP

Model Context Protocol: protocolo estandar para exponer herramientas a
agentes de IA. Este proyecto sirve un servidor local por stdio.

## LSN

Identificador de leccion aprendida, formato `LSN-NNN`. Entrada en
`.docs/lessons/<anio>.yaml`.
