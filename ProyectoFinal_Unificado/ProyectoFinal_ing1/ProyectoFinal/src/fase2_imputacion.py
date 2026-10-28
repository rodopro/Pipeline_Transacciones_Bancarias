"""
FASE 2 – MANEJO DE FALTANTES E IMPUTACIÓN
Responsable: Ingeniero/a 1 (Calidad, Nulos y Outliers)

Pasos (en este orden):
  2.0  Normalizar nulos ocultos ('' / 'N/A' / 'null' ...) a NaN y etiquetas a MAYÚSCULAS.
  2.1  Eliminar duplicados exactos (reintentos de cajero) ANTES de calcular estadísticos,
       para no sesgar la mediana con registros repetidos.
  2.2  Clasificar cada ausencia como MCAR o MAR con pruebas estadísticas.
  2.3  Recalcular campos que pueden deducirse de otras columnas (regla determinista).
  2.4  Imputar numéricas sesgadas con la MEDIANA por grupo.
  2.5  Imputar categóricas con ETIQUETAS CONTROLADAS.
  2.6  Bitácora: cada valor imputado queda registrado (id, columna, valor, método).

Reglas de diseño:
  * Las llaves e identificadores (id_cuenta, CLABE, fecha, moneda...) NUNCA se imputan:
    si faltan, el registro debe ir a cuarentena (Fase 6).
  * Un valor presente pero corrupto (ej. monto='abc') NO se imputa: se deja NaN y se
    marca en `obs_calidad` para que la validación lo mande a cuarentena. Solo se imputa
    lo que realmente estaba ausente.
  * Las funciones no lanzan excepciones por datos sucios (robustez / no crash).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import config as C

# --------------------------------------------------------------------------
# 2.0 Normalización previa
# --------------------------------------------------------------------------

def normalizar_nulos(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte nulos ocultos en NaN explícitos en columnas de texto."""
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
    """strip() + upper() en columnas categóricas ('exitosa' -> 'EXITOSA')."""
    df = df.copy()
    for col in columnas:
        if col in df:
            df[col] = pd.Series([v.strip().upper() if isinstance(v, str) else v
                                 for v in df[col].tolist()], index=df.index, dtype=object)
    return df


def agregar_obs(df: pd.DataFrame, mask: pd.Series, texto: str) -> None:
    """Agrega una observación de calidad (trazabilidad) a las filas indicadas."""
    if "obs_calidad" not in df:
        df["obs_calidad"] = ""
    df.loc[mask, "obs_calidad"] = df.loc[mask, "obs_calidad"].map(
        lambda s: f"{s};{texto}" if s else texto)


