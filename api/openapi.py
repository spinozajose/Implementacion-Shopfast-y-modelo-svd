"""Especificación OpenAPI 3 y página Swagger UI (sección 16, Tabla 20)."""

_KEY = [{"ApiKeyAuth": []}]
_ERR = {"description": "Error", "content": {"application/json": {"schema": {
    "$ref": "#/components/schemas/Error"}}}}

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "ShopFast Recomendaciones API", "version": "1.0.0",
             "description": "Prototipo EP3. Modelo SVD con Top 10 precalculado por usuario."},
    "components": {
        "securitySchemes": {"ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}},
        "schemas": {
            "Error": {"type": "object", "properties": {"error": {"type": "string"},
                                                        "message": {"type": "string"}}},
            "Interaction": {"type": "object",
                            "required": ["user_id", "product_id", "interaction_type"],
                            "properties": {
                                "user_id": {"type": "string", "example": "U00001"},
                                "product_id": {"type": "string", "example": "P0042"},
                                "interaction_type": {"type": "string",
                                                     "enum": ["view", "click", "cart", "purchase"]}}}}},
    "paths": {
        "/health": {"get": {"summary": "Estado del servicio", "responses": {
            "200": {"description": "Servicio disponible"}, "503": _ERR}}},
        "/recommendations/{user_id}": {"get": {
            "summary": "Top 10 con puntaje y explicación", "security": _KEY,
            "parameters": [{"name": "user_id", "in": "path", "required": True,
                            "schema": {"type": "string"}, "example": "U00001"}],
            "responses": {"200": {"description": "Recomendaciones (fallback=true si no hay historial)"},
                          "400": _ERR, "401": _ERR, "404": _ERR, "429": _ERR}}},
        "/track-interaction": {"post": {
            "summary": "Valida y publica la interacción en RabbitMQ", "security": _KEY,
            "requestBody": {"required": True, "content": {"application/json": {"schema": {
                "$ref": "#/components/schemas/Interaction"}}}},
            "responses": {"202": {"description": "Aceptada (se procesa de forma asíncrona)"},
                          "400": _ERR, "401": _ERR, "404": _ERR, "429": _ERR, "503": _ERR}}},
        "/products/{product_id}/related": {"get": {
            "summary": "Productos relacionados", "security": _KEY,
            "parameters": [{"name": "product_id", "in": "path", "required": True,
                            "schema": {"type": "string"}, "example": "P0042"}],
            "responses": {"200": {"description": "Lista de productos"}, "400": _ERR,
                          "401": _ERR, "404": _ERR}}},
        "/metrics": {"get": {"summary": "Métricas operativas básicas", "security": _KEY,
                             "responses": {"200": {"description": "Métricas"}, "401": _ERR}}},
        "/model/info": {"get": {"summary": "Modelo y versión cargados", "security": _KEY,
                                "responses": {"200": {"description": "Información del modelo"},
                                              "401": _ERR}}},
    },
}

# Swagger UI desde CDN (requiere Internet en el navegador del evaluador)
SWAGGER_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>ShopFast API - Swagger</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css">
</head><body><div id="ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url: "/openapi.json", dom_id: "#ui"});</script></body></html>"""
