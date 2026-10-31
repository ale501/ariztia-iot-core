import sqlite3
import time
from datetime import datetime

DB_NAME = "tracking.db"

def obtener_conexion():
    """Crea una conexión con timeout para evitar bloqueos entre hilos."""
    conn = sqlite3.connect(DB_NAME, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_bd():
    """Crea las tablas necesarias si no existen."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        
        # Tabla 1: Historial continuo (resumen cada N segundos)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historial_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                pollitos_detectados INTEGER,
                fps REAL,
                agrupamiento_activo INTEGER,
                tiempo_agrupados REAL,
                en_alerta INTEGER
            )
        """)

        # Tabla 2: Registro específico de alertas (para auditoría o reportes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS registro_alertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_inicio DATETIME,
                fecha_fin DATETIME,
                duracion_segundos REAL,
                pollitos_involucrados INTEGER,
                descripcion TEXT
            )
        """)
        conn.commit()
    print("[BD] Base de datos inicializada correctamente.")

def guardar_resumen(pollitos, fps, agrupamiento, tiempo_agrupados, alerta):
    """Guarda una muestra periódica del estado del tracking."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO historial_tracking 
                (pollitos_detectados, fps, agrupamiento_activo, tiempo_agrupados, en_alerta)
                VALUES (?, ?, ?, ?, ?)
            """, (
                pollitos,
                round(fps, 1),
                1 if agrupamiento else 0,
                round(tiempo_agrupados, 1),
                1 if alerta else 0
            ))
            conn.commit()
    except Exception as e:
        print(f"[BD ERROR] Error guardando resumen: {e}")

def registrar_evento_alerta(fecha_inicio, duracion, cantidad_pollos):
    """Registra cuando un episodio de alerta ocurre."""
    try:
        with obtener_conexion() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO registro_alertas 
                (fecha_inicio, fecha_fin, duracion_segundos, pollitos_involucrados, descripcion)
                VALUES (?, datetime('now'), ?, ?, ?)
            """, (
                fecha_inicio,
                round(duracion, 1),
                cantidad_pollos,
                "Agrupamiento prolongado detectado"
            ))
            conn.commit()
    except Exception as e:
        print(f"[BD ERROR] Error registrando alerta: {e}")

def obtener_ultimas_lecturas(limite=50):
    """Consulta los últimos registros para mostrarlos en la web."""
    with obtener_conexion() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM historial_tracking 
            ORDER BY id DESC LIMIT ?
        """, (limite,))
        return [dict(fila) for fila in cursor.fetchall()]

# Al importar o ejecutar directamente, asegura que las tablas existan
if __name__ == "__main__":
    inicializar_bd()