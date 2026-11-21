#!/usr/bin/env bash
# Convierte los CSV de Locust en filas para la Tabla 23.
# Uso:  bash scripts/resumen_locust.sh evidencias/locust_10_stats.csv [más archivos...]
for f in "$@"; do
  awk -F, -v file="$(basename "$f")" '
    NR==1 { for (i=1;i<=NF;i++) col[$i]=i; next }
    $col["Name"]=="Aggregated" {
      printf "%-26s RPS real=%-7.1f p50=%-6s p95=%-6s p99=%-6s solicitudes=%-7s errores=%s\n", file,
        $col["Requests/s"], $col["50%"], $col["95%"], $col["99%"], $col["Request Count"], $col["Failure Count"] }' "$f"
done
