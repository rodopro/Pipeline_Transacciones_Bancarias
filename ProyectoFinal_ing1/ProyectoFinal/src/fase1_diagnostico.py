"""
FASE 1 – DIAGNÓSTICO DE CALIDAD INICIAL
Responsable: Ingeniero/a 1 (Calidad, Nulos y Outliers)

Perfilado cuantitativo de los datos CRUDOS antes de cualquier transformación:
  * Completitud  -> % de nulos por columna (incluye nulos "ocultos" como '' o 'N/A')
  * Unicidad     -> duplicados exactos y duplicados por llave primaria
  * Tipos        -> dtypes inferidos por pandas + tipos Python mezclados en una columna

Además genera una lista de HALLAZGOS DE VALIDEZ que se entregan a las fases
3 a 7 (outliers, fechas, divisas, huérfanos, CLABE, correos) para que el equipo
sepa exactamente qué problemas existen y cuántos registros afectan.

Regla de robustez: ninguna función lanza excepciones hacia afuera por datos
corruptos; si una métrica no puede calcularse se reporta como 'ERROR: ...'.
"""
from __future__ import annotations

import json
import re
from typing import Callable

import numpy as np
import pandas as pd

from . import config as C

# --------------------------------------------------------------------------
# 1. INGESTA
# --------------------------------------------------------------------------

def cargar_crudo_ingenuo() -> dict[str, pd.DataFrame]:
    """Carga 'por defecto' (sin indicar tipos). Se usa SOLO para documentar
    qué tipos infiere pandas y qué se pierde (ej. ceros iniciales de la CLABE)."""
    return {
        "catalogo_cuentas": pd.read_csv(C.ARCH_CATALOGO, encoding="utf-8"),
        "transacciones_atm": pd.read_csv(C.ARCH_ATM, encoding="utf-8"),
        "transferencias_digitales": pd.read_json(C.ARCH_TRANSFER, encoding="utf-8"),
    }


def explorar_nulos_disfrazados() -> pd.DataFrame:
    """Paso 1 de la sesión 22: cargar SIN convertir nada a NaN
    (keep_default_na=False, dtype=str) para ver qué textos representan
    'no hay dato' antes de que pandas los transforme."""
    crudos = {
        "catalogo_cuentas": pd.read_csv(C.ARCH_CATALOGO, keep_default_na=False, dtype=str),
        "transacciones_atm": pd.read_csv(C.ARCH_ATM, keep_default_na=False, dtype=str),
    }
    with open(C.ARCH_TRANSFER, encoding="utf-8") as fh:
        registros = json.load(fh)
    # En JSON el nulo explícito es `null`; lo mostramos como texto para contarlo
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
    """Carga recomendada para el pipeline:
      * CSV con na_values explícitos (sesión 22) e identificadores como texto.
      * JSON leído con json.load (sin conversión automática de tipos); como
        read_json no acepta na_values, los nulos disfrazados se reemplazan después.
    """
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


# --------------------------------------------------------------------------
# 2. PERFILADO POR COLUMNA
# --------------------------------------------------------------------------

def _es_nulo_oculto(v) -> bool:
    """True si el valor es texto que representa ausencia ('', 'N/A', 'null'...)."""
    return isinstance(v, str) and v.strip().upper() in C.TOKENS_NULOS


def _contar_ocultos(serie: pd.Series) -> int:
    # Se itera sobre la lista para no depender del comportamiento de .map()
    # con valores NA, que cambia entre versiones de pandas (2.x vs 3.x).
    return sum(_es_nulo_oculto(v) for v in serie.tolist())


def _tipos_python(serie: pd.Series) -> str:
    """Devuelve los tipos Python presentes (detecta columnas con tipos mezclados,
    p. ej. timestamp como texto ISO y como entero epoch en el mismo campo)."""
    tipos = serie.dropna().map(lambda v: type(v).__name__).value_counts()
    return ", ".join(f"{t}:{n}" for t, n in tipos.items())


