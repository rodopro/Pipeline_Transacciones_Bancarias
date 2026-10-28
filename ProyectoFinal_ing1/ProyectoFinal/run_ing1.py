"""
Ejecuta las Fases 1 y 2 del pipeline (Ingeniero/a 1) y genera todas las evidencias.

Uso (desde la raíz del proyecto):
    python run_ing1.py

Salidas:
    reportes/ing1/*.csv            -> perfiles, pruebas MCAR/MAR, bitácora, comparativo
    reportes/ing1/figuras/*.png    -> gráficas de evidencia
    data/interim/*_fase2.*         -> datos listos para la Fase 3 / Ingeniero/a 2
"""
from __future__ import annotations

import json
import sys
import time

import pandas as pd

from src import config as C
from src import fase1_diagnostico as F1
from src import fase2_imputacion as F2
from src import figuras_ing1 as FIG

ENC = "utf-8-sig"  # BOM para que Excel en Windows muestre bien los acentos


def _guardar(df: pd.DataFrame, nombre: str):
    ruta = C.DIR_REPORTES / nombre
    df.to_csv(ruta, index=False, encoding=ENC)
    print(f"   ✔ {ruta.relative_to(C.RAIZ)}  ({len(df)} filas)")


def fase1():
    print("\n=== FASE 1: DIAGNÓSTICO DE CALIDAD INICIAL ===")
    disfrazados = F1.explorar_nulos_disfrazados()        # keep_default_na=False, dtype=str
    ingenuo = F1.cargar_crudo_ingenuo()
    seguro = F1.cargar_crudo_seguro()                    # na_values explícitos
    perfil_cols, perfil_res = F1.perfil_completo(ingenuo)
    ranking = F1.ranking_completitud(perfil_cols)
    _guardar(disfrazados, "f1_nulos_disfrazados.csv")
    _guardar(ranking, "f1_ranking_completitud.csv")
    tipos = F1.comparar_tipos(ingenuo, seguro)
    hall = F1.hallazgos_validez(seguro, ingenuo)
    _guardar(perfil_res, "f1_resumen_datasets_crudo.csv")
    _guardar(perfil_cols, "f1_perfil_columnas_crudo.csv")
    _guardar(tipos, "f1_tipos_inferidos.csv")
    _guardar(hall, "f1_hallazgos_validez.csv")
    print(perfil_res[["dataset", "filas", "completitud_global_pct", "duplicados_exactos",
                      "duplicados_por_llave"]].to_string(index=False))
    return ingenuo, seguro, perfil_cols, perfil_res


