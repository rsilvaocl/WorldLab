# WorldLab

> **Estado: experimento finalizado y archivado (15 de agosto de 2026).**
>
> WorldLab no demostró que los agentes sean “menos inteligentes”. En este
> experimento concreto, tres modelos recuperaron información disponible, pero
> tuvieron menor exactitud al intentar combinarla que sus respectivos controles
> sin memoria. El patrón se replicó, pero su mecanismo no quedó demostrado y los
> resultados no permiten generalizar a la inteligencia de los agentes.

## Qué terminó siendo el experimento

WorldLab comenzó como un laboratorio de agentes autónomos en un mundo 2D. El
objetivo original era observar si agentes con distintas memorias sobrevivían,
cruzaban regiones y componían regularidades aprendidas durante su experiencia.

Esa ronda completa, llamada **Ronda 1, no se ejecutó**. Los gates previos
encontraron errores de contrato, lectura y observabilidad que hacían que sus
resultados no fueran interpretables. El proyecto terminó con un estudio más
estrecho y controlado: un probe numérico para medir si un modelo podía combinar
correctamente dos dimensiones vividas —región y fase— usando memoria indexada.

La pregunta que efectivamente se midió fue:

> Cuando el valor correcto depende de combinar región y fase, ¿cambia la
> exactitud del modelo al recibir una memoria indexada de experiencias previas,
> comparado con responder sin memoria?

No se midió inteligencia general, autonomía ni supervivencia efectiva de los
agentes.

## Qué ocurrió

El estudio confirmatorio utilizó un banco congelado de 64 ontologías y tres
modelos preespecificados. La réplica técnica volvió a ejecutar ambos brazos y
persistió los **2.304 probes crudos**.

Resultado de la réplica (`memoria_indexada − sin_memoria`):

| modelo | con memoria indexada | sin memoria | diferencia |
|---|---:|---:|---:|
| `deepseek-v4-flash` | 0,078 | 0,203 | **−0,125** |
| `gemma2:9b` | 0,010 | 0,188 | **−0,177** |
| `llama3.1:8b` | 0,031 | 0,208 | **−0,177** |

En los tres modelos, la exactitud observada fue menor en el brazo con memoria
indexada. El contraste contra una diferencia de cero fue significativo en los
tres. La réplica reprodujo exactamente la diferencia de los dos modelos
locales; DeepSeek cambió en 0,008.

Al mismo tiempo, la coincidencia exacta con algún valor vivido fue mayor con
memoria:

| modelo | recuperación con memoria | recuperación sin memoria |
|---|---:|---:|
| `deepseek-v4-flash` | 78,0% | 18,0% |
| `gemma2:9b` | 96,6% | 0,0% (`0/384`) |
| `llama3.1:8b` | 87,0% | 18,2% |

Esto describe lo ocurrido: los modelos tendieron a devolver números presentes
en la memoria, pero no el número resultante de combinar correctamente región y
fase. La comparación de recuperación es descriptiva; no se preregistró un
contraste inferencial específico que permita convertirla en una afirmación
causal.

## Qué permite sostener la evidencia

- Bajo este banco, estos prompts y estos tres modelos, el brazo con memoria
  indexada tuvo menor exactitud que su respectivo control sin memoria.
- El efecto primario negativo reapareció en una segunda ejecución técnica:
  fue exacto en `gemma2:9b` y `llama3.1:8b`, y difirió 0,008 en
  `deepseek-v4-flash`.
- En el brazo con memoria aparecieron más valores vividos en las respuestas,
  pero esa recuperación observada no se tradujo en seleccionar la combinación
  correcta.
- DeepSeek no fue determinista en este entorno: 4 de 10 respuestas completas
  reejecutadas cambiaron. Solo una de esas diez cambió el valor puntuado.

## Qué no se demostró

- Que los agentes o los modelos sean poco inteligentes en términos generales.
- Que la memoria perjudique el razonamiento en otros problemas, formatos o
  modelos.
- Qué mecanismo produjo la menor exactitud. La hipótesis de un sesgo general
  hacia la fase **no replicó** y fue descartada.
- Que el efecto poblacional sea de al menos 10 puntos en los tres modelos. El
  contraste contra `−0,10` no fue significativo para DeepSeek.
- Que los modelos locales sean deterministas. En 10 reejecuciones por modelo no
  se observaron discordancias, pero esa muestra no demuestra determinismo.
- Que los agentes puedan sobrevivir, cruzar y componer dentro del mundo 2D. La
  Ronda 1 que debía responder eso quedó bloqueada y nunca se corrió.

## Por qué se cerró aquí

Los gates cumplieron su función: impidieron interpretar como cognición varios
fallos del instrumento. Durante el desarrollo se detectaron, entre otros,
acciones mal formuladas, memoria que el probe no recibía y una región no
observable a distancia. El visor hizo visible que corridas con 91–96% de
acciones rechazadas podían parecer sanas.

Después de corregir esos problemas fue posible ejecutar y replicar el estudio
numérico descrito arriba, pero ese estudio ya no respondía por completo la
pregunta original sobre agentes autónomos dentro del mundo. No se desbloqueó ni
se gastó la Ronda 1. El repositorio se conserva como registro auditable de lo
que se construyó, falló, corrigió y finalmente se observó.

## Auditar el resultado

El visor carga el agregado confirmatorio y los probes crudos, comprueba el
esquema, los dos brazos, la reconciliación y los checksums, y permite inspeccionar
cada respuesta:

```bash
.venv/bin/python -m http.server 8791
open 'http://localhost:8791/viewer.html?file=data/resultados/replica_v3/agregado.json'
```

Artefactos principales:

- [`viewer.html`](viewer.html) — dashboard auditable del resultado.
- [`agregado.json`](data/resultados/replica_v3/agregado.json) — métricas de la
  réplica técnica.
- [`probes_crudos.jsonl`](data/resultados/replica_v3/probes_crudos.jsonl) —
  2.304 probes persistidos, sin promediar entre corridas.
- [`comparaciones.jsonl`](data/resultados/repetibilidad/comparaciones.jsonl) —
  30 reejecuciones usadas para evaluar repetibilidad.
- [`PROTOCOLO-confirmatorio-v3.md`](docs/PROTOCOLO-confirmatorio-v3.md) — diseño
  confirmatorio congelado.
- [`BITACORA.md`](docs/BITACORA.md) — historial completo, incluidos errores,
  correcciones y límites.

Checksums oficiales de la réplica:

```text
probes_crudos.jsonl  b322ea053dfed6c6a15ecfb4a83a8392fdd4be31b1d45effe804452624e26df3
agregado.json        8276564976eb4fda4fc406a71db6b7c21b7dcaf56c9ca6cddcb51de7a00d187d
```

## Verificación local

Requiere Python 3.12 y `pytest`:

```bash
.venv/bin/python -m pytest -q
```

La última verificación del cierre ejecutó **322 tests** correctamente.
