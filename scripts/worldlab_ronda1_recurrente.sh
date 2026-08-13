#!/bin/bash
# WorldLab — RONDA 1 en modo RECURRENTE (cada 2 h).
# Pregunta: ¿sobreviven y cruzan? Densidad única 7%, D-022..D-026 aplicados.
# Misma mecánica validada que el piloto: bash lanza el python en background y
# sale limpio; el python queda huérfano y el próximo ciclo lo reanuda con
# --resume. Directorio PROPIO (data/silver/ronda1) para NO sobrescribir el
# piloto (pitfall: colisión de nombres entre corridas).
cd /Users/ruben/Proyectos/worldlab || exit 1

EXP_PREFIX="ronda1"
OUT_DIR="data/silver/ronda1"
N_MUNDOS=32   # 8 seeds × 4 condiciones × 1 densidad (7%)
GATE="docs/gates/ronda1.gate"

# GATE EN CÓDIGO, no solo en la bitácora. La ronda 1 está bloqueada mientras el
# techo informado (oráculo) no sobreviva: sin techo, LE no tiene denominador.
# Un bloqueo que solo vive en un .md se salta agendando el script por error.
# Para abrir: crear docs/gates/ronda1.gate con la decisión y su fecha (queda
# versionado en git — la decisión de desbloquear es parte del registro).
if [ ! -f "$GATE" ]; then
  echo "$(date '+%Y-%m-%d %H:%M') BLOQUEADA: falta $GATE — no se lanza" >> data/silver/ronda1_recurrente.log
  echo "RONDA 1 BLOQUEADA: no existe $GATE. Ver docs/BITACORA.md (gate del oráculo)."
  exit 0
fi

# guard anti-doble-instancia: el patrón debe ser un substring LITERAL de la
# línea de comando real (--out-dir no va pegado a ai.run_pilot).
if pgrep -f "out-dir $OUT_DIR" >/dev/null 2>&1; then
  echo "$(date '+%H:%M:%S') ronda1 ya corriendo — salgo" >> data/silver/ronda1_recurrente.log
  exit 0
fi

# si ya están los mundos, terminar limpio y avisar una sola vez
N=$(python3 -c "
import json, os
p='$OUT_DIR/${EXP_PREFIX}_summary.json'
print(len(json.load(open(p))) if os.path.exists(p) else 0)" 2>/dev/null || echo 0)
if [ "$N" -ge "$N_MUNDOS" ]; then
  echo "$(date '+%Y-%m-%d %H:%M') RONDA 1 COMPLETA ($N/$N_MUNDOS mundos)" >> data/silver/ronda1_recurrente.log
  echo "RONDA 1 COMPLETA: $N/$N_MUNDOS mundos. Resultados en $OUT_DIR/${EXP_PREFIX}_summary.json"
  exit 0
fi

echo "$(date '+%H:%M:%S') ciclo nuevo — mundos completados hasta ahora: $N" >> data/silver/ronda1_recurrente.log
# lanzar en background: el bash termina ya, el python sigue (huérfano, PPID 1)
.venv/bin/python -m ai.run_pilot --worlds 8 --days 30 --model qwen2.5:7b \
  --density 7 --out-dir "$OUT_DIR" --exp-prefix "$EXP_PREFIX" --resume \
  >> data/silver/ronda1_progress.log 2>&1 &
exit 0
