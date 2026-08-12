#!/bin/bash
# WorldLab — extensión del piloto a 100 días (decisión de Opus, 12/08).
# σ a 30 días no predice σ a 100 días: espera a que el piloto principal
# (30 días) termine y corre 3 condiciones × seeds 1,2,3 × 100 días en
# directorio aparte (no sobrescribe los archivos de 30 días).
cd /Users/ruben/Proyectos/worldlab || exit 1

SUMMARY=data/silver/piloto/piloto_summary.json
WAITED=0
# esperar hasta 72 h a que el piloto principal esté COMPLETO (96 mundos en el
# summary — el piloto ahora corre en ciclos recurrentes con checkpoint)
while :; do
  N=$(python3 -c "
import json, os
p='$SUMMARY'
print(len(json.load(open(p))) if os.path.exists(p) else 0)" 2>/dev/null || echo 0)
  if [ "$N" -ge 96 ]; then
    break
  fi
  if [ "$WAITED" -ge 4320 ]; then
    echo "TIMEOUT: el piloto principal no completó 96 mundos en 72 h — aborto extensión."
    exit 1
  fi
  sleep 60
  WAITED=$((WAITED+1))
done

{
  echo "=== EXTENSIÓN 100 días iniciada: $(date '+%Y-%m-%d %H:%M:%S') ==="
  .venv/bin/python -m ai.extend_pilot qwen2.5:7b
  echo "=== FIN extensión: $(date '+%Y-%m-%d %H:%M:%S') ==="
} 2>&1 | tee data/silver/piloto_extension100d.log