def coercionar_numerico(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Convierte a numérico. Distingue 'ausente' (imputable) de 'corrupto' (cuarentena)."""
    df = df.copy()
    original = df[col]
    num = pd.to_numeric(original, errors="coerce")
    corrupto = original.notna() & num.isna()
    df[col] = num.astype(float)
    if corrupto.any():
        agregar_obs(df, corrupto, f"{col.upper()}_NO_NUMERICO")
    df[f"_{col}_corrupto"] = corrupto
    return df


# --------------------------------------------------------------------------
# 2.1 Duplicados exactos (reintentos)
# --------------------------------------------------------------------------

def eliminar_duplicados_exactos(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Elimina filas 100% idénticas; conserva la primera. Devuelve (limpio, eliminados)."""
    try:
        mask = df.duplicated(keep="first")          # = df.drop_duplicates() de la sesión 26
    except TypeError:                               # celdas no hashables en lotes corruptos
        mask = df.astype(str).duplicated(keep="first")
    return df.loc[~mask].reset_index(drop=True), df.loc[mask].copy()


# --------------------------------------------------------------------------
# 2.2 Clasificación MCAR / MAR
# --------------------------------------------------------------------------

def _chi2_permutacion(indicador: np.ndarray, grupo: pd.Series,
                      n_perm: int, rng: np.random.Generator) -> tuple[float, float]:
    """Chi-cuadrada con p-valor por permutación (válida aunque haya frecuencias
    esperadas < 5, que es el caso con pocos nulos)."""
    codigos, _ = pd.factorize(pd.Series(grupo).astype(str).fillna("NA"))
    k = codigos.max() + 1
    ind = np.asarray(indicador, dtype=bool)
    n_grupo = np.bincount(codigos, minlength=k).astype(float)
    p_nulo = ind.mean()
    if k < 2 or p_nulo in (0.0, 1.0):
        return 0.0, 1.0
    esperado_1 = n_grupo * p_nulo
    esperado_0 = n_grupo * (1 - p_nulo)

    def stat(v):  # chi² de Pearson vectorizado (tabla 2 x k)
        o1 = np.bincount(codigos[v], minlength=k)
        o0 = n_grupo - o1
        return (((o1 - esperado_1) ** 2) / esperado_1 + ((o0 - esperado_0) ** 2) / esperado_0).sum()

    obs = stat(ind)
    mayores = sum(stat(rng.permutation(ind)) >= obs - 1e-12 for _ in range(n_perm))
    return float(obs), (mayores + 1) / (n_perm + 1)


def clasificar_faltante(df: pd.DataFrame, col: str, dataset: str,
                        categoricas: list[str], numericas: list[str],
                        filtro: pd.Series | None = None) -> pd.DataFrame:
    """Evidencia para decidir si la ausencia de `col` es MCAR o MAR.

    Misma idea que la actividad de la sesión 22: se crea el indicador
    "falta = 1 / no falta = 0" y se revisa si se relaciona con OTRA columna observada.

      a) Categóricas: % de nulos de `col` en cada categoría (groupby) + su brecha
         (máx - mín, en puntos porcentuales) y una prueba chi² de independencia
         (scipy.stats.chi2_contingency) para saber si esa brecha es real o azar.
         Si alguna frecuencia esperada es < 5, la chi² clásica no es confiable y se
         usa el p-valor por permutación.
      b) Numéricas: media y mediana de la otra variable cuando `col` falta vs cuando
         no falta + prueba Mann-Whitney U (no supone normalidad).

    Regla: si alguna prueba da p < 0.05 -> MAR respecto a esa variable; si ninguna,
    -> MCAR. MNAR no se puede probar con los datos (el valor que lo causaría es justo
    el que falta); se argumenta con conocimiento del negocio en REGLAS_DE_NEGOCIO.md.
    """
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
                          "prueba": "Chi² de independencia", "estadistico": round(float(chi2), 3),
                          "frec_esperada_min": round(esp_min, 2),
                          "p_chi2_clasica": round(float(p_clasica), 4),
                          "p_permutacion": round(float(p_perm), 4),
                          "p_valor": round(float(p_perm if usar_perm else p_clasica), 4),
                          "p_usado": "permutación (esperadas < 5)" if usar_perm else "chi² clásica"})
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
                          "evidencia_sesion22": (f"media {g}: con dato={con.mean():.2f} / sin dato={sin.mean():.2f}; "
                                                 f"mediana: con dato={con.median():.2f} / sin dato={sin.median():.2f}"),
                          "prueba": "Mann-Whitney U", "estadistico": round(float(u), 3),
                          "p_valor": round(float(p), 4), "p_usado": "Mann-Whitney"})
        except Exception as exc:
            filas.append({**base, "variable_explicativa": g, "prueba": f"ERROR: {exc}"})
    res = pd.DataFrame(filas)
    sig = res["p_valor"] < C.ALFA
    res["significativo"] = np.where(sig, "SÍ", "no")
    if sig.any():
        res["conclusion"] = "MAR (depende de: " + ", ".join(res.loc[sig, "variable_explicativa"]) + ")"
    else:
        res["conclusion"] = "MCAR (ninguna dependencia significativa)"
    return res


# --------------------------------------------------------------------------
# 2.3 – 2.5 Imputación
# --------------------------------------------------------------------------

def _bitacora(df, mask, id_col, col, valores, metodo, dataset, grupo_col=None):
    out = pd.DataFrame({
        "dataset": dataset,
        "id_registro": df.loc[mask, id_col].values,
        "columna": col,
        "valor_imputado": np.asarray(valores),
        "metodo": metodo,
        "grupo": df.loc[mask, grupo_col].values if grupo_col else "",
    })
    return out


def recalcular_monto_consulta(df: pd.DataFrame, dataset="transacciones_atm"):
    """Regla determinista: una CONSULTA_SALDO no mueve dinero -> monto_mxn = 0.
    Se recupera el dato a partir de otra columna (tipo_operacion) en lugar de
    estimarlo. Equivalente fintech de 'monto_total = cantidad * precio'."""
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
    """Imputa con la mediana de `col` dentro de cada `grupo`.

    * La mediana se calcula solo con valores válidos (> 0 si solo_positivos) para que
      ceros estructurales (consultas) o montos imposibles no la contaminen.
    * Si un grupo no tiene datos, se usa la mediana global (respaldo).
    * Agrega la columna booleana `<col>_imputado` para trazabilidad.
    """
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
    """Rellena ausentes de una categórica con una etiqueta controlada y la marca."""
    df = df.copy()
    flag = f"{col}_imputado"
    mask = df[col].isna()
    df[col] = df[col].astype(object)
    df.loc[mask, col] = etiqueta
    df[flag] = mask
    log = _bitacora(df, mask, id_col, col, [etiqueta] * int(mask.sum()),
                    f"ETIQUETA CONTROLADA '{etiqueta}'", dataset)
    return df, log


# --------------------------------------------------------------------------
# Orquestadores por fuente
# --------------------------------------------------------------------------

