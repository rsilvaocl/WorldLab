#!/bin/bash
# Piloto WorldLab — job de larga duración (12+ h) lanzado vía Hermes cron.
# Corre el piloto completo (4 condiciones × 3 densidades × 8 mundos, intercalado)
# y entrega el análisis de las 5 métricas que Opus necesita.
cd /Users/ruben/Proyectos/worldlab || exit 1
{
  echo "=== PILOTO WORLDLAB iniciado: $(date '+%Y-%m-%d %H:%M:%S') ==="
  .venv/bin/python -m ai.run_pilot --worlds 8 --days 30 --model qwen2.5:7b
  echo ""
  echo "=== ANÁLISIS ==="
  .venv/bin/python -m ai.analyze_pilot
  echo ""
  echo "=== FIN: $(date '+%Y-%m-%d %H:%M:%S') ==="
} 2>&1 | tee data/silver/piloto_progress.log
