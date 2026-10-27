# Guion para la defensa oral – Ingeniera 1: Carol Ivette Rodríguez Lepe (≈ 2 minutos)

## Lo que tengo que decir
1. **Diagnóstico (Fase 1).** “Antes de tocar los datos medimos completitud, unicidad y tipos. Como en la sesión 22, primero cargamos todo como texto con `keep_default_na=False` para encontrar nulos disfrazados, y después cargamos con `na_values`. Así encontramos que, además de 8 correos `null`, había **8 correos como cadena vacía** que `isna()` no detecta. Las tres columnas más críticas son `id_cajero` (92.9 % completa), `monto_mxn` (95.65 %) y el correo (97.33 %). En ATM hay 20 duplicados exactos: reintentos de cajero.”
2. **Tipos.** “Si se carga el JSON por defecto, pandas convierte la CLABE a entero y **le quita el cero inicial**: 554 CLABEs válidas quedarían en 17 dígitos. Por eso los identificadores se leen como texto.”
3. **MCAR/MAR (Fase 2).** “Con el indicador falta/no falta comparamos el % de nulos por categoría y la media de otras columnas con dato y sin dato. Para saber si las diferencias eran reales usamos χ² de independencia y Mann-Whitney. Ninguna dio p < 0.05, y en `msno.heatmap` la correlación de nulidad es −0.03, así que las tres son MCAR. MNAR lo descartamos con el negocio: por ejemplo, el ID del cajero lo escribe la terminal, no depende de cuál cajero era.”
4. **Sensibilidad.** “Si no hubiéramos detectado los vacíos, el correo parecía MAR por `status` (p = 0.034). Detectar nulos disfrazados cambió la conclusión.”
5. **Mediana.** “Los montos tienen sesgo 22: la media es 11 229 y la mediana 3 000 por un retiro de 3.5 millones. La mediana tiene punto de ruptura de 50 %, la media de 0 %. `SimpleImputer` pondría 3 000 a todos, pero un retiro típico es 2 000 y un depósito 4 000, así que imputamos con la mediana por tipo de operación.”
6. **Resultado.** “Completitud 100 %, la mediana no se movió y la media cambió −1 %. No borramos ningún registro válido; con `dropna` habríamos perdido 68 operaciones (11.3 %). Todo quedó en una bitácora.”

## Preguntas probables y respuesta corta
| Pregunta | Respuesta |
|---|---|
| ¿Diferencia MCAR, MAR, MNAR? | MCAR: falta al azar, no depende de nada. MAR: depende de otra variable **observada**. MNAR: depende del **propio valor** faltante; no se puede probar con los datos, se argumenta por dominio. |
| ¿Cómo decidiste que era MCAR? | % de nulos por categoría y media con/sin dato (sesión 22), confirmado con χ² y Mann-Whitney (ningún p < 0.05) y con `msno.matrix`/`msno.heatmap` (nulos dispersos, correlación ≈ 0). |
| ¿Por qué a veces usaste permutación? | La χ² clásica pide frecuencias esperadas ≥ 5. Con pocos nulos no se cumple; la permutación revuelve el indicador 5 000 veces y construye la distribución nula sin ese supuesto. |
| Si es MCAR, ¿por qué imputar por grupo? | MCAR solo dice que no hay sesgo en *qué* falta; los montos sí difieren por tipo, así que la mediana del grupo da un valor más realista que la global. |
| ¿Por qué no usar la media? | Sesgo 22; un outlier la arrastra (punto de ruptura 0 %). La media de RETIRO es 17 489 y la mediana 2 000. |
| ¿Por qué no eliminar las filas con nulos? | Perderíamos 68 de 600 operaciones (11.3 %) en ATM (eliminación por lista); la rúbrica pide no hacer pérdida destructiva. |
| ¿Por qué no imputar el cajero con la moda? | `most_frequent` inventaría una ubicación física falsa. `CAJERO_DESCONOCIDO` es honesto y auditable (equivale a `SimpleImputer(strategy="constant")`). |
| ¿Por qué eliminar duplicados antes de imputar? | Un reintento duplicado cuenta dos veces en la mediana y en los totales. |
| ¿Por qué no imputar la CLABE o la cuenta? | Son llaves: imputarlas crea relaciones falsas. Van a cuarentena. |
| ¿Qué pasa si llega `monto = "abc"`? | No se imputa: queda NaN con `obs_calidad = MONTO_MXN_NO_NUMERICO` y Pydantic lo manda a cuarentena. Hay prueba automática. |
| ¿Las comisiones en 0 son nulos? | No: no hay NaN y la proporción de ceros no difiere significativamente entre resultados (χ² p = 0.058) → exención. Si llegara NaN, se imputa con mediana por tipo. |
| ¿Por qué IQR y no Z-score para outliers? | En SPEI el Z-score detecta 12 y el IQR 18: con datos sesgados la media y la desviación se inflan con los propios outliers (enmascaramiento). IQR usa cuartiles, que son robustos. |
| ¿Por qué el monto 0 de consultas no es error? | Una consulta de saldo no mueve dinero; por eso la Fase 3 debe excluir CONSULTA_SALDO de “monto ≤ 0”. |
