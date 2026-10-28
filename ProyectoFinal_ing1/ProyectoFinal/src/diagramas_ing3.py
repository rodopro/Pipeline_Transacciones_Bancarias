"""Genera pipeline por fases, UML y flujo de datos como PNG, SVG y Mermaid.

Los atributos y validadores se leen de las clases reales; los conteos provienen
del resumen del lote. No requiere Graphviz, conexión a Internet ni un servidor.
"""
from __future__ import annotations

import argparse
import ast
from html import escape
import inspect
import json
from pathlib import Path
import types
from typing import Literal, Union, get_args, get_origin

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

from .modelos_ing3 import RegistroCuarentena, TransaccionLimpia

AZUL = "#2557a7"
VERDE = "#15734c"
ROJO = "#ad3442"
TINTA = "#19283f"
GRIS = "#52637a"
BORDE = "#d2dce9"
FONDO = "#f5f8fc"


def _tipo(anotacion) -> str:
    origen, argumentos = get_origin(anotacion), get_args(anotacion)
    if origen is Literal:
        return "Literal[" + " | ".join(str(v) for v in argumentos) + "]"
    if origen in (types.UnionType, Union):
        return " | ".join(_tipo(v) for v in argumentos)
    return "None" if anotacion is type(None) else getattr(anotacion, "__name__", str(anotacion))


def _atributos(modelo) -> list[str]:
    lineas = []
    for nombre, campo in modelo.model_fields.items():
        limites = []
        for restriccion in campo.metadata:
            for atributo, etiqueta in (("ge", ">="), ("le", "<="), ("min_length", "long. >="), ("max_length", "long. <=")):
                valor = getattr(restriccion, atributo, None)
                if valor is not None:
                    limites.append(f"{etiqueta} {valor}")
        detalle = " {" + ", ".join(limites) + "}" if limites else ""
        lineas.append(f"+ {nombre}: {_tipo(campo.annotation)}{detalle}")
    return lineas


def _validadores(modelo) -> list[tuple[str, str]]:
    clase = ast.parse(inspect.getsource(modelo)).body[0]
    resultado = []
    for metodo in clase.body:
        if isinstance(metodo, ast.FunctionDef):
            for decorador in metodo.decorator_list:
                if isinstance(decorador, ast.Call) and isinstance(decorador.func, ast.Name):
                    if decorador.func.id in {"field_validator", "model_validator"}:
                        resultado.append((metodo.name, decorador.func.id))
    return resultado


def _lienzo(ancho: int, alto: int):
    fig = Figure(figsize=(ancho / 100, alto / 100), dpi=100, facecolor=FONDO)
    FigureCanvasAgg(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, ancho)
    ax.set_ylim(alto, 0)
    ax.axis("off")
    return fig, ax


def _texto(ax, x, y, contenido, *, tam=13, color=TINTA, negrita=False, mono=False, ha="left"):
    return ax.text(x, y, contenido, fontsize=tam, color=color, va="top", ha=ha,
                   fontweight="bold" if negrita else "normal",
                   family="DejaVu Sans Mono" if mono else "DejaVu Sans", linespacing=1.5,
                   zorder=5)


def _caja(ax, x, y, ancho, alto, color=BORDE, fondo="white"):
    ax.add_patch(FancyBboxPatch((x, y), ancho, alto, boxstyle="round,pad=0,rounding_size=14",
                               linewidth=1.7, edgecolor=color, facecolor=fondo, zorder=2))


def _flecha(ax, puntos, color=AZUL):
    for primero, segundo in zip(puntos[:-2], puntos[1:-1]):
        ax.plot([primero[0], segundo[0]], [primero[1], segundo[1]], color=color, lw=2.1, zorder=1)
    ax.add_patch(FancyArrowPatch(puntos[-2], puntos[-1], arrowstyle="-|>", mutation_scale=17,
                                color=color, lw=2.1, zorder=1, shrinkA=0, shrinkB=2))


def _encabezado(ax, subtitulo, titulo, descripcion):
    _texto(ax, 60, 35, subtitulo, tam=11, color=AZUL, negrita=True)
    _texto(ax, 60, 69, titulo, tam=26, negrita=True)
    _texto(ax, 60, 120, descripcion, tam=12, color=GRIS)


