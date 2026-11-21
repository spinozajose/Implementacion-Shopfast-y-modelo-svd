"""Worker: consume interacciones de RabbitMQ y las persiste en SQLite (EP3, pasos 7 y 8)."""
import json
import logging
import os
import sqlite3
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker %(message)s")
log = logging.getLogger("shopfast.worker")

RATING = {"view": 1, "click": 2, "cart": 4, "purchase": 5}
QUEUE = os.getenv("QUEUE_NAME", "interactions")


def connect_db(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=30)
    con.execute("PRAGMA journal_mode = WAL")       # lectura de la API concurrente con escrituras
    con.execute("PRAGMA busy_timeout = 30000")
    return con


def process_message(con: sqlite3.Connection, body: bytes | str) -> bool:
    """Valida y guarda una interacción. Devuelve True si se guardó, False si el mensaje es inválido
    (los mensajes inválidos no se reintentan: se descartan y se registran)."""
    try:
        m = json.loads(body)
        user_id, product_id, itype = m["user_id"], m["product_id"], m["interaction_type"]
        rating = RATING[itype]
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("Mensaje inválido descartado (%s): %r", exc, body)
        return False
    prod = con.execute("SELECT category, price FROM products WHERE product_id = ?",
                       (product_id,)).fetchone()
    if prod is None or con.execute("SELECT 1 FROM users WHERE user_id = ?",
                                   (user_id,)).fetchone() is None:
        log.warning("Usuario o producto inexistente, descartado: %r", body)
        return False
    con.execute("INSERT INTO interactions (user_id, product_id, interaction_type, rating, "
                "timestamp, category, price) VALUES (?,?,?,?,?,?,?)",
                (user_id, product_id, itype, rating,
                 m.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                 prod[0], prod[1]))
    con.commit()
    log.info("Interacción guardada: %s %s %s", user_id, itype, product_id)
    return True


def main() -> None:
    import pika  # import diferido

    con = connect_db(os.getenv("DB_PATH", "/data/shopfast.db"))
    params = pika.ConnectionParameters(
        host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
        credentials=pika.PlainCredentials(os.getenv("RABBITMQ_USER", "shopfast"),
                                          os.getenv("RABBITMQ_PASS", "")),
        heartbeat=60)
    while True:                                     # reintenta si RabbitMQ aún no está listo
        try:
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=QUEUE, durable=True)
            ch.basic_qos(prefetch_count=10)

            def on_message(channel, method, _props, body):
                try:
                    process_message(con, body)
                    channel.basic_ack(method.delivery_tag)
                except sqlite3.Error as exc:        # error transitorio: reencolar
                    log.error("Error de BD, se reencola: %s", exc)
                    channel.basic_nack(method.delivery_tag, requeue=True)
                    time.sleep(1)

            ch.basic_consume(queue=QUEUE, on_message_callback=on_message)
            log.info("Esperando mensajes en la cola '%s'...", QUEUE)
            ch.start_consuming()
        except pika.exceptions.AMQPConnectionError:
            log.warning("RabbitMQ no disponible, reintentando en 3 s")
            time.sleep(3)


if __name__ == "__main__":
    main()
