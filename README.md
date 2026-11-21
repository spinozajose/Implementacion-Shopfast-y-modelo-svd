# ShopFast – Prototipo EP3

Sistema de recomendación (SVD) con API REST, mensajería asíncrona y despliegue en AWS EC2.

## Estructura
```
dataset/generate_dataset.py   # Paso 1: dataset sintético (semilla 42)
model/train.py                # Paso 1: entrena SVD, evalúa, precalcula Top 10 -> SQLite
api/        worker/  frontend/  tests/    # Pasos 2 a 5 (pendientes)
docs/diagramas.md             # Figuras 8 y 9 (Mermaid)
```

## Paso 1 – Dataset y modelo (local)
```bash
python3.11 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python dataset/generate_dataset.py --out data     # 5.000 usuarios, 500 productos, 150.000 interacciones
python model/train.py --data data --out artifacts # genera svd_model.pkl, metrics.json, shopfast.db
```
`artifacts/metrics.json` contiene RMSE, MAE, Precision@10, Recall@10 y F1@10 reales
(copiarlos a la Tabla 24; los valores deben salir de esta ejecución, no de otra fuente).

## Configuración
- Copiar `.env.example` a `.env` y cambiar las claves. **Nunca** subir `.env` a Git.
- Subir `data/` y `artifacts/` a S3 (se hace en el Paso 4, despliegue).

## Paso 2 – API REST, worker y mensajería
```
api/app.py        # Flask: 6 endpoints + /docs (Swagger) + /openapi.json
api/openapi.py    # especificación OpenAPI 3
worker/worker.py  # consume la cola 'interactions' y escribe en SQLite
api/Dockerfile, worker/Dockerfile   # (build desde la raíz del repo; los usa docker-compose en el Paso 3)
```
Comportamiento clave:
- **Auth**: cabecera `X-API-Key` (401 si falta o es incorrecta). La API **no arranca** sin `API_KEY`.
- **Validación**: `user_id`/`product_id` con regex `^[A-Za-z0-9_]{1,20}$` y consultas parametrizadas (400/404).
- **Rate limiting**: ventana de 60 s por cliente, `RATE_LIMIT_PER_MIN` (429 + `Retry-After`).
- **Fallback**: usuario existente sin recomendaciones (p. ej. `U_COLD01`) recibe los 10 más populares, con `fallback: true`.
- **Asíncrono**: `POST /track-interaction` publica en RabbitMQ y responde `202`; si el broker cae responde `503`.
- **/model/info** lee `metrics.json` y calcula el hash de `svd_model.pkl`; la API no carga Surprise (el Top 10 viene precalculado).
- **/metrics**: contadores y p50/p95/p99 en memoria **por proceso**; por eso Gunicorn corre con 1 worker y 4 hilos. Si subes `-w`, las métricas quedarán divididas.
- Swagger UI (`/docs`) carga su JS desde un CDN: el navegador necesita Internet.

Prueba rápida sin Docker (tras el Paso 1; necesita `pip install flask pika`):
```bash
API_KEY=dev DB_PATH=artifacts/shopfast.db ARTIFACTS_DIR=artifacts python api/app.py
curl -H "X-API-Key: dev" localhost:8000/recommendations/U00001
```
(`/track-interaction` necesita RabbitMQ; se prueba completo con el `docker-compose` del Paso 3.)

## Paso 3 – Frontend y docker-compose
```
frontend/            # React 18 + Vite (sin JSX, solo createElement)
  src/App.js         #   pestaña Tienda (Top 10, interacciones, relacionados) y pestaña Dashboard
  src/api.js, util.js, util.test.js
  nginx.conf.template, Dockerfile   # build multi-etapa; nginx reenvía /api/ y agrega la API Key
docker-compose.yml   # rabbitmq + api + worker + frontend; volumen ./artifacts compartido
```
Ejecución (local o en EC2), con `.env` creado y `artifacts/` generado por `model/train.py`:
```bash
docker compose up -d --build
docker compose ps                      # captura para la sección 15.1
# Tienda:    http://localhost/          Swagger: http://localhost:8000/docs
curl -H "X-API-Key: <tu clave>" http://localhost:8000/recommendations/U00001
docker compose logs -f worker          # ver las interacciones persistidas (paso 8)
```
Desarrollo del frontend sin Docker: `cd frontend && npm install && API_KEY=dev npm run dev`.

Puertos publicados: **80** (frontend) y **8000** (API). RabbitMQ y SQLite no se exponen.
Notas de diseño:
- La API Key vive en el servidor (nginx), no en el JavaScript. Consecuencia: quien alcance el puerto 80 puede usar `/api/`; es aceptable en un prototipo y debe declararse como limitación.
- Todo el tráfico del frontend llega a la API desde la IP de nginx, así que comparte un solo cupo de rate limiting (`RATE_LIMIT_PER_MIN`, por defecto 120). Súbelo en `.env` si el dashboard (cada 5 s) y las pruebas conviven.
- Para las pruebas de carga (Paso 5) apunta Locust al puerto 8000, no al 80.
