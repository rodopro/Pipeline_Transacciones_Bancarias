import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from .fase5_transformacion import transformacion_discretizacion_escalado
except ImportError:  # Ejecución directa: python src/Transformación_E_Integración.py
    from fase5_transformacion import transformacion_discretizacion_escalado

# Configuración visual para las gráficas
AZUL = "#2a78d6"
VERDE = "#2eb872"
ROJO = "#e74c3c"
NARANJA = "#eb6834"
GRIS = "#8a8984"

plt.rcParams.update({
    "figure.dpi": 130,
    "savefig.dpi": 160,
    "font.size": 9.5,
    "axes.edgecolor": "#c9c8c2",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#ebeae6",
})

# ==========================================
# CONSTANTES DE NEGOCIO Y RUTAS RELATIVAS
# ==========================================
TASA_CAMBIO_USD_MXN = 19.50

BASE_DIR = Path(__file__).resolve().parent.parent
PATH_DATA = BASE_DIR / "data"
PATH_REPORTES = BASE_DIR / "reportes"
PATH_FIGURAS = PATH_REPORTES / "figuras_ing2"

PATH_REPORTES.mkdir(parents=True, exist_ok=True)
PATH_FIGURAS.mkdir(parents=True, exist_ok=True)


def cargar_datos_fuentes(path_cuentas, path_atm, path_json):
    """Fase 4: Carga y consolidación robusta mapeando columnas reales de ATM y JSON"""
    df_cuentas = pd.read_csv(path_cuentas, dtype={"id_cuenta": str})
    df_atm = pd.read_csv(path_atm, dtype={"id_transaccion": str, "id_cuenta": str, "id_cajero": str})

    with open(path_json, "r", encoding="utf-8") as f:
        data_json = json.load(f)
    df_json = pd.DataFrame(data_json)

    # 1. Homologar columnas de ATM
    df_atm.rename(
        columns={
            "id_transaccion": "transaccion_id",
            "fecha_hora": "timestamp",
            "id_cuenta": "account_id",
            "monto_mxn": "monto_original",
        },
        inplace=True,
    )
    df_atm["moneda"] = "MXN"
    df_atm["tipo_origen"] = "ATM"
    df_atm["notification_email"] = "ANONIMO"
    df_atm["beneficiary_clabe"] = None  # No aplica a operaciones de cajero.

    # 2. Homologar columnas de Transferencias Digitales
    df_json.rename(
        columns={
            "transfer_id": "transaccion_id",
            "amount": "monto_original",
            "currency": "moneda",
        },
        inplace=True,
    )
    df_json["tipo_origen"] = "SPEI_DIGITAL"

    cols_comunes = [
        "transaccion_id",
        "timestamp",
        "account_id",
        "monto_original",
        "moneda",
        "tipo_origen",
        "notification_email",
        "beneficiary_clabe",
        "tipo_operacion",
        "comision_aplicada",
        "obs_calidad",
    ]

    for col in cols_comunes:
        if col not in df_atm.columns:
            df_atm[col] = np.nan
        if col not in df_json.columns:
            df_json[col] = np.nan

    df_unificado = pd.concat(
        [df_atm, df_json], ignore_index=True
    )
    return df_cuentas, df_unificado


def homologar_fechas_y_monedas(df):
    """Fase 4: Unificación de fechas ISO/UNIX a YYYY-MM-DD y conversión USD a MXN @ $19.50"""
    df = df.copy()

    def parse_timestamp(val):
        try:
            if pd.isna(val) or val == "":
                return pd.NaT
            if isinstance(val, bool):
                return pd.NaT
            if isinstance(val, (int, float)) or (
                isinstance(val, str) and val.isdigit()
            ):
                return pd.to_datetime(float(val), unit="s", errors="coerce", utc=True).tz_convert("America/Mexico_City")
            if isinstance(val, str) and len(val) >= 10 and val[2] == "/":
                return pd.to_datetime(val, dayfirst=True, errors="coerce")
            return pd.to_datetime(val, errors="coerce")
        except Exception:
            return pd.NaT

    # Cada fuente puede traer zonas distintas: no inferir toda la columna a partir
    # del primer formato ni sustituir fechas corruptas con una fecha inventada.
    fechas = [parse_timestamp(v) for v in df["timestamp"]]
    df["fecha_dt"] = pd.Series(fechas, index=df.index, dtype=object)
    df["fecha_estandar"] = [None if pd.isna(v) else v.strftime("%Y-%m-%d %H:%M:%S") for v in fechas]
    df["fecha_corta"] = [None if pd.isna(v) else v.strftime("%Y-%m-%d") for v in fechas]
    montos = pd.to_numeric(df["monto_original"], errors="coerce")
    df["monto_mxn"] = montos * df["moneda"].map({"USD": TASA_CAMBIO_USD_MXN, "MXN": 1.0})
    return df


