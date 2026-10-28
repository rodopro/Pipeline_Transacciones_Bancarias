import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, field_validator # instalar python -m pip install pydantic

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
PATH_SEGMENTOS = PATH_REPORTES / "transacciones_por_nivel"  # Carpeta para archivos individuales

PATH_REPORTES.mkdir(parents=True, exist_ok=True)
PATH_FIGURAS.mkdir(parents=True, exist_ok=True)
PATH_SEGMENTOS.mkdir(parents=True, exist_ok=True)


# ==========================================
# MODELO PYDANTIC (Validación y Cuarentena)
# ==========================================
class TransaccionModel(BaseModel):
    transaccion_id: str
    account_id: str
    monto_mxn_capped: float
    moneda: str

    @field_validator("monto_mxn_capped")
    @classmethod
    def validar_monto_positivo(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("El monto debe ser estrictamente mayor a 0")
        return v

    @field_validator("account_id")
    @classmethod
    def validar_formato_cuenta(cls, v: str) -> str:
        if not v or not v.startswith("CTA-"):
            raise ValueError("ID de cuenta inválido o no cumple el formato CTA-XXXX")
        return v


def validar_con_pydantic_y_cuarentena(df, cuentas_validas):
    """Fase 4: Validación robusta usando modelos Pydantic y separación de cuarentena"""
    registros_validos = []
    registros_cuarentena = []

    for _, row in df.iterrows():
        cuenta_str = str(row["account_id"])
        es_huerfano = cuenta_str not in cuentas_validas

        if es_huerfano:
            row_dict = row.to_dict()
            row_dict["es_huerfano"] = True
            row_dict["motivo_rechazo_cuarentena"] = "Cuenta huérfana no registrada en Core Bancario"
            registros_cuarentena.append(row_dict)
            continue

        try:
            TransaccionModel(
                transaccion_id=str(row["transaccion_id"]),
                account_id=cuenta_str,
                monto_mxn_capped=float(row["monto_mxn_capped"]),
                moneda=str(row["moneda"])
            )
            row_dict = row.to_dict()
            row_dict["es_huerfano"] = False
            row_dict["motivo_rechazo_cuarentena"] = None
            registros_validos.append(row_dict)
        except ValidationError as e:
            row_dict = row.to_dict()
            row_dict["es_huerfano"] = False
            errores = "; ".join([err["msg"] for err in e.errors()])
            row_dict["motivo_rechazo_cuarentena"] = f"Error Pydantic: {errores}"
            registros_cuarentena.append(row_dict)

    df_validos = pd.DataFrame(registros_validos)
    df_cuarentena = pd.DataFrame(registros_cuarentena)

    df_resultado = pd.concat([df_validos, df_cuarentena], ignore_index=True)
    return df_resultado


def cargar_datos_fuentes(path_cuentas, path_atm, path_json):
    """Fase 4: Carga y consolidación robusta mapeando columnas reales de ATM y JSON"""
    df_cuentas = pd.read_csv(path_cuentas)
    df_atm = pd.read_csv(path_atm)

    with open(path_json, "r", encoding="utf-8") as f:
        data_json = json.load(f)
    df_json = pd.DataFrame(data_json)

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
    df_atm["notification_email"] = "atm_sin_correo@banco.com.mx"
    df_atm["beneficiary_clabe"] = "000000000000000000"

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
    ]

    for col in cols_comunes:
        if col not in df_atm.columns:
            df_atm[col] = np.nan
        if col not in df_json.columns:
            df_json[col] = np.nan

    df_unificado = pd.concat(
        [df_atm[cols_comunes], df_json[cols_comunes]], ignore_index=True
    )
    return df_cuentas, df_unificado


def homologar_fechas_y_monedas(df):
    """Fase 4: Unificación de fechas ISO/UNIX a YYYY-MM-DD y conversión USD a MXN @ $19.50"""
    df = df.copy()

    def parse_timestamp(val):
        try:
            if pd.isna(val) or val == "":
                return pd.NaT
            if isinstance(val, (int, float)) or (
                isinstance(val, str) and val.isdigit()
            ):
                return pd.to_datetime(float(val), unit="s", errors="coerce")
            return pd.to_datetime(val, errors="coerce")
        except Exception:
            return pd.NaT

    df["fecha_dt"] = pd.to_datetime(
        df["timestamp"].apply(parse_timestamp), errors="coerce"
    )

    df["fecha_estandar"] = (
        df["fecha_dt"]
        .dt.strftime("%Y-%m-%d %H:%M:%S")
        .fillna("1970-01-01 00:00:00")
    )
    df["fecha_corta"] = (
        df["fecha_dt"].dt.strftime("%Y-%m-%d").fillna("1970-01-01")
    )

    def a_mxn(row):
        monto = row["monto_original"]
        moneda = str(row["moneda"]).upper()
        if moneda == "USD":
            return monto * TASA_CAMBIO_USD_MXN
        return monto

    df["monto_mxn"] = df.apply(a_mxn, axis=1)
    return df


