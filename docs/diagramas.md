# Figuras 8 y 9 (Mermaid)

Pega cada bloque en https://mermaid.live , exporta como PNG/SVG e insértalo en el informe.

## Figura 8. Arquitectura del prototipo (Tabla 14)

```mermaid
flowchart LR
    U([Usuario / Evaluador]) -->|HTTP| FE[Frontend + Dashboard<br/>React]
    FE -->|REST + API Key| API[API REST<br/>Flask + Gunicorn]
    subgraph EC2["AWS EC2 (Docker Compose)  -  red interna Docker"]
        API -->|lee Top 10 / fallback| DB[(SQLite<br/>volumen compartido)]
        API -->|publica evento| MQ{{RabbitMQ}}
        MQ -->|consume| W[Worker Python]
        W -->|escribe interaccion| DB
        API -.carga al iniciar.-> M[[svd_model.pkl]]
    end
    S3[(Amazon S3<br/>dataset, modelo, metricas)] -.descarga al desplegar.-> EC2
    T[Entrenamiento local<br/>Surprise SVD] -->|sube artefactos| S3
    classDef pub fill:#e8f1ff,stroke:#2b6cb0;
    class FE,API pub;
```

Solo el frontend y la API son accesibles desde Internet; RabbitMQ y SQLite quedan en la red interna.

## Figura 9. Diagrama de secuencia (Tabla 15)

```mermaid
sequenceDiagram
    actor U as Usuario
    participant F as Frontend (React)
    participant A as API (Flask)
    participant D as SQLite
    participant Q as RabbitMQ
    participant W as Worker
    U->>F: 1. Selecciona usuario de prueba
    F->>A: 2. GET /recommendations/{user_id} (API Key)
    A->>D: 3. Lee Top 10 precalculado (o fallback por popularidad)
    D-->>A: productos + puntaje + motivo
    A-->>F: 4. JSON con 10 productos
    U->>F: clic / carrito / compra
    F->>A: 5. POST /track-interaction
    A->>Q: 6. Valida y publica mensaje
    A-->>F: 202 Accepted (sin esperar procesamiento)
    Q->>W: 7. Entrega mensaje
    W->>D: 8. Persiste interaccion
    F->>A: 9. GET /metrics (dashboard)
    A-->>F: metricas operativas
```