def imputar_faltantes(df):
    """Respeta la imputación de fase 2: no inventa CLABEs ni repara corrupción."""
    df = df.copy()
    df["notification_email"] = df["notification_email"].fillna("ANONIMO")
    df["obs_calidad"] = df["obs_calidad"].fillna("")
    return df


def tratar_outliers_iqr(df):
    """Fase 3: Outliers con IQR y Capping / Winsorizing."""
    df = df.copy()
    montos = pd.to_numeric(df["monto_mxn"], errors="coerce")
    positivos = montos[(montos > 0) & np.isfinite(montos)]
    Q1 = positivos.quantile(0.25)
    Q3 = positivos.quantile(0.75)
    IQR = Q3 - Q1

    limite_inferior = Q1 - 1.5 * IQR
    limite_superior = Q3 + 1.5 * IQR

    # Cero válido en CONSULTA_SALDO. Los imposibles/corruptos no desaparecen:
    # se conservan para que fase 6 registre su motivo de rechazo.
    df["monto_mxn_capped"] = montos.where(~((montos > 0) & np.isfinite(montos)),
                                         montos.clip(upper=limite_superior))

    return df, Q1, Q3, IQR, limite_superior


def cruce_y_detectar_huerfanos(df_transacciones, df_cuentas):
    """Fase 4: Detección de cuentas huérfanas no registradas en Core Bancario"""
    df = df_transacciones.copy()

    posibles_nombres = ["account_id", "id_cuenta", "cuenta_id", "id", "cuenta"]
    col_cuenta_master = None

    for col in posibles_nombres:
        if col in df_cuentas.columns:
            col_cuenta_master = col
            break

    if not col_cuenta_master:
        col_cuenta_master = df_cuentas.columns[0]

    cuentas_validas = set(df_cuentas[col_cuenta_master].astype(str).unique())

    df["es_huerfano"] = ~df["account_id"].astype(str).isin(cuentas_validas)
    df["motivo_rechazo_cuarentena"] = np.where(
        df["es_huerfano"],
        "Cuenta huérfana no registrada en Core Bancario",
        None,
    )

    return df


# ==========================================
# GENERACIÓN DE FIGURAS DE EVIDENCIA (ING 2)
# ==========================================
def generar_graficas_ing2(df_final, limite_superior):
    """Genera un panel dashboard con las 4 evidencias clave del Ingeniero 2 (IQR optimizado)"""
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle(
        "Evidencia Visual de Transformaciones e Integración (Ingeniero/a 2)",
        fontsize=14,
        fontweight="bold",
    )

    # 1. Tratamiento de Outliers (IQR Capping) - Versión con Zoom en la distribución real
    ax1 = axes[0, 0]
    # Filtramos para visualizar la zona donde se concentra el 98% de los datos y ver el efecto del Capping
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
    ruta_panel = PATH_FIGURAS / "panel_transformaciones_ing2.png"
    fig.savefig(ruta_panel)
    plt.close(fig)
    print(f"   [OK] Panel gráfico optimizado guardado en: {ruta_panel.relative_to(BASE_DIR)}")

# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == "__main__":
    path_cuentas = PATH_DATA / "interim" / "catalogo_cuentas_fase2.csv"
    path_atm = PATH_DATA / "interim" / "transacciones_atm_fase2.csv"
    path_json = PATH_DATA / "interim" / "transferencias_digitales_fase2.json"

    # 1. Carga e integración
    df_cuentas, df_unificado = cargar_datos_fuentes(
        path_cuentas, path_atm, path_json
    )

    # 2. Homologación de fechas y divisas (USD -> MXN @ 19.50)
    df_homologado = homologar_fechas_y_monedas(df_unificado)

    # 3. Imputación de faltantes
    df_imputado = imputar_faltantes(df_homologado)

    # 4. Outliers con IQR (Capping)
    df_sin_outliers, Q1, Q3, IQR, sup = tratar_outliers_iqr(df_imputado)

    # 5. Cruce maestro y detección de huérfanos
    df_cruzado = cruce_y_detectar_huerfanos(df_sin_outliers, df_cuentas)

    # 6. Escalamiento Min-Max y Discretización
    df_final = transformacion_discretizacion_escalado(df_cruzado)

    # 7. Generar evidencia gráfica
    generar_graficas_ing2(df_final, sup)

    # Resumen técnico en consola
    print("\n=== RESUMEN TÉCNICO DE TRANSFORMACIÓN (INGENIERO/A 2) ===")
    print(f"Total registros integrados: {len(df_unificado)}")
    print(
        f"Registros huérfanos detectados: {df_final['es_huerfano'].sum()} (Desviados a cuarentena)"
    )
    print(f"Límite superior IQR para Capping de Monto: ${sup:,.2f} MXN")
    print(
        "\nDistribución por Nivel de Monto (Discretización):\n",
        df_final["nivel_monto"].value_counts(),
    )

    output_file = PATH_REPORTES / "transacciones_procesadas_limpias.csv"
    df_final.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n[ÉXITO] Archivo '{output_file.name}' generado correctamente en {output_file.parent.name}/.")