def imputar_faltantes(df):
    """Fase 2: Imputación de nulos (MCAR/MAR)"""
    df = df.copy()
    df["notification_email"] = df["notification_email"].fillna(
        "sin_correo@banco.com.mx"
    )
    df["beneficiary_clabe"] = df["beneficiary_clabe"].fillna(
        "000000000000000000"
    )

    mediana_monto = df["monto_mxn"].median()
    df["monto_mxn"] = df["monto_mxn"].fillna(mediana_monto)

    return df


def tratar_outliers_iqr(df):
    """Fase 3: Outliers con IQR y Capping / Winsorizing."""
    df = df.copy()
    df = df[df["monto_mxn"] > 0].copy()

    Q1 = df["monto_mxn"].quantile(0.25)
    Q3 = df["monto_mxn"].quantile(0.75)
    IQR = Q3 - Q1

    limite_inferior = Q1 - 1.5 * IQR
    limite_superior = Q3 + 1.5 * IQR

    df["monto_mxn_capped"] = np.where(
        df["monto_mxn"] > limite_superior,
        limite_superior,
        np.where(
            df["monto_mxn"] < limite_inferior, limite_inferior, df["monto_mxn"]
        ),
    )

    return df, Q1, Q3, IQR, limite_superior


def transformacion_discretizacion_escalado(df):
    """Fase 5: Normalización Min-Max [0, 1] y Discretización por Ancho Igual (pd.cut)"""
    df = df.copy()

    min_val = df["monto_mxn_capped"].min()
    max_val = df["monto_mxn_capped"].max()

    if max_val != min_val:
        df["monto_minmax"] = (df["monto_mxn_capped"] - min_val) / (
            max_val - min_val
        )
    else:
        df["monto_minmax"] = 0.0

    df["nivel_monto"] = pd.cut(
        df["monto_mxn_capped"],
        bins=3,
        labels=["Bajo", "Medio", "Alto"],
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

    # 5. Validación robusta con Pydantic y detección de huérfanos
    posibles_nombres = ["account_id", "id_cuenta", "cuenta_id", "id", "cuenta"]
    col_cuenta_master = next((col for col in posibles_nombres if col in df_cuentas.columns), df_cuentas.columns[0])
    cuentas_validas = set(df_cuentas[col_cuenta_master].astype(str).unique())

    df_cruzado = validar_con_pydantic_y_cuarentena(df_sin_outliers, cuentas_validas)

    # 6. Escalamiento Min-Max y Discretización
    df_final = transformacion_discretizacion_escalado(df_cruzado)

    # 7. Generar evidencia gráfica
    generar_graficas_ing2(df_final, sup)

    # Guardar archivo maestro completo
    output_file = PATH_REPORTES / "transacciones_procesadas_limpias.csv"
    df_final.to_csv(output_file, index=False, encoding="utf-8-sig")

    # ==========================================
    # 8. GUARDAR ARCHIVOS INDIVIDUALES POR CARPETA
    # ==========================================
    # Segmentos por Nivel de Monto (solo transacciones válidas)
    df_validas = df_final[df_final["es_huerfano"] == False]
    
    df_validas[df_validas["nivel_monto"] == "Bajo"].to_csv(PATH_SEGMENTOS / "nivel_bajo.csv", index=False, encoding="utf-8-sig")
    df_validas[df_validas["nivel_monto"] == "Medio"].to_csv(PATH_SEGMENTOS / "nivel_medio.csv", index=False, encoding="utf-8-sig")
    df_validas[df_validas["nivel_monto"] == "Alto"].to_csv(PATH_SEGMENTOS / "nivel_alto.csv", index=False, encoding="utf-8-sig")
    
    # Registros en Cuarentena (huérfanos o con errores de validación)
    df_final[df_final["es_huerfano"] == True].to_csv(PATH_SEGMENTOS / "cuarentena.csv", index=False, encoding="utf-8-sig")

    # Resumen técnico en consola
    print("\n=== RESUMEN TÉCNICO DE TRANSFORMACIÓN (INGENIERO/A 2) ===")
    print(f"Total registros integrados: {len(df_unificado)}")
    print(f"Registros en Cuarentena guardados en carpeta: {PATH_SEGMENTOS.relative_to(BASE_DIR)}")
    print(f"Límite superior IQR para Capping de Monto: ${sup:,.2f} MXN")
    print(
        "\nDistribución por Nivel de Monto (Discretización):\n",
        df_final["nivel_monto"].value_counts(),
    )
    print(f"\n[ÉXITO] Archivo maestro y segmentos individuales generados correctamente.")
