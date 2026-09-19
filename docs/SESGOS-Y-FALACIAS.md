# Sesgos y falacias en las decisiones de un proyecto de código

> Documento de referencia del **Pilar 4** (calidad de las decisiones). Texto base
> aportado por el programador e integrado por la IA el 2026-09-19 (P1.14). Se
> complementa con el **plan de mitigación y las herramientas ejecutables** de la
> sección 8. Referenciado desde `README.md`, `AGENTS.md`, `CHECKLIST.md` y
> `docs/REGLAS-COMPLETAS.md`.

Aplicar el análisis crítico a un proyecto real de software significa examinar
**cómo decidimos** —qué arquitectura, qué lenguaje, qué patrón, qué librería,
qué algoritmo o qué deuda técnica aceptamos— y **cómo justificamos** esas
elecciones. Cada decisión de diseño es un argumento formal o informal: tiene
premisas (requisitos, restricciones, experiencia previa), una inferencia (si
implementamos X, obtendremos Y) y una conclusión (por tanto, adoptamos X). Como
todo argumento, este proceso está expuesto a vicios lógicos y distorsiones
cognitivas.

---

## 1. El sesgo como "oblicuidad" en el diseño

La RAE define el sesgo como **oblicuidad o torcimiento hacia un lado**. En el
diseño de software, esa oblicuidad se manifiesta cuando una decisión se inclina
sistemáticamente en una dirección sin una razón técnica objetiva que la
respalde. No es un error aleatorio, sino una **tendencia predecible** que se
repite a lo largo del ciclo de vida.

La acepción estadística —**error sistemático al seleccionar o favorecer unas
respuestas frente a otras**— es esclarecedora. En un proyecto de código,
"seleccionar respuestas" equivale a:

- Priorizar determinados requisitos funcionales e ignorar otros (p. ej.,
  atributos de calidad o accesibilidad).
- Definir qué métricas e indicadores clave de rendimiento (KPI) medir y cuáles
  omitir.
- Seleccionar los perfiles de usuario o escenarios representados en las suites
  de pruebas.
- Determinar qué stack tecnológico adoptar y cuál descartar.
- Elegir qué deuda técnica refactorizar y saldar y cuál postergar
  indefinidamente.

Cada una de estas elecciones puede estar distorsionada. A diferencia del error
fortuito, **el sesgo no se corrige incrementando el volumen de datos del mismo
tipo**: requiere transformar el proceso de selección e inferencia.

---

## 2. Taxonomía de sesgos cognitivos en el ciclo de desarrollo

### 2.1 Sesgos en la selección y procesamiento de información

#### Sesgo de confirmación

Tendencia a buscar, interpretar y recordar información que confirma las
hipótesis previas.

- **Manifestación**: un equipo decide adoptar microservicios y consulta
  únicamente literatura que destaca sus beneficios (escalabilidad,
  independencia de despliegue), ignorando los costos operativos (latencia de
  red, consistencia distribuida, complejidad de trazabilidad). En revisiones de
  código, el autor busca validar que el flujo principal funciona, omitiendo
  pruebas de bordes o fallos.
- **Falacia asociada**: *evidencia suprimida*. Omisión deliberada o inconsciente
  de contraejemplos críticos.

#### Sesgo de disponibilidad

Evaluación de la probabilidad o adecuación de un elemento basada en la facilidad
con la que acuden ejemplos a la mente.

- **Manifestación**: selección de una librería o framework por ser tendencia
  reciente o por haberse usado en el proyecto anterior, en lugar de evaluar su
  ajuste con los requisitos actuales. En depuración, buscar la causa raíz en el
  mismo componente donde ocurrió el último incidente relevante.
- **Falacia asociada**: *generalización apresurada*. Transferir el éxito de un
  contexto A a un contexto B sin verificar la equivalencia de condiciones.

#### Sesgo de anclaje

Dependencia desproporcionada de la primera información recibida al tomar
decisiones posteriores.