def _clase(ax, modelo, x, y, ancho, color):
    atributos, validadores = _atributos(modelo), _validadores(modelo)
    fila = 31
    inicio_atributos = y + 100
    separador = inicio_atributos + len(atributos) * fila + 12
    metodos = [f"+ {nombre}(...)  [@{decorador}]" for nombre, decorador in validadores]
    if not metodos:
        metodos = ["Hereda model_validate() y model_dump()"]
    alto = separador - y + 58 + len(metodos) * fila + 16
    _caja(ax, x, y, ancho, alto, color)
    _texto(ax, x + 24, y + 18, "«clase Pydantic»", tam=11, color=color)
    _texto(ax, x + 24, y + 45, modelo.__name__, tam=20, color=color, negrita=True)
    ax.plot([x, x + ancho], [y + 86, y + 86], color=BORDE, lw=1, zorder=3)
    for i, atributo in enumerate(atributos):
        _texto(ax, x + 24, inicio_atributos + i * fila, atributo, tam=11, mono=True)
    ax.plot([x, x + ancho], [separador, separador], color=BORDE, lw=1, zorder=3)
    titulo_metodos = "VALIDADORES DEFINIDOS EN ESTA CLASE" if validadores else "MÉTODOS HEREDADOS"
    _texto(ax, x + 24, separador + 14, titulo_metodos, tam=10, color=GRIS, negrita=True)
    for i, metodo in enumerate(metodos):
        _texto(ax, x + 24, separador + 47 + i * fila, metodo, tam=10, mono=True)
    return alto


def _guardar(fig, directorio: Path, nombre: str) -> list[str]:
    archivos = []
    for extension in ("png", "svg"):
        archivo = directorio / f"{nombre}.{extension}"
        fig.savefig(archivo, dpi=150, facecolor=fig.get_facecolor())
        archivos.append(archivo.name)
    fig.clear()
    return archivos


def _diagrama_clases(directorio: Path) -> list[str]:
    fig, ax = _lienzo(1800, 1640)
    _encabezado(ax, "INGENIERO/A 3  /  MODELO DE VALIDACIÓN", "Diagrama de clases real",
                "Atributos y validadores extraídos de src/modelos_ing3.py. La flecha triangular indica herencia.")
    _caja(ax, 620, 190, 560, 155, AZUL, "#edf3ff")
    _texto(ax, 900, 207, "«Pydantic v2»", tam=11, color=AZUL, ha="center")
    _texto(ax, 900, 233, "BaseModel", tam=21, negrita=True, ha="center")
    _texto(ax, 650, 278, "+ model_validate(datos, context): modelo\n+ model_dump(): dict", tam=11, mono=True)
    # Generalización UML: los dos modelos heredan de la misma clase padre.
    ax.plot([550, 550, 1430, 1430], [420, 382, 382, 420], color=AZUL, lw=2)
    ax.plot([900, 900], [382, 363], color=AZUL, lw=2)
    ax.add_patch(Polygon([(900, 345), (889, 363), (911, 363)], facecolor="white", edgecolor=AZUL, lw=2))
    _clase(ax, TransaccionLimpia, 60, 420, 980, VERDE)
    _clase(ax, RegistroCuarentena, 1120, 420, 620, ROJO)
    _caja(ax, 1120, 960, 620, 270)
    _texto(ax, 1148, 986, "CÓMO PARTICIPAN EN EL PROCESO", tam=12, negrita=True)
    _texto(ax, 1148, 1030,
           "1. Entra una fila del DataFrame como dict.\n"
           "2. TransaccionLimpia.model_validate()\n"
           "   comprueba tipos y reglas de negocio.\n"
           "3. Si es válida, devuelve TransaccionLimpia.\n"
           "4. Si lanza ValidationError, el except crea\n"
           "   un RegistroCuarentena con sus causas.", tam=11, color=GRIS)
    _caja(ax, 1120, 1270, 620, 205, AZUL, "#edf3ff")
    _texto(ax, 1148, 1295, "SALIDA DE AMBAS CLASES", tam=12, color=AZUL, negrita=True)
    _texto(ax, 1148, 1339,
           "model_dump() convierte cada objeto en dict.\n"
           "cargar_base_datos() persiste ambas listas\n"
           "en sus tablas SQLite. El pipeline exporta\n"
           "las mismas listas a archivos CSV.\n"
           "El flujo de datos detalla entradas y salidas.", tam=11, color=GRIS)
    _texto(ax, 60, 1578, "+ miembro público   |   None: valor nulo permitido; no implica que se pueda omitir el campo   |   {...}: restricciones del esquema",
           tam=10, color=GRIS)
    return _guardar(fig, directorio, "diagrama_clases_ing3")


def _numero(resumen, clave):
    valor = resumen.get(clave)
    return f"{valor:,}" if isinstance(valor, int) else "según el lote"


