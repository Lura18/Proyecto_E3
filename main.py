from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ─── Conexión MongoDB ──────────────────────────────────
#MONGO_URI = os.getenv("MONGO_URI", "mongodb://ISIS2304E28202610:KUYeUnb7wEgC@157.253.236.88:8087")
client = MongoClient(os.environ["MONGO_URI"])
db          = client["ISIS2304E28202610"]
reviews_col = db["reviews"]
votes_col   = db["votes_reviews"]

# ─── Helper ───────────────────────────────────────────
def serial(doc):
    doc["_id"] = str(doc["_id"])
    if "fecha_creacion" in doc and isinstance(doc["fecha_creacion"], datetime):
        doc["fecha_creacion"] = doc["fecha_creacion"].isoformat()
    if "respuesta_admin" in doc and doc["respuesta_admin"]:
        if "fecha" in doc["respuesta_admin"] and isinstance(doc["respuesta_admin"]["fecha"], datetime):
            doc["respuesta_admin"]["fecha"] = doc["respuesta_admin"]["fecha"].isoformat()
    return doc

# ══════════════════════════════════════════════════════
# RF1 – Crear reseña
# ══════════════════════════════════════════════════════
@app.post("/resenas")
def crear_resena(datos: dict):
    reserva_id   = datos.get("reserva_id")
    cliente_id   = datos.get("cliente_id")
    hotel_id     = datos.get("hotel_id")
    calificacion = datos.get("calificacion")
    comentario   = datos.get("comentario")

    if not all([reserva_id, cliente_id, hotel_id, calificacion, comentario]):
        raise HTTPException(status_code=400, detail="Faltan campos obligatorios.")

    if reviews_col.find_one({"reserva_id": int(reserva_id)}):
        raise HTTPException(status_code=400, detail="Ya existe una reseña para esta reserva.")

    doc = {
        "hotel_id":        int(hotel_id),
        "cliente_id":      int(cliente_id),
        "reserva_id":      int(reserva_id),
        "fecha_creacion":  datetime.now(),
        "calificacion":    int(calificacion),
        "comentario":      comentario,
        "estado":          "publicada",
        "destacada":       False,
        "votos_utilidad":  0,
        "respuesta_admin": None
    }
    reviews_col.insert_one(doc)
    return {"mensaje": "Reseña creada exitosamente."}

# ══════════════════════════════════════════════════════
# RF2 – Editar reseña
# ══════════════════════════════════════════════════════
@app.put("/resenas/{resena_id}")
def editar_resena(resena_id: str, datos: dict):
    calificacion = datos.get("calificacion")
    comentario   = datos.get("comentario")

    if not calificacion and not comentario:
        raise HTTPException(status_code=400, detail="Debe enviar calificación o comentario.")

    update = {}
    if calificacion: update["calificacion"] = int(calificacion)
    if comentario:   update["comentario"]   = comentario

    result = reviews_col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada.")
    return {"mensaje": "Reseña actualizada."}

# ══════════════════════════════════════════════════════
# RF3 – Eliminar reseña (cliente)
# ══════════════════════════════════════════════════════
@app.delete("/resenas/{resena_id}")
def eliminar_resena(resena_id: str):
    result = reviews_col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$set": {"estado": "eliminada"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada.")
    return {"mensaje": "Reseña eliminada."}

# ══════════════════════════════════════════════════════
# RF4 – Consultar reseñas de un hotel
# ══════════════════════════════════════════════════════
@app.get("/hoteles/{hotel_id}/resenas")
def get_resenas_hotel(hotel_id: int, orden: str = "fecha", pagina: int = 1, por_pagina: int = 10):
    skip = (pagina - 1) * por_pagina
    sort_field = "fecha_creacion" if orden == "fecha" else "votos_utilidad"

    resenas = list(reviews_col.find(
        {"hotel_id": hotel_id, "estado": "publicada"},
        {"_id": 1, "fecha_creacion": 1, "calificacion": 1,
         "comentario": 1, "votos_utilidad": 1, "destacada": 1,
         "respuesta_admin": 1}
    ).sort([("destacada", -1), (sort_field, -1)]).skip(skip).limit(por_pagina))

    return [serial(r) for r in resenas]

# ══════════════════════════════════════════════════════
# RF4 – Consultar reseña individual
# ══════════════════════════════════════════════════════
@app.get("/resenas/{resena_id}")
def get_resena(resena_id: str):
    resena = reviews_col.find_one({"_id": ObjectId(resena_id)})
    if not resena:
        raise HTTPException(status_code=404, detail="Reseña no encontrada.")
    return serial(resena)

# ══════════════════════════════════════════════════════
# RF5 – Marcar reseña como útil
# ══════════════════════════════════════════════════════
@app.post("/resenas/{resena_id}/votos")
def votar_resena(resena_id: str, datos: dict):
    usuario_id = datos.get("usuario_id")
    if not usuario_id:
        raise HTTPException(status_code=400, detail="Falta usuario_id.")

    if votes_col.find_one({"review_id": ObjectId(resena_id), "usuario_id": int(usuario_id)}):
        raise HTTPException(status_code=400, detail="Ya votaste por esta reseña.")

    votes_col.insert_one({
        "review_id":  ObjectId(resena_id),
        "usuario_id": int(usuario_id),
        "fecha_voto": datetime.now()
    })
    reviews_col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$inc": {"votos_utilidad": 1}}
    )
    return {"mensaje": "Voto registrado."}

