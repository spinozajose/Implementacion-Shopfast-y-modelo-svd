#!/usr/bin/env bash
# Recolecta la evidencia de EP3: casos de la Tabla 22, seguridad (17), modelo (Tabla 24),
# datos de la instancia (15.1) y logs (18/19). Guarda todo en evidencias/<fecha>/.
#   En la instancia:   cd ~/shopfast && bash scripts/evidencia.sh
#   Desde tu PC:       env API=http://IP:8000 FRONT=http://IP KEY=tu_clave bash scripts/evidencia.sh
set -u
cd "$(dirname "$0")/.."
API=${API:-http://localhost:8000}
FRONT=${FRONT:-${API%:8000}}
if [ -z "${KEY:-}" ] && [ -f .env ]; then KEY=$(grep -E '^API_KEY=' .env | cut -d= -f2-); fi
[ -z "${KEY:-}" ] && { echo "Falta KEY (o un .env con API_KEY)"; exit 1; }
OUT=evidencias/$(date +%Y%m%d-%H%M%S); mkdir -p "$OUT"
HAVE_DOCKER=0
if command -v docker >/dev/null && [ -f docker-compose.yml ] && docker compose ps >/dev/null 2>&1; then HAVE_DOCKER=1; fi
H=(-H "X-API-Key: $KEY"); J=(-H "Content-Type: application/json")
PASS=0; FAIL=0; LAST=""; : > "$OUT/resumen.txt"

# caso ID "descripción" CODIGO_ESPERADO <argumentos de curl...>
caso() {
  local id=$1 desc=$2 exp=$3; shift 3
  local f="$OUT/caso_$id.txt" code
  code=$(curl -s -m 10 -D "$f.hdr" -o "$f.body" -w '%{http_code}' "$@")
  LAST=$(cat "$f.body" 2>/dev/null)
  { echo "# Caso $id: $desc"; echo "# Esperado: HTTP $exp | Obtenido: HTTP $code"; echo
    cat "$f.hdr" 2>/dev/null; cat "$f.body" 2>/dev/null; echo; } > "$f"
  rm -f "$f.hdr" "$f.body"
  local r=FALLA; if [ "$code" = "$exp" ]; then r=OK; PASS=$((PASS+1)); else FAIL=$((FAIL+1)); fi
  printf '%-4s %-46s esperado %s obtenido %s  %s\n' "$id" "$desc" "$exp" "$code" "$r" | tee -a "$OUT/resumen.txt"
}
nota() { echo "     -> $*" | tee -a "$OUT/resumen.txt"; }
n_prod() { echo "$LAST" | grep -o '"product_id"' | wc -l; }

echo "== Tabla 22: casos de prueba ($API) ==" | tee -a "$OUT/resumen.txt"
caso 01 "GET /health" 200 "$API/health"
caso 02 "Recomendaciones usuario válido (U00001)" 200 "${H[@]}" "$API/recommendations/U00001"
nota "productos devueltos: $(n_prod); fallback: $(echo "$LAST" | grep -Eo '"fallback": ?(true|false)')"
caso 03 "Usuario inexistente (U99999)" 404 "${H[@]}" "$API/recommendations/U99999"
caso 04 "Usuario sin historial (U_COLD01)" 200 "${H[@]}" "$API/recommendations/U_COLD01"
nota "productos devueltos: $(n_prod); fallback: $(echo "$LAST" | grep -Eo '"fallback": ?(true|false)')"
caso 05 "POST interacción view" 202 -X POST "${H[@]}" "${J[@]}" \
  -d '{"user_id":"U00001","product_id":"P0001","interaction_type":"view"}' "$API/track-interaction"
caso 06 "POST interacción purchase" 202 -X POST "${H[@]}" "${J[@]}" \
  -d '{"user_id":"U00001","product_id":"P0002","interaction_type":"purchase"}' "$API/track-interaction"

# Caso 07: el worker guardó la interacción (solo donde hay Docker Compose)
if [ $HAVE_DOCKER = 1 ]; then
  sleep 3
  { echo "# Caso 07: procesamiento del worker"
    docker compose logs worker --tail 10 --no-color
    echo "# Últimas 3 filas de interactions en SQLite:"
    docker compose exec -T worker python -c "import sqlite3;c=sqlite3.connect('/data/shopfast.db');[print(r) for r in c.execute('select * from interactions order by rowid desc limit 3')]"
  } > "$OUT/caso_07.txt" 2>&1
  if grep -q "Interacción guardada: U00001 purchase P0002" "$OUT/caso_07.txt"; then r=OK; PASS=$((PASS+1)); else r=FALLA; FAIL=$((FAIL+1)); fi
  printf '%-4s %-46s %s\n' 07 "Worker almacena la interacción (logs + SQLite)" "$r" | tee -a "$OUT/resumen.txt"
else
  echo "07   (omitido: ejecuta este script dentro de la instancia para verificar el worker)" | tee -a "$OUT/resumen.txt"
fi
caso 08 "GET /products/P0001/related" 200 "${H[@]}" "$API/products/P0001/related"
caso 09 "GET /model/info" 200 "${H[@]}" "$API/model/info"
caso 10 "Ruta protegida sin API Key" 401 "$API/recommendations/U00001"
caso 11 "GET /metrics" 200 "${H[@]}" "$API/metrics"
caso 12 "Parámetro inválido (user_id con comilla)" 400 "${H[@]}" "$API/recommendations/U1%27OR1"
caso 12b "interaction_type inválido" 400 -X POST "${H[@]}" "${J[@]}" \
  -d '{"user_id":"U00001","product_id":"P0002","interaction_type":"hack"}' "$API/track-interaction"
caso 12c "Producto inexistente (P9999)" 404 -X POST "${H[@]}" "${J[@]}" \
  -d '{"user_id":"U00001","product_id":"P9999","interaction_type":"view"}' "$API/track-interaction"
caso 12d "Cuerpo que no es JSON" 400 -X POST "${H[@]}" -d 'hola' "$API/track-interaction"

echo "== Seguridad (sección 17) y documentación (16) ==" | tee -a "$OUT/resumen.txt"
caso S1 "API Key incorrecta" 401 -H "X-API-Key: clave-falsa" "$API/recommendations/U00001"
caso S2 "Swagger UI /docs" 200 "$API/docs"
caso S3 "Especificación /openapi.json" 200 "$API/openapi.json"
caso F1 "Frontend (tienda y dashboard)" 200 "$FRONT/"
caso F2 "Proxy nginx /api/health" 200 "$FRONT/api/health"

echo "== Modelo (Tabla 24) y división (sección 14) ==" | tee -a "$OUT/resumen.txt"
curl -s -m 10 "${H[@]}" "$API/model/info" > "$OUT/model_info.json"
if [ -f artifacts/metrics.json ]; then cp artifacts/metrics.json "$OUT/metrics.json"; cat artifacts/metrics.json | tee -a "$OUT/resumen.txt"; fi

if [ $HAVE_DOCKER = 1 ]; then
  echo "== Instancia y contenedores (15.1) ==" | tee -a "$OUT/resumen.txt"
  imds() { local t; t=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60'); [ -n "$t" ] && curl -s -m 2 -H "X-aws-ec2-metadata-token: $t" "http://169.254.169.254/latest/meta-data/$1"; }
  {
    echo "tipo de instancia : $(imds instance-type)"; echo "AMI               : $(imds ami-id)"
    echo "zona              : $(imds placement/availability-zone)"; echo "id instancia      : $(imds instance-id)"
    echo "IP pública        : $(imds public-ipv4)"; echo "encendida desde   : $(uptime -s) ($(uptime -p))"
    echo "SO                : $(. /etc/os-release; echo "$PRETTY_NAME")"; echo "vCPU              : $(nproc)"
    echo; free -h; echo; df -h /; echo; docker --version; docker compose version; echo
    docker compose ps; echo; docker stats --no-stream; echo
    echo "# Cola RabbitMQ:"; docker compose exec -T rabbitmq rabbitmqctl list_queues name messages consumers
    echo; ls -la artifacts; sha256sum artifacts/svd_model.pkl
  } > "$OUT/instancia.txt" 2>&1
  cat "$OUT/instancia.txt" | head -12 | tee -a "$OUT/resumen.txt"
  docker compose logs api --tail 40 --no-color > "$OUT/log_api.txt" 2>&1
  docker compose logs worker --tail 40 --no-color > "$OUT/log_worker.txt" 2>&1
fi

echo "== Límite de solicitudes: 130 peticiones seguidas a /metrics ==" | tee -a "$OUT/resumen.txt"
for i in $(seq 1 130); do curl -s -m 5 -o /dev/null -w '%{http_code}\n' "${H[@]}" "$API/metrics"; done \
  | sort | uniq -c | tee "$OUT/rate_limit.txt" | tee -a "$OUT/resumen.txt"
grep -q ' 429$' "$OUT/rate_limit.txt" && nota "se activó el límite (HTTP 429)" || nota "NO se observó 429 (¿RATE_LIMIT_PER_MIN muy alto?)"

# La clave nunca debe quedar escrita en la evidencia
if grep -rqF "$KEY" "$OUT"; then echo "ALERTA: la API Key aparece en $OUT; tápala antes de compartir"; fi
echo; echo "Resultado: $PASS OK, $FAIL con falla. Evidencia en: $OUT"
echo "Espera ~60 s antes de usar la API o el dashboard: el límite de solicitudes quedó activado."
