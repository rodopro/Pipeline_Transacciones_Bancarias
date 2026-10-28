"""
Script unificado completo: Fases 1 a 7 (Ingenieros/as 1, 2 y 3)
Pipeline ETL - Fintech & Transacciones Bancarias
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ==========================================================================
# 0. CONFIGURACIÓN CENTRAL Y CONSTANTES DE NEGOCIO
# ==========================================================================
class C:
    RAIZ = Path(__file__).resolve().parent.parent
    DIR_DATASETS = RAIZ / "datasets"
    DIR_INTERIM = RAIZ / "data" / "interim"
    DIR_REPORTES = RAIZ / "reportes" / "ing1"
    DIR_FIGURAS = DIR_REPORTES / "figuras"
    DIR_FIGURAS_ING2 = RAIZ / "reportes" / "figuras_ing2"

    ARCH_CATALOGO = DIR_DATASETS / "catalogo_cuentas.csv"
    ARCH_ATM = DIR_DATASETS / "transacciones_atm.csv"
    ARCH_TRANSFER = DIR_DATASETS / "transferencias_digitales.json"

    LLAVES = {
        "catalogo_cuentas": "id_cuenta",
        "transacciones_atm": "id_transaccion",
        "transferencias_digitales": "transfer_id",
    }

    COLUMNAS_TEXTO = {
        "catalogo_cuentas": ["id_cuenta"],
        "transacciones_atm": ["id_transaccion", "id_cuenta", "id_cajero"],
        "transferencias_digitales": ["transfer_id", "account_id", "beneficiary_clabe"],
    }

    NA_VALUES = ["", " ", "N/A", "NA", "n/a", "na", "null", "NULL", "None", "none",
                 "-", "--", "?", "nan", "NaN", "unknown", "Unknown", "desconocido", "S/D"]
    TOKENS_NULOS = {v.strip().upper() for v in NA_VALUES}

    ETIQUETA_CAJERO = "CAJERO_DESCONOCIDO"
    ETIQUETA_EMAIL = "ANONIMO"

    ALFA = 0.05
    N_PERMUTACIONES = 5000
    SEMILLA = 2026
    TASA_CAMBIO_USD_MXN = 19.50

    NO_IMPUTABLES = {
        "transacciones_atm": ["id_transaccion", "id_cuenta", "fecha_hora", "tipo_operacion"],
        "transferencias_digitales": ["transfer_id", "account_id", "timestamp",
                                     "beneficiary_clabe", "currency"],
    }


# ==========================================================================
# 1. FASE 1: DIAGNÓSTICO (fase1_diagnostico.py)
# ==========================================================================
def cargar_crudo_ingenuo() -> dict[str, pd.DataFrame]:
    return {
        "catalogo_cuentas": pd.read_csv(C.ARCH_CATALOGO, encoding="utf-8"),
        "transacciones_atm": pd.read_csv(C.ARCH_ATM, encoding="utf-8"),
        "transferencias_digitales": pd.read_json(C.ARCH_TRANSFER, encoding="utf-8"),
    }


def explorar_nulos_disfrazados() -> pd.DataFrame:
    crudos = {
        "catalogo_cuentas": pd.read_csv(C.ARCH_CATALOGO, keep_default_na=False, dtype=str),
        "transacciones_atm": pd.read_csv(C.ARCH_ATM, keep_default_na=False, dtype=str),
    }
    with open(C.ARCH_TRANSFER, encoding="utf-8") as fh:
        registros = json.load(fh)
    crudos["transferencias_digitales"] = pd.DataFrame.from_records(registros).map(
        lambda v: "null" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))
    filas = []
    for nombre, d in crudos.items():
        for col in d.columns:
            valores = d[col].str.strip()
            encontrados = valores[valores.str.upper().isin(C.TOKENS_NULOS)]
            for valor, n in encontrados.value_counts().items():
                filas.append({"dataset": nombre, "columna": col,
                              "valor_encontrado": "(vacío)" if valor == "" else valor,
                              "conteo": int(n)})
    return pd.DataFrame(filas, columns=["dataset", "columna", "valor_encontrado", "conteo"])


def cargar_crudo_seguro() -> dict[str, pd.DataFrame]:
    cat = pd.read_csv(C.ARCH_CATALOGO, encoding="utf-8", na_values=C.NA_VALUES,
                      dtype={c: "string" for c in C.COLUMNAS_TEXTO["catalogo_cuentas"]})
    atm = pd.read_csv(C.ARCH_ATM, encoding="utf-8", na_values=C.NA_VALUES,
                      dtype={c: "string" for c in C.COLUMNAS_TEXTO["transacciones_atm"]})
    with open(C.ARCH_TRANSFER, encoding="utf-8") as fh:
        registros = json.load(fh)
    tr = pd.DataFrame.from_records(registros)
    for col in tr.columns:
        if tr[col].dtype == object or pd.api.types.is_string_dtype(tr[col]):
            tr[col] = tr[col].astype(object)
            mask = pd.Series([isinstance(v, str) and v.strip().upper() in C.TOKENS_NULOS
                              for v in tr[col].tolist()], index=tr.index)
            tr.loc[mask, col] = None
    for c in C.COLUMNAS_TEXTO["transferencias_digitales"]:
        if c in tr.columns:
            tr[c] = tr[c].astype("string")
    return {"catalogo_cuentas": cat, "transacciones_atm": atm,
            "transferencias_digitales": tr}


def _es_nulo_oculto(v) -> bool:
    return isinstance(v, str) and v.strip().upper() in C.TOKENS_NULOS


def _contar_ocultos(serie: pd.Series) -> int:
    return sum(_es_nulo_oculto(v) for v in serie.tolist())


def _tipos_python(serie: pd.Series) -> str:
    tipos = serie.dropna().map(lambda v: type(v).__name__).value_counts()
    return ", ".join(f"{t}:{n}" for t, n in tipos.items())


def perfil_columnas(df: pd.DataFrame, nombre: str) -> pd.DataFrame:
    filas = []
    n = len(df)
    for col in df.columns:
        s = df[col]
        try:
            nulos = int(s.isna().sum())
            ocultos = _contar_ocultos(s)
            total_aus = nulos + ocultos
            n_unicos = int(s.nunique(dropna=True))
            ejemplo = s.dropna().astype(str).head(3).tolist()
            filas.append({
                "dataset": nombre, "columna": col,
                "dtype_inferido": str(s.dtype), "tipos_python": _tipos_python(s),
                "n_filas": n, "nulos_explicitos": nulos, "nulos_ocultos": ocultos,
                "total_ausentes": total_aus,
                "pct_nulos": round(100 * total_aus / n, 2) if n else 0.0,
                "pct_completitud": round(100 * (n - total_aus) / n, 2) if n else 0.0,
                "n_unicos": n_unicos, "pct_unicidad": round(100 * n_unicos / n, 2) if n else 0.0,
                "ejemplo_valores": " | ".join(ejemplo),
            })
        except Exception as exc:
            filas.append({"dataset": nombre, "columna": col, "dtype_inferido": f"ERROR: {exc}"})
    return pd.DataFrame(filas)


def resumen_dataset(df: pd.DataFrame, nombre: str, llave: str | None) -> dict:
    n, m = df.shape
    try:
        aus = int(df.isna().sum().sum() + sum(_contar_ocultos(df[c]) for c in df.columns))
    except Exception:
        aus = int(df.isna().sum().sum())
    try:
        dup_exactos = int(df.duplicated().sum())
    except TypeError:
        dup_exactos = int(df.astype(str).duplicated().sum())
    except Exception as exc:
        dup_exactos = f"ERROR: {exc}"
    dup_llave = int(df[llave].duplicated().sum()) if llave and llave in df else None
    return {
        "dataset": nombre, "filas": n, "columnas": m, "celdas": n * m,
        "celdas_ausentes": aus,
        "completitud_global_pct": round(100 * (1 - aus / (n * m)), 2) if n * m else 0,
        "duplicados_exactos": dup_exactos,
        "pct_duplicados_exactos": round(100 * dup_exactos / n, 2) if n and isinstance(dup_exactos, int) else 0,
        "llave": llave, "duplicados_por_llave": dup_llave,
    }


def perfil_completo(dfs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = pd.concat([perfil_columnas(d, k) for k, d in dfs.items()], ignore_index=True)
    res = pd.DataFrame([resumen_dataset(d, k, C.LLAVES.get(k)) for k, d in dfs.items()])
    return cols, res


def ranking_completitud(perfil_cols: pd.DataFrame, n_criticas: int = 3) -> pd.DataFrame:
    r = perfil_cols.sort_values(["pct_completitud", "dataset", "columna"]).reset_index(drop=True)
    r = r[["dataset", "columna", "total_ausentes", "pct_nulos", "pct_completitud"]].copy()
    criticas = r[r["total_ausentes"] > 0].head(n_criticas).index
    r["critica"] = np.where(r.index.isin(criticas), "SÍ", "")
    return r


def comparar_tipos(ingenuo: dict, seguro: dict) -> pd.DataFrame:
    filas = []
    for k in ingenuo:
        for col in ingenuo[k].columns:
            filas.append({"dataset": k, "columna": col,
                          "dtype_carga_por_defecto": str(ingenuo[k][col].dtype),
                          "dtype_carga_segura": str(seguro[k][col].dtype)})
    return pd.DataFrame(filas)


RE_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")


def _clabe_digito_ok(c: str) -> bool:
    pesos = [3, 7, 1] * 6
    s = sum((int(c[i]) * pesos[i]) % 10 for i in range(17))
    return (10 - s % 10) % 10 == int(c[17])


def _fuera_iqr(s: pd.Series) -> int:
    s = pd.to_numeric(s, errors="coerce").dropna()
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    return int(((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum())


def hallazgos_validez(dfs: dict[str, pd.DataFrame],
                      ingenuo: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    cat = dfs["catalogo_cuentas"]
    atm = dfs["transacciones_atm"]
    tr = dfs["transferencias_digitales"]
    n_atm, n_tr = len(atm), len(tr)
    cuentas = set(cat["id_cuenta"].dropna())
    H: list[dict] = []

    def add(dataset, columna, hallazgo, fn: Callable[[], int], total, fase, accion):
        try:
            n = int(fn())
        except Exception as exc:
            n, hallazgo = -1, f"{hallazgo} (ERROR: {exc})"
        H.append({"dataset": dataset, "columna": columna, "hallazgo": hallazgo,
                  "registros_afectados": n,
                  "pct": round(100 * n / total, 2) if total and n >= 0 else None,
                  "fase_responsable": fase, "accion_propuesta": accion})

    monto = pd.to_numeric(atm["monto_mxn"], errors="coerce")
    tipo = atm["tipo_operacion"].astype(str).str.strip().str.upper()

    add("transacciones_atm", "(fila completa)", "Duplicados exactos = reintentos de cajero",
        lambda: atm.astype(str).duplicated().sum(), n_atm, "Fase 2 (Ing. 1)", "Eliminar duplicados")
    patrones = atm["fecha_hora"].astype(str).str.replace(r"\d", "9", regex=True)
    add("transacciones_atm", "fecha_hora", f"Fechas en {patrones.nunique()} formatos distintos",
        lambda: (patrones != "9999-99-99 99:99:99").sum(), n_atm, "Fase 4 (Ing. 2)", "Homologar ISO")
    add("transferencias_digitales", "timestamp", "timestamp mezcla ISO con epoch",
        lambda: tr["timestamp"].map(lambda v: isinstance(v, (int, np.integer))).sum(),
        n_tr, "Fase 4 (Ing. 2)", "Convertir epoch")
    add("transacciones_atm", "resultado", "Etiquetas con mayúsculas/minúsculas inconsistentes",
        lambda: (atm["resultado"].astype(str) != atm["resultado"].astype(str).str.upper()).sum(),
        n_atm, "Fase 2 (Ing. 1)", "strip() + upper()")
    add("transferencias_digitales", "status", "Etiquetas con mayúsculas/minúsculas inconsistentes",
        lambda: (tr["status"].astype(str) != tr["status"].astype(str).str.upper()).sum(),
        n_tr, "Fase 2 (Ing. 1)", "strip() + upper()")
    add("transacciones_atm", "monto_mxn", "monto = 0 en CONSULTA_SALDO (VÁLIDO)",
        lambda: ((monto == 0) & (tipo == "CONSULTA_SALDO")).sum(), n_atm, "Fase 3 (Ing. 1)", "NO eliminar")
    add("transacciones_atm", "monto_mxn", "monto <= 0 en operaciones monetarias",
        lambda: ((monto <= 0) & (tipo != "CONSULTA_SALDO")).sum(), n_atm, "Fase 3 (Ing. 1)", "Eliminar")
    add("transacciones_atm", "monto_mxn", "Montos negativos", lambda: (monto < 0).sum(), n_atm, "Fase 3 (Ing. 1)", "Eliminar")
    add("transacciones_atm", "monto_mxn", "Outliers por IQR×1.5", lambda: _fuera_iqr(monto[monto > 0]), n_atm, "Fase 3 (Ing. 1)", "Capping")
    amt = pd.to_numeric(tr["amount"], errors="coerce")
    def _fuera_z(s, umbral=3):
        s = pd.to_numeric(s, errors="coerce").dropna()
        z = (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) else s * 0
        return int((z.abs() > umbral).sum())
    add("transacciones_atm", "monto_mxn", "Outliers por Z-score", lambda: _fuera_z(monto[monto > 0]), n_atm, "Fase 3 (Ing. 1)", "Comparar")
    add("transferencias_digitales", "amount", "Outliers por Z-score", lambda: _fuera_z(amt), n_tr, "Fase 3 (Ing. 1)", "Comparar")
    add("transferencias_digitales", "amount", "Montos <= 0", lambda: (amt <= 0).sum(), n_tr, "Fase 3 (Ing. 1)", "Eliminar")
    add("transferencias_digitales", "amount", "Outliers por IQR", lambda: _fuera_iqr(amt), n_tr, "Fase 3 (Ing. 1)", "Capping")
    add("transferencias_digitales", "currency", "Importes en USD", lambda: (tr["currency"].astype(str).str.upper() == "USD").sum(), n_tr, "Fase 4 (Ing. 2)", "Convertir MXN")
    com = pd.to_numeric(atm["comision_aplicada"], errors="coerce")
    add("transacciones_atm", "comision_aplicada", "Comisión = 0.0", lambda: (com == 0).sum(), n_atm, "Fase 2 (Ing. 1)", "Conservar")
    add("transacciones_atm", "id_cuenta", "Cuentas huérfanas", lambda: (~atm["id_cuenta"].isin(cuentas)).sum(), n_atm, "Fase 4 (Ing. 2)", "Cuarentena")
    add("transferencias_digitales", "account_id", "Cuentas huérfanas", lambda: (~tr["account_id"].isin(cuentas)).sum(), n_tr, "Fase 4 (Ing. 2)", "Cuarentena")
    clabe = tr["beneficiary_clabe"].astype("string")
    add("transferencias_digitales", "beneficiary_clabe", "CLABE != 18 dígitos", lambda: (~clabe.str.fullmatch(r"\d{18}").fillna(False)).sum(), n_tr, "Fase 6 (Ing. 3)", "Cuarentena")
    if ingenuo is not None:
        add("transferencias_digitales", "beneficiary_clabe", "CLABE convertida a int64 pierde cero inicial",
            lambda: (ingenuo["transferencias_digitales"]["beneficiary_clabe"].astype(str).str.len() == 17).sum(), n_tr, "Fase 1 (Ing. 1)", "Carga segura")
    em = tr["notification_email"]
    add("transferencias_digitales", "notification_email", "Nulos ocultos (vacíos)",
        lambda: _contar_ocultos(ingenuo["transferencias_digitales"]["notification_email"] if ingenuo is not None else em), n_tr, "Fase 1-2 (Ing. 1)", "Convertir a NaN")
    add("transferencias_digitales", "notification_email", "Correo inválido",
        lambda: (em.notna() & ~em.map(_es_nulo_oculto).astype(bool) & ~em.astype(str).str.match(RE_EMAIL)).sum(), n_tr, "Fase 6 (Ing. 3)", "Cuarentena")
    return pd.DataFrame(H)


# ==========================================================================
# 2. FASE 2: IMPUTACIÓN Y PROCESAMIENTO (fase2_imputacion.py)
# ==========================================================================
def normalizar_nulos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object or pd.api.types.is_string_dtype(df[col]):
            mask = pd.Series([isinstance(v, str) and v.strip().upper() in C.TOKENS_NULOS
                              for v in df[col].tolist()], index=df.index)
            if mask.any():
                df[col] = df[col].astype(object)
                df.loc[mask, col] = np.nan
    return df


def normalizar_etiquetas(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columnas:
        if col in df:
            df[col] = pd.Series([v.strip().upper() if isinstance(v, str) else v
                                 for v in df[col].tolist()], index=df.index, dtype=object)
    return df


def agregar_obs(df: pd.DataFrame, mask: pd.Series, texto: str) -> None:
    if "obs_calidad" not in df:
        df["obs_calidad"] = ""
    df.loc[mask, "obs_calidad"] = df.loc[mask, "obs_calidad"].map(
        lambda s: f"{s};{texto}" if s else texto)


def coercionar_numerico(df: pd.DataFrame, col: str) -> pd.DataFrame:
    df = df.copy()
    original = df[col]
    num = pd.to_numeric(original, errors="coerce")
    corrupto = original.notna() & num.isna()
    df[col] = num.astype(float)
    if corrupto.any():
        agregar_obs(df, corrupto, f"{col.upper()}_NO_NUMERICO")
    df[f"_{col}_corrupto"] = corrupto
    return df


def eliminar_duplicados_exactos(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    try:
        mask = df.duplicated(keep="first")
    except TypeError:
        mask = df.astype(str).duplicated(keep="first")
    return df.loc[~mask].reset_index(drop=True), df.loc[mask].copy()


def _chi2_permutacion(indicador: np.ndarray, grupo: pd.Series,
                      n_perm: int, rng: np.random.Generator) -> tuple[float, float]:
    codigos, _ = pd.factorize(pd.Series(grupo).astype(str).fillna("NA"))
    k = codigos.max() + 1
    ind = np.asarray(indicador, dtype=bool)
    n_grupo = np.bincount(codigos, minlength=k).astype(float)
    p_nulo = ind.mean()
    if k < 2 or p_nulo in (0.0, 1.0):
        return 0.0, 1.0
    esperado_1 = n_grupo * p_nulo
    esperado_0 = n_grupo * (1 - p_nulo)

    def stat(v):
        o1 = np.bincount(codigos[v], minlength=k)
        o0 = n_grupo - o1
        return (((o1 - esperado_1) ** 2) / esperado_1 + ((o0 - esperado_0) ** 2) / esperado_0).sum()

    obs = stat(ind)
    mayores = sum(stat(rng.permutation(ind)) >= obs - 1e-12 for _ in range(n_perm))
    return float(obs), (mayores + 1) / (n_perm + 1)


def clasificar_faltante(df: pd.DataFrame, col: str, dataset: str,
                        categoricas: list[str], numericas: list[str],
                        filtro: pd.Series | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(C.SEMILLA)
    d = df if filtro is None else df.loc[filtro]
    falta = d[col].isna()
    ind = falta.to_numpy()
    n_nulos = int(ind.sum())
    if n_nulos == 0:
        return pd.DataFrame([{"dataset": dataset, "variable_con_nulos": col,
                              "n_nulos": 0, "conclusion": "SIN NULOS"}])
    filas = []
    base = {"dataset": dataset, "variable_con_nulos": col, "n_nulos": n_nulos,
            "pct_nulos": round(100 * n_nulos / len(d), 2), "n_evaluado": len(d)}
    for g in categoricas:
        if g == col or g not in d:
            continue
        try:
            grupo = d[g].astype(str)
            tasa = (falta.groupby(grupo).mean() * 100).round(1)
            tabla = pd.crosstab(falta, grupo)
            chi2, p_clasica, _, esperadas = stats.chi2_contingency(tabla, correction=False)
            esp_min = float(esperadas.min())
            _, p_perm = _chi2_permutacion(ind, grupo, C.N_PERMUTACIONES, rng)
            usar_perm = esp_min < 5
            filas.append({**base, "variable_explicativa": g, "tipo": "categórica",
                          "evidencia_sesion22": "; ".join(f"{k}={v}%" for k, v in tasa.items()),
                          "brecha_pp": round(float(tasa.max() - tasa.min()), 1),
                          "prueba": "Chi²", "estadistico": round(float(chi2), 3),
                          "frec_esperada_min": round(esp_min, 2),
                          "p_valor": round(float(p_perm if usar_perm else p_clasica), 4)})
        except Exception as exc:
            filas.append({**base, "variable_explicativa": g, "prueba": f"ERROR: {exc}"})
    for g in numericas:
        if g == col or g not in d:
            continue
        try:
            x = pd.to_numeric(d[g], errors="coerce")
            con, sin = x[~ind].dropna(), x[ind].dropna()
            u, p = stats.mannwhitneyu(sin, con) if len(con) and len(sin) else (np.nan, np.nan)
            filas.append({**base, "variable_explicativa": g, "tipo": "numérica",
                          "prueba": "Mann-Whitney U", "estadistico": round(float(u), 3),
                          "p_valor": round(float(p), 4)})
        except Exception as exc:
            filas.append({**base, "variable_explicativa": g, "prueba": f"ERROR: {exc}"})
    res = pd.DataFrame(filas)
    sig = res["p_valor"] < C.ALFA
    res["significativo"] = np.where(sig, "SÍ", "no")
    if sig.any():
        res["conclusion"] = "MAR (depende de: " + ", ".join(res.loc[sig, "variable_explicativa"]) + ")"
    else:
        res["conclusion"] = "MCAR"
    return res


def _bitacora(df, mask, id_col, col, valores, metodo, dataset, grupo_col=None):
    return pd.DataFrame({
        "dataset": dataset,
        "id_registro": df.loc[mask, id_col].values,
        "columna": col,
        "valor_imputado": np.asarray(valores),
        "metodo": metodo,
        "grupo": df.loc[mask, grupo_col].values if grupo_col else "",
    })


def recalcular_monto_consulta(df: pd.DataFrame, dataset="transacciones_atm"):
    df = df.copy()
    mask = df["monto_mxn"].isna() & (df["tipo_operacion"] == "CONSULTA_SALDO") & ~df["_monto_mxn_corrupto"]
    df.loc[mask, "monto_mxn"] = 0.0
    df.loc[mask, "monto_mxn_imputado"] = True
    log = _bitacora(df, mask, "id_transaccion", "monto_mxn", np.zeros(mask.sum()),
                    "RECALCULO: CONSULTA_SALDO => 0", dataset, "tipo_operacion")
    return df, log


def imputar_mediana_por_grupo(df: pd.DataFrame, col: str, grupo: str, id_col: str,
                              dataset: str, solo_positivos: bool = True,
                              excluir: pd.Series | None = None):
    df = df.copy()
    flag = f"{col}_imputado"
    if flag not in df:
        df[flag] = False
    validos = df[col].notna() & ((df[col] > 0) if solo_positivos else True)
    medianas = df.loc[validos].groupby(grupo)[col].median()
    global_ = df.loc[validos, col].median()
    corrupto = df.get(f"_{col}_corrupto", pd.Series(False, index=df.index))
    mask = df[col].isna() & ~corrupto
    if excluir is not None:
        mask &= ~excluir
    valores = df.loc[mask, grupo].map(medianas).fillna(global_)
    df.loc[mask, col] = valores
    df.loc[mask, flag] = True
    log = _bitacora(df, mask, id_col, col, valores.values,
                    f"MEDIANA por {grupo}", dataset, grupo)
    return df, log, medianas.rename("mediana").reset_index()


def imputar_categorica(df: pd.DataFrame, col: str, etiqueta: str, id_col: str, dataset: str):
    df = df.copy()
    flag = f"{col}_imputado"
    mask = df[col].isna()
    df[col] = df[col].astype(object)
    df.loc[mask, col] = etiqueta
    df[flag] = mask
    log = _bitacora(df, mask, id_col, col, [etiqueta] * int(mask.sum()),
                    f"ETIQUETA CONTROLADA '{etiqueta}'", dataset)
    return df, log


def procesar_atm(df: pd.DataFrame):
    ds = "transacciones_atm"
    df = normalizar_nulos(df)
    df = normalizar_etiquetas(df, ["tipo_operacion", "resultado", "id_cajero", "id_cuenta"])
    df, dups = eliminar_duplicados_exactos(df)
    df = coercionar_numerico(df, "monto_mxn")
    df = coercionar_numerico(df, "comision_aplicada")
    df["monto_mxn_imputado"] = False

    monetarias = df["tipo_operacion"] != "CONSULTA_SALDO"
    pruebas = pd.concat([
        clasificar_faltante(df, "monto_mxn", ds, ["tipo_operacion", "resultado", "id_cajero"],
                            ["comision_aplicada"], filtro=monetarias),
        clasificar_faltante(df, "id_cajero", ds, ["tipo_operacion", "resultado"],
                            ["monto_mxn", "comision_aplicada"]),
        clasificar_faltante(df, "comision_aplicada", ds, ["tipo_operacion", "resultado"], ["monto_mxn"]),
    ], ignore_index=True)

    logs = []
    df, l = recalcular_monto_consulta(df); logs.append(l)
    df, l, med_monto = imputar_mediana_por_grupo(df, "monto_mxn", "tipo_operacion", "id_transaccion", ds)
    logs.append(l)
    df, l, _ = imputar_mediana_por_grupo(df, "comision_aplicada", "tipo_operacion", "id_transaccion", ds, solo_positivos=False)
    logs.append(l)
    df, l = imputar_categorica(df, "id_cajero", C.ETIQUETA_CAJERO, "id_transaccion", ds)
    logs.append(l)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    if "obs_calidad" not in df:
        df["obs_calidad"] = ""
    return df, dups, pruebas, pd.concat(logs, ignore_index=True), med_monto


def procesar_transferencias(df: pd.DataFrame):
    ds = "transferencias_digitales"
    df = normalizar_nulos(df)
    df = normalizar_etiquetas(df, ["status", "currency", "platform", "account_id"])
    df, dups = eliminar_duplicados_exactos(df)
    df = coercionar_numerico(df, "amount")

    pruebas = pd.concat([
        clasificar_faltante(df, "notification_email", ds, ["status", "currency", "concept", "platform"], ["amount"]),
        clasificar_faltante(df, "amount", ds, ["currency", "status", "platform"], []),
    ], ignore_index=True)

    logs = []
    df, l, med_amt = imputar_mediana_por_grupo(df, "amount", "currency", "transfer_id", ds)
    logs.append(l)
    df, l = imputar_categorica(df, "notification_email", C.ETIQUETA_EMAIL, "transfer_id", ds)
    logs.append(l)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    if "obs_calidad" not in df:
        df["obs_calidad"] = ""
    return df, dups, pruebas, pd.concat(logs, ignore_index=True), med_amt


def estadisticos_antes_despues(antes: pd.Series, despues: pd.Series, nombre: str) -> pd.DataFrame:
    a = pd.to_numeric(antes, errors="coerce")
    d = pd.to_numeric(despues, errors="coerce")
    filas = []
    for etapa, s in [("antes (crudo)", a), ("después (Fase 2)", d)]:
        filas.append({"variable": nombre, "etapa": etapa, "n_no_nulos": int(s.notna().sum()),
                      "nulos": int(s.isna().sum()), "media": round(s.mean(), 2),
                      "mediana": round(s.median(), 2), "desv_std": round(s.std(), 2),
                      "sesgo_skew": round(s.skew(), 2), "min": s.min(), "max": s.max()})
    return pd.DataFrame(filas)


# ==========================================================================
# 3. FASES DE INTEGRACIÓN Y TRANSFORMACIÓN DEL INGENIERO/A 2
# ==========================================================================
# Integracion compartida para mantener el mismo contrato en ambos ejecutores.
if __package__:
    from .Transformación_E_Integración import (
        cargar_datos_fuentes as cargar_datos_fuentes_ing2,
        homologar_fechas_y_monedas, imputar_faltantes as imputar_faltantes_ing2,
        tratar_outliers_iqr, cruce_y_detectar_huerfanos,
        transformacion_discretizacion_escalado,
    )
    from .pipeline_ing3 import ejecutar_fases_5_a_7
else:
    sys.path.insert(0, str(C.RAIZ))
    from src.Transformación_E_Integración import (
        cargar_datos_fuentes as cargar_datos_fuentes_ing2,
        homologar_fechas_y_monedas, imputar_faltantes as imputar_faltantes_ing2,
        tratar_outliers_iqr, cruce_y_detectar_huerfanos,
        transformacion_discretizacion_escalado,
    )
    from src.pipeline_ing3 import ejecutar_fases_5_a_7


# ==========================================
# 4. FIGURAS Y DASHBOARD DEL INGENIERO/A 2
# ==========================================
AZUL, VERDE, ROJO, NARANJA, GRIS, TINTA, TINTA2 = "#2a78d6", "#2eb872", "#e74c3c", "#eb6834", "#8a8984", "#0b0b0b", "#52514e"
plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9.5,
    "axes.edgecolor": "#c9c8c2", "axes.labelcolor": TINTA2, "xtick.color": TINTA2,
    "ytick.color": TINTA2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": TINTA,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": "#ebeae6", "grid.linewidth": 0.8,
})


def completitud_antes_despues(comp: pd.DataFrame, ruta):
    d = comp[(comp["pct_nulos_antes"] > 0) | (comp["pct_nulos_despues"] > 0)].copy()
    d["etq"] = d["dataset"].str.replace("transacciones_", "").str.replace("transferencias_", "") + " · " + d["columna"]
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(7.2, 0.55 * len(d) + 1.4))
    ax.barh(y + 0.2, d["pct_nulos_antes"], 0.36, color=AZUL, label="Antes (crudo)")
    ax.barh(y - 0.2, d["pct_nulos_despues"], 0.36, color=NARANJA, label="Después (Fase 2)")
    for i, (a, b) in enumerate(zip(d["pct_nulos_antes"], d["pct_nulos_despues"])):
        ax.text(a + 0.15, i + 0.2, f"{a:.2f}%", va="center", fontsize=8.5, color=TINTA)
        ax.text(b + 0.15, i - 0.2, f"{b:.2f}%", va="center", fontsize=8.5, color=TINTA)
    ax.set_yticks(y, d["etq"])
    ax.invert_yaxis()
    ax.set_xlabel("% de valores nulos")
    ax.set_title("Nulos por columna: antes vs después de la Fase 2", loc="left")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout(); fig.savefig(ruta); plt.close(fig)


def distribucion_sesgada(s: pd.Series, titulo: str, xlabel: str, ruta):
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[s > 0]
    media, mediana = s.mean(), s.median()
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    bins = np.logspace(np.log10(s.min()), np.log10(s.max()), 40)
    ax.hist(s, bins=bins, color=AZUL, edgecolor="white", linewidth=1)
    ax.set_xscale("log")
    ax.axvline(mediana, color=TINTA, lw=2)
    ax.axvline(media, color=NARANJA, lw=2, ls="--")
    ymax = ax.get_ylim()[1]
    caja = dict(facecolor="white", edgecolor="none", pad=1.5, alpha=0.9)
    ax.text(mediana * 0.92, ymax * 0.93, f"mediana = {mediana:,.0f}", color=TINTA, fontsize=9, ha="right", bbox=caja)
    ax.text(media * 1.08, ymax * 0.80, f"media = {media:,.0f}", color=TINTA, fontsize=9, ha="left", bbox=caja)
    ax.set_xlabel(xlabel + " (escala log)"); ax.set_ylabel("Frecuencia")
    ax.set_title(titulo + f"   ·   sesgo (skew) = {s.skew():.1f}", loc="left")
    fig.tight_layout(); fig.savefig(ruta); plt.close(fig)


def generar_graficas_ing2(df_final, limite_superior):
    """Genera el panel dashboard optimizado con las 4 evidencias clave del Ingeniero 2"""
    C.DIR_FIGURAS_ING2.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle(
        "Evidencia Visual de Transformaciones e Integración (Ingeniero/a 2)",
        fontsize=14,
        fontweight="bold",
    )

    # 1. Tratamiento de Outliers (IQR Capping con zoom optimizado)
    ax1 = axes[0, 0]
    zoom_max = min(df_final["monto_mxn"].max(), limite_superior * 2.5)
    datos_visibles = df_final["monto_mxn"][df_final["monto_mxn"] <= zoom_max]
    datos_capped = df_final["monto_mxn_capped"][df_final["monto_mxn_capped"] <= zoom_max]

    ax1.hist(datos_visibles, bins=35, alpha=0.5, color=NARANJA, label="Original (con outliers)")
    ax1.hist(datos_capped, bins=35, alpha=0.7, color=AZUL, label="Con Capping IQR")
    ax1.axvline(
        limite_superior,
        color=ROJO,
        linestyle="--",
        linewidth=2,
        label=f"Límite Sup (${limite_superior:,.0f})",
    )
    ax1.set_title("1. Tratamiento de Outliers (Zoom en la Distribución)")
    ax1.set_xlabel("Monto en MXN")
    ax1.set_ylabel("Cantidad de Registros")
    ax1.legend(fontsize=8, loc="upper right")

    # 2. Origen de Moneda y Conversión USD a MXN
    ax2 = axes[0, 1]
    conteo_moneda = df_final["moneda"].value_counts()
    bars = ax2.bar(
        conteo_moneda.index,
        conteo_moneda.values,
        color=[AZUL, VERDE],
        width=0.5,
    )
    for bar in bars:
        yval = bar.get_height()
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            yval + 5,
            f"{yval}",
            ha="center",
            va="bottom",
            fontweight="bold",
        )
    ax2.set_title("2. Transacciones por Moneda de Origen")
    ax2.set_ylabel("Cantidad de Registros")
    ax2.set_ylim(0, max(conteo_moneda.values) * 1.15)

    # 3. Detección de Cuentas Huérfanas (Cuarentena)
    ax3 = axes[1, 0]
    huerfanos_counts = (
        df_final["es_huerfano"]
        .map({False: "Válidas (Core)", True: "Huérfanas (Cuarentena)"})
        .value_counts()
    )
    ax3.pie(
        huerfanos_counts,
        labels=huerfanos_counts.index,
        autopct="%1.1f%%",
        colors=[VERDE, ROJO],
        startangle=140,
        explode=(0, 0.1),
    )
    ax3.set_title("3. Validación de Integridad (Core Bancario)")

    # 4. Discretización Nivel de Monto
    ax4 = axes[1, 1]
    niveles = df_final["nivel_monto"].value_counts().reindex(["Bajo", "Medio", "Alto"])
    bars4 = ax4.bar(niveles.index, niveles.values, color=AZUL, width=0.5)
    for bar in bars4:
        yval = bar.get_height()
        ax4.text(
            bar.get_x() + bar.get_width() / 2,
            yval + 5,
            f"{yval}",
            ha="center",
            va="bottom",
            fontweight="bold",
        )
    ax4.set_title("4. Discretización en 3 Tramos (Nivel de Monto)")
    ax4.set_ylabel("Cantidad de Transacciones")
    ax4.set_ylim(0, max(niveles.values) * 1.15)

    fig.tight_layout()
    ruta_panel = C.DIR_FIGURAS_ING2 / "panel_transformaciones_ing2.png"
    fig.savefig(ruta_panel)
    plt.close(fig)
    print(f"   [OK] {ruta_panel.relative_to(C.RAIZ)}")


# ==========================================================================
# 5. ORQUESTADOR GENERAL (EJECUCIÓN DE TODAS LAS FASES)
# ==========================================================================
ENC = "utf-8-sig"

def _guardar(df: pd.DataFrame, nombre: str):
    ruta = C.DIR_REPORTES / nombre
    df.to_csv(ruta, index=False, encoding=ENC)
    print(f"   [OK] {ruta.relative_to(C.RAIZ)}  ({len(df)} filas)")


def ejecutar_pipeline():
    t0 = time.time()
    C.DIR_FIGURAS.mkdir(parents=True, exist_ok=True)

    print("\n=== FASE 1: DIAGNÓSTICO DE CALIDAD INICIAL ===")
    disfrazados = explorar_nulos_disfrazados()
    ingenuo = cargar_crudo_ingenuo()
    seguro = cargar_crudo_seguro()
    perfil_cols, perfil_res = perfil_completo(ingenuo)
    ranking = ranking_completitud(perfil_cols)
    _guardar(disfrazados, "f1_nulos_disfrazados.csv")
    _guardar(ranking, "f1_ranking_completitud.csv")
    tipos = comparar_tipos(ingenuo, seguro)
    hall = hallazgos_validez(seguro, ingenuo)
    _guardar(perfil_res, "f1_resumen_datasets_crudo.csv")
    _guardar(perfil_cols, "f1_perfil_columnas_crudo.csv")
    _guardar(tipos, "f1_tipos_inferidos.csv")
    _guardar(hall, "f1_hallazgos_validez.csv")
    print(perfil_res[["dataset", "filas", "completitud_global_pct", "duplicados_exactos",
                      "duplicados_por_llave"]].to_string(index=False))

    print("\n=== FASE 2: MANEJO DE FALTANTES E IMPUTACIÓN ===")
    atm, dup_atm, p_atm, log_atm, med_atm = procesar_atm(seguro["transacciones_atm"])
    tr, dup_tr, p_tr, log_tr, med_tr = procesar_transferencias(seguro["transferencias_digitales"])
    cat = normalizar_etiquetas(normalizar_nulos(seguro["catalogo_cuentas"]),
                               ["tipo_cuenta", "estado_cuenta"])

    pruebas = pd.concat([p_atm, p_tr], ignore_index=True)
    bitacora = pd.concat([log_atm, log_tr], ignore_index=True)
    duplicados = pd.concat([dup_atm.assign(dataset="transacciones_atm")], ignore_index=True)
    med_atm["dataset"], med_atm["variable"] = "transacciones_atm", "monto_mxn"
    med_tr["dataset"], med_tr["variable"] = "transferencias_digitales", "amount"
    medianas = pd.concat([med_atm.rename(columns={"tipo_operacion": "grupo"}),
                          med_tr.rename(columns={"currency": "grupo"})], ignore_index=True)

    _guardar(pruebas, "f2_pruebas_mcar_mar.csv")
    _guardar(bitacora, "f2_bitacora_imputacion.csv")
    _guardar(duplicados, "f2_duplicados_eliminados.csv")
    _guardar(medianas[["dataset", "variable", "grupo", "mediana"]], "f2_medianas_usadas.csv")

    despues = {"catalogo_cuentas": cat, "transacciones_atm": atm, "transferencias_digitales": tr}
    originales = {k: list(v.columns) for k, v in seguro.items()}
    pc_desp, pr_desp = perfil_completo({k: v[originales[k]] for k, v in despues.items()})
    _guardar(pc_desp, "f2_perfil_columnas_post.csv")

    comp = perfil_cols[["dataset", "columna", "dtype_inferido", "total_ausentes", "pct_nulos"]].merge(
        pc_desp[["dataset", "columna", "dtype_inferido", "total_ausentes", "pct_nulos"]],
        on=["dataset", "columna"], suffixes=("_antes", "_despues"))
    comp = comp.rename(columns={"total_ausentes_antes": "nulos_antes", "total_ausentes_despues": "nulos_despues"})
    comp["pct_completitud_antes"] = 100 - comp["pct_nulos_antes"]
    comp["pct_completitud_despues"] = 100 - comp["pct_nulos_despues"]
    _guardar(comp, "comparativo_columnas_antes_despues.csv")

    res = perfil_res[["dataset", "filas", "celdas_ausentes", "completitud_global_pct",
                      "duplicados_exactos", "duplicados_por_llave"]].merge(
        pr_desp[["dataset", "filas", "celdas_ausentes", "completitud_global_pct",
                 "duplicados_exactos", "duplicados_por_llave"]],
        on="dataset", suffixes=("_antes", "_despues"))
    _guardar(res, "comparativo_datasets_antes_despues.csv")

    est = pd.concat([
        estadisticos_antes_despues(seguro["transacciones_atm"]["monto_mxn"], atm["monto_mxn"], "monto_mxn (ATM)"),
        estadisticos_antes_despues(seguro["transferencias_digitales"]["amount"], tr["amount"], "amount (SPEI)"),
    ], ignore_index=True)
    _guardar(est, "comparativo_estadisticos_monto.csv")

    C.DIR_INTERIM.mkdir(parents=True, exist_ok=True)
    atm.to_csv(C.DIR_INTERIM / "transacciones_atm_fase2.csv", index=False, encoding="utf-8")
    cat.to_csv(C.DIR_INTERIM / "catalogo_cuentas_fase2.csv", index=False, encoding="utf-8")
    registros = json.loads(tr.to_json(orient="records", force_ascii=False))
    with open(C.DIR_INTERIM / "transferencias_digitales_fase2.json", "w", encoding="utf-8") as fh:
        json.dump(registros, fh, ensure_ascii=False, indent=2)

    completitud_antes_despues(comp, C.DIR_FIGURAS / "01_nulos_antes_despues.png")
    distribucion_sesgada(seguro["transacciones_atm"]["monto_mxn"], "monto_mxn ATM (> 0)", "MXN", C.DIR_FIGURAS / "04_sesgo_monto_atm.png")
    distribucion_sesgada(seguro["transferencias_digitales"]["amount"], "amount SPEI", "importe", C.DIR_FIGURAS / "05_sesgo_amount_spei.png")
    print("   [OK] reportes/ing1/figuras/*.png")

    print("\n=== FASE 3-5: INTEGRACIÓN, HOMOLOGACIÓN, IQR Y ESCALAMIENTO (INGENIERO/A 2) ===")
    path_cuentas = C.DIR_INTERIM / "catalogo_cuentas_fase2.csv"
    path_atm = C.DIR_INTERIM / "transacciones_atm_fase2.csv"
    path_json = C.DIR_INTERIM / "transferencias_digitales_fase2.json"

    df_cuentas, df_unificado = cargar_datos_fuentes_ing2(path_cuentas, path_atm, path_json)
    df_homologado = homologar_fechas_y_monedas(df_unificado)
    df_imputado = imputar_faltantes_ing2(df_homologado)
    df_sin_outliers, Q1, Q3, IQR, sup = tratar_outliers_iqr(df_imputado)
    df_cruzado = cruce_y_detectar_huerfanos(df_sin_outliers, df_cuentas)
    df_final = transformacion_discretizacion_escalado(df_cruzado)

    # Generar panel de gráficas del Ingeniero/a 2
    generar_graficas_ing2(df_final, sup)

    print("=== RESUMEN TÉCNICO DE TRANSFORMACIÓN (INGENIERO/A 2) ===")
    print(f"Total registros integrados: {len(df_unificado)}")
    print(f"Registros huérfanos detectados: {df_final['es_huerfano'].sum()} (Desviados a cuarentena)")
    print(f"Límite superior IQR para Capping de Monto: ${sup:,.2f} MXN")
    print("\nDistribución por Nivel de Monto (Discretización):\n", df_final["nivel_monto"].value_counts())

    output_file = C.RAIZ / "reportes" / "transacciones_procesadas_limpias.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(output_file, index=False, encoding=ENC)
    print(f"\n[ÉXITO] Archivo '{output_file.name}' generado correctamente en reportes/.")
    print("\n=== FASES 5-7: VALIDACION, CUARENTENA Y CARGA SQLITE (ING. 3) ===")
    resumen_ing3 = ejecutar_fases_5_a_7(
        df_cruzado, set(df_cuentas["id_cuenta"].dropna()),
        C.RAIZ / "data" / "proyecto_final.sqlite3", C.RAIZ / "reportes" / "ing3",
    )
    print(json.dumps(resumen_ing3, ensure_ascii=False, indent=2))
    print(f"\n¡Todo ejecutado con éxito de punta a punta en {time.time() - t0:.1f} s!")
    return 0


if __name__ == "__main__":
    sys.exit(ejecutar_pipeline())