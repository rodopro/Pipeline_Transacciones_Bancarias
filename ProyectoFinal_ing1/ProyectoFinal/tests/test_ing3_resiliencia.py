"""Datos corruptos, bordes de fase 5, carga real y fallos transaccionales."""
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from src.config import DIR_INTERIM
from src.fase5_transformacion import transformacion_discretizacion_escalado as fase5
from src.fase6_validacion import segregar_registros
from src.fase7_base_datos import cargar_base_datos
from src.modelos_ing3 import TransaccionLimpia
from src.pipeline_ing3 import ejecutar_fases_5_a_7
from src.Todas_las_fases import ejecutar_fases_6_y_7
from src.Transformación_E_Integración import (
    cargar_datos_fuentes, cruce_y_detectar_huerfanos, homologar_fechas_y_monedas,
    imputar_faltantes, tratar_outliers_iqr,
)

CUENTAS = {"CTA-0001"}


def transaccion(**cambios):
    return {
        "transaccion_id": "SPEI-1", "account_id": "CTA-0001", "tipo_origen": "SPEI_DIGITAL",
        "fecha_corta": "2026-09-12", "moneda": "MXN", "monto_original": 100.0,
        "monto_mxn": 100.0, "monto_mxn_capped": 100.0, "monto_minmax": 0.0,
        "nivel_monto": "Bajo", "notification_email": "persona@banco.com.mx",
        "beneficiary_clabe": "012210100614023846", "tipo_operacion": None,
        "comision_aplicada": None, "es_huerfano": False, "obs_calidad": "", **cambios,
    }


@pytest.mark.parametrize("montos", [[], [100.0], [100.0, 100.0], [0.0, 100.0, 200.0, 300.0]])
def test_minmax_y_lotes_pequenos(montos):
    d = fase5(pd.DataFrame({"monto_mxn_capped": montos}))
    assert len(d) == len(montos)
    assert d.monto_minmax.between(0, 1).all()
    if len(set(montos)) > 1:
        assert d.monto_minmax.min() == 0 and d.monto_minmax.max() == 1
    elif montos:
        assert d.monto_minmax.eq(0).all() and d.nivel_monto.eq("Bajo").all()


def test_cuantiles_estables_con_empates_y_orden_distinto():
    d = pd.DataFrame({"monto_mxn_capped": [10.0] * 5 + [20.0] * 5 + [30.0] * 5})
    a, b = fase5(d), fase5(d.sample(frac=1, random_state=26))
    assert a.groupby("monto_mxn_capped").nivel_monto.nunique().eq(1).all()
    assert a.nivel_monto.to_dict() == b.nivel_monto.to_dict()
    assert set(a.nivel_monto) == {"Bajo", "Medio", "Alto"}


@pytest.mark.parametrize("valor", [None, np.nan, np.inf, -1.0, "abc", "100", True, [123], {"monto": 1}])
def test_fase5_no_repara_importes_corruptos(valor):
    df = fase5(pd.DataFrame([transaccion(monto_mxn_capped=valor)]))
    aptos, errores = segregar_registros(df, CUENTAS)
    assert not aptos and len(errores) == 1
    assert errores[0].motivo_rechazo_cuarentena
    json.loads(errores[0].registro_original_json)


