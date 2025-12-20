import firebase_admin
from firebase_admin import credentials, firestore

# Inicializar Firebase solo una vez
# Asegúrate de que el archivo serviceAccountKey.json esté en la misma carpeta
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()


# ---------- FUNCIÓN PARA CONVERTIR TIMESTAMP ---------- #

def serializar_timestamp(ts):
    try:
        return ts.isoformat()
    except:
        return None


# ---------- CATEGORÍAS: MÉTODOS ---------- #

def obtener_categoria_por_nombre(nombre):
    docs = db.collection("categoriaNota").where("nombre", "==", nombre).stream()
    for d in docs:
        return d.id
    return None


def crear_categoria(nombre):
    nueva_ref = db.collection("categoriaNota").document()
    nueva_ref.set({
        "nombre": nombre
    })
    return nueva_ref.id


def obtener_o_crear_categoria_por_nombre(nombre):
    existente = obtener_categoria_por_nombre(nombre)
    if existente:
        return existente
    return crear_categoria(nombre)


# ---------- MÉTODO PARA RELACIONAR NOTA - CATEGORÍA ---------- #

def crear_relacion_nota_categoria(id_nota, id_categoriaNota):
    nueva_ref = db.collection("notas_categoriaNota").document()
    nueva_ref.set({
        "id_nota": id_nota,
        "id_categoriaNota": id_categoriaNota
    })
    return nueva_ref.id


# ---------- MÉTODOS DE CRUD PARA NOTAS ---------- #

def crear_nota(id_usuario, id_plantilla, titulo, contenido,
               etiquetas=None, dibujo=None, estado="activa", 
               animacion_fondo=None, color_fondo=None):
    if etiquetas is None:
        etiquetas = []

    nueva_ref = db.collection("notas").document()

    data = {
        "id_usuario": id_usuario,
        "id_plantilla": id_plantilla,
        "titulo": titulo,
        "contenido": contenido,
        "etiquetas": etiquetas,
        "dibujo": dibujo,
        "estado": estado,
        "favorita": False,
        # Guardamos la configuración visual
        "animacion_fondo": animacion_fondo,
        "color_fondo": color_fondo,
        
        "fecha_creacion": firestore.SERVER_TIMESTAMP,
        "fecha_modificacion": firestore.SERVER_TIMESTAMP
    }

    nueva_ref.set(data)
    return nueva_ref.id


def obtener_notas_usuario(id_usuario):
    docs = db.collection("notas").where("id_usuario", "==", id_usuario).stream()

    notas = []
    for d in docs:
        data = d.to_dict()
        data["id"] = d.id

        data["fecha_creacion"] = serializar_timestamp(data.get("fecha_creacion"))
        data["fecha_modificacion"] = serializar_timestamp(data.get("fecha_modificacion"))

        notas.append(data)

    return notas


def obtener_nota(id_nota):
    doc = db.collection("notas").document(id_nota).get()
    if doc.exists:
        data = doc.to_dict()

        data["fecha_creacion"] = serializar_timestamp(data.get("fecha_creacion"))
        data["fecha_modificacion"] = serializar_timestamp(data.get("fecha_modificacion"))

        return data
    return None


def actualizar_nota(id_nota, cambios):
    cambios["fecha_modificacion"] = firestore.SERVER_TIMESTAMP
    # Firestore crea campos nuevos si no existen, así que animacion_fondo
    # se guardará automáticamente si viene en 'cambios'
    db.collection("notas").document(id_nota).update(cambios)
    return True


def eliminar_nota(id_nota):
    db.collection("notas").document(id_nota).delete()
    return True


# ---------- MÉTODOS PARA CATEGORÍAS (UPDATE/DELETE) ---------- #

def actualizar_categoria(id_categoria, nuevo_nombre):
    doc_ref = db.collection("categoriaNota").document(id_categoria)
    doc_ref.update({"nombre": nuevo_nombre})
    return True


def eliminar_categoria(id_categoria):
    doc_ref = db.collection("categoriaNota").document(id_categoria)
    doc_ref.delete()
    return True

# firestore.py

def obtener_monedas_usuario(id_usuario):
    doc = db.collection("usuarios").document(id_usuario).get()
    if doc.exists:
        return doc.to_dict().get("monedas", 0)
    return 0

def realizar_compra_plantilla(id_usuario, id_plantilla, costo):
    user_ref = db.collection("usuarios").document(id_usuario)
    
    # Usamos una transacción para asegurar que no se descuenten monedas sin dar el producto
    @firestore.transactional
    def transaccion_compra(transaction, user_ref):
        snapshot = user_ref.get(transaction=transaction)
        monedas_actuales = snapshot.get("monedas")
        
        if monedas_actuales < costo:
            return False, "Monedas insuficientes"
        
        # 1. Restar monedas
        transaction.update(user_ref, {"monedas": monedas_actuales - costo})
        
        # 2. Registrar la plantilla desbloqueada
        compra_ref = db.collection("usuarios_plantillas").document()
        transaction.set(compra_ref, {
            "id_usuario": id_usuario,
            "id_plantilla": id_plantilla,
            "fecha_compra": firestore.SERVER_TIMESTAMP
        })
        return True, "Compra exitosa"

    transaction = db.transaction()
    return transaccion_compra(transaction, user_ref)

def plantilla_esta_desbloqueada(id_usuario, id_plantilla):
    # Verifica si existe el registro de compra
    docs = db.collection("usuarios_plantillas")\
             .where("id_usuario", "==", id_usuario)\
             .where("id_plantilla", "==", id_plantilla).stream()
    return any(docs)

def obtener_plantillas_desbloqueadas_usuario(id_usuario):
    # Buscamos en la colección de transacciones/compras
    docs = db.collection("usuarios_plantillas")\
             .where("id_usuario", "==", id_usuario).stream()
    
    return [d.to_dict().get("id_plantilla") for d in docs]

# firestore.py - Añadir estas funciones al final

def usuario_tiene_feature(id_usuario, feature_name):
    """Verifica si el usuario ya compró una funcionalidad (ej: 'multimedia_images')"""
    docs = db.collection("usuarios_features")\
             .where("id_usuario", "==", id_usuario)\
             .where("feature", "==", feature_name).stream()
    return any(docs)

def realizar_compra_feature(id_usuario, feature_name, costo=20):
    user_ref = db.collection("usuarios").document(id_usuario)
    
    @firestore.transactional
    def transaccion_compra(transaction, user_ref):
        snapshot = user_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False, "Usuario no existe"
        
        monedas_actuales = snapshot.to_dict().get("monedas", 0)
        
        if monedas_actuales < costo:
            return False, f"Monedas insuficientes. Tienes {monedas_actuales}"
        
        # 1. Restar monedas
        transaction.update(user_ref, {"monedas": monedas_actuales - costo})
        
        # 2. Registrar la funcionalidad desbloqueada
        feature_ref = db.collection("usuarios_features").document()
        transaction.set(feature_ref, {
            "id_usuario": id_usuario,
            "feature": feature_name,
            "fecha_compra": firestore.SERVER_TIMESTAMP
        })
        return True, "Desbloqueado correctamente"

    transaction = db.transaction()
    return transaccion_compra(transaction, user_ref)