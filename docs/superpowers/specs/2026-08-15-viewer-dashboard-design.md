# Dashboard de auditoría del visor — diseño

## Propósito

Convertir `viewer.html` de una consola de reproducción a un dashboard de
auditoría: una persona sin conocimiento del protocolo debe poder determinar si
la corrida está completa, si su evidencia puede interpretarse y dónde mirar
para comprobarlo. La interfaz no debe inferir ni declarar éxito experimental.

## Usuarios y decisión principal

- Investigador: decide si la corrida está lista para revisión o si debe
  completarla/corregirla antes de gastar otro ciclo.
- Revisor externo: entiende que la pregunta trata de una celda nunca vivida y
  reconoce qué evidencia está disponible sin abrir documentación externa.

La primera lectura responde: **¿puedo interpretar esta corrida y con qué
límites?** La reproducción temporal continúa disponible para investigar el
detalle, pero deja de ser el punto de entrada.

## Diseño aprobado

### 1. Resumen de auditoría

Debajo del riel superior, se agrega una franja `Lectura de esta corrida`.
Incluye un estado y una explicación breve, basada solamente en archivos
cargados y campos existentes:

| Estado | Cuándo aparece | Mensaje base |
|---|---|---|
| `Incompleta` | Faltan trazas o probes. | Indica qué archivo hermano falta y qué parte de la auditoría no se puede comprobar. |
| `No interpretable` | Hay probes pero falta una celda marcada `never_lived`, o hay agentes subexpuestos. | Advierte que la evidencia no permite sostener la conclusión del probe. |
| `Lista para revisar` | Están las tres fuentes y no se detectan las condiciones anteriores. | Indica que la evidencia está completa para revisión; no afirma que el agente haya compuesto reglas ni que el resultado sea positivo. |
| `Sin corrida` | Antes de cargar datos. | Invita a cargar la corrida y explica los tres archivos que componen su auditoría. |

El bloque mostrará hasta tres razones accionables. Cada razón será un botón o
enlace interno que desplaza el foco al instrumento relevante. Las etiquetas
indicarán si el dato fue medido o derivado cuando aplique.

### 2. Completar la auditoría

Cuando falte un archivo hermano, el resumen y el anunciador correspondiente
mostrarán `Agregar archivos`. El botón abre el selector existente en modo
múltiple y conserva la corrida ya cargada; el usuario puede seleccionar
trazas, probes o ambos. La ayuda especifica las convenciones de nombre:
`<exp>_seed<N>_traces.jsonl` y `<exp>_probes.jsonl`.

El aviso no bloquea la reproducción de la corrida primaria. Su finalidad es
hacer visible qué no se puede auditar aún.

### 3. Jerarquía de instrumentos

La columna derecha se divide visualmente, sin cambiar los datos que calcula
cada instrumento:

1. `Validez de la evidencia`: resumen de integridad, experiencias necesarias
   y predicción sobre la celda nunca vivida.
2. `Detalle de la corrida`: reloj, energía, frontera, tripulación y registro.

Los términos se traducen en la cara de cada instrumento:

- `Exposición` pasa a titularse `Experiencias necesarias`, con `Exposición`
  como subtítulo técnico.
- `Calibración` pasa a titularse `Predicción sobre la celda nunca vivida`, con
  `Probe de composición` como subtítulo técnico.
- La explicación de la celda retenida aparece junto al resumen y junto a la
  cuadrícula de exposición.

### 4. Controles claros y accesibles

- El filtro se etiqueta por su acción y estado: `Mostrar solo acciones
  logradas` / `Mostrar todos los intentos`. El estado inicial deja todos los
  intentos visibles.
- Se muestra una ayuda breve de teclado junto al transporte: espacio reproduce
  o pausa; flechas avanzan o retroceden; inicio y fin van a los extremos.
- Se incorporan los landmarks `header`, `main`, `section` y `aside`; el título
  de arranque mantiene una jerarquía de encabezados correcta.
- El canvas recibe un resumen textual dinámico del instante actual para
  lectores de pantalla. El overlay de arrastre expone su estado solo cuando
  está activo.
- La tipografía de orientación y acciones no baja del tamaño legible actual;
  no se cambia el lenguaje de color existente, pero los estados incluyen texto
  y no dependen solo del color.

## Límites

- Un único `viewer.html`, sin CDN, sin build ni dependencias; debe abrir con
  `file://`.
- Todo contenido proveniente de JSONL sigue escapándose antes de llegar al DOM.
- No se modifican el motor, datos de experimentos ni contratos JSONL.
- No se elimina ningún instrumento actual ni se ocultan intentos fallidos por
  defecto.
- No se introducen métricas ni reglas científicas nuevas: el dashboard resume
  solo señales que el visor ya computa (`traces`, `probes`, `never_lived`,
  `underexposed`).

## Criterios de aceptación

1. Una corrida cargada muestra un estado de auditoría y razones trazables a
   instrumentos concretos.
2. Con solo el JSONL primario, la UI explica que faltan trazas y probes y
   permite agregarlos sin perder la corrida visible.
3. Una corrida con probe inválido o agentes subexpuestos se rotula `No
   interpretable`; una corrida completa sin esas alertas se rotula `Lista para
   revisar`.
4. Un lector sin jerga puede identificar: qué es la celda nunca vivida, qué
   evidencia se requiere y que una corrida lista para revisar no equivale a un
   resultado exitoso.
5. El filtro conserva todos los intentos como opción inicial y expresa
   claramente qué va a ocultar o mostrar.
6. La carga, reproducción, navegación, inspección y controles de archivo se
   mantienen operables por teclado.

## Verificación

- Prueba de regresión de la suite existente: `python -m pytest`.
- Validación estática de estructura y referencias del HTML/JS con un script
  Node sin dependencias, ejecutable localmente.
- Revisión manual con un JSONL primario y sus dos hermanos, incluyendo el caso
  sin probes/traces. Si el entorno permite servir archivos locales, revisar
  además el layout en viewport de escritorio y móvil.
