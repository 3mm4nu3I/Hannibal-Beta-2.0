"""Charts for the Hannibal mission report (static, print). One series per chart, one hue."""
import collections
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
    font_manager.fontManager.addfont(f)

SERIES = "#2a78d6"      # categorical slot 1 (validated on the light surface)
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e4e3df"
SURFACE = "#ffffff"
REF = "#8a8984"         # reference lines: recessive gray, labelled in text ink

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5, "text.color": TEXT, "axes.labelcolor": TEXT2,
    "xtick.color": TEXT2, "ytick.color": TEXT2, "axes.edgecolor": GRID, "axes.linewidth": 0.8,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def tidy(ax, grid_axis="x"):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def funnel():
    stages = [("Military objects over Antwerp\n(N2YO, 17 Oct, 19:48)", 148),
              ("Any transmitter on record\n(SatNOGS DB)", 6),
              ("Active transmitter on record", 5),
              ("Heard in the last 30 days\n(vetted SatNOGS observation)", 2),
              ("Heard, with an uplink on record", 0)]
    fig, ax = plt.subplots(figsize=(6.6, 2.55), dpi=300)
    y = list(range(len(stages)))[::-1]
    vals = [v for _, v in stages]
    ax.barh(y, vals, height=0.52, color=SERIES, edgecolor=SURFACE, linewidth=0)
    for yi, v in zip(y, vals):
        ax.text(v + 2.0, yi, f"{v}", va="center", ha="left", color=TEXT, fontsize=9, fontweight="bold")
    ax.set_yticks(y, [s for s, _ in stages], fontsize=8)
    ax.set_xlim(0, 165)
    ax.set_xlabel("objects")
    tidy(ax)
    fig.tight_layout()
    fig.savefig(HERE / "chart_funnel.png")
    plt.close(fig)


def ers15_years():
    obs = json.load(open(HERE / "ers15_good_all.json"))
    by = collections.Counter(o["start"][:4] for o in obs)
    years = [str(y) for y in range(2020, 2027)]
    vals = [by.get(y, 0) for y in years]
    labels = ["2020\n(from 21 Oct)" if y == "2020" else ("2026\n(to 23 Oct)" if y == "2026" else y) for y in years]
    fig, ax = plt.subplots(figsize=(6.6, 2.35), dpi=300)
    ax.bar(range(len(years)), vals, width=0.5, color=SERIES, linewidth=0)
    for i, v in enumerate(vals):
        ax.text(i, v + 4, str(v), ha="center", va="bottom", color=TEXT, fontsize=8.5, fontweight="bold")
    ax.set_xticks(range(len(years)), labels, fontsize=8)
    ax.set_ylabel("vetted good observations")
    ax.set_ylim(0, max(vals) * 1.22)
    tidy(ax, "y")
    fig.tight_layout()
    fig.savefig(HERE / "chart_ers15_years.png")
    plt.close(fig)
    return dict(zip(years, vals)), len(obs), len({o["station_name"] for o in obs})


def eme_bands():
    c = json.load(open(HERE / "calcs.json"))
    rows = c["eme"]
    fig, ax = plt.subplots(figsize=(6.6, 2.6), dpi=300)
    x = list(range(len(rows)))
    snr = [r["snr"] for r in rows]
    for yref, name in ((-25, "Q65 digital decode (−25 dB)"), (-15, "CW by ear (−15 dB)")):
        ax.axhline(yref, color=REF, linewidth=1.0)
        ax.text(len(rows) - 0.45, yref + 0.6, name, ha="right", va="bottom", color=TEXT2, fontsize=7.5)
    ax.scatter(x, snr, s=46, color=SERIES, edgecolors=SURFACE, linewidths=1.5, zorder=3)
    for xi, r in zip(x, rows):
        ax.text(xi, r["snr"] + 1.6, f"{r['snr']:+.1f}".replace("-", "\u2212"), ha="center", va="bottom", color=TEXT, fontsize=8, fontweight="bold")
    ax.set_xticks(x, [f"{r['band']}\n{r['antenna'].replace(' prime-focus dish @ 55%', ' dish').replace(' x ', ' \u00d7 ')}"
                      for r in rows], fontsize=7)
    ax.set_ylabel("echo SNR in 2500 Hz (dB)")
    ax.set_ylim(-31, 6)
    ax.set_xlim(-0.5, len(rows) - 0.4)
    tidy(ax, "y")
    fig.tight_layout()
    fig.savefig(HERE / "chart_eme.png")
    plt.close(fig)


if __name__ == "__main__":
    funnel()
    print(ers15_years())
    eme_bands()
    print("charts written")
