"""Fase 5: Min-Max y terciles sobre importes en MXN después del capping."""
from __future__ import annotations

from numbers import Real

import numpy as np
import pandas as pd


def transformacion_discretizacion_escalado(df: pd.DataFrame) -> pd.DataFrame:
    """No imputa corrupción ni reparte importes iguales por orden de llegada.

    Bajo: x <= P33; Medio: P33 < x <= P67; Alto: x > P67.
    Con pocos valores distintos puede haber segmentos vacíos. Un lote constante
    se escala a cero y pertenece a Bajo. Los datos inválidos llegan a la fase 6.
    """
    salida = df.copy()
    montos = salida["monto_mxn_capped"]
    aptos = montos.map(
        lambda x: isinstance(x, Real) and not isinstance(x, (bool, np.bool_))
        and np.isfinite(x) and x >= 0
    )
    valores = montos.loc[aptos].astype(float)
    salida["monto_minmax"] = np.nan
    salida["nivel_monto"] = pd.Series(None, index=salida.index, dtype=object)
    parametros = {"minimo": None, "maximo": None, "p33": None, "p67": None}
    if not valores.empty:
        minimo, maximo = float(valores.min()), float(valores.max())
        p33, p67 = (float(x) for x in valores.quantile([1 / 3, 2 / 3]))
        salida.loc[aptos, "monto_minmax"] = (
            (valores - minimo) / (maximo - minimo) if maximo != minimo else 0.0
        )
        salida.loc[aptos, "nivel_monto"] = np.select(
            [valores <= p33, valores <= p67], ["Bajo", "Medio"], default="Alto"
        )
        parametros = {"minimo": minimo, "maximo": maximo, "p33": p33, "p67": p67}
    salida.attrs["parametros_fase5"] = {
        **parametros, "columna": "monto_mxn_capped", "metodo": "terciles_por_importe",
        "registros_para_ajuste": len(valores),
        "regla": "Bajo <= P33; P33 < Medio <= P67; Alto > P67; constante => Bajo y 0",
    }
    return salida
