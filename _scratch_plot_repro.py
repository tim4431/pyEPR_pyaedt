"""Throwaway repro: which convergence panel crashes on variation-2-like data (no HFSS)."""
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib as mpl

from pyEPR_pyaedt.reports import (
    plot_convergence_f_vspass,
    plot_convergence_max_df,
    plot_convergence_solved_elem,
    plot_convergence_maxdf_vs_sol,
)

# Variation-2-like data
idx = pd.Index([12.0] + [np.nan] * 11, name="Pass Number")
convergence_t = pd.DataFrame(
    {
        "Solved Elements": [49220.0] + [np.nan] * 11,
        "Max Delta Freq. %": [np.nan] * 12,
    },
    index=idx,
)
convergence_f = pd.DataFrame(
    {"re(Mode(1))": [np.nan] * 11 + [5.28], "re(Mode(2))": [np.nan] * 11 + [9.25]},
    index=pd.Index(range(1, 13), name="Pass []"),
)

panels = {
    "f_vspass": lambda ax: plot_convergence_f_vspass(ax, convergence_f),
    "max_df": lambda ax: plot_convergence_max_df(ax, convergence_t.iloc[:, 1]),
    "solved_elem": lambda ax: plot_convergence_solved_elem(ax, convergence_t.iloc[:, 0]),
    "maxdf_vs_sol": lambda ax: plot_convergence_maxdf_vs_sol(
        ax, convergence_t.iloc[:, 1], convergence_t.iloc[:, 0]
    ),
}

for name, fn in panels.items():
    fig = plt.figure()
    ax = fig.add_subplot(111)
    try:
        fn(ax)
        fig.canvas.draw()
        print(f"{name}: OK")
    except Exception as e:
        print(f"{name}: FAILED -> {type(e).__name__}: {e}")
    plt.close(fig)

# Full figure like hfss_report_full_convergence
fig = plt.figure(figsize=(11, 3.0))
gs = mpl.gridspec.GridSpec(1, 3, width_ratios=[1.2, 1.5, 1])
axs = [fig.add_subplot(gs[i]) for i in range(3)]
ax0t = axs[1].twinx()
try:
    plot_convergence_f_vspass(axs[0], convergence_f)
    plot_convergence_max_df(axs[1], convergence_t.iloc[:, 1])
    plot_convergence_solved_elem(ax0t, convergence_t.iloc[:, 0])
    plot_convergence_maxdf_vs_sol(axs[2], convergence_t.iloc[:, 1], convergence_t.iloc[:, 0])
    fig.tight_layout(w_pad=0.1)
    fig.canvas.draw()
    print("full figure: OK")
except Exception as e:
    print(f"full figure: FAILED -> {type(e).__name__}: {e}")
