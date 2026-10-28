"""Ejecuta la entrega de Ing. 3 usando las salidas de fase 2 del equipo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import webbrowser

import pandas as pd

from src.Transformación_E_Integración import (
    cargar_datos_fuentes, cruce_y_detectar_huerfanos, homologar_fechas_y_monedas,
    imputar_faltantes, tratar_outliers_iqr,
)
from src.pipeline_ing3 import ejecutar_fases_5_a_7

RAIZ = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=RAIZ / "data" / "proyecto_final.sqlite3")
    parser.add_argument("--reportes", type=Path, default=RAIZ / "reportes" / "ing3")
    parser.add_argument("--ver-diagramas", action="store_true", help="Abre los diagramas generados en el navegador")
    args = parser.parse_args()
    try:
        interim = RAIZ / "data" / "interim"
        catalogo, unificadas = cargar_datos_fuentes(
            interim / "catalogo_cuentas_fase2.csv", interim / "transacciones_atm_fase2.csv",
            interim / "transferencias_digitales_fase2.json",
        )
        homologadas = imputar_faltantes(homologar_fechas_y_monedas(unificadas))
        capped, *_ = tratar_outliers_iqr(homologadas)
        cruzadas = cruce_y_detectar_huerfanos(capped, catalogo)
        resumen = ejecutar_fases_5_a_7(
            cruzadas, set(catalogo["id_cuenta"].dropna()), args.bd, args.reportes
        )
    except (OSError, sqlite3.Error, ValueError, KeyError, pd.errors.ParserError) as error:
        print(f"[ERROR] No se completó la carga: {error}")
        return 1
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    if args.ver_diagramas:
        webbrowser.open((args.reportes / "diagramas" / "ver_diagramas.html").resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
