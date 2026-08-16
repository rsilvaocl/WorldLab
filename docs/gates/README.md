# Gates — bloqueos ejecutables

Un bloqueo escrito solo en la bitácora se salta agendando un script por error.
Los gates de este directorio los lee el propio script antes de correr.

| Gate | Lo lee | Condición para crearlo |
|---|---|---|
| `ronda1.gate` | `scripts/worldlab_ronda1_recurrente.sh` | El oráculo (techo informado) sobrevive el smoke de 30 días. Sin techo, LE no tiene denominador. |

Crear un gate es una decisión experimental: el archivo debe declarar quién la
tomó, con qué evidencia y en qué fecha, y se commitea. Así el desbloqueo queda
en el registro igual que el bloqueo.