def fase2(seguro, perfil_cols_antes, perfil_res_antes):
    print("\n=== FASE 2: MANEJO DE FALTANTES E IMPUTACIÓN ===")
    atm, dup_atm, p_atm, log_atm, med_atm = F2.procesar_atm(seguro["transacciones_atm"])
    tr, dup_tr, p_tr, log_tr, med_tr = F2.procesar_transferencias(seguro["transferencias_digitales"])
    cat = F2.normalizar_etiquetas(F2.normalizar_nulos(seguro["catalogo_cuentas"]),
                                  ["tipo_cuenta", "estado_cuenta"])

    pruebas = pd.concat([p_atm, p_tr], ignore_index=True)
    bitacora = pd.concat([log_atm, log_tr], ignore_index=True)
    duplicados = pd.concat([dup_atm.assign(dataset="transacciones_atm")], ignore_index=True)
    med_atm["dataset"], med_atm["variable"] = "transacciones_atm", "monto_mxn"
    med_tr["dataset"], med_tr["variable"] = "transferencias_digitales", "amount"
    medianas = pd.concat([med_atm.rename(columns={"tipo_operacion": "grupo"}),
                          med_tr.rename(columns={"currency": "grupo"})], ignore_index=True)

    _guardar(pruebas, "f2_pruebas_mcar_mar.csv")
    _guardar(bitacora, "f2_bitacora_imputacion.csv")
    _guardar(duplicados, "f2_duplicados_eliminados.csv")
    _guardar(medianas[["dataset", "variable", "grupo", "mediana"]], "f2_medianas_usadas.csv")
    try:
        a_ded, _ = F2.eliminar_duplicados_exactos(F2.normalizar_etiquetas(
            seguro["transacciones_atm"], ["tipo_operacion", "resultado"]))
        comp_si = F2.comparar_con_simpleimputer(a_ded)
        comp_si["categorica_equivale_SimpleImputer_constant"] = comp_si.attrs["categorica_equivalente"]
        _guardar(comp_si, "f2_comparacion_simpleimputer.csv")
    except ImportError:
        print("   (scikit-learn no instalado: se omite la comparación con SimpleImputer)")

    # ---------- Comparativo antes / después ----------
    despues = {"catalogo_cuentas": cat, "transacciones_atm": atm, "transferencias_digitales": tr}
    originales = {k: list(v.columns) for k, v in seguro.items()}
    pc_desp, pr_desp = F1.perfil_completo({k: v[originales[k]] for k, v in despues.items()})
    _guardar(pc_desp, "f2_perfil_columnas_post.csv")

    comp = perfil_cols_antes[["dataset", "columna", "dtype_inferido", "total_ausentes", "pct_nulos"]].merge(
        pc_desp[["dataset", "columna", "dtype_inferido", "total_ausentes", "pct_nulos"]],
        on=["dataset", "columna"], suffixes=("_antes", "_despues"))
    comp = comp.rename(columns={"total_ausentes_antes": "nulos_antes",
                                "total_ausentes_despues": "nulos_despues"})
    comp["pct_completitud_antes"] = 100 - comp["pct_nulos_antes"]
    comp["pct_completitud_despues"] = 100 - comp["pct_nulos_despues"]
    _guardar(comp, "comparativo_columnas_antes_despues.csv")

    res = perfil_res_antes[["dataset", "filas", "celdas_ausentes", "completitud_global_pct",
                            "duplicados_exactos", "duplicados_por_llave"]].merge(
        pr_desp[["dataset", "filas", "celdas_ausentes", "completitud_global_pct",
                 "duplicados_exactos", "duplicados_por_llave"]],
        on="dataset", suffixes=("_antes", "_despues"))
    _guardar(res, "comparativo_datasets_antes_despues.csv")

    est = pd.concat([
        F2.estadisticos_antes_despues(seguro["transacciones_atm"]["monto_mxn"], atm["monto_mxn"], "monto_mxn (ATM)"),
        F2.estadisticos_antes_despues(seguro["transferencias_digitales"]["amount"], tr["amount"], "amount (SPEI)"),
    ], ignore_index=True)
    _guardar(est, "comparativo_estadisticos_monto.csv")

    # ---------- Datos para la siguiente fase ----------
    C.DIR_INTERIM.mkdir(parents=True, exist_ok=True)
    atm.to_csv(C.DIR_INTERIM / "transacciones_atm_fase2.csv", index=False, encoding="utf-8")
    cat.to_csv(C.DIR_INTERIM / "catalogo_cuentas_fase2.csv", index=False, encoding="utf-8")
    registros = json.loads(tr.to_json(orient="records", force_ascii=False))
    with open(C.DIR_INTERIM / "transferencias_digitales_fase2.json", "w", encoding="utf-8") as fh:
        json.dump(registros, fh, ensure_ascii=False, indent=2)
    print("   ✔ data/interim/*_fase2.*  (entrada para Fase 3 / Ingeniero/a 2)")

    # ---------- Figuras ----------
    FIG.completitud_antes_despues(comp, C.DIR_FIGURAS / "01_nulos_antes_despues.png")
    FIG.mapa_nulos(seguro["transacciones_atm"], "msno.matrix – transacciones_atm (crudo)",
                   C.DIR_FIGURAS / "02_mapa_nulos_atm.png")
    FIG.mapa_nulos(seguro["transferencias_digitales"].drop(columns=["timestamp"]),
                   "msno.matrix – transferencias (8 null + 8 '' ocultos)",
                   C.DIR_FIGURAS / "03_mapa_nulos_transferencias.png")
    FIG.barras_completitud(seguro["transacciones_atm"], "msno.bar – registros con dato por columna (ATM)",
                           C.DIR_FIGURAS / "02b_barras_completitud_atm.png")
    FIG.heatmap_nulidad(seguro["transacciones_atm"], "msno.heatmap – correlación de nulidad (ATM)",
                        C.DIR_FIGURAS / "02c_heatmap_nulidad_atm.png")
    FIG.distribucion_sesgada(seguro["transacciones_atm"]["monto_mxn"],
                             "monto_mxn ATM (> 0)", "MXN", C.DIR_FIGURAS / "04_sesgo_monto_atm.png")
    FIG.distribucion_sesgada(seguro["transferencias_digitales"]["amount"],
                             "amount SPEI", "importe", C.DIR_FIGURAS / "05_sesgo_amount_spei.png")

    def p_de(var, expl):
        r = pruebas[(pruebas.variable_con_nulos == var) & (pruebas.variable_explicativa == expl)]
        return float(r.p_valor.iloc[0]) if len(r) else None
    a_ded, _ = F2.eliminar_duplicados_exactos(F2.normalizar_etiquetas(
        seguro["transacciones_atm"], ["tipo_operacion", "resultado"]))
    FIG.tasa_nulos_por_grupo(a_ded[a_ded.tipo_operacion != "CONSULTA_SALDO"], "monto_mxn",
                             "tipo_operacion", "% monto_mxn nulo por tipo de operación",
                             C.DIR_FIGURAS / "06_nulos_monto_por_tipo.png", p_de("monto_mxn", "tipo_operacion"))
    FIG.tasa_nulos_por_grupo(a_ded, "id_cajero", "resultado", "% id_cajero nulo por resultado",
                             C.DIR_FIGURAS / "07_nulos_cajero_por_resultado.png", p_de("id_cajero", "resultado"))
    t_norm = F2.normalizar_etiquetas(F2.normalizar_nulos(seguro["transferencias_digitales"]), ["status"])
    FIG.tasa_nulos_por_grupo(t_norm, "notification_email", "status", "% email nulo por status",
                             C.DIR_FIGURAS / "08_nulos_email_por_status.png",
                             p_de("notification_email", "status"))
    print("   ✔ reportes/ing1/figuras/*.png")
    print("\nConclusiones MCAR/MAR:")
    print(pruebas.groupby(["dataset", "variable_con_nulos"])["conclusion"].first().to_string())
    return despues


def main():
    t0 = time.time()
    C.DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    _, seguro, pc, pr = fase1()
    fase2(seguro, pc, pr)
    print(f"\nListo en {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
