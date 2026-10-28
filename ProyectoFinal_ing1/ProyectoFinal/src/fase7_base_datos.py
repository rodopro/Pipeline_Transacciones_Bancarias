"""Carga atómica de ambas tablas usando SQLite de la biblioteca estándar."""
from __future__ import annotations

from pathlib import Path
import sqlite3

from .modelos_ing3 import RegistroCuarentena, TransaccionLimpia

DDL_LIMPIAS = """
CREATE TABLE IF NOT EXISTS transacciones_limpias (
    transaccion_id TEXT PRIMARY KEY NOT NULL,
    account_id TEXT NOT NULL,
    tipo_origen TEXT NOT NULL CHECK(tipo_origen IN ('ATM', 'SPEI_DIGITAL')),
    fecha_corta TEXT NOT NULL,
    moneda TEXT NOT NULL CHECK(moneda IN ('MXN', 'USD')),
    monto_original REAL NOT NULL CHECK(monto_original >= 0),
    monto_mxn REAL NOT NULL CHECK(monto_mxn >= 0),
    monto_mxn_capped REAL NOT NULL CHECK(monto_mxn_capped >= 0),
    monto_minmax REAL NOT NULL CHECK(monto_minmax BETWEEN 0 AND 1),
    nivel_monto TEXT NOT NULL CHECK(nivel_monto IN ('Bajo', 'Medio', 'Alto')),
    notification_email TEXT NOT NULL,
    beneficiary_clabe TEXT CHECK(beneficiary_clabe IS NULL OR
        (length(beneficiary_clabe) = 18 AND beneficiary_clabe NOT GLOB '*[^0-9]*')),
    tipo_operacion TEXT,
    comision_aplicada REAL CHECK(comision_aplicada IS NULL OR comision_aplicada >= 0),
    es_huerfano INTEGER NOT NULL CHECK(es_huerfano = 0),
    obs_calidad TEXT NOT NULL,
    datos_origen_json TEXT NOT NULL,
    CHECK(tipo_origen != 'SPEI_DIGITAL' OR beneficiary_clabe IS NOT NULL),
    CHECK(tipo_origen != 'ATM' OR (tipo_operacion IS NOT NULL AND comision_aplicada IS NOT NULL)),
    CHECK((tipo_origen = 'ATM' AND tipo_operacion = 'CONSULTA_SALDO' AND monto_mxn = 0)
          OR monto_mxn > 0)
)
"""
DDL_CUARENTENA = """
CREATE TABLE IF NOT EXISTS cuarentena_errores (
    id_error INTEGER PRIMARY KEY,
    numero_fila INTEGER NOT NULL CHECK(numero_fila >= 1),
    transaccion_id TEXT,
    tipo_origen TEXT,
    motivo_rechazo_cuarentena TEXT NOT NULL CHECK(length(motivo_rechazo_cuarentena) > 0),
    errores_validacion_json TEXT NOT NULL,
    registro_original_json TEXT NOT NULL
)
"""


def cargar_base_datos(
    limpios: list[TransaccionLimpia], cuarentena: list[RegistroCuarentena],
    ruta_bd: str | Path, *, reemplazar: bool = False,
) -> dict:
    """Append por defecto; reemplazar renueva las dos tablas en una sola transacción.

    No usa INSERT OR IGNORE ni executescript: un error debe revertir todas las
    inserciones, incluidos los DELETE de una actualización del lote.
    """
    ruta = Path(ruta_bd)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ruta)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(DDL_LIMPIAS)
        conn.execute(DDL_CUARENTENA)
        if reemplazar:
            conn.execute("DELETE FROM transacciones_limpias")
            conn.execute("DELETE FROM cuarentena_errores")
        for tabla, modelo, registros in (
            ("transacciones_limpias", TransaccionLimpia, limpios),
            ("cuarentena_errores", RegistroCuarentena, cuarentena),
        ):
            columnas = list(modelo.model_fields)
            # Tabla y columnas son constantes internas; solo los valores son externos.
            sql = f"INSERT INTO {tabla} ({', '.join(columnas)}) VALUES ({', '.join('?' for _ in columnas)})"
            conn.executemany(sql, [tuple(datos[c] for c in columnas)
                                   for datos in (r.model_dump() for r in registros)])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"limpias_cargadas": len(limpios), "cuarentena_cargada": len(cuarentena)}