- **Manifestación**: la primera estimación expresada informalmente ("esto toma
  dos semanas") actúa como ancla para todas las planificaciones futuras, aun
  cuando emerjan nuevos requisitos. En arquitectura, la primera propuesta
  condiciona la evaluación de alternativas, usándola como base fija en lugar de
  comparar opciones de forma independiente.
- **Falacia asociada**: *falsa dicotomía*. Limitar el espacio de decisión a
  "mantener la propuesta anclada" o "no hacer nada".

### 2.2 Sesgos en la atribución y dinámica de equipos

#### Realismo naíf

Creencia implícita de que percibimos la realidad de manera objetiva y que quienes
discrepan carecen de información o actúan de mala fe.

- **Manifestación**: asumir que una implementación es "claramente legible" y que
  las observaciones del revisor se deben a falta de contexto; tratar la
  legibilidad como propiedad intrínseca del código y no como relación entre el
  código y el lector.
- **Falacia asociada**: *argumentum ad hominem*. Descalificar la capacidad
  técnica del revisor en lugar de abordar el hallazgo sobre la mantenibilidad.

#### Error de atribución grupal

Atribuir comportamientos puntuales de un individuo o subgrupo a características
internas y estables de todo el colectivo.

- **Manifestación**: afirmar que "el equipo de infraestructura siempre bloquea
  los despliegues", ignorando variables contextuales (cuellos de botella en la
  canalización CI/CD, falta de entornos de prueba, cambios de alcance de último
  momento).
- **Falacia asociada**: *estereotipo* y *generalización apresurada*.

#### Favoritismo intragrupal (*in-group favoritism*)

Tendencia a evaluar de manera más favorable las propuestas, estándares o código
generados dentro del propio subequipo.

- **Manifestación**: defender con rigurosidad las convenciones de diseño del
  equipo local frente a las de equipos remotos o externos, reduciendo la
  interoperabilidad de APIs y la reutilización de componentes.

### 2.3 Sesgos por autoridad y procedencia

#### Sesgo de autoridad

Validación de una premisa técnica en función del estatus o reputación de quien la
emite.