@pytest.mark.parametrize("cambio", [
    {"account_id": "CTA-9999"}, {"account_id": None}, {"account_id": 123},
    {"transaccion_id": " "}, {"es_huerfano": True}, {"es_huerfano": "False"},
    {"beneficiary_clabe": "12345"}, {"beneficiary_clabe": 12210100614023846},
    {"beneficiary_clabe": None}, {"beneficiary_clabe": "０" * 18},
    {"notification_email": "correo@@sinformato"}, {"fecha_corta": "2026-02-30"},
    {"fecha_corta": "12/09/2026"}, {"fecha_corta": None}, {"moneda": "EUR"},
    {"tipo_origen": "WEB"}, {"monto_original": "100"}, {"monto_original": True},
    {"monto_original": -1.0}, {"monto_original": 0.0}, {"monto_original": float("inf")},
    {"monto_minmax": 1.01}, {"monto_minmax": float("nan")}, {"nivel_monto": "Muy alto"},
    {"monto_mxn": 1950.0}, {"obs_calidad": "MONTO_MXN_NO_NUMERICO"},
    {"tipo_origen": "ATM", "tipo_operacion": "RETIRO", "comision_aplicada": -5.0},
    {"tipo_origen": "ATM", "tipo_operacion": None, "comision_aplicada": 0.0},
    {"tipo_origen": "ATM", "tipo_operacion": "RETIRO", "comision_aplicada": None},
])
def test_segregacion_continua_ante_cada_corrupcion(cambio):
    df = pd.DataFrame([transaccion(**cambio), transaccion(transaccion_id="SIGUIENTE")])
    aptos, errores = segregar_registros(df, CUENTAS)
    assert len(aptos) == len(errores) == 1
    assert aptos[0].transaccion_id == "SIGUIENTE"
    assert errores[0].numero_fila == 1
    assert json.loads(errores[0].errores_validacion_json)


def test_modelo_estricto_rechaza_campos_desconocidos():
    with pytest.raises(ValidationError):
        TransaccionLimpia.model_validate(transaccion(campo_inesperado=1), context={"cuentas_validas": CUENTAS})


def test_anonimo_consulta_cero_y_usd_son_validos():
    filas = [
        transaccion(notification_email="ANONIMO"),
        transaccion(transaccion_id="ATM-CONSULTA", tipo_origen="ATM", tipo_operacion="CONSULTA_SALDO",
                    monto_original=0.0, monto_mxn=0.0, monto_mxn_capped=0.0,
                    comision_aplicada=0.0, beneficiary_clabe=None),
        transaccion(transaccion_id="USD", moneda="USD", monto_mxn=1950.0, monto_mxn_capped=1950.0),
    ]
    aptos, errores = segregar_registros(fase5(pd.DataFrame(filas)), CUENTAS)
    assert len(aptos) == 3 and not errores
    assert aptos[0].beneficiary_clabe.startswith("0")


def test_duplicados_y_multiples_causas_conservan_todas_las_filas():
    filas = [transaccion(), transaccion(), transaccion(account_id="HUERFANA", notification_email="malo")]
    aptos, errores = segregar_registros(pd.DataFrame(filas), CUENTAS)
    assert len(aptos) == 1 and len(errores) == 2
    assert "duplicado" in errores[0].motivo_rechazo_cuarentena
    assert len(json.loads(errores[1].errores_validacion_json)) >= 2


def conteos(ruta):
    with sqlite3.connect(ruta) as conn:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                     for t in ("transacciones_limpias", "cuarentena_errores"))


def test_commit_persistencia_clabe_y_parametros_sql(tmp_path):
    # El texto parecido a SQL es un valor literal; no se interpola en la consulta.
    ident = "TX'); DROP TABLE cuarentena_errores; --"
    aptos, errores = segregar_registros(pd.DataFrame([
        transaccion(transaccion_id=ident), transaccion(notification_email="malo"),
    ]), CUENTAS)
    ruta = tmp_path / "bd.sqlite3"
    cargar_base_datos(aptos, errores, ruta)
    assert conteos(ruta) == (1, 1)
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT transaccion_id, beneficiary_clabe FROM transacciones_limpias").fetchone() == (
            ident, "012210100614023846")
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_rollback_por_duplicado_revierte_insercion_previa(tmp_path):
    aptos, errores = segregar_registros(pd.DataFrame([transaccion()]), CUENTAS)
    ruta = tmp_path / "bd.sqlite3"
    cargar_base_datos(aptos, errores, ruta)
    nuevo, _ = segregar_registros(pd.DataFrame([transaccion(transaccion_id="NUEVA")]), CUENTAS)
    with pytest.raises(sqlite3.IntegrityError):
        cargar_base_datos(nuevo + aptos, [], ruta)
    assert conteos(ruta) == (1, 0)
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT transaccion_id FROM transacciones_limpias").fetchone()[0] == "SPEI-1"


