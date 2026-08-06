# Arquitectura de la demo

## Almacenamiento local

Las notas viven en `notas.json` junto al script (REQ-001). El archivo se
crea si no existe y se reescribe en cada mutacion: formato simple y
portable, sin base de datos.

## Interfaz de linea de comandos

`src/notas.py` usa argparse: `add "texto"`, `list` y `done <id>`. Cada
subcomando opera sobre el mismo archivo JSON; la salida es texto plano
para encajar con pipes y scripts.