def _rombo(ax, cx, cy, ancho, alto, texto):
    ax.add_patch(Polygon(
        [(cx, cy - alto / 2), (cx + ancho / 2, cy), (cx, cy + alto / 2), (cx - ancho / 2, cy)],
        closed=True, facecolor="#edf3ff", edgecolor=AZUL, linewidth=2, zorder=2,
    ))
    _texto(ax, cx, cy - 45, texto, tam=12, color=AZUL, negrita=True, ha="center")


def _diagrama_pipeline(directorio: Path, resumen: dict) -> list[str]:
    """Vista completa con el orden ejecutado: 1, 2, 4a, 3, 4b, 5, 6 y 7."""
    fig, ax = _lienzo(1900, 3430)
    _encabezado(ax, "PROYECTO FINAL  /  PIPELINE ETL ROBUSTO", "Pipeline robusto por fases",
                "Recorrido completo desde datos crudos hasta SQLite. Los conteos corresponden al último lote validado.")

    for x, titulo, archivo, descripcion in (
        (60, "CAJEROS ATM", "transacciones_atm.csv", "Reintentos, nulos y fechas mixtas"),
        (680, "SPEI / APP", "transferencias_digitales.json", "USD/MXN, CLABEs y correos"),
        (1300, "CORE BANCARIO", "catalogo_cuentas.csv", "Catálogo maestro de cuentas"),
    ):
        _caja(ax, x, 190, 540, 150, AZUL, "#edf3ff")
        _texto(ax, x + 24, 210, titulo, tam=13, color=AZUL, negrita=True)
        _texto(ax, x + 24, 251, archivo, tam=11, mono=True)
        _texto(ax, x + 24, 289, descripcion, tam=11, color=GRIS)
    _flecha(ax, [(330, 340), (330, 390), (950, 390), (950, 430)])
    _flecha(ax, [(950, 340), (950, 430)])
    _flecha(ax, [(1570, 340), (1570, 390), (950, 390), (950, 430)])

    fases = [
        (430, 165, "FASE 1  ·  DIAGNÓSTICO DE CALIDAD", (
            "Carga segura de CSV y JSON; identificadores y CLABEs se conservan como texto.\n"
            "Completitud, nulos ocultos, duplicados, tipos inferidos y hallazgos de validez.\n"
            "Salida: perfiles de calidad antes de transformar los datos."
        )),
        (650, 205, "FASE 2  ·  FALTANTES, IMPUTACIÓN Y DUPLICADOS", (
            "Nulos disfrazados → nulos reales; etiquetas homogéneas; MCAR/MAR.\n"
            "Eliminar solo reintentos exactos; imputar medianas por grupo y etiquetas controladas.\n"
            "No imputar llaves ni corrupción: guardar obs_calidad y banderas de imputación.\n"
            "Salida: tres archivos de fase 2 en data/interim/ y bitácora de cambios."
        )),
        (910, 160, "FASE 4a  ·  INTEGRACIÓN INICIAL Y HOMOLOGACIÓN", (
            "Unir ATM + SPEI; homologar fechas ISO; convertir USD → MXN a 19.50.\n"
            "Se hace antes del IQR para comparar importes en la misma moneda.\n"
            "Conservar operaciones, comisiones y trazabilidad de las fases anteriores."
        )),
        (1125, 180, "FASE 3  ·  OUTLIERS CON IQR Y CAPPING", (
            "Calcular Q1, Q3 e IQR con importes positivos y finitos en MXN.\n"
            "Recortar extremos superiores a Q3 + 1.5 × IQR → monto_mxn_capped.\n"
            "Conservar CONSULTA_SALDO con importe cero.\n"
            "Los importes imposibles o corruptos siguen presentes para rechazo auditable."
        )),
        (1360, 150, "FASE 4b  ·  CRUCE CON EL CATÁLOGO MAESTRO", (
            "Comparar account_id contra las cuentas registradas en Core Bancario.\n"
            "Marcar es_huerfano y su causa, conservando la fila hasta la validación.\n"
            "Salida: DataFrame integrado y conjunto de cuentas válidas."
        )),
        (1565, 160, "FASE 5  ·  TRANSFORMACIÓN, DISCRETIZACIÓN Y ESCALAMIENTO", (
            "Min-Max sobre monto_mxn_capped → monto_minmax en [0, 1].\n"
            "Terciles por importe → nivel_monto: Bajo, Medio o Alto.\n"
            "Registrar mínimo, máximo y cuantiles; tratar lotes vacíos, constantes y empates."
        )),
        (1780, 195, "FASE 6  ·  PYDANTIC Y SEGREGACIÓN POR FILA", (
            "TransaccionLimpia.model_validate(datos, context=...) dentro de try/except.\n"
            "Tipos estrictos; fecha, cuenta, duplicados, CLABE, correo e importes.\n"
            "@field_validator + @model_validator: comprobar coherencia de negocio.\n"
            "Contexto: cuentas válidas del catálogo e identificadores ya aceptados."
        )),
    ]
    anterior = 430
    for y, alto, titulo, cuerpo in fases:
        if y != 430:
            _flecha(ax, [(950, anterior), (950, y)])
        _caja(ax, 340, y, 1220, alto, AZUL, "white")
        _texto(ax, 368, y + 20, titulo, tam=13, color=AZUL, negrita=True)
        _texto(ax, 368, y + 62, cuerpo, tam=12)
        anterior = y + alto

    _caja(ax, 60, 650, 230, 205, BORDE, "#fffdf3")
    _texto(ax, 82, 674, "TRAZABILIDAD", tam=10, negrita=True)
    _texto(ax, 82, 713, "Bitácora, banderas\ny registro original.\nLos errores se\nconservan durante\nlas transformaciones.", tam=10, color=GRIS)
    _caja(ax, 1620, 1360, 220, 185, ROJO, "#fff3f3")
    _texto(ax, 1642, 1382, "HUÉRFANOS", tam=10, color=ROJO, negrita=True)
    _texto(ax, 1642, 1422, "Aquí se marcan.\nEn fase 6 se\nvalidan y desvían\na cuarentena.", tam=10, color=GRIS)

    _flecha(ax, [(950, 1975), (950, 2025)])
    _rombo(ax, 950, 2110, 520, 170, "¿Cumple el\nesquema y las\nreglas de negocio?")
    _flecha(ax, [(690, 2110), (470, 2110), (470, 2290)], VERDE)
    _flecha(ax, [(1210, 2110), (1430, 2110), (1430, 2290)], ROJO)
    _texto(ax, 440, 2142, "SÍ · modelo válido", tam=11, color=VERDE, negrita=True, ha="right")
    _texto(ax, 1460, 2142, "NO · ValidationError", tam=11, color=ROJO, negrita=True)
    _caja(ax, 60, 2290, 820, 220, VERDE, "#effaf4")
    _texto(ax, 88, 2313, f"{_numero(resumen, 'limpias_cargadas')} REGISTROS APTOS", tam=18, color=VERDE, negrita=True)
    _texto(ax, 88, 2365,
           "list[TransaccionLimpia]\nCampos validados + variables derivadas + datos_origen_json.\n"
           "Preparados para la tabla transacciones_limpias.", tam=12)
    _caja(ax, 1020, 2290, 820, 220, ROJO, "#fff3f3")
    _texto(ax, 1048, 2313, f"{_numero(resumen, 'cuarentena_cargada')} REGISTROS EN CUARENTENA", tam=18, color=ROJO, negrita=True)
    _texto(ax, 1048, 2365,
           "list[RegistroCuarentena]\nFila, identificador, motivo, errores y registro recibido.\n"
           "El error de una fila permite continuar con la siguiente.", tam=12)
    _flecha(ax, [(470, 2510), (470, 2580)], VERDE)
    _flecha(ax, [(1430, 2510), (1430, 2580)], ROJO)

    _caja(ax, 340, 2580, 1220, 170, AZUL, "#edf3ff")
    _texto(ax, 368, 2602, "FASE 7  ·  CARGA TRANSACCIONAL DE AMBAS LISTAS", tam=13, color=AZUL, negrita=True)
    _texto(ax, 368, 2646,
           "BEGIN IMMEDIATE → INSERT parametrizados en transacciones_limpias y cuarentena_errores.\n"
           "Los ejecutores reemplazan ambas tablas dentro de la misma transacción.\n"
           "Un fallo en la segunda tabla también debe revertir los cambios de la primera.", tam=12)
    _flecha(ax, [(950, 2750), (950, 2815)])
    _rombo(ax, 950, 2910, 500, 190, "¿Se cargaron\nambas tablas\nsin error SQL?")
    _flecha(ax, [(700, 2910), (620, 2910)], VERDE)
    _flecha(ax, [(1200, 2910), (1280, 2910)], ROJO)
    _texto(ax, 660, 2876, "SÍ", tam=11, color=VERDE, negrita=True, ha="center")
    _texto(ax, 1240, 2876, "NO", tam=11, color=ROJO, negrita=True, ha="center")
    _caja(ax, 60, 2820, 560, 180, VERDE, "#effaf4")
    _texto(ax, 88, 2845, "conn.commit()", tam=18, color=VERDE, negrita=True)
    _texto(ax, 88, 2899, "Se confirma la transacción.\nAmbas tablas quedan persistidas.", tam=12)
    _caja(ax, 1280, 2820, 560, 180, ROJO, "#fff3f3")
    _texto(ax, 1308, 2845, "conn.rollback()", tam=18, color=ROJO, negrita=True)
    _texto(ax, 1308, 2899, "Se revierte TODO el lote.\nSe conserva el contenido previo.", tam=12)
    _flecha(ax, [(340, 3000), (340, 3100)], VERDE)
    _flecha(ax, [(1560, 3000), (1560, 3100)], ROJO)
    _caja(ax, 60, 3100, 1080, 180, VERDE, "white")
    _texto(ax, 88, 3123, "SALIDAS CONFIRMADAS", tam=13, color=VERDE, negrita=True)
    _texto(ax, 88, 3166,
           "data/proyecto_final.sqlite3: transacciones_limpias + cuarentena_errores.\n"
           "reportes/ing3/: CSV, resumen JSON, evidencia y diagramas.\n"
           "PRAGMA integrity_check: verificación de integridad de SQLite.", tam=12)
    _caja(ax, 1280, 3100, 560, 180, ROJO, "white")
    _texto(ax, 1308, 3123, "LOTE NO CONFIRMADO", tam=13, color=ROJO, negrita=True)
    _texto(ax, 1308, 3166, "Reportar el error de persistencia.\nCorregir la causa antes de reintentar.\nLa conexión se cierra en finally.", tam=12)
    _texto(ax, 950, 3330,
           f"BALANCE DEL LOTE VALIDADO: {_numero(resumen, 'registros_entrada')} entradas = "
           f"{_numero(resumen, 'limpias_cargadas')} aptas + {_numero(resumen, 'cuarentena_cargada')} en cuarentena",
           tam=13, color=AZUL, negrita=True, ha="center")
    _texto(ax, 950, 3375,
           "Ejecutor completo: python -m src.Todas_las_fases  |  run_ing3.py reutiliza las salidas de fase 2.",
           tam=11, color=GRIS, ha="center")
    return _guardar(fig, directorio, "pipeline_robusto_por_fases")


