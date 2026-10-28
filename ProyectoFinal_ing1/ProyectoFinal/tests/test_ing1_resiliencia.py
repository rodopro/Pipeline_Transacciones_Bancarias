"""
Pruebas de resiliencia de las Fases 1 y 2 (Ingeniero/a 1).
Inyectan datos corruptos y verifican que el código NO se cae (no crash),
que imputa solo lo que debe y que deja trazabilidad.

Ejecutar desde la raíz:  python -m pytest -q tests
"""
import numpy as np
import pandas as pd
import pytest

from src import fase1_diagnostico as F1
from src import fase2_imputacion as F2


@pytest.fixture
def atm_corrupto():
    return pd.DataFrame({
        "id_transaccion": ["T1", "T2", "T3", "T4", "T5", "T5", "T6", "T7"],
        "fecha_hora": ["2026-09-01 10:00:00"] * 8,
        "id_cuenta": ["CTA-0001"] * 8,
        "tipo_operacion": ["retiro", "RETIRO", " Deposito ", "CONSULTA_SALDO",
                           "RETIRO", "RETIRO", "DEPOSITO", "RETIRO"],
        "monto_mxn": [1000, None, None, None, "abc", "abc", 4000, "N/A"],
        "id_cajero": ["ATM-COL-01", "", None, "N/A", "ATM-COL-01", "ATM-COL-01", "x", None],
        "resultado": ["exitosa", "EXITOSA", "FALLO_FONDOS", "exitosa",
                      "EXITOSA", "EXITOSA", "EXITOSA", "EXITOSA"],
        "comision_aplicada": [15, None, 0, 25, 15, 15, "error", 0],
    })


@pytest.fixture
def transfer_corrupto():
    return pd.DataFrame({
        "transfer_id": ["S1", "S2", "S3", "S4"],
        "timestamp": ["2026-09-01T10:00:00-06:00", 1788816180, None, "basura"],
        "account_id": ["CTA-0001", "CTA-0002", None, "CTA-9999"],
        "amount": [100.0, None, "mil", 50.0],
        "currency": ["MXN", "usd", "USD", "MXN"],
        "beneficiary_clabe": ["012210100614023846", "12345", None, "012"],
        "notification_email": ["a@b.com", "", None, "correo@@sinformato"],
        "concept": ["Nómina"] * 4,
        "status": ["liquidada", "LIQUIDADA", "PENDIENTE", "rechazada"],
        "platform": ["App iOS"] * 4,
    })


def test_perfil_no_falla_con_tipos_mezclados(atm_corrupto):
    perfil = F1.perfil_columnas(atm_corrupto, "atm")
    assert len(perfil) == atm_corrupto.shape[1]
    fila = perfil.set_index("columna").loc["id_cajero"]
    assert fila["nulos_ocultos"] == 2        # '' y 'N/A'
    assert fila["nulos_explicitos"] == 2     # None x2


def test_resumen_detecta_duplicados(atm_corrupto):
    r = F1.resumen_dataset(atm_corrupto, "atm", "id_transaccion")
    assert r["duplicados_exactos"] == 1 and r["duplicados_por_llave"] == 1


def test_fase2_atm_no_crash_y_reglas(atm_corrupto):
    df, dups, pruebas, log, _ = F2.procesar_atm(atm_corrupto)
    assert len(dups) == 1 and len(df) == 7                          # reintento eliminado
    d = df.set_index("id_transaccion")
    assert d.loc["T4", "monto_mxn"] == 0.0                          # CONSULTA_SALDO recalculada
    assert d.loc["T2", "monto_mxn"] == 1000.0                       # mediana de RETIRO
    assert d.loc["T3", "monto_mxn"] == 4000.0                       # mediana de DEPOSITO (tras strip/upper)
    assert np.isnan(d.loc["T5", "monto_mxn"])                       # 'abc' = corrupto: NO se imputa
    assert "MONTO_MXN_NO_NUMERICO" in d.loc["T5", "obs_calidad"]
    assert d.loc["T7", "monto_mxn"] == 1000.0                       # 'N/A' = nulo oculto: sí se imputa
    assert d.loc["T2", "id_cajero"] == "CAJERO_DESCONOCIDO"
    assert d["resultado"].isin(["EXITOSA", "FALLO_FONDOS"]).all()
    assert d.loc["T2", "comision_aplicada_imputado"]                # comisión NaN imputada
    assert "COMISION_APLICADA_NO_NUMERICO" in d.loc["T6", "obs_calidad"]
    assert set(log["columna"]) >= {"monto_mxn", "id_cajero", "comision_aplicada"}


def test_fase2_transferencias_no_imputa_llaves(transfer_corrupto):
    df, _, _, log, _ = F2.procesar_transferencias(transfer_corrupto)
    d = df.set_index("transfer_id")
    assert pd.isna(d.loc["S3", "account_id"])            # llave: nunca se imputa
    assert pd.isna(d.loc["S3", "beneficiary_clabe"])     # CLABE: nunca se imputa
    assert d.loc["S2", "notification_email"] == "ANONIMO"
    assert d.loc["S3", "notification_email"] == "ANONIMO"
    assert d.loc["S4", "notification_email"] == "correo@@sinformato"  # inválido -> lo valida Pydantic
    assert d.loc["S2", "amount"] == 100.0 or d.loc["S2", "amount"] > 0  # mediana por moneda / global
    assert np.isnan(d.loc["S3", "amount"])                # 'mil' corrupto -> cuarentena


def test_hallazgos_con_dataset_vacio():
    vacio = {
        "catalogo_cuentas": pd.DataFrame(columns=["id_cuenta", "estado_cuenta"]),
        "transacciones_atm": pd.DataFrame(columns=["id_transaccion", "fecha_hora", "id_cuenta",
                                                   "tipo_operacion", "monto_mxn", "id_cajero",
                                                   "resultado", "comision_aplicada"]),
        "transferencias_digitales": pd.DataFrame(columns=["transfer_id", "timestamp", "account_id",
                                                          "amount", "currency", "beneficiary_clabe",
                                                          "notification_email", "status"]),
    }
    h = F1.hallazgos_validez(vacio)     # no debe lanzar excepción
    assert len(h) > 0


def test_clasificacion_mcar_vs_mar():
    rng = np.random.default_rng(0)
    n = 400
    g = np.where(np.arange(n) < 200, "A", "B")
    x = rng.normal(100, 10, n)
    mar = x.copy(); mar[(g == "B") & (rng.random(n) < 0.4)] = np.nan   # depende de g
    mcar = x.copy(); mcar[rng.random(n) < 0.1] = np.nan                 # aleatorio
    df = pd.DataFrame({"g": g, "mar": mar, "mcar": mcar})
    assert F2.clasificar_faltante(df, "mar", "t", ["g"], [])["conclusion"].iloc[0].startswith("MAR")
    assert F2.clasificar_faltante(df, "mcar", "t", ["g"], [])["conclusion"].iloc[0].startswith("MCAR")


def test_carga_segura_detecta_nulos_disfrazados():
    """Los 8 correos '' del JSON deben llegar como NaN (8 null + 8 '' = 16),
    y la CLABE debe conservar sus 18 dígitos (no perder el '0' inicial)."""
    seguro = F1.cargar_crudo_seguro()
    tr = seguro["transferencias_digitales"]
    assert tr["notification_email"].isna().sum() == 16
    assert (tr["beneficiary_clabe"].str.len() == 18).sum() == 554
    dis = F1.explorar_nulos_disfrazados()
    assert set(dis["valor_encontrado"]) >= {"(vacío)", "null"}
