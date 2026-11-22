"""
MÓDULO DE BASE DE DATOS DUAL (POSTGRESQL + SQLITE)
==================================================
Soporta PostgreSQL (ideal para Grafana y producción) con respaldo
automático transparente a SQLite local (tracking.db) si PostgreSQL
no está disponible o Docker está apagado.
"""

import json
import os
import sqlite3
import time
from datetime import datetime

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_CONFIG = os.path.join(CARPETA, "config_hardware.json")

# Estado del motor activo
MOTOR_ACTIVO = "sqlite"
PG_POOL = None


def cargar_config_db():
    cfg = {
        "motor": "auto",
        "postgres": {
          "host": "localhost",
          "puerto": 5432,
          "db": "ariztia_db",
          "usuario": "ariztia",
          "password": "ariztia_password"
        },
        "sqlite_archivo": "tracking.db"
    }
    if os.path.exists(RUTA_CONFIG):
        try:
            with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
                datos = json.load(f)
                if "base_de_datos" in datos:
                    cfg.update(datos["base_de_datos"])
        except Exception:
            pass

    # Si corre en contenedor Docker o variable de entorno
    if "POSTGRES_HOST" in os.environ:
        cfg["postgres"]["host"] = os.environ["POSTGRES_HOST"]

    return cfg