def _diagrama_flujo(directorio: Path, resumen: dict) -> list[str]:
    fig, ax = _lienzo(1500, 2090)
    _encabezado(ax, "INGENIERO/A 3  /  ENTRADAS Y SALIDAS", "Cómo entra, se valida y sale cada registro",
                "Los conteos corresponden a la ejecución que generó estos diagramas.")
    _caja(ax, 60, 190, 1380, 185, AZUL, "#edf3ff")
    _texto(ax, 88, 211, "ENTRADA  ·  ARCHIVOS PREPARADOS POR INGENIERÍA 1", tam=13, color=AZUL, negrita=True)
    _texto(ax, 88, 257,
           "transacciones_atm_fase2.csv  +  transferencias_digitales_fase2.json\n"
           "catalogo_cuentas_fase2.csv  →  conjunto de cuentas válidas\n"
           "Estas entradas se leen de data/interim/.", tam=13)
    _flecha(ax, [(750, 375), (750, 425)])
    _caja(ax, 60, 425, 1380, 155)
    _texto(ax, 88, 447, "INTEGRACIÓN REUTILIZADA  ·  FASES 3 Y 4", tam=13, negrita=True)
    _texto(ax, 88, 489,
           "Fechas ISO, USD → MXN a 19.50, capping IQR y marca de cuenta huérfana.\n"
           f"Sale un DataFrame integrado con {_numero(resumen, 'registros_entrada')} filas; conserva evidencia de calidad.", tam=13)
    _flecha(ax, [(750, 580), (750, 635)])
    _caja(ax, 60, 635, 1380, 175, AZUL, "#edf3ff")
    _texto(ax, 88, 657, "FASE 5  ·  TRANSFORMACIÓN", tam=13, color=AZUL, negrita=True)
    _texto(ax, 88, 700,
           "Entra: monto_mxn_capped, en pesos.\n"
           "Se agregan: monto_minmax ∈ [0, 1] y nivel_monto ∈ {Bajo, Medio, Alto}.\n"
           "Salida: el mismo DataFrame con columnas derivadas; los corruptos siguen disponibles para rechazo.", tam=13)
    _flecha(ax, [(750, 810), (750, 865)])
    _caja(ax, 60, 865, 1380, 210)
    _texto(ax, 88, 888, "FASE 6  ·  segregar_registros(df, cuentas_validas)", tam=13, negrita=True)
    _texto(ax, 88, 931,
           "Por cada fila: dict → TransaccionLimpia.model_validate(datos, context=...).\n"
           "Contexto: cuentas del catálogo e identificadores ya aceptados.\n"
           "Validación: tipos estrictos, fecha, CLABE, correo, importes y coherencia de negocio.\n"
           "try: devuelve un modelo válido   /   except ValidationError: conserva las causas y el registro.", tam=13)
    _flecha(ax, [(420, 1075), (420, 1150)], VERDE)
    _flecha(ax, [(1080, 1075), (1080, 1150)], ROJO)
    _texto(ax, 450, 1097, "VALIDACIÓN CORRECTA", tam=10, color=VERDE, negrita=True)
    _texto(ax, 1050, 1097, "VALIDATIONERROR CAPTURADO", tam=10, color=ROJO, ha="right", negrita=True)
    _caja(ax, 60, 1150, 650, 260, VERDE, "#effaf4")
    _texto(ax, 88, 1174, f"{_numero(resumen, 'limpias_cargadas')} REGISTROS VÁLIDOS", tam=18, color=VERDE, negrita=True)
    _texto(ax, 88, 1225,
           "list[TransaccionLimpia]\n"
           "Contiene los campos validados, las variables\n"
           "transformadas y datos_origen_json.\n\n"
           "Ejemplo aceptable de CLABE SPEI:\n"
           "012210100614023846 (texto, 18 dígitos).", tam=12)
    _caja(ax, 790, 1150, 650, 260, ROJO, "#fff3f3")
    _texto(ax, 818, 1174, f"{_numero(resumen, 'cuarentena_cargada')} REGISTROS RECHAZADOS", tam=18, color=ROJO, negrita=True)
    _texto(ax, 818, 1225,
           "list[RegistroCuarentena]\n"
           "Guarda número de fila, identificador, motivo,\n"
           "errores estructurados y registro recibido.\n\n"
           "Ejemplo: CLABE '12345' → motivo de rechazo.\n"
           "El procesamiento continúa con la siguiente fila.", tam=12)
    _flecha(ax, [(385, 1410), (385, 1485)], VERDE)
    _flecha(ax, [(1115, 1410), (1115, 1485)], ROJO)
    _caja(ax, 60, 1485, 1380, 270, AZUL, "#edf3ff")
    _texto(ax, 88, 1509, "FASE 7  ·  SQLite: cargar_base_datos(limpios, cuarentena, ruta_bd)", tam=13, color=AZUL, negrita=True)
    _texto(ax, 88, 1554,
           "BEGIN IMMEDIATE → INSERT parametrizados en las DOS tablas:\n"
           "   transacciones_limpias                       cuarentena_errores\n"
           "Todo correcto → commit(): ambas tablas quedan persistidas.\n"
           "Error SQL → rollback(): se revierte el lote completo, incluidos los DELETE de reemplazo.\n"
           "Archivo predeterminado: data/proyecto_final.sqlite3", tam=13)
    _flecha(ax, [(750, 1755), (750, 1810)])
    _caja(ax, 60, 1810, 1380, 180)
    _texto(ax, 88, 1834, "ARCHIVOS DE SALIDA  ·  DESPUÉS DEL COMMIT", tam=13, negrita=True)
    _texto(ax, 88, 1878,
           "reportes/ing3/: fase5_transformadas.csv, transacciones_limpias.csv y cuarentena_errores.csv\n"
           "resumen_ing3.json: conteos, parámetros Min-Max/cuantiles e integridad de SQLite.\n"
           "diagramas/: pipeline por fases, UML, flujo de datos y visor con los conteos de este lote.", tam=12)
    _texto(ax, 750, 2030,
           f"BALANCE DEL LOTE: {_numero(resumen, 'registros_entrada')} entradas = "
           f"{_numero(resumen, 'limpias_cargadas')} limpias + {_numero(resumen, 'cuarentena_cargada')} en cuarentena",
           tam=13, color=AZUL, negrita=True, ha="center")
    return _guardar(fig, directorio, "flujo_entradas_salidas_ing3")


