"""Prueba de carga sobre GET /recommendations/{user_id} (EP3, sección 18.1).

Cada usuario virtual envía ~1 solicitud/s (constant_throughput), de modo que
N usuarios virtuales ≈ N solicitudes por segundo (RPS objetivo).
"""
import os
import random

from locust import HttpUser, constant_throughput, task

API_KEY = os.environ["API_KEY"]
USERS = [f"U{i:05d}" for i in range(1, 5001)]   # usuarios con historial (modo precalculado)


class Shopper(HttpUser):
    wait_time = constant_throughput(1)

    @task
    def recomendaciones(self):
        self.client.get(f"/recommendations/{random.choice(USERS)}",
                        headers={"X-API-Key": API_KEY}, name="/recommendations/{user_id}")