- **Manifestación**: adopción de patrones o herramientas respaldados por grandes
  corporaciones o referentes ("lo utiliza Big Tech X, luego es la arquitectura
  correcta"), omitiendo el análisis de idoneidad respecto a la escala real del
  problema.
- **Falacia asociada**: *argumentum ad verecundiam*. Apelar a la autoridad como
  prueba suficiente de adecuación técnica.

#### Devaluación reactiva

Descuento o rechazo de una propuesta técnica debido al origen de la fuente o a
relaciones interpersonales complejas.

- **Manifestación**: descartar un refactor o una librería porque la sugirió un
  departamento con el que existen conflictos organizacionales, o por prejuicios
  hacia el lenguaje en el que está implementada.

### 2.4 Sesgos de influencia social

#### Efecto de arrastre (*bandwagon effect*)

Adopción de un comportamiento, herramienta o paradigma en función de la tasa de
adopción masiva en la industria.

- **Manifestación**: reemplazo masivo de tecnologías consolidadas por frameworks
  emergentes sin una evaluación de costo-beneficio o madurez del ecosistema.
- **Falacia asociada**: *argumentum ad populum*. Asumir que la popularidad
  implica corrección técnica.

#### Falso consenso

Presunción de que la propia opinión o decisión es compartida por la mayoría del
equipo.

- **Manifestación**: dar por aprobada una decisión de arquitectura por ausencia
  de objeciones explícitas, omitiendo consultar activamente a los roles más
  reservados o con opiniones divergentes.

### 2.5 Sesgos en la evaluación de argumentos y resultados

#### Sesgo de mi lado (*my-side bias*)

Tendencia a evaluar la evidencia de forma asimétrica para favorecer las posturas
previamente adoptadas.

- **Manifestación**: generar activamente argumentos para justificar una decisión
  de diseño propia durante una revisión, manteniendo una postura hipercrítica
  frente a diseños alternativos de terceros.

#### Sesgo de resultado (*outcome bias*)

Evaluación de la calidad de una decisión basándose solo en el resultado final,
ignorando la calidad del proceso y la información disponible al momento de
tomarla.

- **Manifestación**: catalogar una arquitectura con deficiencias de seguridad
  como "correcta" porque no sufrió incidentes durante el primer año, o juzgar
  una decisión prudente como "errónea" por un evento fortuito impredecible.
- **Falacia asociada**: *post hoc ergo propter hoc*. Establecer relaciones de
  causalidad arbitrarias entre una práctica y el resultado obtenido.

---

## 3. Catálogo formal de falacias en argumentos técnicos

| Categoría | Falacia | Definición | Ejemplo en ingeniería de software |
| --- | --- | --- | --- |
| **Relevancia** | *Ad hominem* | Ataque a la persona que propone la solución. | "Esa propuesta de refactorización la hizo un programador junior; no vale la pena revisarla." |
|  | *Ad verecundiam* | Apelación a la autoridad como prueba suficiente. | "Debemos usar este ORM porque lo recomienda un autor reconocido de arquitectura." |
|  | *Ad populum* | Justificación basada en la adopción mayoritaria. | "La mayoría de las startups usan esta base de datos NoSQL; debiéramos migrar." |
|  | *Ad antiquitatem* | Apelación a la tradición o costumbre. | "Siempre hemos desplegado manualmente este monolito; no hay razón para automatizarlo." |
|  | *Ad novitatem* | Apelación a la novedad como sinónimo de superioridad. | "Esta librería se publicó este mes, por lo tanto es superior a la alternativa estable." |
|  | *Tu quoque* | Descalificar una crítica señalando una falta similar en el interlocutor. | "Criticas la falta de pruebas en mi módulo, pero tu servicio tampoco tiene cobertura de integración." |
| **Ambigüedad** | Equívoco | Uso de un término en distintos sentidos dentro del mismo argumento. | "El sistema es *escalable*" (confundiendo escalado horizontal con procesamiento vertical de una instancia). |
|  | Anfibología | Ambigüedad en la estructura sintáctica de una afirmación. | "El servicio procesa 10 000 peticiones" (sin precisar si es por segundo, por día o bajo qué infraestructura). |
|  | Composición | Inferir propiedades del todo a partir de las partes. | "Cada función ejecuta en menos de 1 ms, por ende la transacción completa será rápida" (ignorando latencia de red y bloqueos de E/S). |
|  | División | Inferir propiedades de las partes a partir del todo. | "Este framework de procesamiento masivo es de alta velocidad, por lo tanto este script individual responderá inmediatamente." |
| **Presunción** | Petición de principio | Asumir en las premisas la conclusión que se pretende probar. | "Este diseño es óptimo porque respeta las buenas prácticas de arquitectura" (sin demostrar por qué aplican a este problema). |
|  | Falsa dicotomía | Reducir el espacio de opciones a dos alternativas excluyentes. | "O migramos la aplicación completa a Serverless o el sistema colapsará en el siguiente pico de tráfico." |
|  | Generalización apresurada | Extraer una regla general de una muestra insuficiente. | "Ejecutamos la prueba de carga con 10 usuarios concurrentes y el tiempo de respuesta fue bajo; el sistema soporta producción." |
|  | Accidente inverso | Aplicar rígidamente una regla general a un caso excepcional. | "El estándar exige 100 % de cobertura unitaria, por lo tanto debemos probar los métodos autogenerados y DTOs sin lógica." |
|  | Francotirador | Manipular datos o límites de análisis para hacer parecer exitoso un resultado. | "Ajustamos los rangos del benchmark descartando las peticiones lentas para demostrar que el algoritmo cumple el SLA." |
| **Causales** | *Post hoc ergo propter hoc* | Asumir que la secuencia temporal implica causa-efecto. | "Introdujimos el patrón X y al mes siguiente cayeron los incidentes; el patrón eliminó las fallas." |
|  | *Cum hoc ergo propter hoc* | Asumir que la correlación implica causalidad. | "Los módulos con más líneas de código presentan más errores; reducir líneas solucionará los errores." |
|  | Causa falsa | Identificar un factor irrelevante como causa principal. | "La caída del servidor ocurrió justo tras el despliegue del frontend, por lo tanto el frontend tiró la base de datos." |
|  | Pendiente resbaladiza | Argumentar que una medida conduce inevitablemente a un extremo sin evidencia de la cadena causal. | "Si permitimos una excepción a las convenciones de nombres en este script, en tres meses el código será inmanejable." |
| **Inductivas** | Falsa analogía | Comparar sistemas que difieren en aspectos estructurales críticos. | "Los microfrontends funcionan para una plataforma global con 500 desarrolladores, así que funcionarán para nuestro equipo de 4." |
|  | Enumeración incompleta | Concluir la validez de un sistema solo con casos favorables. | "Los escenarios de uso común responden correctamente, por ende el algoritmo de asignación es robusto." |
|  | Falacia del jugador | Creer que eventos pasados independientes alteran la probabilidad de eventos futuros. | "Llevamos cinco despliegues seguidos fallando en este entorno; el siguiente necesariamente saldrá bien." |

---

## 4. Matriz de vulnerabilidad en el ciclo de vida del software

| Fase de desarrollo | Sesgo dominante | Falacia resultante | Impacto en el software |
| --- | --- | --- | --- |
| **Requisitos y descubrimiento** | Sesgo de confirmación | Evidencia suprimida | Definición incompleta de casos extremos y atributos de calidad. |
| **Diseño y arquitectura** | Anclaje | Falsa dicotomía | Evaluación de una única opción arquitectónica frente al estado actual. |
| **Selección de stack** | Autoridad / arrastre | *Ad verecundiam* / *Ad populum* | Dependencias innecesarias o tecnologías no dominadas. |
| **Estimación** | Optimismo / anclaje | Generalización apresurada | Compromisos de entrega basados en escenarios ideales sin contingencia. |
| **Implementación** | Sesgo de automatización | *Ad verecundiam* | Aceptación ciega de sugerencias de IA sin auditoría. |
| **Pruebas y QA** | Sesgo de confirmación | Inducción incompleta | Pruebas diseñadas para pasar, no para romper el sistema. |
| **Revisión de código** | Realismo naíf | *Argumentum ad hominem* | Discusiones sobre autoría e intencionalidad en lugar de calidad. |
| **Despliegue** | Sesgo de resultado | *Post hoc ergo propter hoc* | Atribución errónea del éxito a decisiones riesgosas no documentadas. |
| **Retrospectiva** | Sesgo de supervivencia | Falsa analogía | Adopción de procesos de terceros ignorando sus factores de fallo. |

Cadena típica (ejemplo): *arrastre/autoridad → ad populum → confirmación →
evidencia suprimida → anclaje/falsa dicotomía*.

---

## 5. Estrategias formales de mitigación

### 5.1 Protocolos de decisión y arquitectura

1. **Registros de Decisiones de Arquitectura (ADR)**: documentar contexto,
   alternativas evaluadas, criterios, compromisos (*trade-offs*) y supuestos.
2. **Análisis pre-mortem**: antes de ejecutar una decisión mayor, simular que
   falló catastróficamente y argumentar hacia atrás las causas. Neutraliza el
   optimismo y la confirmación.
3. **Revisión por pares externa o cruzada**: someter la propuesta a
   desarrolladores ajenos al contexto inmediato para detectar supuestos
   implícitos.
4. **Definición cuantitativa de atributos de calidad**: reemplazar adjetivos
   ambiguos ("escalable", "mantenible", "robusto") por métricas verificables
   (p. ej., "tiempo de respuesta p99 < 200 ms bajo 5000 req/s").

### 5.2 Herramientas de auditoría de sesgos y razonamiento

**Evaluación de datos y modelos ML** (aplican si el proyecto entrena/despliega
modelos predictivos; no es el caso de este repositorio):

- **Fairlearn / AI Fairness 360**: detección y mitigación de sesgos en modelos
  predictivos y algoritmos de selección.
- **Evidently AI / Deepchecks**: monitoreo de deriva de datos (*data drift*) y
  sesgos de selección en producción.
- **SHAP / LIME**: explicabilidad de decisiones algorítmicas para evitar sesgos
  opacos.

**Auditoría de código e inferencias asistidas por IA**:

- Análisis estático y dinámico para detectar patrones anómalos o supuestos no
  verificados en el código.
- Linters de arquitectura y verificadores de contratos (*Design by Contract*)
  para sostener las premisas de diseño durante la ejecución.

**Procesos organizacionales**:

- **Rotación de roles en la revisión**: alternar quién actúa como "abogado del
  diablo" (*red team*) para buscar activamente contraejemplos.
- **Listas de chequeo cognitivo**: verificar si se incurrió en anclaje, arrastre
  o apelaciones a la autoridad.

---

## 6. Caso de estudio integrador: migración de un monolito a microservicios

Un equipo evalúa reingeniería por problemas de rendimiento en picos de tráfico.

**Flujo sin mitigación:**

1. **Arrastre y autoridad**: "las Big Tech usan microservicios" (*ad
   verecundiam / ad populum*).
2. **Confirmación**: se recopila solo documentación sobre desacoplamiento y
   escalabilidad, desestimando latencia de red, consistencia eventual y costo de
   infraestructura (*evidencia suprimida*).
3. **Anclaje y falsa dicotomía**: mantener el monolito sin cambios o dividir el
   sistema en 20 microservicios; no se evalúan alternativas intermedias
   (monolito modular, optimización de consultas).
4. **Sesgo de resultado**: tras un año sin colapso se concluye que la decisión
   fue óptima, omitiendo que la infraestructura costó 300 % más y el MTTR se
   duplicó (*post hoc ergo propter hoc*).

**Intervención con el proceso de mitigación:**

- **ADR**: formalizar la necesidad de soportar el incremento de tráfico e
  incluir alternativas (monolito modular, réplicas de lectura, microservicios
  por dominio específico).
- **Pre-mortem**: asumir que la migración causó caídas de red y fallos de
  consistencia transaccional; definir observabilidad, transacciones distribuidas
  (sagas) y presupuesto operativo antes de escribir código.
- **Criterios de parada y métricas**: mantener una sola unidad de despliegue a
  menos que un subdominio requiera escalar asimétricamente por un factor > 10×
  sobre el resto.

---

## 7. Conclusión

En ingeniería de software, los **sesgos** son desviaciones sistemáticas e
inconscientes que inclinan las decisiones hacia soluciones no justificadas por
los requisitos; las **falacias** son la estructura argumentativa defectuosa con
la que se defienden. Un sesgo de percepción genera la falla lógica, y el
argumento falaz blinda el sesgo frente a la crítica técnica.

La mitigación efectiva no depende de la intuición ni de la buena voluntad, sino
de la **institucionalización de procesos críticos**: lógica formal y análisis de
argumentos; herramientas cuantitativas y analíticas; y mecanismos de equipo
(ADR, pre-mortem, revisión cruzada) que fuercen explicitar supuestos y buscar
contraejemplos.

Tratar cada decisión no como una verdad absoluta, sino como una **hipótesis
falible sujeta a refutación**, es la salvaguarda para construir software
robusto, mantenible y acorde a sus necesidades reales.

---

## 8. Plan de mitigación y herramientas del proyecto

Este repositorio **ejecuta** las mitigaciones aplicables con herramientas
propias, testeadas y verificadas en el hook de pre-commit (REQ-013).

### 8.1 Mapa de estrategia → herramienta

| Estrategia (§5) | Herramienta en better-project | Evidencia / estado |
| --- | --- | --- |
| ADR | `docs/decisions/` + `docs/decisions/PLANTILLA.md`; `scripts/adr_validator.py` | Implementado 2026-09-19 |
| Auditoría de sesgos en decisiones | `scripts/adr_validator.py` (alertas: falsa dicotomía, adjetivos ambiguos, supuestos ocultos, afirmaciones absolutas) | Implementado 2026-09-19 |
| Pre-mortem | Sección obligatoria en la plantilla de ADR (guía §5.1) | Implementado (guía) |
| Revisión cruzada / red team | Agentes de solo lectura `@code-reviewer`, `@security-auditor`, `@compliance-checker`, `@dependency-auditor` | Implementado |
| Métricas cuantitativas | `scripts/verificar-proyecto.sh` (38 checks), `scripts/jev_calibration.py` (NLL/Brier/ECE) | Implementado |
| Listas de chequeo cognitivo | `CHECKLIST.md`, sección "Pilar 4" | Implementado |
| Lógica formal (premisas/alternativas/refutación) | Estructura de ADR + validación de secciones obligatorias | Implementado |
| Herramientas ML (Fairlearn, SHAP, Evidently) | No aplican: el repo no entrena ni sirve modelos predictivos propios | N/A |
| Rotación del "abogado del diablo" | Proceso de revisión con los agentes de solo lectura | En proceso (proceso humano) |

### 8.2 Ejecución: cómo se usa

```bash
# Validar los ADR del proyecto (errores de formato/estructura + alertas de sesgo)
python3 scripts/adr_validator.py

# Modo estricto: las alertas de sesgo también fallan (auditoría dura)
python3 scripts/adr_validator.py --strict

# Crear una decisión nueva
cp docs/decisions/PLANTILLA.md docs/decisions/ADR-00N-titulo-corto.md
```

El verificador (`scripts/verificar-proyecto.sh`) ejecuta el validador de ADR en
cada pre-commit, de modo que ninguna decisión de arquitectura entra sin
contexto, alternativas, consecuencias y supuestos.

### 8.3 Plan por fases

1. **Fase 1 (hecha, 2026-09-19)**: documentación del Pilar 4, REQ-013, registro
   de ADR, validador con auditoría de sesgos e integración en verificación.
2. **Fase 2 (propuesta)**: registrar ADR retroactivos de las decisiones clave ya
   tomadas (cliente Jev liviano, derivación del ruleset de better-ai, cuatro
   pilares).
3. **Fase 3 (propuesta)**: pre-mortem obligatorio para cambios de alto impacto
   (P1.23) y métrica de "decisiones refutadas" en la retrospectiva.

### 8.4 Límites declarados

- La auditoría es heurística (detección de patrones textuales), no un análisis
  lógico formal: **asiste** la revisión humana, no la sustituye (P1.15).
- Las herramientas ML de §5.2 no aplican a este repositorio; se documentan para
  proyectos anfitriones que sí entrenen modelos.
- El sesgo no se elimina con más datos del mismo tipo: se corrige cambiando el
  proceso de decisión (ADR + revisión cruzada + métricas).

---

## 9. Referencias

- RAE, definición de *sesgo* (oblicuidad, error sistemático).
- OWASP GenAI LLM Top 10 2026 y MITRE ATLAS: mapeo de cobertura en
  `docs/REGLAS-COMPLETAS.md` (§7).
- Kahneman, D. *Pensar rápido, pensar despacio* (sesgos de anclaje,
  disponibilidad, confirmación).
- Tversky, A., Kahneman, D. *Judgment under Uncertainty: Heuristics and Biases*
  (Science, 1974).
- Documentación de ADR: Michael Nygard, *Documenting Architecture Decisions*.