def _mermaid_clases() -> str:
    lineas = ["classDiagram", "direction TB", "class BaseModel {", "+model_validate(datos, context)", "+model_dump() dict", "}"]
    for modelo in (TransaccionLimpia, RegistroCuarentena):
        lineas.append(f"BaseModel <|-- {modelo.__name__}")
        lineas.append(f"class {modelo.__name__} {{")
        for nombre, campo in modelo.model_fields.items():
            tipo = "str" if get_origin(campo.annotation) is Literal else _tipo(campo.annotation).replace(" | ", "_o_")
            lineas.append(f"+{tipo} {nombre}")
        lineas.extend(f"+{nombre}(...)" for nombre, _ in _validadores(modelo))
        lineas.append("}")
    lineas.append('note for RegistroCuarentena "Se crea al capturar ValidationError; conserva causas y registro original."')
    return "\n".join(lineas) + "\n"


def _mermaid_flujo(resumen: dict) -> str:
    return f'''flowchart TD
    A["ATM CSV + transferencias JSON de fase 2"] --> I["Integracion: fechas, moneda, IQR y huerfanos"]
    C["Catalogo de cuentas"] --> I
    C --> V
    I --> T["Fase 5: monto_minmax y nivel_monto"]
    T --> V["Fase 6: TransaccionLimpia.model_validate por fila"]
    V -->|Valido| L["list de TransaccionLimpia: {_numero(resumen, 'limpias_cargadas')}"]
    V -->|except ValidationError| Q["list de RegistroCuarentena: {_numero(resumen, 'cuarentena_cargada')}"]
    L --> B["Fase 7: una transaccion SQLite para ambas tablas"]
    Q --> B
    B -->|Todo correcto| COMMIT["commit: transacciones_limpias y cuarentena_errores"]
    B -->|Error SQL| R["rollback del lote completo"]
    COMMIT --> S["CSV, resumen JSON y diagramas visuales"]
'''


