#!/bin/bash
# WorldLab — piloto principal en modo RECURRENTE (cada 2 h).
# El bash lanza el python en background y SALE LIMPIO (exit 0) para que el
# scheduler NO marque timeout (los "errores" previos eran ese timeout, no
# fallos del piloto). El python queda huérfano y corre hasta completar o
# morir; el próximo ciclo lo reanuda con --resume (checkpoint por mundo).
cd /Users/ruben/Proyectos/worldlab || exit 1

# guard anti-doble-instancia
if pgrep -f "ai.run_pilot --worlds 8" >/dev/null 2>&1; then
  echo "$(date '+%H:%M:%S') piloto ya corriendo — salgo" >> data/silver/piloto_recurrente.log
  exit 0
fi

# si ya están los 96 mundos, terminar limpio y avisar una sola vez
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
# lanzar en background: el bash termina ya, el python sigue (huérfano, PPID 1)
.venv/bin/python -m ai.run_pilot --worlds 8 --days 30 --model qwen2.5:7b --resume \
  >> data/silver/piloto_progress.log 2>&1 &
exit 0