# ══════════════════════════════════════════════════════
# RF6 – Historial de reseñas propias
# ══════════════════════════════════════════════════════
@app.get("/clientes/{cliente_id}/resenas")
def historial_resenas(cliente_id: str, orden: str = "fecha"):
    sort_field = "fecha_creacion" if orden == "fecha" else "hotel_id"
    resenas = list(reviews_col.find(
        {"cliente_id": int(cliente_id)},
        {"_id": 1, "hotel_id": 1, "fecha_creacion": 1, "calificacion": 1,
         "comentario": 1, "estado": 1, "votos_utilidad": 1, "respuesta_admin": 1}
    ).sort(sort_field, -1))
    return [serial(r) for r in resenas]

# ══════════════════════════════════════════════════════
# RF7 – Responder reseña (administrador)
# ══════════════════════════════════════════════════════
@app.put("/resenas/{resena_id}/respuesta")
def responder_resena(resena_id: str, datos: dict):
    texto    = datos.get("texto")
    admin_id = datos.get("admin_id", 1)
    if not texto:
        raise HTTPException(status_code=400, detail="Falta el texto de la respuesta.")

    result = reviews_col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$set": {
            "respuesta_admin": {
                "admin_id": int(admin_id),
                "texto":    texto,
                "fecha":    datetime.now()
            }
        }}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada.")
    return {"mensaje": "Respuesta guardada."}

# ══════════════════════════════════════════════════════
# RF8 – Eliminar reseña (administrador)
# ══════════════════════════════════════════════════════
@app.delete("/admin/resenas/{resena_id}")
def eliminar_resena_admin(resena_id: str):
    result = reviews_col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$set": {"estado": "eliminada"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reseña no encontrada.")
    return {"mensaje": "Reseña eliminada por administrador."}

# ══════════════════════════════════════════════════════
# RF9 – Destacar reseña
# ══════════════════════════════════════════════════════
@app.put("/resenas/{resena_id}/destacar")
def destacar_resena(resena_id: str):
    resena = reviews_col.find_one({"_id": ObjectId(resena_id)})
    if not resena:
        raise HTTPException(status_code=404, detail="Reseña no encontrada.")

    reviews_col.update_many(
        {"hotel_id": resena["hotel_id"], "destacada": True},
        {"$set": {"destacada": False}}
    )
    reviews_col.update_one(
        {"_id": ObjectId(resena_id)},
        {"$set": {"destacada": True}}
    )
    return {"mensaje": "Reseña destacada exitosamente."}

# ══════════════════════════════════════════════════════
# RFC1 – Top 10 hoteles por calificación
# ══════════════════════════════════════════════════════
@app.get("/rfc1")
def rfc1(fecha_inicio: str, fecha_fin: str):
    pipeline = [
        {
            "$match": {
                "estado": "publicada",
                "fecha_creacion": {
                    "$gte": datetime.fromisoformat(fecha_inicio),
                    "$lte": datetime.fromisoformat(fecha_fin)
                }
            }
        },
        {
            "$group": {
                "_id": "$hotel_id",
                "promedio": {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1}
            }
        },
        {"$sort": {"promedio": -1}},
        {"$limit": 10}
    ]
    return list(reviews_col.aggregate(pipeline))

# ══════════════════════════════════════════════════════
# RFC2 – Evolución de reputación mes a mes
# ══════════════════════════════════════════════════════
@app.get("/rfc2")
def rfc2(hotel_id: int, anio: int):
    pipeline = [
        {
            "$match": {
                "hotel_id": hotel_id,
                "estado":   "publicada",
                "$expr": {
                    "$eq": [{"$year": "$fecha_creacion"}, anio]
                }
            }
        },
        {
            "$group": {
                "_id": {"mes": {"$month": "$fecha_creacion"}},
                "promedio":      {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1}
            }
        },
        {
            "$project": {
                "_id": 0,
                "mes":           "$_id.mes",
                "promedio":      1,
                "total_resenas": 1
            }
        },
        {"$sort": {"mes": 1}}
    ]
    return list(reviews_col.aggregate(pipeline))

# ══════════════════════════════════════════════════════
# RFC3 – Perfil comparativo por ciudad
# ══════════════════════════════════════════════════════
@app.get("/rfc3")
def rfc3(ciudad: str):
    pipeline = [
        {"$match": {"estado": "publicada"}},
        {
            "$group": {
                "_id": "$hotel_id",
                "promedio":      {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1},
                "con_respuesta": {
                    "$sum": {
                        "$cond": [{"$ne": ["$respuesta_admin", None]}, 1, 0]
                    }
                },
                "destacadas": {
                    "$sum": {"$cond": ["$destacada", 1, 0]}
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "hotel_id":        "$_id",
                "promedio":        1,
                "total_resenas":   1,
                "pct_con_respuesta": {
                    "$round": [
                        {"$multiply": [
                            {"$divide": ["$con_respuesta", "$total_resenas"]},
                            100
                        ]}, 1
                    ]
                },
                "pct_destacadas": {
                    "$round": [
                        {"$multiply": [
                            {"$divide": ["$destacadas", "$total_resenas"]},
                            100
                        ]}, 1
                    ]
                }
            }
        },
        {"$sort": {"promedio": -1}}
    ]

    hoteles = list(reviews_col.aggregate(pipeline))
    if not hoteles:
        return {"hoteles": [], "promedio_ciudad": 0}

    promedio_ciudad = sum(h["promedio"] for h in hoteles) / len(hoteles)
    return {"hoteles": hoteles, "promedio_ciudad": promedio_ciudad}