def _mermaid_pipeline(resumen: dict) -> str:
    return f'''flowchart TD
    A["datasets/transacciones_atm.csv"] --> F1
    B["datasets/transferencias_digitales.json"] --> F1
    C["datasets/catalogo_cuentas.csv"] --> F1
    F1["FASE 1 · Diagnostico: completitud, unicidad, tipos y validez"] --> F2
    F2["FASE 2 · MCAR/MAR, medianas, etiquetas, reintentos y trazabilidad"] --> F4A
    F4A["FASE 4a · Unir fuentes, fechas ISO y USD a MXN a 19.50"] --> F3
    F3["FASE 3 · IQR y capping en MXN; conservar consultas de saldo cero"] --> F4B
    F4B["FASE 4b · Cruce con catalogo; marcar cuentas huerfanas"] --> F5
    F5["FASE 5 · Min-Max 0 a 1 y terciles Bajo, Medio, Alto"] --> F6
    F6["FASE 6 · BaseModel, field_validator y model_validator por fila"] --> D
    D{{"Cumple esquema y reglas?"}} -->|Si| L["list TransaccionLimpia: {_numero(resumen, 'limpias_cargadas')}"]
    D -->|except ValidationError| Q["list RegistroCuarentena: {_numero(resumen, 'cuarentena_cargada')} · causas y registro recibido"]
    L --> F7
    Q --> F7
    F7["FASE 7 · BEGIN IMMEDIATE e INSERT parametrizados en ambas tablas"] --> SQL
    SQL{{"Ambas cargas sin error SQL?"}} -->|Si| OK["conn.commit: confirmar ambas tablas"]
    SQL -->|No| ERROR["conn.rollback: revertir el lote completo"]
    OK --> DB[("SQLite: transacciones_limpias y cuarentena_errores")]
    DB --> OUT["CSV, resumen JSON, integridad y diagramas"]
    ERROR --> FIN["Conservar contenido previo y reportar fallo de persistencia"]
    classDef fase fill:#edf3ff,stroke:#2557a7,color:#19283f
    classDef valido fill:#effaf4,stroke:#15734c,color:#15734c
    classDef rechazo fill:#fff3f3,stroke:#ad3442,color:#ad3442
    class F1,F2,F4A,F3,F4B,F5,F6,F7 fase
    class L,OK,DB,OUT valido
    class Q,ERROR,FIN rechazo
'''


