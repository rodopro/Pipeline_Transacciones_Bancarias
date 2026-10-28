# Pipeline ETL Robusto con Zona de Cuarentena

## Entrega del Ingeniero/a 3: fases 5, 6 y 7

Desde la carpeta `ProyectoFinal`, con las salidas de fase 2 ya incluidas:

```bash
python -m pip install -r requirements.txt
python run_ing3.py
python -m pytest -q tests -o junit_family=legacy --junitxml=reportes/ing3/resultados_pruebas.xml
```

Para ejecutar las siete fases desde los datos crudos:

```bash
python -m src.Todas_las_fases
```

La BD se genera en `data/proyecto_final.sqlite3`, con las tablas
`transacciones_limpias` y `cuarentena_errores`. Repetir el ejecutor reemplaza el
lote anterior de ambas tablas dentro de una sola transacción. Si falla la carga,
se conserva el contenido anterior. Para usar otra BD:

```bash
python run_ing3.py --bd data/otra_entrega.sqlite3 --reportes reportes/otra_entrega
```

Los CSV, los parámetros de escalamiento y el resumen quedan en `reportes/ing3/`.
Cada ejecución también genera el pipeline robusto por fases, el UML de las clases
y el flujo de entradas y salidas en `reportes/ing3/diagramas/`, como PNG, SVG y Mermaid. Abre
[el visor visual](reportes/ing3/diagramas/ver_diagramas.html) en un navegador para
ver los tres diagramas con los conteos del lote. La primera pestaña muestra las
siete fases, las rutas de validación/cuarentena y las decisiones de commit/rollback.
El orden refleja la implementación: se homologan las divisas (fase 4a) antes del
capping IQR (fase 3) y después se cruza el catálogo (fase 4b).
Para regenerarlos sin cargar la BD:

```bash
python -m src.diagramas_ing3
```

Para ejecutar la carga y abrir los diagramas automáticamente en el navegador:

```bash
python run_ing3.py --ver-diagramas
```

La prueba de estrés inyecta 20 000 registros: 10 000 válidos y 10 000 corruptos.
También se verifican fallos SQL y rollback de las dos tablas, incluso después de
borrar el lote anterior. Consulta [la guía de ejecución y defensa](docs/GUIA_ING3.md)
para conocer las reglas, los módulos y las consultas de revisión.

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
