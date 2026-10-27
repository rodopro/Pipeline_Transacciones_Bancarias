# Checklist y autoevaluación – Ingeniera 1 (Fases 1 y 2)
**Carol Ivette Rodríguez Lepe – 23460709** · Grupo 2 Fintech

## A. Requisitos técnicos de la guía (sección 4)

| Requisito | Estado | Dónde se evidencia |
|---|:---:|---|
| **F1** Perfilado cuantitativo **antes** de cualquier transformación | ✅ | `fase1()` en `run_ing1.py` sobre la carga cruda; notebook §1 |
| **F1** Completitud: % de nulos por columna | ✅ | `f1_perfil_columnas_crudo.csv`, `f1_ranking_completitud.csv` (ordenado, 3 críticas) |
| **F1** Unicidad: conteo de duplicados exactos | ✅ | `f1_resumen_datasets_crudo.csv` (20 en ATM) + duplicados por llave |
| **F1** Tipos inferidos (dtypes) | ✅ | `f1_perfil_columnas_crudo.csv`, `f1_tipos_inferidos.csv`, `info()` en el notebook |
| **F2** Clasificar ausencias MCAR / MAR | ✅ | `f2_pruebas_mcar_mar.csv`, figuras 02c y 06–08, discusión MNAR en REGLAS §2.4 |
| **F2** Imputar numéricas sesgadas con mediana | ✅ | R2.2 / R2.3; `f2_medianas_usadas.csv` |
| **F2** Justificar por qué no la media | ✅ | REGLAS §2.6; figuras 04–05 (sesgo 22.2 y 7.5) |
| **F2** Categóricas con etiquetas controladas (ej. 'ANONIMO') | ✅ | `CAJERO_DESCONOCIDO`, `ANONIMO` (R2.5, R2.6) |
| **F2** Recalcular campos con información en otras columnas | ✅* | R2.1: CONSULTA_SALDO ⇒ monto = 0. *En este lote aplica a 0 registros (ninguna consulta venía sin monto); la regla está implementada y probada en `tests/`. |
| Reto del grupo: reintentos de cajero | ✅ | 20 duplicados exactos eliminados (`f2_duplicados_eliminados.csv`) |
| Reto del grupo: comisiones nulas | ✅ | R2.4: no hay NaN; el 0.0 se analizó como exención; regla lista para NaN (probada en tests) |
| Entregable Ing. 1: funciones de limpieza | ✅ | `src/fase1_diagnostico.py`, `src/fase2_imputacion.py` |
| Entregable Ing. 1: reporte comparativo antes/después | ✅ | `Reporte_Calidad_Antes_Despues_Ing1.pdf`, `comparativo_*.csv`, figura 01 |

## B. Técnicas vistas en clase que se usan

| Clase | Técnica | Dónde |
|---|---|---|
| Sesión 22 – Detección de nulos | `keep_default_na=False, dtype=str` para nulos disfrazados; `na_values`; `isna().sum()`; completitud ordenada y 3 críticas; % de nulos por categoría; media con/sin dato; MCAR/MAR/MNAR; `msno.matrix`, `msno.bar`, `msno.heatmap` | `explorar_nulos_disfrazados`, `cargar_crudo_seguro`, `ranking_completitud`, `clasificar_faltante`, figuras 02–03 |
| Actividad 3.1.2 – Outliers | Tukey/IQR vs Z-score | `hallazgos_validez` (18 vs 12 en SPEI) |
| Sesión 26 – Limpieza | `drop_duplicates()`; funciones que regresan `.copy()`; no eliminar filas con nulos no críticos | `eliminar_duplicados_exactos`, todas las funciones de Fase 2 |
| Sesión 28 – Pipelines | `SimpleImputer(strategy="median" / "constant", add_indicator=True)` | `comparar_con_simpleimputer`, banderas `<col>_imputado` |
| Unidad 1 – Ingesta | Validar esquema/tipos al inicio y fallar de forma controlada | carga segura de tipos, `obs_calidad`, try/except sin crash |