def _visor(directorio: Path, resumen: dict) -> str:
    paneles = []
    pestañas = []
    for indice, (nombre, titulo) in enumerate((
        ("pipeline_robusto_por_fases", "Pipeline por fases"),
        ("diagrama_clases_ing3", "Clases Pydantic"),
        ("flujo_entradas_salidas_ing3", "Entradas y salidas"),
    )):
        pestañas.append(f'<button data-panel="{indice}" aria-selected="{str(indice == 0).lower()}">{titulo}</button>')
        svg = (directorio / f"{nombre}.svg").read_text(encoding="utf-8")
        svg = svg[svg.index("<svg"):]
        paneles.append(
            f'<section id="panel-{indice}" {"hidden" if indice else ""} aria-label="{titulo}">'
            f'<p class="descargas"><a href="{nombre}.png">Descargar PNG</a> · '
            f'<a href="{nombre}.svg">Abrir SVG</a> · <a href="{nombre}.mmd">Fuente Mermaid</a></p>{svg}</section>'
        )
    html = '''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pipeline robusto por fases y modelo de datos</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f5f8fc;color:#19283f;font-family:Segoe UI,Arial,sans-serif}
header,main{max-width:1500px;margin:auto;padding:24px}header{padding-bottom:10px}
h1{font-size:30px;margin:10px 0}p{line-height:1.6}.meta{color:#52637a}.conteos{display:flex;gap:14px;flex-wrap:wrap}
.dato{background:white;border:1px solid #d2dce9;border-radius:12px;padding:12px 20px}.dato strong{display:block;font-size:25px}
nav{display:flex;gap:10px;flex-wrap:wrap;margin-top:24px}button{padding:12px 22px;border:1px solid #2557a7;border-radius:9px;color:#2557a7;background:white;font:inherit;cursor:pointer}
button[aria-selected=true]{background:#2557a7;color:white}section{background:white;border:1px solid #d2dce9;border-radius:14px;overflow:hidden}
section[hidden]{display:none}svg{display:block;width:100%;height:auto}.descargas{padding:0 24px}a{color:#2557a7}
@media print{nav,.descargas{display:none}section[hidden]{display:block}section{break-after:page;border:none}header{display:none}}
</style></head><body><header><p class="meta">PROYECTO FINAL · PIPELINE ETL ROBUSTO</p>
<h1>Pipeline por fases, clases y flujo de datos</h1>
<p>Las siete fases del equipo, el modelo Pydantic y el detalle de entradas y salidas. Los conteos se actualizan con cada ejecución.</p>
<div class="conteos">__CONTEOS__</div>
<nav aria-label="Elegir diagrama">__PESTANAS__</nav>
</header><main>__PANELES__</main>
<script>document.querySelectorAll('button[data-panel]').forEach(b=>b.addEventListener('click',()=>{
document.querySelectorAll('section').forEach((p,i)=>p.hidden=String(i)!==b.dataset.panel);
document.querySelectorAll('button[data-panel]').forEach(x=>x.setAttribute('aria-selected',String(x===b)));
}));</script></body></html>
'''
    conteos = "".join(
        f'<div class="dato"><strong>{escape(_numero(resumen, clave))}</strong>{etiqueta}</div>'
        for clave, etiqueta in (("registros_entrada", "filas de entrada"), ("limpias_cargadas", "transacciones válidas"),
                                ("cuarentena_cargada", "registros en cuarentena"))
    )
    return html.replace("__CONTEOS__", conteos).replace("__PANELES__", "".join(paneles)).replace("__PESTANAS__", "".join(pestañas))


