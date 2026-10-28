"""Figuras de evidencia para el reporte de calidad (Ingeniero/a 1)."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

AZUL, NARANJA, GRIS, TINTA, TINTA2 = "#2a78d6", "#eb6834", "#8a8984", "#0b0b0b", "#52514e"
plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 160, "font.size": 9.5,
    "axes.edgecolor": "#c9c8c2", "axes.labelcolor": TINTA2, "xtick.color": TINTA2,
    "ytick.color": TINTA2, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": TINTA,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": "#ebeae6", "grid.linewidth": 0.8,
})


def completitud_antes_despues(comp: pd.DataFrame, ruta):
    """Barras horizontales: % nulos por columna antes vs después (solo columnas con nulos)."""
    d = comp[(comp["pct_nulos_antes"] > 0) | (comp["pct_nulos_despues"] > 0)].copy()
    d["etq"] = d["dataset"].str.replace("transacciones_", "").str.replace("transferencias_", "") + " · " + d["columna"]
    y = np.arange(len(d))
    fig, ax = plt.subplots(figsize=(7.2, 0.55 * len(d) + 1.4))
    ax.barh(y + 0.2, d["pct_nulos_antes"], 0.36, color=AZUL, label="Antes (crudo)")
    ax.barh(y - 0.2, d["pct_nulos_despues"], 0.36, color=NARANJA, label="Después (Fase 2)")
    for i, (a, b) in enumerate(zip(d["pct_nulos_antes"], d["pct_nulos_despues"])):
        ax.text(a + 0.15, i + 0.2, f"{a:.2f}%", va="center", fontsize=8.5, color=TINTA)
        ax.text(b + 0.15, i - 0.2, f"{b:.2f}%", va="center", fontsize=8.5, color=TINTA)
    ax.set_yticks(y, d["etq"])
    ax.invert_yaxis()
    ax.set_xlabel("% de valores nulos")
    ax.set_title("Nulos por columna: antes vs después de la Fase 2", loc="left")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout(); fig.savefig(ruta); plt.close(fig)


def _msno():
    try:
        import missingno as msno
        return msno
    except ImportError:          # missingno es opcional: se usa el respaldo en matplotlib
        return None


def mapa_nulos(df: pd.DataFrame, titulo: str, ruta):
    """Matriz de nulos con missingno (msno.matrix), como en la sesión 22.
    Cada línea blanca = registro con nulo en esa columna."""
    msno = _msno()
    if msno is not None:
        ax = msno.matrix(df, figsize=(9, 4), fontsize=9, sparkline=False, color=(0.16, 0.47, 0.84))
        ax.set_title(titulo, loc="left", fontsize=11, fontweight="bold")
        fig = ax.get_figure()
    else:
        m = df.isna().to_numpy()
        fig, ax = plt.subplots(figsize=(7.2, 3.2))
        ax.imshow(m.T, aspect="auto", interpolation="nearest",
                  cmap=matplotlib.colors.ListedColormap(["#f3f2ee", AZUL]))
        ax.set_yticks(range(df.shape[1]), [f"{c} ({m[:, i].sum()})" for i, c in enumerate(df.columns)])
        ax.set_title(titulo, loc="left"); ax.grid(False)
    fig.tight_layout(); fig.savefig(ruta); plt.close(fig)


def barras_completitud(df: pd.DataFrame, titulo: str, ruta):
    """msno.bar: registros con dato por columna (completitud)."""
    msno = _msno()
    if msno is None:
        return
    ax = msno.bar(df, figsize=(9, 3.6), fontsize=9, color=(0.16, 0.47, 0.84))
    ax.set_title(titulo, loc="left", fontsize=11, fontweight="bold", pad=28)
    fig = ax.get_figure(); fig.tight_layout(); fig.savefig(ruta); plt.close(fig)


def heatmap_nulidad(df: pd.DataFrame, titulo: str, ruta):
    """msno.heatmap: correlación de nulidad entre columnas. Valores cercanos a 0
    indican que los nulos de una columna NO aparecen junto con los de otra."""
    msno = _msno()
    if msno is None:
        return
    ax = msno.heatmap(df, figsize=(5.5, 4), fontsize=9, cmap="RdBu")
    ax.grid(False)
    cols = [c for c in df.columns if df[c].isna().any() and not df[c].isna().all()]
    if len(cols) == 2:   # msno oculta valores cercanos a 0: se anota la correlación real
        r = df[cols].isna().astype(int).corr().iloc[0, 1]
        ax.text(0.25, 0.25, f"r = {r:.2f}", ha="center", va="center", fontsize=12, transform=ax.transAxes)
    ax.set_title(titulo, loc="left", fontsize=11, fontweight="bold")
    fig = ax.get_figure(); fig.tight_layout(); fig.savefig(ruta); plt.close(fig)


def distribucion_sesgada(s: pd.Series, titulo: str, xlabel: str, ruta):
    """Histograma en escala log con media vs mediana: evidencia de por qué se usa mediana."""
    s = pd.to_numeric(s, errors="coerce").dropna()
    s = s[s > 0]
    media, mediana = s.mean(), s.median()
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    bins = np.logspace(np.log10(s.min()), np.log10(s.max()), 40)
    ax.hist(s, bins=bins, color=AZUL, edgecolor="white", linewidth=1)
    ax.set_xscale("log")
    ax.axvline(mediana, color=TINTA, lw=2)
    ax.axvline(media, color=NARANJA, lw=2, ls="--")
    ymax = ax.get_ylim()[1]
    caja = dict(facecolor="white", edgecolor="none", pad=1.5, alpha=0.9)
    ax.text(mediana * 0.92, ymax * 0.93, f"mediana = {mediana:,.0f}", color=TINTA, fontsize=9,
            ha="right", bbox=caja)
    ax.text(media * 1.08, ymax * 0.80, f"media = {media:,.0f}", color=TINTA, fontsize=9,
            ha="left", bbox=caja)
    ax.set_xlabel(xlabel + " (escala log)"); ax.set_ylabel("Frecuencia")
    ax.set_title(titulo + f"   ·   sesgo (skew) = {s.skew():.1f}", loc="left")
    fig.tight_layout(); fig.savefig(ruta); plt.close(fig)


def tasa_nulos_por_grupo(df: pd.DataFrame, col: str, grupo: str, titulo: str, ruta, p_valor=None):
    t = df.groupby(df[grupo].astype(str))[col].apply(lambda s: 100 * s.isna().mean()).sort_values()
    n = df.groupby(df[grupo].astype(str))[col].size().reindex(t.index)
    fig, ax = plt.subplots(figsize=(7.2, 0.45 * len(t) + 1.3))
    ax.barh(t.index, t.values, color=AZUL, height=0.55)
    for i, (v, k) in enumerate(zip(t.values, n.values)):
        ax.text(v + 0.15, i, f"{v:.1f}%  (n={k})", va="center", fontsize=8.5, color=TINTA)
    ax.set_xlabel(f"% de '{col}' nulo")
    sub = f"   ·   p = {p_valor:.3f}" if p_valor is not None else ""
    ax.set_title(titulo + sub, loc="left"); ax.grid(axis="y", visible=False)
    ax.set_xlim(0, max(t.max() * 1.35, 1))
    fig.tight_layout(); fig.savefig(ruta); plt.close(fig)