def procesar_atm(df: pd.DataFrame):
    """Fase 2 completa sobre transacciones_atm.csv."""
    ds = "transacciones_atm"
    df = normalizar_nulos(df)
    df = normalizar_etiquetas(df, ["tipo_operacion", "resultado", "id_cajero", "id_cuenta"])
    df, dups = eliminar_duplicados_exactos(df)
    df = coercionar_numerico(df, "monto_mxn")
    df = coercionar_numerico(df, "comision_aplicada")
    df["monto_mxn_imputado"] = False

    # Clasificación (después de deduplicar). Para monto se excluye CONSULTA_SALDO
    # porque ahí el valor es estructuralmente 0 y nunca falta (evita un falso MAR).
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
    df, l, med_monto = imputar_mediana_por_grupo(df, "monto_mxn", "tipo_operacion",
                                                 "id_transaccion", ds)
    logs.append(l)
    # comisión: hoy sin NaN; el código queda listo para lotes futuros / pruebas de estrés
    df, l, _ = imputar_mediana_por_grupo(df, "comision_aplicada", "tipo_operacion",
                                         "id_transaccion", ds, solo_positivos=False)
    logs.append(l)
    df, l = imputar_categorica(df, "id_cajero", C.ETIQUETA_CAJERO, "id_transaccion", ds)
    logs.append(l)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    if "obs_calidad" not in df:
        df["obs_calidad"] = ""
    return df, dups, pruebas, pd.concat(logs, ignore_index=True), med_monto


def procesar_transferencias(df: pd.DataFrame):
    """Fase 2 completa sobre transferencias_digitales.json."""
    ds = "transferencias_digitales"
    df = normalizar_nulos(df)
    df = normalizar_etiquetas(df, ["status", "currency", "platform", "account_id"])
    df, dups = eliminar_duplicados_exactos(df)
    df = coercionar_numerico(df, "amount")

    pruebas = pd.concat([
        clasificar_faltante(df, "notification_email", ds,
                            ["status", "currency", "concept", "platform"], ["amount"]),
        clasificar_faltante(df, "amount", ds, ["currency", "status", "platform"], []),
    ], ignore_index=True)

    logs = []
    # amount: hoy sin NaN; si llegaran nulos, mediana POR MONEDA (USD y MXN no son comparables)
    df, l, med_amt = imputar_mediana_por_grupo(df, "amount", "currency", "transfer_id", ds)
    logs.append(l)
    df, l = imputar_categorica(df, "notification_email", C.ETIQUETA_EMAIL, "transfer_id", ds)
    logs.append(l)
    df = df.drop(columns=[c for c in df.columns if c.startswith("_")])
    if "obs_calidad" not in df:
        df["obs_calidad"] = ""
    return df, dups, pruebas, pd.concat(logs, ignore_index=True), med_amt


def estadisticos_antes_despues(antes: pd.Series, despues: pd.Series, nombre: str) -> pd.DataFrame:
    """Compara la distribución de una variable antes y después de imputar.
    Una buena imputación con mediana conserva la mediana y casi no mueve la media."""
    a = pd.to_numeric(antes, errors="coerce")
    d = pd.to_numeric(despues, errors="coerce")
    filas = []
    for etapa, s in [("antes (crudo)", a), ("después (Fase 2)", d)]:
        filas.append({"variable": nombre, "etapa": etapa, "n_no_nulos": int(s.notna().sum()),
                      "nulos": int(s.isna().sum()), "media": round(s.mean(), 2),
                      "mediana": round(s.median(), 2), "desv_std": round(s.std(), 2),
                      "sesgo_skew": round(s.skew(), 2), "min": s.min(), "max": s.max()})
    return pd.DataFrame(filas)


def comparar_con_simpleimputer(atm_dedup: pd.DataFrame) -> pd.DataFrame:
    """Contraste con lo visto en la sesión 28 (sklearn SimpleImputer).

    SimpleImputer(strategy="median") usa UNA mediana global para toda la columna.
    Aquí se compara contra la mediana POR tipo_operacion que usa el pipeline, para
    justificar por qué se imputa por grupo. También se verifica que la imputación
    categórica equivale a SimpleImputer(strategy="constant", fill_value=...).
    """
    from sklearn.impute import SimpleImputer

    d = atm_dedup.copy()
    d["monto_mxn"] = pd.to_numeric(d["monto_mxn"], errors="coerce")
    monetarias = d[d["tipo_operacion"] != "CONSULTA_SALDO"]
    imp = SimpleImputer(strategy="median", add_indicator=True)
    imp.fit(monetarias.loc[monetarias["monto_mxn"] > 0, ["monto_mxn"]])
    global_ = float(imp.statistics_[0])
    filas = []
    for tipo, g in monetarias.groupby("tipo_operacion"):
        validos = g.loc[g["monto_mxn"] > 0, "monto_mxn"]
        filas.append({"tipo_operacion": tipo,
                      "nulos_a_imputar": int(g["monto_mxn"].isna().sum()),
                      "mediana_global_SimpleImputer": global_,
                      "mediana_por_grupo_pipeline": float(validos.median()),
                      "diferencia_mxn": float(validos.median() - global_),
                      "media_del_grupo": round(float(validos.mean()), 2)})
    res = pd.DataFrame(filas)
    cat = SimpleImputer(strategy="constant", fill_value=C.ETIQUETA_CAJERO)
    cajero = d["id_cajero"].astype(object).where(d["id_cajero"].notna(), np.nan)
    via_sklearn = cat.fit_transform(cajero.to_frame()).ravel()
    via_pipeline = cajero.fillna(C.ETIQUETA_CAJERO).to_numpy()
    res.attrs["categorica_equivalente"] = bool((via_sklearn == via_pipeline).all())
    return res
