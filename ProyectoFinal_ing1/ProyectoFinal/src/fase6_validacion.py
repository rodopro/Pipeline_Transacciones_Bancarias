"""Segregación por fila: un ValidationError no detiene el resto del lote."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
from pydantic import ValidationError

from .modelos_ing3 import RegistroCuarentena, TransaccionLimpia


def _python(valor):
    """Adapta escalares de pandas/numpy sin convertir textos a números."""
    if valor is pd.NA or valor is pd.NaT:
        return None
    if isinstance(valor, np.generic):
        valor = valor.item()
    if isinstance(valor, float) and math.isnan(valor):
        return None
    return valor


def _json_seguro(valor):
    if isinstance(valor, (float, np.floating)) and not math.isfinite(valor):
        return str(valor)
    valor = _python(valor)
    if isinstance(valor, dict):
        return {str(k): _json_seguro(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_json_seguro(v) for v in valor]
    if isinstance(valor, float) and not math.isfinite(valor):
        return str(valor)  # Conserva evidencia de nan/inf; JSON estándar no los admite.
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def serializar_registro(registro: dict) -> str:
    return json.dumps(_json_seguro(registro), ensure_ascii=False, allow_nan=False)


def segregar_registros(df: pd.DataFrame, cuentas_validas: set[str]):
    limpios: list[TransaccionLimpia] = []
    cuarentena: list[RegistroCuarentena] = []
    vistos: set[str] = set()
    for numero, original in enumerate(df.to_dict(orient="records"), start=1):
        fila = {k: _python(v) for k, v in original.items()}
        # Proyección explícita: las columnas auxiliares de las fases 1-4 se
        # conservan en JSON, pero no forman parte del esquema de la tabla final.
        datos = {k: fila[k] for k in TransaccionLimpia.model_fields if k in fila}
        datos["datos_origen_json"] = serializar_registro(original)
        try:
            registro = TransaccionLimpia.model_validate(
                datos, context={"cuentas_validas": cuentas_validas, "ids_vistos": vistos}
            )
            limpios.append(registro)
            vistos.add(registro.transaccion_id)
        except ValidationError as error:
            errores = error.errors(include_url=False, include_context=False, include_input=False)
            motivo = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'registro'}: {e['msg']}" for e in errores
            )
            previo = fila.get("motivo_rechazo_cuarentena")
            if isinstance(previo, str) and previo.strip():
                motivo = f"{previo}; {motivo}"
            cuarentena.append(RegistroCuarentena(
                numero_fila=numero,
                transaccion_id=fila.get("transaccion_id") if isinstance(fila.get("transaccion_id"), str) else None,
                tipo_origen=fila.get("tipo_origen") if isinstance(fila.get("tipo_origen"), str) else None,
                motivo_rechazo_cuarentena=motivo,
                errores_validacion_json=json.dumps(errores, ensure_ascii=False),
                registro_original_json=datos["datos_origen_json"],
            ))
    return limpios, cuarentena
