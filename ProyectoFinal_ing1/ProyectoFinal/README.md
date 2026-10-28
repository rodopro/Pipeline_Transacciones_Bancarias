# Pipeline ETL Robusto con Zona de Cuarentena
**Grupo 2 – Fintech & Transacciones Bancarias** · Ingeniería de Datos (ATD-2602) · TecNM Campus Colima

## Estructura del repositorio
```
ProyectoFinal/
├── datasets/                     # datos crudos oficiales (NO se modifican)
│   ├── catalogo_cuentas.csv
│   ├── transacciones_atm.csv
│   └── transferencias_digitales.json
├── src/
│   ├── config.py                 # rutas, llaves, tokens de nulos, etiquetas
│   ├── fase1_diagnostico.py      # Ing. 1 – Fase 1: perfilado de calidad
│   ├── fase2_imputacion.py       # Ing. 1 – Fase 2: MCAR/MAR + imputación
│   └── figuras_ing1.py           # gráficas de evidencia (missingno + matplotlib)
├── run_ing1.py                   # ejecuta Fases 1 y 2 y genera evidencias
├── notebooks/
│   └── Ing1_Fase1_Fase2_Calidad.ipynb   # evidencia ejecutada con resultados
├── data/interim/                 # salida de la Fase 2 → entrada de Fase 3 / Ing. 2
├── reportes/ing1/                # CSV de perfiles, pruebas, bitácora, comparativos
│   ├── figuras/                  # PNG de evidencia
│   └── Reporte_Calidad_Antes_Despues_Ing1.pdf
├── tests/test_ing1_resiliencia.py  # pruebas con datos corruptos (no crash)
├── docs/
│   ├── CHECKLIST_RUBRICA_ING1.md
│   └── GUION_DEFENSA_ING1.md
├── REGLAS_DE_NEGOCIO.md          # reglas y justificación técnica (equipo)
└── requirements.txt
```

## Cómo ejecutar (Windows / Linux / macOS)
```bash
pip install -r requirements.txt
python run_ing1.py                 # Fases 1 y 2 → reportes/ing1 y data/interim
python -m pytest -q tests          # pruebas de resiliencia
jupyter notebook notebooks/Ing1_Fase1_Fase2_Calidad.ipynb
```

## Matriz de responsabilidades
| Rol | Integrante | Entregable |
|---|---|---|
| Ingeniera 1 – Calidad, Nulos y Outliers | Carol Ivette Rodríguez Lepe (23460709) | `src/fase1_diagnostico.py`, `src/fase2_imputacion.py`, reporte antes/después |
| Ingeniero/a 2 – Transformación e Integración | _(nombre)_ | módulo de integración multifuente |
| Ingeniero/a 3 – Validación, Resiliencia y BD | _(nombre)_ | esquemas Pydantic, carga a BD, pruebas de estrés |

## Uso de las salidas de la Fase 2 (para Ing. 2 / Ing. 3)
```python
import pandas as pd, json
atm = pd.read_csv("data/interim/transacciones_atm_fase2.csv",
                  dtype={"id_transaccion": str, "id_cuenta": str, "id_cajero": str})
tr = pd.DataFrame(json.load(open("data/interim/transferencias_digitales_fase2.json", encoding="utf-8")))
tr["beneficiary_clabe"] = tr["beneficiary_clabe"].astype("string")   # ¡siempre texto!
```
Columnas añadidas: `<col>_imputado` (bool) y `obs_calidad` (motivos de calidad, ej. `MONTO_MXN_NO_NUMERICO`).
