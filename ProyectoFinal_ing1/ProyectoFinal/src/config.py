"""
Configuración central del pipeline ETL – Grupo 2: Fintech & Transacciones Bancarias.
Sección Ingeniero/a 1 (Calidad, Nulos y Outliers) – Fases 1 y 2.

Todas las rutas son relativas a la raíz del proyecto, por lo que el código
funciona igual en Windows, Linux o macOS.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIR_DATASETS = RAIZ / "datasets"
DIR_INTERIM = RAIZ / "data" / "interim"
DIR_REPORTES = RAIZ / "reportes" / "ing1"
DIR_FIGURAS = DIR_REPORTES / "figuras"

ARCH_CATALOGO = DIR_DATASETS / "catalogo_cuentas.csv"
ARCH_ATM = DIR_DATASETS / "transacciones_atm.csv"
ARCH_TRANSFER = DIR_DATASETS / "transferencias_digitales.json"

# Llave primaria esperada de cada fuente (para medir unicidad por llave)
LLAVES = {
    "catalogo_cuentas": "id_cuenta",
    "transacciones_atm": "id_transaccion",
    "transferencias_digitales": "transfer_id",
}

# Columnas que se leen SIEMPRE como texto en la carga segura.
# Motivo: la CLABE inicia con "0" (código de banco 012); si pandas la infiere
# como int64 se pierde el cero inicial y una CLABE válida de 18 dígitos queda en 17.
COLUMNAS_TEXTO = {
    "catalogo_cuentas": ["id_cuenta"],
    "transacciones_atm": ["id_transaccion", "id_cuenta", "id_cajero"],
    "transferencias_digitales": ["transfer_id", "account_id", "beneficiary_clabe"],
}

# Nulos "disfrazados" (sesión 22): valores de texto que significan "no hay dato".
# NA_VALUES se pasa a pd.read_csv(na_values=...) igual que en la actividad de clase.
NA_VALUES = ["", " ", "N/A", "NA", "n/a", "na", "null", "NULL", "None", "none",
             "-", "--", "?", "nan", "NaN", "unknown", "Unknown", "desconocido", "S/D"]
# Misma lista en mayúsculas para comparar valores ya cargados (JSON, lotes nuevos)
TOKENS_NULOS = {v.strip().upper() for v in NA_VALUES}

# Etiquetas controladas para imputación de categóricas
ETIQUETA_CAJERO = "CAJERO_DESCONOCIDO"
ETIQUETA_EMAIL = "ANONIMO"

# Nivel de significancia para las pruebas MCAR/MAR
ALFA = 0.05
N_PERMUTACIONES = 5000
SEMILLA = 2026

# Columnas que NUNCA se imputan (identificadores / datos sensibles).
# Si faltan, el registro debe ir a cuarentena (Fase 6, Ingeniero/a 3).
NO_IMPUTABLES = {
    "transacciones_atm": ["id_transaccion", "id_cuenta", "fecha_hora", "tipo_operacion"],
    "transferencias_digitales": ["transfer_id", "account_id", "timestamp",
                                 "beneficiary_clabe", "currency"],
}
