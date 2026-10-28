# Ingeniero/a 3: validación, resiliencia y base de datos

## Archivos de la entrega

| Archivo | Responsabilidad |
|---|---|
| `src/fase5_transformacion.py` | Min-Max en [0, 1], terciles Bajo/Medio/Alto y parámetros del lote. |
| `src/modelos_ing3.py` | `TransaccionLimpia` y `RegistroCuarentena`, con `BaseModel`, `@field_validator` y `@model_validator`. |
| `src/fase6_validacion.py` | Separación por fila con `try/except ValidationError`, errores detallados y registro recibido en JSON. |
| `src/fase7_base_datos.py` | Creación de tablas, INSERT parametrizados, `commit()` y `rollback()`. |
| `src/pipeline_ing3.py` | Ejecución de fases 5-7 y exportación de evidencias después del commit. |
| `src/diagramas_ing3.py` | Generación automática del pipeline por fases, UML y flujo de datos en PNG, SVG, Mermaid y un visor HTML local. |
| `run_ing3.py` | Ejecutor de la entrega usando los archivos de fase 2 incluidos. |
| `tests/test_ing3_resiliencia.py` | Pruebas de bordes, corrupción, estrés y atomicidad. |

## Ejecución

Abrir una terminal dentro de `ProyectoFinal`:

```bash
python -m pip install -r requirements.txt
python run_ing3.py
python -m pytest -q tests -o junit_family=legacy --junitxml=reportes/ing3/resultados_pruebas.xml
```

Para ejecutar únicamente las pruebas de esta entrega:

```bash
python -m pytest -q tests/test_ing3_resiliencia.py
```

Para ejecutar desde las fuentes crudas las fases de los tres integrantes:

```bash
python -m src.Todas_las_fases
```

`run_ing3.py` reutiliza las funciones de integración de Ing. 2 y las salidas de fase
2; no repite el diagnóstico estadístico. `Todas_las_fases.py` ejecuta las siete
fases y comparte esas mismas funciones. Las rutas predeterminadas se resuelven
desde el archivo Python, sin rutas absolutas propias del equipo.

## Diagramas visuales generados por el programa

Cada ejecución de `python run_ing3.py` o del pipeline completo genera:

- `reportes/ing3/diagramas/pipeline_robusto_por_fases.png` y `.svg`: diagrama de las
  siete fases desde los CSV/JSON crudos hasta las tablas finales, cuarentena y
  decisiones de commit/rollback. Respeta el orden ejecutado: la fase 4a convierte
  importes a MXN antes del IQR de fase 3; fase 4b cruza el catálogo después.
- `reportes/ing3/diagramas/diagrama_clases_ing3.png` y `.svg`: UML con `BaseModel`,
  `TransaccionLimpia` y `RegistroCuarentena`, herencia, atributos con tipos y
  restricciones, validadores por campo y validador de coherencia. Los miembros se
  leen de las clases reales del proyecto.
- `reportes/ing3/diagramas/flujo_entradas_salidas_ing3.png` y `.svg`: archivos de
  entrada, integración, transformación, validación por fila, salidas válidas y
  rechazadas, tablas SQLite, commit/rollback y archivos exportados. Muestra los
  conteos del lote que se acaba de procesar.
- `reportes/ing3/diagramas/ver_diagramas.html`: visor local con pestañas para los
  tres diagramas y enlaces a las imágenes. Muestra el pipeline por fases al abrir
  el archivo. Se abre en un navegador, sin Internet.
- Tres archivos `.mmd` con las versiones editables en Mermaid.

Para regenerar solo los diagramas usando el resumen ya guardado, sin volver a
cargar las tablas:

```bash
python -m src.diagramas_ing3
```

También se pueden abrir automáticamente al terminar la carga:

```bash
python run_ing3.py --ver-diagramas
```

## Fase 5: transformación

Se aplica `monto_minmax = (x - mínimo) / (máximo - mínimo)` sobre
`monto_mxn_capped`, ya convertido a MXN y tratado con IQR. Si máximo = mínimo,
se asigna 0. El lote vacío mantiene sus columnas y no divide entre cero.

Se calculan los percentiles P33 y P67 del importe: Bajo si `x <= P33`, Medio si
`P33 < x <= P67` y Alto si `x > P67`. Se usa el importe y no el rango por posición:
dos montos iguales siempre reciben la misma etiqueta, aunque se reordene el lote.
Los segmentos pueden quedar vacíos en lotes pequeños o constantes; no se inventan
diferencias entre importes idénticos para forzar tres grupos poblados.

El ajuste usa todos los importes finitos no negativos recibidos de la fase 4,
antes de la validación de correos y llaves. Los valores corruptos o negativos no
aportan a mínimo, máximo ni cuantiles y permanecen disponibles para rechazo.
Los parámetros se registran en `reportes/ing3/resumen_ing3.json`.

## Fase 6: reglas y cuarentena

El esquema exige tipos estrictos y prohíbe campos desconocidos. La capa de entrada
proyecta las columnas del esquema y guarda las columnas auxiliares de las fases
anteriores dentro de `datos_origen_json`. Adaptar un escalar numpy a Python o un
nulo pandas a `None` no convierte textos numéricos en números válidos.

- Los identificadores son texto no vacío. Se detectan duplicados entre registros
  aceptados del lote. La cuenta se comprueba contra el catálogo, aunque la bandera
  `es_huerfano` venga falsamente marcada como `False`.
- La fecha final debe ser `YYYY-MM-DD` y existir en el calendario.
- Moneda de origen: MXN o USD. La conversión debe coincidir con 19.50 MXN por USD.
- Los importes son numéricos finitos y no admiten booleanos. El importe escalado
  debe estar entre 0 y 1 y la etiqueta debe pertenecer a Bajo/Medio/Alto.
