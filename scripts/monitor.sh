#!/usr/bin/env bash
# Registra CPU y RAM del host (y CPU del contenedor api) mientras corre una prueba de carga.
# Uso (en la instancia):  bash scripts/monitor.sh SEGUNDOS evidencias/monitor_50rps.csv
DUR=${1:-60}; OUT=${2:-monitor.csv}
cd "$(dirname "$0")/.."
API_CID=""; command -v docker >/dev/null && API_CID=$(docker compose ps -q api 2>/dev/null)
cpu() { awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5+$6}' /proc/stat; }
echo "segundo,cpu_host_pct,ram_usada_mb,cpu_api_pct" > "$OUT"
read -r T0 I0 < <(cpu); t=0
while [ $t -lt "$DUR" ]; do
  sleep 2; t=$((t+2))
  read -r T1 I1 < <(cpu)
  pct=$(awk -v t=$((T1-T0)) -v i=$((I1-I0)) 'BEGIN{ if(t>0) printf "%.1f", (t-i)*100/t; else print 0 }')
  T0=$T1; I0=$I1
  ram=$(free -m | awk '/^Mem:/{print $3}')
  apicpu=""; [ -n "$API_CID" ] && apicpu=$(docker stats --no-stream --format '{{.CPUPerc}}' "$API_CID" | tr -d '%')
  echo "$t,$pct,$ram,$apicpu" >> "$OUT"
done
awk -F, 'NR>1{n++; s+=$2; if($2>m)m=$2; if($3>r)r=$3; if($4>a)a=$4} END{
  printf "CPU host: prom %.1f%%  máx %.1f%% | RAM usada máx: %d MB | CPU contenedor api máx: %s%%\n", s/n, m, r, a}' "$OUT"
