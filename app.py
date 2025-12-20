from flask import Flask, request, jsonify
from firestore import (
    db,
    crear_nota,
    obtener_notas_usuario,
    obtener_nota,
    actualizar_nota,
    eliminar_nota,
    obtener_o_crear_categoria_por_nombre,
    crear_relacion_nota_categoria,
    eliminar_categoria,
    actualizar_categoria,
    realizar_compra_plantilla,
    plantilla_esta_desbloqueada,
    obtener_plantillas_desbloqueadas_usuario,
    usuario_tiene_feature,
    realizar_compra_feature
)

app = Flask(__name__)


# =====================================================
# -----------   CREAR NOTA   --------------------------
# =====================================================
@app.route("/api/notas/nueva", methods=["POST"])
def api_crear_nota():
    data = request.json

    required = ["id_usuario", "id_plantilla", "titulo", "contenido"]
    if not all(field in data for field in required):
        return jsonify({"error": "Faltan campos requeridos"}), 400

    # ------------------------------
    # MANEJO DE CATEGORÍA
    # ------------------------------
    id_categoriaNota = data.get("id_categoriaNota")
    categoria_nombre = data.get("categoria_nombre")

    if categoria_nombre and not id_categoriaNota:
        id_categoriaNota = obtener_o_crear_categoria_por_nombre(categoria_nombre)

    if not id_categoriaNota:
        return jsonify({
            "error": "Debes enviar 'id_categoriaNota' o 'categoria_nombre'"
        }), 400

    # 🔥 ACTUALIZADO: Pasamos los nuevos campos de estilo a la función
    id_nota = crear_nota(
        id_usuario=data["id_usuario"],
        id_plantilla=data["id_plantilla"],
        titulo=data["titulo"],
        contenido=data["contenido"],
        etiquetas=data.get("etiquetas", []),
        dibujo=data.get("dibujo", None),
        estado=data.get("estado", "activa"),
        # Nuevos campos para personalización
        animacion_fondo=data.get("animacion_fondo"),
        color_fondo=data.get("color_fondo")
    )

    crear_relacion_nota_categoria(id_nota, id_categoriaNota)

    return jsonify({
        "ok": True,
        "id_nota": id_nota,
        "id_categoriaNota": id_categoriaNota
    })


# =====================================================
# -----------   OBTENER NOTAS   ------------------------
# =====================================================
@app.route("/api/notas/<id_usuario>", methods=["GET"])
def api_get_notas(id_usuario):
    notas = obtener_notas_usuario(id_usuario)
    return jsonify(notas)


# =====================================================
# -----------   OBTENER UNA NOTA   ---------------------
# =====================================================
@app.route("/api/nota/<id_nota>", methods=["GET"])
def api_get_nota(id_nota):
    nota = obtener_nota(id_nota)
    if nota:
        return jsonify({**nota, "id": id_nota})
    return jsonify({"error": "Nota no encontrada"}), 404


# =====================================================
# -----------   ACTUALIZAR NOTA  -----------------------
# =====================================================
@app.route("/api/nota/<id_nota>", methods=["PUT"])
def api_update_nota(id_nota):
    cambios = request.json or {}

    categoria_nombre = cambios.get("categoria_nombre")
    id_categoriaNota = cambios.get("id_categoriaNota")

    if categoria_nombre or id_categoriaNota:
        if categoria_nombre:
            id_categoriaNota = obtener_o_crear_categoria_por_nombre(categoria_nombre)

        crear_relacion_nota_categoria(id_nota, id_categoriaNota)

    actualizar_nota(id_nota, cambios)

    return jsonify({"ok": True})


# =====================================================
# -----------   ELIMINAR NOTA   ------------------------
# =====================================================
@app.route("/api/nota/<id_nota>", methods=["DELETE"])
def api_delete_nota(id_nota):
    eliminar_nota(id_nota)
    return jsonify({"ok": True})


# =====================================================
# -----------   FAVORITOS   ----------------------------
# =====================================================
@app.route("/api/notas/favorita/<id_nota>", methods=["PUT"])
def api_toggle_favorita(id_nota):
    data = request.json or {}
    nueva_fav = data.get("favorita")

    if nueva_fav is None:
        return jsonify({"error": "Falta 'favorita': true/false"}), 400

    actualizar_nota(id_nota, {"favorita": nueva_fav})

    if nueva_fav:
        id_categoria = obtener_o_crear_categoria_por_nombre("Favoritos")
    else:
        id_categoria = obtener_o_crear_categoria_por_nombre("General")

    crear_relacion_nota_categoria(id_nota, id_categoria)

    return jsonify({
        "ok": True,
        "favorita": nueva_fav,
        "id_categoriaNota": id_categoria
    })