- Las operaciones monetarias exigen importe positivo. `CONSULTA_SALDO` de ATM
  conserva importe cero; una consulta con importe monetario se rechaza.
- Las operaciones ATM requieren tipo conocido, moneda MXN y comisión no negativa.
- SPEI requiere CLABE de exactamente 18 dígitos ASCII, conservando ceros iniciales.
  No se calcula dígito verificador por la regla de datos sintéticos del equipo.
  En ATM la CLABE no aplica y puede ser `None`.
- Se acepta correo con el formato del proyecto o la etiqueta `ANONIMO`. La regla
  revisa formato; no consulta la existencia de la dirección ni de su dominio.
- Una observación previa `NO_NUMERICO` provoca rechazo aunque otro campo haya sido
  completado después.

Cada fila se valida dentro de un `try`. Un `ValidationError` crea una entrada en
cuarentena con número de fila (desde 1), identificador si existe, causa legible,
errores estructurados y registro completo recibido por la fase 6. Así,
`entrada = limpias + cuarentena` y el error de una fila no impide procesar la
siguiente. En el JSON de evidencia, los valores IEEE no finitos se representan
como texto `nan`, `inf` o `-inf`, para mantener JSON estándar y distinguirlos de
los nulos originales.

Las comisiones con `FALLO_CONEXION` y las cuentas BLOQUEADA/SUSPENDIDA siguen como
decisiones pendientes del equipo. No se añadieron rechazos por estas dos reglas
sin una decisión de negocio documentada.

## Fase 7: transacciones y evidencias

SQLite no necesita instalar un servidor ni un controlador adicional.
`cargar_base_datos()` ejecuta `BEGIN IMMEDIATE`, crea las dos tablas, inserta
mediante parámetros y llama `conn.commit()` únicamente cuando termina todo.
Ante una excepción llama `conn.rollback()` y propaga el error; la conexión se
cierra en `finally`. Un error SQL no se presenta como un registro corrupto:
afecta a la persistencia del lote completo.

La función de carga añade filas por defecto. Los ejecutores usan
`reemplazar=True`: los dos `DELETE` y todas las inserciones forman la misma
transacción. Repetir la ejecución no acumula duplicados; un fallo conserva el lote
anterior completo. No se usa `INSERT OR IGNORE`, porque ocultaría pérdida de datos.

Entregables generados:

- `data/proyecto_final.sqlite3`: BD con las dos tablas obligatorias.
- `reportes/ing3/fase5_transformadas.csv`: salida previa a Pydantic, incluidos
  registros que pueden ser rechazados después.
- `reportes/ing3/transacciones_limpias.csv`: registros conformes.
- `reportes/ing3/cuarentena_errores.csv`: registros y motivos de rechazo.
- `reportes/ing3/resumen_ing3.json`: conteos, balance, parámetros e integridad SQLite.
- `reportes/ing3/resultados_pruebas.xml`: resultados de pytest al usar el comando
  con `--junitxml`.

Consultas para abrir en DB Browser for SQLite u otro cliente:

```sql
SELECT COUNT(*) FROM transacciones_limpias;
SELECT COUNT(*) FROM cuarentena_errores;
SELECT MIN(monto_minmax), MAX(monto_minmax) FROM transacciones_limpias;
SELECT nivel_monto, COUNT(*) FROM transacciones_limpias GROUP BY nivel_monto;
SELECT transaccion_id, motivo_rechazo_cuarentena FROM cuarentena_errores LIMIT 10;
PRAGMA integrity_check;
```

## Pruebas de estrés y defensa

La prueba `test_estres_20000_registros_mitad_corruptos` intercala 10 000 operaciones
válidas con 10 000 corrupciones de ocho clases: correo inválido, CLABE corta,
cuenta huérfana, fecha imposible, importe textual, importe infinito, moneda
desconocida y bandera de huérfano. Verifica exactamente 10 000 filas en cada
tabla y la integridad de SQLite. Usa una BD temporal y no contamina la entrega.

Las pruebas de rollback provocan dos fallos reales: un identificador duplicado
después de una inserción válida y un trigger que rechaza la inserción en
cuarentena después de renovar la tabla limpia. En ambos casos se comprueba que
los datos previos se conservan. Además se cubren nulos, tipos incorrectos, valores
anidados, importes negativos, lotes vacíos/constantes, empates, carga repetida,
consultas de saldo y conservación de ceros en CLABE.

Para explicar la solución en la defensa:

1. Mostrar fórmula, parámetros y regla de terciles de fase 5.
2. Abrir `TransaccionLimpia` y explicar un `@field_validator` y una regla entre
   campos de `@model_validator`.
3. Mostrar el `except ValidationError` y una fila de cuarentena con sus causas.
4. Abrir `cargar_base_datos` y señalar el único commit y el rollback de ambas tablas.
5. Ejecutar pytest y explicar por qué una prueba de rollback debe fallar después
   de haber hecho una modificación dentro de la transacción.

## Ajustes necesarios en la integración existente

Se conservaron `tipo_operacion`, `comision_aplicada` y las columnas de trazabilidad
que el archivo integrado anterior omitía. Se eliminaron las CLABEs inventadas y la
segunda imputación que podía ocultar importes corruptos. Las fechas día/mes se
leen explícitamente; los epoch Unix se convierten a la zona de México y las fechas
ilegibles quedan nulas para cuarentena. El capping conserva las consultas de saldo
con cero y deja los importes imposibles disponibles para rechazo auditable.

El archivo histórico `reportes/transacciones_procesadas_limpias.csv` producido por
Ing. 2 es una salida anterior a Pydantic; el resultado final validado es
`reportes/ing3/transacciones_limpias.csv` y su tabla en SQLite.