def test_rollback_en_cuarentena_restaura_ambas_tablas_y_delete(tmp_path):
    ruta = tmp_path / "bd.sqlite3"
    aptos, errores = segregar_registros(pd.DataFrame([
        transaccion(), transaccion(notification_email="malo"),
    ]), CUENTAS)
    cargar_base_datos(aptos, errores, ruta)
    with sqlite3.connect(ruta) as conn:
        antes = list(conn.iterdump())
        conn.execute("""CREATE TRIGGER fallo_cuarentena BEFORE INSERT ON cuarentena_errores
                        BEGIN SELECT RAISE(ABORT, 'fallo inyectado'); END""")
    nuevos, _ = segregar_registros(pd.DataFrame([transaccion(transaccion_id="NUEVA")]), CUENTAS)
    with pytest.raises(sqlite3.IntegrityError, match="fallo inyectado"):
        cargar_base_datos(nuevos, errores, ruta, reemplazar=True)
    with sqlite3.connect(ruta) as conn:
        conn.execute("DROP TRIGGER fallo_cuarentena")
        assert list(conn.iterdump()) == antes


@pytest.mark.parametrize("filas,esperado", [([], (0, 0)), ([transaccion(notification_email="malo")], (0, 1))])
def test_pipeline_vacio_o_totalmente_corrupto(tmp_path, filas, esperado):
    df = pd.DataFrame(filas) if filas else pd.DataFrame(columns=["monto_mxn_capped"])
    ruta = tmp_path / "bd.sqlite3"
    resumen = ejecutar_fases_5_a_7(df, CUENTAS, ruta, tmp_path / "reportes")
    assert conteos(ruta) == esperado
    assert resumen["balance_correcto"] and resumen["integridad_sqlite"] == "ok"
    assert list(pd.read_csv(tmp_path / "reportes/cuarentena_errores.csv").columns)


def test_fechas_mixtas_y_corrupcion_sin_fecha_inventada():
    df = pd.DataFrame({
        "timestamp": ["12/09/2026 13:26", "2026/09/28 11:15:00", "2026-09-12T19:49:00-06:00",
                      1788816180, "basura", None],
        "monto_original": [100.0] * 6, "moneda": ["MXN"] * 6,
    })
    resultado = homologar_fechas_y_monedas(df)
    assert resultado.fecha_corta.iloc[:4].tolist() == ["2026-09-12", "2026-09-28", "2026-09-12", "2026-09-07"]
    assert resultado.fecha_corta.iloc[4:].isna().all()


@pytest.mark.parametrize("filas,esperado", [
    ([], (0, 0)),
    ([transaccion(notification_email="malo")], (0, 1)),
    ([transaccion(), transaccion(transaccion_id="RECHAZADA", account_id="HUERFANA")], (1, 1)),
])
def test_todas_las_fases_valida_carga_y_conserva_evidencias(tmp_path, filas, esperado):
    df = pd.DataFrame(filas) if filas else pd.DataFrame(columns=["monto_mxn_capped"])
    transformadas = fase5(df)
    ruta = tmp_path / "unificado.sqlite3"
    reportes = tmp_path / "reportes"
    primero = ejecutar_fases_6_y_7(transformadas, CUENTAS, ruta, reportes)
    segundo = ejecutar_fases_6_y_7(transformadas, CUENTAS, ruta, reportes)

    assert primero == segundo
    assert conteos(ruta) == esperado
    assert segundo["registros_entrada"] == len(filas)
    assert segundo["balance_correcto"] and segundo["integridad_sqlite"] == "ok"
    assert segundo["parametros_fase5"] == transformadas.attrs["parametros_fase5"]
    assert json.loads((reportes / "resumen_ing3.json").read_text(encoding="utf-8")) == segundo
    assert len(pd.read_csv(reportes / "transacciones_limpias.csv")) == esperado[0]
    assert len(pd.read_csv(reportes / "cuarentena_errores.csv")) == esperado[1]
    for archivo in segundo["diagramas"].values():
        assert (reportes / archivo).is_file()
    if esperado[0]:
        with sqlite3.connect(ruta) as conn:
            assert conn.execute("SELECT beneficiary_clabe FROM transacciones_limpias").fetchone()[0] == "012210100614023846"