# =====================================================
# -----------   OBTENER TODAS LAS CATEGORÍAS   --------
# =====================================================
@app.route("/api/categorias", methods=["GET"])
def api_get_categorias():
    try:
        docs = db.collection("categoriaNota").stream()
        categorias = []
        for d in docs:
            data = d.to_dict()
            if data:
                categorias.append({
                    "id": d.id,
                    "nombre": data.get("nombre", "")
                })
        return jsonify(categorias)

    except Exception as e:
        print("ERROR al obtener categorías:", e)
        return jsonify([]), 500

# =====================================================
# -----------   CREAR CATEGORÍA  ----------------------
# =====================================================
@app.route("/api/categorias", methods=["POST"])
def api_crear_categoria():
    data = request.json or {}
    nombre = data.get("nombre")

    if not nombre:
        return jsonify({"error": "Falta 'nombre'"}), 400

    try:
        # Verificar si ya existe
        categorias = db.collection("categoriaNota")\
                        .where("nombre", "==", nombre)\
                        .stream()

        for c in categorias:
            return jsonify({
                "ok": False,
                "error": "La categoría ya existe",
                "id": c.id
            }), 400

        # Crear nueva categoría
        nueva_ref = db.collection("categoriaNota").add({"nombre": nombre})
        id_categoria = nueva_ref[1].id

        return jsonify({
            "ok": True,
            "id": id_categoria,
            "nombre": nombre
        }), 201

    except Exception as e:
        print("ERROR al crear categoría:", e)
        return jsonify({"error": "Error interno"}), 500

# =====================================================
# -----------   NOTAS POR CATEGORÍA   -----------------
# =====================================================
@app.route("/api/notas/categoria/<id_usuario>/<id_categoria>", methods=["GET"])
def api_get_notas_por_categoria(id_usuario, id_categoria):

    rels = db.collection("notas_categoriaNota")\
             .where("id_categoriaNota", "==", id_categoria)\
             .stream()

    ids_notas = [r.to_dict().get("id_nota") for r in rels]

    if not ids_notas:
        return jsonify([])

    notas = []
    for id_nota in ids_notas:
        nota = obtener_nota(id_nota)
        if nota and nota["id_usuario"] == id_usuario:
            nota["id"] = id_nota
            notas.append(nota)

    return jsonify(notas)


# =====================================================
# -----------   ACTUALIZAR CATEGORÍA -------------------
# =====================================================
@app.route("/api/categorias/<id_categoria>", methods=["PUT"])
def api_update_categoria(id_categoria):
    data = request.json or {}
    nuevo_nombre = data.get("nombre")

    if not nuevo_nombre:
        return jsonify({"error": "Falta 'nombre'"}), 400

    try:
        doc_ref = db.collection("categoriaNota").document(id_categoria)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({
                "error": "La categoría no existe",
                "id_categoria": id_categoria
            }), 404

        doc_ref.update({"nombre": nuevo_nombre})

        return jsonify({"ok": True})

    except Exception as e:
        print("ERROR al actualizar categoría:", e)
        return jsonify({"error": "Error interno del servidor"}), 500


# =====================================================
# -----------   ELIMINAR CATEGORÍA ---------------------
# =====================================================
@app.route("/api/categorias/<id_categoria>", methods=["DELETE"])
def api_delete_categoria(id_categoria):
    try:
        # Verificar si la categoría existe
        doc_ref = db.collection("categoriaNota").document(id_categoria)
        doc = doc_ref.get()

        if not doc.exists:
            return jsonify({
                "error": "La categoría no existe",
                "id_categoria": id_categoria
            }), 404

        # 🔴 Verificar si alguna nota usa esta categoría
        notas_relacionadas = db.collection("notas") \
            .where("id_categoriaNota", "==", id_categoria) \
            .stream()

        tiene_notas = False
        for _ in notas_relacionadas:
            tiene_notas = True
            break  # Con una que exista basta

        if tiene_notas:
            return jsonify({
                "ok": False,
                "error": "La categoría no puede eliminarse porque tiene notas relacionadas"
            }), 400

        # 🟢 Si no tiene notas → eliminar categoría
        doc_ref.delete()

        return jsonify({
            "ok": True,
            "msg": "Categoría eliminada correctamente"
        })

    except Exception as e:
        print("ERROR al eliminar categoría:", e)
        return jsonify({"error": "Error interno del servidor"}), 500