## C. Rúbrica oficial – criterios en los que aporta la Ing. 1

| Criterio (pts) | Qué pide “Excelente” | Cumplimiento Fases 1–2 |
|---|---|---|
| **1. Mockup y Reglas (10)** | Diagrama de flujo completo; decisiones justificadas estadísticamente | ✅ Diagrama de las 7 fases + reglas R1.x/R2.x con p-valores, sesgo y punto de ruptura. *Faltan las secciones de Ing. 2 e Ing. 3 y las firmas.* |
| **2. Calidad de Datos (20)** | Imputación correcta según tipo de ausencia; outliers por IQR/Capping sin pérdida destructiva | ✅ Nulos: completo. Solo se eliminaron 20 reintentos idénticos; 0 registros válidos perdidos. ⏳ **Outliers (Fase 3)** pendiente; también le toca a la Ing. 1 según la matriz. |
| **3. Integración (20)** | — | Aporta hallazgos cuantificados (fechas, USD, huérfanos) para Ing. 2 |
| **4. Pydantic (20)** | — | Aporta: CLABE como texto, correos inválidos cuantificados, `obs_calidad`, aceptar `ANONIMO` |
| **5. BD (15)** | — | — |
| **6. Resiliencia y defensa (15)** | No crash con datos corruptos; dominio individual | ✅ 6 pruebas en `tests/` (tipos mezclados, `'abc'`, `'N/A'`, `''`, dataset vacío, llaves nulas). Guion: `docs/GUION_DEFENSA_ING1.md` |

## D. Revisión como evaluador (25-oct-2026) – qué se corrigió
| # | Observación | Corrección |
|---|---|---|
| 1 | Los nulos disfrazados se trataban con una función propia, no como en clase | Exploración con `keep_default_na=False` + carga con `na_values` (sesión 22) |
| 2 | No había ranking de completitud ni “3 columnas más críticas” | `ranking_completitud()` + tabla en REGLAS §1.1 |
| 3 | Las gráficas de nulos no usaban `missingno` | `msno.matrix`, `msno.bar`, `msno.heatmap` (r = −0.03) |
| 4 | La evidencia MCAR/MAR solo era estadística, sin la comparación de clase | Se agregó % de nulos por categoría, brecha en pp y media/mediana con/sin dato; χ² ahora con `chi2_contingency` (permutación solo si esperadas < 5) |
| 5 | Faltaba discutir MNAR columna por columna | REGLAS §2.4 |
| 6 | No se contrastaba con `SimpleImputer` (sesión 28) | `comparar_con_simpleimputer()` + REGLAS §2.7 |
| 7 | Solo se usaba IQR, no se comparó con Z-score (3.1.2) | Conteos IQR vs Z-score en hallazgos |
| 8 | Duplicados con `astype(str)` en lugar del método de clase | `df.duplicated()` / `drop_duplicates()` con respaldo para datos corruptos |
| 9 | El notebook dependía de que antes se corriera `run_ing1.py` | Notebook autosuficiente: genera sus propias figuras |
| 10 | El “recalcular” aplica a 0 registros y no se decía | Se transparentó en R2.1 y en este checklist |
| 11 | El reporte PDF no tenía portada institucional ni nombre | Portada TecNM con nombre, número de control, asesor y fecha |
| 12 | Dato de comisión (p = 0.15) calculado con duplicados | Recalculado sin duplicados: 27.3 %, p = 0.058 |

## E. Pendientes antes de la entrega final
- [ ] Nombres de Ing. 2 e Ing. 3 en `README.md` y `REGLAS_DE_NEGOCIO.md`, y firmas.
- [ ] Fase 3 (outliers IQR + capping); recordar **excluir CONSULTA_SALDO** de la regla “monto ≤ 0”.
- [ ] Confirmar con Ing. 3 que el validador de correo acepta `ANONIMO`.
- [ ] Decisiones de equipo abiertas (comisión en FALLO_CONEXION; cuentas bloqueadas/suspendidas).
- [ ] Commits en Git con mensajes por fase (ej. `feat(fase1): perfilado de calidad`).