def test_corrupcion_de_fase2_llega_a_cuarentena_sin_imputar():
    filas = [
        {**transaccion(), "timestamp": "basura"},
        {**transaccion(transaccion_id="MONTO", monto_original="abc"), "timestamp": "2026-09-12"},
        {**transaccion(transaccion_id="CLABE", beneficiary_clabe=None), "timestamp": "2026-09-12"},
        {**transaccion(transaccion_id="NEGATIVO", monto_original=-1.0), "timestamp": "2026-09-12"},
    ]
    df = imputar_faltantes(homologar_fechas_y_monedas(pd.DataFrame(filas)))
    capped, *_ = tratar_outliers_iqr(df)
    aptos, errores = segregar_registros(fase5(capped), CUENTAS)
    assert not aptos and len(errores) == len(filas)


def test_datos_equipo_end_to_end_y_repeticion_sin_duplicados(tmp_path):
    cat, df = cargar_datos_fuentes(
        DIR_INTERIM / "catalogo_cuentas_fase2.csv", DIR_INTERIM / "transacciones_atm_fase2.csv",
        DIR_INTERIM / "transferencias_digitales_fase2.json",
    )
    df = imputar_faltantes(homologar_fechas_y_monedas(df))
    capped, *_ = tratar_outliers_iqr(df)
    cruzadas = cruce_y_detectar_huerfanos(capped, cat)
    ruta = tmp_path / "bd.sqlite3"
    primero = ejecutar_fases_5_a_7(cruzadas, set(cat.id_cuenta), ruta, tmp_path / "reportes")
    segundo = ejecutar_fases_5_a_7(cruzadas, set(cat.id_cuenta), ruta, tmp_path / "reportes")
    assert primero == segundo
    assert primero["registros_entrada"] == 1200
    assert sum(conteos(ruta)) == 1200
    assert primero["limpias_cargadas"] > 0 and primero["cuarentena_cargada"] >= 61
    with sqlite3.connect(ruta) as conn:
        assert conn.execute("SELECT COUNT(*) FROM transacciones_limpias WHERE tipo_operacion = 'CONSULTA_SALDO'").fetchone()[0] > 0


def test_estres_20000_registros_mitad_corruptos(tmp_path, record_property):
    cambios = [
        {"notification_email": "correo@@malo"}, {"beneficiary_clabe": "123"},
        {"account_id": "HUERFANA"}, {"fecha_corta": "2026-02-30"},
        {"monto_original": "abc"}, {"monto_original": float("inf")},
        {"moneda": "EUR"}, {"es_huerfano": True},
    ]
    filas = []
    for i in range(20_000):
        cambio = cambios[(i // 2) % len(cambios)] if i % 2 else {}
        filas.append(transaccion(transaccion_id=f"STRESS-{i:06d}", **cambio))
    ruta = tmp_path / "estres.sqlite3"
    resumen = ejecutar_fases_5_a_7(pd.DataFrame(filas), CUENTAS, ruta, tmp_path / "reportes")
    assert conteos(ruta) == (10_000, 10_000)
    assert resumen["registros_entrada"] == 20_000 and resumen["balance_correcto"]
    assert resumen["integridad_sqlite"] == "ok"
    record_property("registros_inyectados", 20_000)
    record_property("validos", 10_000)
    record_property("cuarentena", 10_000)
