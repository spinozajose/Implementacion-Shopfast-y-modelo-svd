"""API REST de recomendaciones ShopFast (EP3, secciones 13, 16 y 17).

Endpoints: /health, /recommendations/<user_id>, /track-interaction,
           /products/<product_id>/related, /metrics, /model/info, /docs, /openapi.json
"""
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock

from flask import Flask, Response, g, jsonify, request
from werkzeug.exceptions import HTTPException

from openapi import OPENAPI_SPEC, SWAGGER_HTML

log = logging.getLogger("shopfast.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

ID_RE = re.compile(r"^[A-Za-z0-9_]{1,20}$")
INTERACTION_TYPES = {"view", "click", "cart", "purchase"}
PUBLIC_PATHS = {"/health", "/docs", "/openapi.json"}


class RabbitPublisher:
    """Publica interacciones en RabbitMQ (cola durable, mensajes persistentes)."""

    def __init__(self, host, user, password, queue="interactions"):
        self.host, self.user, self.password, self.queue = host, user, password, queue

    def publish(self, message: dict) -> None:
        import pika  # import diferido: no se necesita para pruebas con publicador falso
        params = pika.ConnectionParameters(
            host=self.host, credentials=pika.PlainCredentials(self.user, self.password),
            connection_attempts=2, retry_delay=1, socket_timeout=3)
        conn = pika.BlockingConnection(params)
        try:
            ch = conn.channel()
            ch.queue_declare(queue=self.queue, durable=True)
            ch.basic_publish(exchange="", routing_key=self.queue, body=json.dumps(message),
                             properties=pika.BasicProperties(delivery_mode=2,
                                                             content_type="application/json"))
        finally:
            conn.close()


class Metrics:
    """Métricas en memoria (por proceso). Con 1 worker de Gunicorn reflejan todo el servicio."""

    def __init__(self):
        self.lock = Lock()
        self.started = time.time()
        self.requests = defaultdict(int)       # "METODO ruta" -> n
        self.status = defaultdict(int)          # código HTTP -> n
        self.latencies = deque(maxlen=5000)     # ms, solo /recommendations
        self.fallbacks = 0
        self.published = 0
        self.publish_errors = 0

    def snapshot(self):
        with self.lock:
            lat = sorted(self.latencies)

            def pct(p):
                return round(lat[min(len(lat) - 1, int(p * len(lat)))], 2) if lat else None
            return {"uptime_seconds": round(time.time() - self.started, 1),
                    "requests_by_endpoint": dict(self.requests),
                    "responses_by_status": {str(k): v for k, v in self.status.items()},
                    "recommendation_latency_ms": {"samples": len(lat), "p50": pct(0.50),
                                                  "p95": pct(0.95), "p99": pct(0.99)},
                    "fallback_responses": self.fallbacks,
                    "interactions_published": self.published,
                    "publish_errors": self.publish_errors}


class RateLimiter:
    """Ventana deslizante de 60 s por cliente (clave de API + IP). Límite a nivel de aplicación."""

    def __init__(self, limit_per_min):
        self.limit, self.hits, self.lock = limit_per_min, defaultdict(deque), Lock()

    def allow(self, client: str) -> bool:
        now = time.time()
        with self.lock:
            q = self.hits[client]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def create_app(config: dict | None = None, publisher=None) -> Flask:
    cfg = {"API_KEY": os.getenv("API_KEY", ""),
           "DB_PATH": os.getenv("DB_PATH", "/data/shopfast.db"),
           "ARTIFACTS_DIR": os.getenv("ARTIFACTS_DIR", "/data"),
           "RATE_LIMIT_PER_MIN": int(os.getenv("RATE_LIMIT_PER_MIN", "120")),
           "RABBITMQ_HOST": os.getenv("RABBITMQ_HOST", "rabbitmq"),
           "RABBITMQ_USER": os.getenv("RABBITMQ_USER", "shopfast"),
           "RABBITMQ_PASS": os.getenv("RABBITMQ_PASS", ""),
           "CORS_ORIGIN": os.getenv("CORS_ORIGIN", "*")}
    cfg.update(config or {})
    if not cfg["API_KEY"]:
        raise RuntimeError("API_KEY no configurada: defínela en .env (no se usa clave por defecto)")

    app = Flask(__name__)
    app.config.update(cfg)
    metrics, limiter = Metrics(), RateLimiter(cfg["RATE_LIMIT_PER_MIN"])
    pub = publisher or RabbitPublisher(cfg["RABBITMQ_HOST"], cfg["RABBITMQ_USER"],
                                       cfg["RABBITMQ_PASS"])
    app.extensions["metrics"] = metrics

    # ---------- utilidades ----------
    def db():
        if "db" not in g:
            con = sqlite3.connect(cfg["DB_PATH"], timeout=10)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only = ON")     # la API solo lee; escribe el worker
            g.db = con
        return g.db

    def err(status, code, message):
        return jsonify({"error": code, "message": message}), status

    @app.teardown_appcontext
    def close_db(_exc):
        con = g.pop("db", None)
        if con is not None:
            con.close()

    # ---------- middleware: auth, rate limit, métricas ----------
    @app.before_request
    def guard():
        g.t0 = time.perf_counter()
        if request.method == "OPTIONS" or request.path in PUBLIC_PATHS:
            return None
        key = request.headers.get("X-API-Key", "")
        if not key or not hmac.compare_digest(key.encode(), cfg["API_KEY"].encode()):
            return err(401, "unauthorized", "API Key ausente o inválida (cabecera X-API-Key)")
        client = hashlib.sha256(key.encode()).hexdigest()[:12] + "|" + (request.remote_addr or "")
        if not limiter.allow(client):
            resp = err(429, "rate_limited", "Demasiadas solicitudes; reintente en unos segundos")
            resp[0].headers["Retry-After"] = "10"
            return resp
        return None

    @app.after_request
    def after(resp):
        ms = (time.perf_counter() - g.get("t0", time.perf_counter())) * 1000
        rule = request.url_rule.rule if request.url_rule else "(no encontrada)"
        with metrics.lock:
            metrics.requests[f"{request.method} {rule}"] += 1
            metrics.status[resp.status_code] += 1
            if rule == "/recommendations/<user_id>" and resp.status_code == 200:
                metrics.latencies.append(ms)
        resp.headers["Access-Control-Allow-Origin"] = cfg["CORS_ORIGIN"]
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    # ---------- endpoints ----------
    @app.get("/health")
    def health():
        try:
            sqlite3.connect(cfg["DB_PATH"], timeout=3).execute("SELECT 1").fetchone()
            return jsonify({"status": "ok"})
        except sqlite3.Error:
            return err(503, "db_unavailable", "Base de datos no disponible")

    @app.get("/recommendations/<user_id>")
    def recommendations(user_id):
        if not ID_RE.match(user_id):
            return err(400, "invalid_user_id", "user_id inválido (letras, números y _; máx. 20)")
        con = db()
        if con.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
            return err(404, "user_not_found", f"Usuario {user_id} no existe")
        rows = con.execute(
            "SELECT r.rank, r.product_id, p.name, p.category, p.price, r.predicted_rating, r.reason "
            "FROM recommendations r JOIN products p USING(product_id) "
            "WHERE r.user_id = ? ORDER BY r.rank", (user_id,)).fetchall()
        fallback = not rows
        if fallback:    # usuario sin historial: productos más populares
            rows = con.execute(
                "SELECT ROW_NUMBER() OVER (ORDER BY pop.n DESC) AS rank, p.product_id, p.name, "
                "p.category, p.price, NULL AS predicted_rating, "
                "'Producto popular (usuario sin historial)' AS reason "
                "FROM popularity pop JOIN products p USING(product_id) "
                "ORDER BY pop.n DESC LIMIT 10").fetchall()
            with metrics.lock:
                metrics.fallbacks += 1
        return jsonify({"user_id": user_id, "fallback": fallback,
                        "model_version": _model_meta().get("model_version", "desconocida"),
                        "recommendations": [dict(r) for r in rows]})

    @app.post("/track-interaction")
    def track_interaction():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return err(400, "invalid_body", "Se espera un JSON con user_id, product_id e "
                                            "interaction_type")
        user_id, product_id = body.get("user_id"), body.get("product_id")
        itype = body.get("interaction_type")
        if not (isinstance(user_id, str) and ID_RE.match(user_id)):
            return err(400, "invalid_user_id", "user_id inválido")
        if not (isinstance(product_id, str) and ID_RE.match(product_id)):
            return err(400, "invalid_product_id", "product_id inválido")
        if itype not in INTERACTION_TYPES:
            return err(400, "invalid_interaction_type",
                       f"interaction_type debe ser uno de {sorted(INTERACTION_TYPES)}")
        con = db()
        if con.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
            return err(404, "user_not_found", f"Usuario {user_id} no existe")
        if con.execute("SELECT 1 FROM products WHERE product_id = ?",
                       (product_id,)).fetchone() is None:
            return err(404, "product_not_found", f"Producto {product_id} no existe")
        msg = {"user_id": user_id, "product_id": product_id, "interaction_type": itype,
               "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())}
        try:
            pub.publish(msg)
        except Exception as exc:                      # broker caído: no se pierde en silencio
            log.error("No se pudo publicar en RabbitMQ: %s", exc)
            with metrics.lock:
                metrics.publish_errors += 1
            return err(503, "queue_unavailable", "Cola de mensajes no disponible")
        with metrics.lock:
            metrics.published += 1
        return jsonify({"status": "accepted", "message": msg}), 202

    @app.get("/products/<product_id>/related")
    def related(product_id):
        if not ID_RE.match(product_id):
            return err(400, "invalid_product_id", "product_id inválido")
        con = db()
        prod = con.execute("SELECT * FROM products WHERE product_id = ?",
                           (product_id,)).fetchone()
        if prod is None:
            return err(404, "product_not_found", f"Producto {product_id} no existe")
        rows = con.execute(
            "SELECT p.product_id, p.name, p.category, p.price, COUNT(*) AS co_interactions "
            "FROM interactions a JOIN interactions b ON a.user_id = b.user_id "
            "AND b.product_id <> a.product_id JOIN products p ON p.product_id = b.product_id "
            "WHERE a.product_id = ? AND a.rating >= 4 AND b.rating >= 4 "
            "GROUP BY p.product_id ORDER BY co_interactions DESC LIMIT 5", (product_id,)).fetchall()
        method = "co_interaction"
        if not rows:                                   # sin co-interacciones: misma categoría
            rows = con.execute(
                "SELECT p.product_id, p.name, p.category, p.price, pop.n AS co_interactions "
                "FROM products p LEFT JOIN popularity pop USING(product_id) "
                "WHERE p.category = ? AND p.product_id <> ? ORDER BY pop.n DESC LIMIT 5",
                (prod["category"], product_id)).fetchall()
            method = "same_category"
        return jsonify({"product_id": product_id, "method": method,
                        "related": [dict(r) for r in rows]})

    def _model_meta():
        try:
            return json.loads((Path(cfg["ARTIFACTS_DIR"]) / "metrics.json").read_text())
        except (OSError, ValueError):
            return {}

    @app.get("/model/info")
    def model_info():
        meta = _model_meta()
        pkl = Path(cfg["ARTIFACTS_DIR"]) / "svd_model.pkl"
        info = {"algorithm": "SVD (Surprise, factorización matricial)",
                "model_file": pkl.name, "model_file_present": pkl.exists(),
                "model_sha256": (hashlib.sha256(pkl.read_bytes()).hexdigest()
                                 if pkl.exists() else None),
                "serving_mode": "Top 10 precalculado por usuario (tabla recommendations)",
                "version": meta.get("model_version"), "training_metrics": meta}
        return jsonify(info)

    @app.get("/metrics")
    def metrics_endpoint():
        snap = metrics.snapshot()
        con = db()
        snap["db"] = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("users", "products", "interactions", "recommendations")}
        snap["top_recommended_products"] = [dict(r) for r in con.execute(
            "SELECT r.product_id, p.name, p.category, COUNT(*) AS times_recommended "
            "FROM recommendations r JOIN products p USING(product_id) "
            "GROUP BY r.product_id ORDER BY times_recommended DESC LIMIT 10")]
        snap["interactions_by_type"] = {r[0]: r[1] for r in con.execute(
            "SELECT interaction_type, COUNT(*) FROM interactions GROUP BY interaction_type")}
        return jsonify(snap)

    @app.get("/openapi.json")
    def openapi():
        return jsonify(OPENAPI_SPEC)

    @app.get("/docs")
    def docs():
        return Response(SWAGGER_HTML, mimetype="text/html")

    @app.errorhandler(404)
    def not_found(_e):
        return err(404, "not_found", "Ruta no encontrada")

    @app.errorhandler(405)
    def not_allowed(_e):
        return err(405, "method_not_allowed", "Método no permitido")

    @app.errorhandler(Exception)
    def unhandled(exc):
        if isinstance(exc, HTTPException):
            return err(exc.code or 500, exc.name.lower().replace(" ", "_"), exc.description)
        log.exception("Error no controlado: %s", exc)
        return err(500, "internal_error", "Error interno")

    return app


if __name__ == "__main__":      # solo desarrollo; en contenedor se usa Gunicorn
    create_app().run(host="0.0.0.0", port=8000)