def perfil_columnas(df: pd.DataFrame, nombre: str) -> pd.DataFrame:
    """Perfil de completitud, unicidad y tipo para cada columna."""
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
                "dataset": nombre,
                "columna": col,
                "dtype_inferido": str(s.dtype),
                "tipos_python": _tipos_python(s),
                "n_filas": n,
                "nulos_explicitos": nulos,
                "nulos_ocultos": ocultos,
                "total_ausentes": total_aus,
                "pct_nulos": round(100 * total_aus / n, 2) if n else 0.0,
                "pct_completitud": round(100 * (n - total_aus) / n, 2) if n else 0.0,
                "n_unicos": n_unicos,
                "pct_unicidad": round(100 * n_unicos / n, 2) if n else 0.0,
                "ejemplo_valores": " | ".join(ejemplo),
            })
        except Exception as exc:  # robustez: nunca detener el perfilado
            filas.append({"dataset": nombre, "columna": col,
                          "dtype_inferido": f"ERROR: {exc}"})
    return pd.DataFrame(filas)


def resumen_dataset(df: pd.DataFrame, nombre: str, llave: str | None) -> dict:
    """Métricas globales del dataset (forma, completitud global, duplicados)."""
    n, m = df.shape
    try:
        aus = int(df.isna().sum().sum() + sum(_contar_ocultos(df[c]) for c in df.columns))
    except Exception:
        aus = int(df.isna().sum().sum())
    try:
        dup_exactos = int(df.duplicated().sum())          # igual que en clase
    except TypeError:                                    # celdas no hashables (listas/dict)
        dup_exactos = int(df.astype(str).duplicated().sum())
    except Exception as exc:
        dup_exactos = f"ERROR: {exc}"
    dup_llave = int(df[llave].duplicated().sum()) if llave and llave in df else None
    return {
        "dataset": nombre,
        "filas": n,
        "columnas": m,
        "celdas": n * m,
        "celdas_ausentes": aus,
        "completitud_global_pct": round(100 * (1 - aus / (n * m)), 2) if n * m else 0,
        "duplicados_exactos": dup_exactos,
        "pct_duplicados_exactos": round(100 * dup_exactos / n, 2) if n and isinstance(dup_exactos, int) else 0,
        "llave": llave,
        "duplicados_por_llave": dup_llave,
    }