def generar_diagramas(directorio: str | Path, resumen: dict | None = None) -> dict[str, str]:
    salida = Path(directorio)
    salida.mkdir(parents=True, exist_ok=True)
    resumen = resumen or {}
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "svg.fonttype": "none"}):
        nombres = _diagrama_pipeline(salida, resumen) + _diagrama_clases(salida) + _diagrama_flujo(salida, resumen)
    (salida / "pipeline_robusto_por_fases.mmd").write_text(_mermaid_pipeline(resumen), encoding="utf-8")
    (salida / "diagrama_clases_ing3.mmd").write_text(_mermaid_clases(), encoding="utf-8")
    (salida / "flujo_entradas_salidas_ing3.mmd").write_text(_mermaid_flujo(resumen), encoding="utf-8")
    (salida / "ver_diagramas.html").write_text(_visor(salida, resumen), encoding="utf-8")
    nombres += ["pipeline_robusto_por_fases.mmd", "diagrama_clases_ing3.mmd", "flujo_entradas_salidas_ing3.mmd", "ver_diagramas.html"]
    return {Path(nombre).stem + "_" + Path(nombre).suffix[1:]: nombre for nombre in nombres}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reportes", type=Path, default=Path(__file__).resolve().parent.parent / "reportes" / "ing3")
    args = parser.parse_args()
    ruta_resumen = args.reportes / "resumen_ing3.json"
    resumen = json.loads(ruta_resumen.read_text(encoding="utf-8")) if ruta_resumen.exists() else {}
    archivos = generar_diagramas(args.reportes / "diagramas", resumen)
    for archivo in archivos.values():
        print(args.reportes / "diagramas" / archivo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
