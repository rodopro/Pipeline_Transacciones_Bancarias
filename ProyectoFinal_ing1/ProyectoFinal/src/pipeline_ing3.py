"""Contrato de integración de las fases 5, 6 y 7 y exportación de evidencias."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3

import pandas as pd

from .fase5_transformacion import transformacion_discretizacion_escalado
from .fase6_validacion import segregar_registros
from .fase7_base_datos import cargar_base_datos
from .modelos_ing3 import RegistroCuarentena, TransaccionLimpia
from .diagramas_ing3 import generar_diagramas


def ejecutar_fases_5_a_7(
    df: pd.DataFrame, cuentas_validas: set[str], ruta_bd: str | Path,
    directorio_reportes: str | Path,
) -> dict:
    transformadas = transformacion_discretizacion_escalado(df)
    limpios, cuarentena = segregar_registros(transformadas, cuentas_validas)
    carga = cargar_base_datos(limpios, cuarentena, ruta_bd, reemplazar=True)
    with closing(sqlite3.connect(ruta_bd)) as conn:
        integridad = conn.execute("PRAGMA integrity_check").fetchone()[0]
    resumen = {
        "registros_entrada": len(df), **carga,
        "balance_correcto": len(df) == len(limpios) + len(cuarentena),
        "parametros_fase5": transformadas.attrs["parametros_fase5"],
        "integridad_sqlite": integridad,
        "modo_carga": "reemplazo_atomico_de_ambas_tablas",
        "base_datos": str(Path(ruta_bd).resolve()),
    }
    salida = Path(directorio_reportes)
    salida.mkdir(parents=True, exist_ok=True)
    transformadas.to_csv(salida / "fase5_transformadas.csv", index=False, encoding="utf-8-sig")
    for nombre, registros, modelo in (
        ("transacciones_limpias.csv", limpios, TransaccionLimpia),
        ("cuarentena_errores.csv", cuarentena, RegistroCuarentena),
    ):
        pd.DataFrame([r.model_dump() for r in registros], columns=list(modelo.model_fields)).to_csv(
            salida / nombre, index=False, encoding="utf-8-sig"
        )
    resumen["diagramas"] = {
        clave: f"diagramas/{archivo}"
        for clave, archivo in generar_diagramas(salida / "diagramas", resumen).items()
    }
    (salida / "resumen_ing3.json").write_text(
        json.dumps(resumen, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return resumen
