#!/bin/bash
# WorldLab — piloto principal en modo RECURRENTE (cada 2 h).
# El scheduler de Hermes mata procesos de larga duración (~1 h). Con checkpoint
# por mundo + --resume, cada ciclo avanza los mundos pendientes y los conserva
# en piloto_summary.json. Cuando estén los 96, este script no hace nada.
cd /Users/ruben/Proyectos/worldlab || exit 1

# guard anti-doble-instancia (el job recurrente puede solaparse con el anterior)
if pgrep -f "ai.run_pilot --worlds 8" >/dev/null 2>&1; then
  echo "$(date '+%H:%M:%S') piloto ya corriendo — salgo" >> data/silver/piloto_recurrente.log
  exit 0
fi

# si ya están los 96 mundos, terminar limpio
N=$(python3 -c "
import json, os
p='data/silver/piloto/piloto_summary.json'
print(len(json.load(open(p))) if os.path.exists(p) else 0)" 2>/dev/null || echo 0)
if [ "$N" -ge 96 ]; then
  echo "$(date '+%Y-%m-%d %H:%M') PILOTO COMPLETO ($N/96 mundos)" >> data/silver/piloto_recurrente.log
  echo "PILOTO COMPLETO: $N/96 mundos. Resultados en data/silver/piloto/piloto_summary.json"
  exit 0
fi

echo "$(date '+%H:%M:%S') ciclo nuevo — mundos completados hasta ahora: $N" >> data/silver/piloto_recurrente.log
.venv/bin/python -m ai.run_pilot --worlds 8 --days 30 --model qwen2.5:7b --resume 2>&1 | tee -a data/silver/piloto_progress.log