def probar_conexion_postgres(cfg_pg):
    """Verifica si psycopg2 está instalado y PostgreSQL responde."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=cfg_pg.get("host", "localhost"),
            port=cfg_pg.get("puerto", 5432),
            dbname=cfg_pg.get("db", "ariztia_db"),
            user=cfg_pg.get("usuario", "ariztia"),
            password=cfg_pg.get("password", "ariztia_password"),
            connect_timeout=2
        )
        conn.close()
        return True
    except Exception:
        return False


_ESTADO_PG_CACHE = {"ok": None, "ts": 0.0}

def obtener_conexion():
    """Devuelve (conexion, motor_nombre) de forma eficiente."""
    global MOTOR_ACTIVO, _ESTADO_PG_CACHE
    cfg = cargar_config_db()
    motor_deseado = cfg.get("motor", "auto").lower()

    # Intentar PostgreSQL si está configurado o en auto
    if motor_deseado in ["postgres", "postgresql", "auto"]:
        cfg_pg = cfg.get("postgres", {})
        ahora = time.time()
        
        # Si sabemos que falló hace menos de 10 segundos, no bloquear con reintentos lentos
        pg_valido = _ESTADO_PG_CACHE["ok"] is True or (_ESTADO_PG_CACHE["ok"] is None) or (ahora - _ESTADO_PG_CACHE["ts"] > 10.0)
        
        if pg_valido:
            try:
                import psycopg2
                conn = psycopg2.connect(
                    host=cfg_pg.get("host", "localhost"),
                    port=cfg_pg.get("puerto", 5432),
                    dbname=cfg_pg.get("db", "ariztia_db"),
                    user=cfg_pg.get("usuario", "ariztia"),
                    password=cfg_pg.get("password", "ariztia_password"),
                    connect_timeout=2
                )
                MOTOR_ACTIVO = "postgres"
                _ESTADO_PG_CACHE["ok"] = True
                _ESTADO_PG_CACHE["ts"] = ahora
                return conn, "postgres"
            except Exception:
                _ESTADO_PG_CACHE["ok"] = False
                _ESTADO_PG_CACHE["ts"] = ahora

    # Respaldo a SQLite
    ruta_sqlite = os.path.join(CARPETA, cfg.get("sqlite_archivo", "tracking.db"))
    conn = sqlite3.connect(ruta_sqlite, timeout=10.0)
    conn.row_factory = sqlite3.Row
    MOTOR_ACTIVO = "sqlite"
    return conn, "sqlite"


def inicializar_bd():
    """Crea las tablas necesarias en PostgreSQL o SQLite."""
    conn, motor = obtener_conexion()
    try:
        with conn:
            cursor = conn.cursor()

            if motor == "postgres":
                print("[BD] Conectado a PostgreSQL (Modo Producción / Grafana)")
                # Tabla 1: Historial de Tracking
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS historial_tracking (
                        id SERIAL PRIMARY KEY,
                        fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        pollitos_detectados INTEGER,
                        fps REAL,
                        agrupamiento_activo INTEGER,
                        tiempo_agrupados REAL,
                        en_alerta INTEGER
                    );
                """)

                # Tabla 2: Registro de Alertas
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS registro_alertas (
                        id SERIAL PRIMARY KEY,
                        fecha_inicio TIMESTAMP,
                        fecha_fin TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        duracion_segundos REAL,
                        pollitos_involucrados INTEGER,
                        descripcion TEXT
                    );
                """)

                # Tabla 3: Lecturas Ambientales (Ariztía)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS lecturas_ambientales (
                        id SERIAL PRIMARY KEY,
                        fecha_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        temperatura REAL,
                        humedad REAL,
                        iec REAL,
                        nivel VARCHAR(50),
                        etiqueta VARCHAR(100),
                        accion TEXT,
                        origen VARCHAR(50),
                        estado_conexion VARCHAR(50)
                    );
                """)
            else:
                print("[BD] Conectado a SQLite local (tracking.db)")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS historial_tracking (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                        pollitos_detectados INTEGER,
                        fps REAL,
                        agrupamiento_activo INTEGER,
                        tiempo_agrupados REAL,
                        en_alerta INTEGER
                    );
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS registro_alertas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fecha_inicio DATETIME,
                        fecha_fin DATETIME DEFAULT CURRENT_TIMESTAMP,
                        duracion_segundos REAL,
                        pollitos_involucrados INTEGER,
                        descripcion TEXT
                    );
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS lecturas_ambientales (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                        temperatura REAL,
                        humedad REAL,
                        iec REAL,
                        nivel TEXT,
                        etiqueta TEXT,
                        accion TEXT,
                        origen TEXT,
                        estado_conexion TEXT
                    );
                """)
            conn.commit()
    except Exception as e:
        print(f"[BD ERROR] Fallo al inicializar tablas: {e}")
    finally:
        conn.close()


def guardar_resumen(pollitos, fps, agrupamiento, tiempo_agrupados, alerta):
    """Guarda una muestra de tracking en la BD activa."""
    try:
        conn, motor = obtener_conexion()
        with conn:
            cursor = conn.cursor()
            p = "%s" if motor == "postgres" else "?"
            cursor.execute(f"""
                INSERT INTO historial_tracking 
                (pollitos_detectados, fps, agrupamiento_activo, tiempo_agrupados, en_alerta)
                VALUES ({p}, {p}, {p}, {p}, {p})
            """, (
                pollitos,
                round(float(fps), 1),
                1 if agrupamiento else 0,
                round(float(tiempo_agrupados), 1),
                1 if alerta else 0
            ))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[BD ERROR] Error guardando tracking: {e}")


def registrar_evento_alerta(fecha_inicio, duracion, cantidad_pollos, descripcion="Alerta detectada"):
    """Registra cuando ocurre un episodio crítico."""
    try:
        conn, motor = obtener_conexion()
        with conn:
            cursor = conn.cursor()
            p = "%s" if motor == "postgres" else "?"
            now_sql = "NOW()" if motor == "postgres" else "datetime('now')"
            cursor.execute(f"""
                INSERT INTO registro_alertas 
                (fecha_inicio, fecha_fin, duracion_segundos, pollitos_involucrados, descripcion)
                VALUES ({p}, {now_sql}, {p}, {p}, {p})
            """, (
                fecha_inicio,
                round(float(duracion), 1),
                cantidad_pollos,
                descripcion
            ))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[BD ERROR] Error registrando alerta: {e}")


def guardar_lectura_ambiental(temp, hum, iec, nivel, etiqueta, accion, origen, estado_conexion):
    """Guarda una lectura de Ariztía en la BD activa (permite tablas en Grafana)."""
    try:
        conn, motor = obtener_conexion()
        with conn:
            cursor = conn.cursor()
            p = "%s" if motor == "postgres" else "?"
            cursor.execute(f"""
                INSERT INTO lecturas_ambientales
                (temperatura, humedad, iec, nivel, etiqueta, accion, origen, estado_conexion)
                VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            """, (
                temp, hum, iec, nivel, etiqueta, accion, origen, estado_conexion
            ))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[BD ERROR] Error guardando lectura ambiental: {e}")


def obtener_ultimas_lecturas(limite=50):
    """Consulta los últimos registros de tracking."""
    conn, motor = obtener_conexion()
    try:
        cursor = conn.cursor()
        p = "%s" if motor == "postgres" else "?"
        cursor.execute(f"""
            SELECT * FROM historial_tracking 
            ORDER BY id DESC LIMIT {p}
        """, (limite,))
        if motor == "postgres":
            import psycopg2.extras
            cols = [desc[0] for desc in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        return [dict(fila) for fila in cursor.fetchall()]
    finally:
        conn.close()


if __name__ == "__main__":
    inicializar_bd()