# app.py

# app.py - Añadir/Modificar estos endpoints

@app.route("/api/usuarios/comprar_plantilla", methods=["POST"])
def api_comprar_plantilla():
    data = request.json
    id_usuario = data.get("id_usuario")
    id_plantilla = data.get("id_plantilla")
    costo = 200

    # 1. VALIDACIÓN: Evitar cobrar de nuevo si ya la tiene
    if plantilla_esta_desbloqueada(id_usuario, id_plantilla):
        return jsonify({"ok": True, "mensaje": "Ya tienes esta plantilla"}), 200

    # 2. PROCESAR COMPRA
    exito, mensaje = realizar_compra_plantilla(id_usuario, id_plantilla, costo)
    
    if exito:
        return jsonify({"ok": True, "mensaje": mensaje})
    else:
        return jsonify({"ok": False, "error": mensaje}), 400

@app.route("/api/usuarios/plantillas_desbloqueadas/<id_usuario>", methods=["GET"])
def api_plantillas_desbloqueadas(id_usuario):
    # Usamos la función que ya definiste en firestore.py
    ids = obtener_plantillas_desbloqueadas_usuario(id_usuario)
    return jsonify(ids)

# app.py - Añadir estos endpoints

@app.route("/api/usuarios/check_feature/<id_usuario>/<feature>", methods=["GET"])
def api_check_feature(id_usuario, feature):
    desbloqueado = usuario_tiene_feature(id_usuario, feature)
    return jsonify({"desbloqueado": desbloqueado})

@app.route("/api/usuarios/comprar_feature", methods=["POST"])
def api_comprar_feature():
    data = request.json
    id_usuario = data.get("id_usuario")
    feature = data.get("feature") 
    
    # MODIFICACIÓN: Leer el costo del JSON, si no viene, usar 150 por defecto
    costo = data.get("costo", 150) 
    
    if usuario_tiene_feature(id_usuario, feature):
        return jsonify({"ok": True, "mensaje": "Ya lo tienes"}), 200

    # Ahora pasamos el costo dinámico a la función de firestore
    exito, mensaje = realizar_compra_feature(id_usuario, feature, costo)
    
    if exito:
        return jsonify({"ok": True, "mensaje": mensaje})
    return jsonify({"ok": False, "error": mensaje}), 400
@app.route("/api/usuarios/fonts_unlocked/<id_usuario>", methods=["GET"])
def api_fonts_unlocked(id_usuario):
    try:
        # Buscamos todas las features del usuario
        docs = db.collection("usuarios_features")\
                 .where("id_usuario", "==", id_usuario)\
                 .stream()
        
        unlocked_fonts = []
        for d in docs:
            feature_name = d.to_dict().get("feature", "")
            # Si la feature empieza con 'font_', extraemos el nombre
            if feature_name.startswith("font_"):
                unlocked_fonts.append(feature_name.replace("font_", ""))
        
        return jsonify(unlocked_fonts) # Retorna ej: ["Lora", "Pacifico"]
    except Exception as e:
        print("Error:", e)
        return jsonify([]), 500


# =====================================================
# -----------  FONDOS DESBLOQUEADOS  ------------------
# =====================================================
@app.route("/api/usuarios/unlocked_backgrounds/<id_usuario>", methods=["GET"])
def api_get_unlocked_backgrounds(id_usuario):
    """
    Retorna una lista de los paths de animaciones (features) 
    que el usuario ha comprado.
    """
    try:
        # Buscamos en la colección usuarios_features
        docs = db.collection("usuarios_features")\
                 .where("id_usuario", "==", id_usuario)\
                 .stream()
        
        unlocked_backgrounds = []
        for d in docs:
            feature_name = d.to_dict().get("feature", "")
            # Filtramos solo aquellos que sean assets de animaciones
            if feature_name.startswith("assets/animations/"):
                unlocked_backgrounds.append(feature_name)
        
        return jsonify(unlocked_backgrounds)
    except Exception as e:
        print("Error al obtener fondos desbloqueados:", e)
        return jsonify([]), 500
    
    
# =====================================================
# -----------   RUN SERVER   ---------------------------
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)