def perfil_completo(dfs: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = pd.concat([perfil_columnas(d, k) for k, d in dfs.items()], ignore_index=True)
    res = pd.DataFrame([resumen_dataset(d, k, C.LLAVES.get(k)) for k, d in dfs.items()])
    return cols, res


def ranking_completitud(perfil_cols: pd.DataFrame, n_criticas: int = 3) -> pd.DataFrame:
    """Pasos 2-3 de la sesión 22: columnas ordenadas de MENOR a MAYOR completitud
    y marca de las `n_criticas` más críticas (las que sí tienen nulos)."""
    r = perfil_cols.sort_values(["pct_completitud", "dataset", "columna"]).reset_index(drop=True)
    r = r[["dataset", "columna", "total_ausentes", "pct_nulos", "pct_completitud"]].copy()
    criticas = r[r["total_ausentes"] > 0].head(n_criticas).index
    r["critica"] = np.where(r.index.isin(criticas), "SÍ", "")
    return r


def comparar_tipos(ingenuo: dict, seguro: dict) -> pd.DataFrame:
    """Tabla de dtypes: carga por defecto vs carga segura (evidencia de por qué
    los identificadores se leen como texto)."""
    filas = []
    for k in ingenuo:
        for col in ingenuo[k].columns:
            filas.append({"dataset": k, "columna": col,
                          "dtype_carga_por_defecto": str(ingenuo[k][col].dtype),
                          "dtype_carga_segura": str(seguro[k][col].dtype)})
    return pd.DataFrame(filas)


# --------------------------------------------------------------------------
# 3. HALLAZGOS DE VALIDEZ (se transfieren a las fases 3–7)
# --------------------------------------------------------------------------

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

    # --- Unicidad / reintentos
    add("transacciones_atm", "(fila completa)",
        "Duplicados exactos = reintentos de cajero (mismo id, fecha, monto y resultado)",
        lambda: atm.astype(str).duplicated().sum(), n_atm, "Fase 2 (Ing. 1)",
        "Eliminar duplicados exactos conservando la primera ocurrencia")
    # --- Formatos de fecha
    patrones = atm["fecha_hora"].astype(str).str.replace(r"\d", "9", regex=True)
    add("transacciones_atm", "fecha_hora",
        f"Fechas en {patrones.nunique()} formatos distintos: "
        + "; ".join(f"'{p}'={c}" for p, c in patrones.value_counts().items()),
        lambda: (patrones != "9999-99-99 99:99:99").sum(), n_atm, "Fase 4 (Ing. 2)",
        "Homologar a ISO YYYY-MM-DD (ojo: 'DD/MM/YYYY' es día primero)")
    add("transferencias_digitales", "timestamp",
        "timestamp mezcla texto ISO-8601 con zona (-06:00) y enteros epoch Unix",
        lambda: tr["timestamp"].map(lambda v: isinstance(v, (int, np.integer))).sum(),
        n_tr, "Fase 4 (Ing. 2)", "Convertir epoch a fecha local y homologar a ISO")
    # --- Inconsistencias de etiquetas
    add("transacciones_atm", "resultado",
        "Etiquetas con mayúsculas/minúsculas inconsistentes ('exitosa' vs 'EXITOSA')",
        lambda: (atm["resultado"].astype(str) != atm["resultado"].astype(str).str.upper()).sum(),
        n_atm, "Fase 2 (Ing. 1)", "strip() + upper() antes de agrupar/imputar")
    add("transferencias_digitales", "status",
        "Etiquetas con mayúsculas/minúsculas inconsistentes ('liquidada' vs 'LIQUIDADA')",
        lambda: (tr["status"].astype(str) != tr["status"].astype(str).str.upper()).sum(),
        n_tr, "Fase 2 (Ing. 1)", "strip() + upper()")
    # --- Montos
    add("transacciones_atm", "monto_mxn",
        "monto = 0 en CONSULTA_SALDO (VÁLIDO: una consulta no mueve dinero)",
        lambda: ((monto == 0) & (tipo == "CONSULTA_SALDO")).sum(), n_atm,
        "Fase 3 (Ing. 1)", "NO eliminar: excluir CONSULTA_SALDO de la regla 'monto <= 0'")
    add("transacciones_atm", "monto_mxn",
        "monto <= 0 en operaciones monetarias (imposible)",
        lambda: ((monto <= 0) & (tipo != "CONSULTA_SALDO")).sum(), n_atm,
        "Fase 3 (Ing. 1)", "Eliminar / cuarentena")
    add("transacciones_atm", "monto_mxn", "Montos negativos",
        lambda: (monto < 0).sum(), n_atm, "Fase 3 (Ing. 1)", "Eliminar / cuarentena")
    add("transacciones_atm", "monto_mxn",
        "Outliers por IQR×1.5 (sobre montos > 0); máximo = "
        f"{monto.max():,.0f} MXN en un ATM",
        lambda: _fuera_iqr(monto[monto > 0]), n_atm, "Fase 3 (Ing. 1)", "Capping/Winsorizing")
    amt = pd.to_numeric(tr["amount"], errors="coerce")
    # Comparación IQR vs Z-score (actividad 3.1.2): con datos tan sesgados la media y
    # la desviación estándar se inflan por los propios outliers y el Z-score detecta menos.
    def _fuera_z(s, umbral=3):
        s = pd.to_numeric(s, errors="coerce").dropna()
        z = (s - s.mean()) / s.std(ddof=0) if s.std(ddof=0) else s * 0
        return int((z.abs() > umbral).sum())
    add("transacciones_atm", "monto_mxn", "Outliers por Z-score |z| > 3 (sobre montos > 0)",
        lambda: _fuera_z(monto[monto > 0]), n_atm, "Fase 3 (Ing. 1)",
        "Comparar con IQR; se prefiere IQR por el sesgo")
    add("transferencias_digitales", "amount", "Outliers por Z-score |z| > 3",
        lambda: _fuera_z(amt), n_tr, "Fase 3 (Ing. 1)",
        "Comparar con IQR; se prefiere IQR por el sesgo")
    add("transferencias_digitales", "amount", "Montos <= 0",
        lambda: (amt <= 0).sum(), n_tr, "Fase 3 (Ing. 1)", "Eliminar / cuarentena")
    add("transferencias_digitales", "amount",
        f"Outliers por IQR×1.5; máximo = {amt.max():,.0f}",
        lambda: _fuera_iqr(amt), n_tr, "Fase 3 (Ing. 1)", "Capping/Winsorizing")
    add("transferencias_digitales", "currency", "Importes en USD (requieren conversión)",
        lambda: (tr["currency"].astype(str).str.upper() == "USD").sum(), n_tr,
        "Fase 4 (Ing. 2)", "Convertir a MXN @ 19.50")
    # --- Comisiones
    com = pd.to_numeric(atm["comision_aplicada"], errors="coerce")
    add("transacciones_atm", "comision_aplicada",
        "Comisión = 0.0 (no es NaN; valor de negocio válido = exención)",
        lambda: (com == 0).sum(), n_atm, "Fase 2 (Ing. 1)", "Conservar; documentar en reglas")
    add("transacciones_atm", "comision_aplicada",
        "Comisión > 0 cobrada en operación con FALLO_CONEXION (anomalía de negocio)",
        lambda: ((com > 0) & (atm["resultado"].astype(str).str.upper() == "FALLO_CONEXION")).sum(),
        n_atm, "Fase 6 (Ing. 3)", "Regla de negocio a validar/decidir en equipo")
    # --- Huérfanos
    add("transacciones_atm", "id_cuenta", "Cuentas huérfanas (no existen en catalogo_cuentas)",
        lambda: (~atm["id_cuenta"].isin(cuentas)).sum(), n_atm, "Fase 4 (Ing. 2)",
        "Marcar y desviar a cuarentena")
    add("transferencias_digitales", "account_id", "Cuentas huérfanas (no existen en catalogo_cuentas)",
        lambda: (~tr["account_id"].isin(cuentas)).sum(), n_tr, "Fase 4 (Ing. 2)",
        "Marcar y desviar a cuarentena")
    inactivas = set(cat.loc[cat["estado_cuenta"] != "ACTIVA", "id_cuenta"])
    add("transacciones_atm", "id_cuenta", "Operaciones de cuentas BLOQUEADA/SUSPENDIDA",
        lambda: atm["id_cuenta"].isin(inactivas).sum(), n_atm, "Fase 6 (Ing. 3)",
        "Decidir en equipo si es causa de cuarentena")
    add("transferencias_digitales", "account_id", "Transferencias de cuentas BLOQUEADA/SUSPENDIDA",
        lambda: tr["account_id"].isin(inactivas).sum(), n_tr, "Fase 6 (Ing. 3)",
        "Decidir en equipo si es causa de cuarentena")
    # --- CLABE
    clabe = tr["beneficiary_clabe"].astype("string")
    add("transferencias_digitales", "beneficiary_clabe",
        "CLABE con longitud distinta de 18 dígitos (ej. '12345')",
        lambda: (~clabe.str.fullmatch(r"\d{18}").fillna(False)).sum(), n_tr,
        "Fase 6 (Ing. 3)", "@field_validator -> cuarentena")
    if ingenuo is not None:
        add("transferencias_digitales", "beneficiary_clabe",
            "Carga por defecto la convierte a int64 y PIERDE el '0' inicial (18 -> 17 dígitos)",
            lambda: (ingenuo["transferencias_digitales"]["beneficiary_clabe"].astype(str).str.len() == 17).sum(),
            n_tr, "Fase 1 (Ing. 1)", "Leer CLABE como texto (carga segura)")
    add("transferencias_digitales", "beneficiary_clabe",
        "CLABE de 18 dígitos que NO pasa dígito verificador (informativo, datos sintéticos)",
        lambda: clabe[clabe.str.fullmatch(r"\d{18}").fillna(False)].map(lambda c: not _clabe_digito_ok(c)).sum(),
        n_tr, "Fase 6 (Ing. 3)", "Solo informativo; NO usar como regla (rechazaría ~89%)")
    # --- Correos
    em = tr["notification_email"]
    add("transferencias_digitales", "notification_email",
        "Nulos OCULTOS: correo como cadena vacía '' (no aparecen en isna())",
        lambda: _contar_ocultos(ingenuo["transferencias_digitales"]["notification_email"]
                                if ingenuo is not None else em), n_tr, "Fase 1-2 (Ing. 1)",
        "Convertir a NaN y tratar como faltante")
    add("transferencias_digitales", "notification_email",
        "Correo con formato inválido ('correo@@sinformato', 'invalido.com'); sin contar nulos ni ''",
        lambda: (em.notna() & ~em.map(_es_nulo_oculto).astype(bool)
                 & ~em.astype(str).str.match(RE_EMAIL)).sum(), n_tr,
        "Fase 6 (Ing. 3)", "@field_validator -> cuarentena")
    return pd.DataFrame(H)
