"""Generate ContractKV Fig. 2--Fig. 6 for the TSC manuscript.

The layouts are intentionally claim-led: ContractKV is visually consistent
across panels, absolute service metrics remain primary, and diagnostic or
cross-runtime evidence is explicitly separated from causal same-runtime rows.
All values are frozen measurements recorded in the project result ledgers.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
import numpy as np


OUT = Path(__file__).resolve().parents[1] / "Paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# Unified, print-safe semantic palette.
CKV = "#15599A"
CKV_LIGHT = "#5B9BD5"
SAFE = "#159A8C"
SAFE_LIGHT = "#74C8BD"
RISK = "#E46A25"
UNSAFE = "#C83E4D"
VIOLET = "#7C5AA6"
NATIVE = "#858585"
NATIVE_LIGHT = "#D5D5D5"
INK = "#20242A"
MUTED = "#5D6670"
GRID = "#DFE4E8"
PALE_BLUE = "#EAF2FA"
PALE_TEAL = "#E8F6F3"
PALE_RED = "#FCEBEC"


def set_style(font_size=7.0):
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "font.size": font_size,
            "axes.titlesize": 8.0,
            "axes.titleweight": "bold",
            "axes.labelsize": 7.1,
            "axes.edgecolor": INK,
            "axes.linewidth": 0.75,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 6.7,
            "ytick.labelsize": 6.7,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "legend.fontsize": 6.4,
            "legend.frameon": False,
            "lines.linewidth": 1.45,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.035,
        }
    )


def finish(fig, stem):
    fig.savefig(OUT / f"{stem}.pdf")
    fig.savefig(OUT / f"{stem}.svg")
    fig.savefig(OUT / f"{stem}.png", dpi=600)
    plt.close(fig)


def panel(ax, label, title, pad=4):
    ax.set_title(f"({label})  {title}", loc="left", pad=pad)


def grid_y(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.55)


def grid_x(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="x", color=GRID, linewidth=0.55)


def label_vertical_bars(ax, bars, fmt, dy, color=INK, size=6.5):
    for bar in bars:
        value = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            value + dy,
            fmt.format(value),
            ha="center",
            va="bottom",
            fontsize=size,
            fontweight="bold",
            color=color,
        )


def figure2_global_benefit():
    """Cross-model headline results with qualification as the safety context."""
    set_style()
    fig = plt.figure(figsize=(3.5, 3.85))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.12, 1.0], hspace=0.55, wspace=0.52)
    ax_a = fig.add_subplot(gs[0, :])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_c = fig.add_subplot(gs[1, 1])
    ax_d = fig.add_subplot(gs[1, 2])

    model_full = ["Qwen3-8B", "Qwen3-14B\nTP=2", "Mistral-7B", "Llama-3.1-8B"]
    model_short = ["8B", "14B", "7B", "8B"]
    colors = [CKV, "#347FC4", SAFE, VIOLET]
    x = np.arange(4)

    goodput = [2.64, 2.92, 1.24, 1.19]
    bars = ax_a.bar(x, goodput, width=0.62, color=colors, edgecolor=INK, linewidth=0.55)
    ax_a.axhline(1.0, color=NATIVE, linestyle=(0, (4, 2)), linewidth=0.9)
    ax_a.text(
        0.985,
        0.94,
        "native reference = 1.0×",
        transform=ax_a.transAxes,
        ha="right",
        va="top",
        color=MUTED,
        fontsize=6.2,
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.88, pad=1.0),
    )
    ax_a.set_xticks(x, model_full)
    ax_a.set_ylim(0, 3.35)
    ax_a.set_ylabel("SLO-goodput multiplier")
    grid_y(ax_a)
    panel(ax_a, "a", "All-workflow net SLO goodput")
    label_vertical_bars(ax_a, bars, "{:.2f}×", 0.07)
    ax_a.annotate(
        "benefit persists at TP=2",
        xy=(1, 2.92),
        xytext=(1.82, 3.18),
        ha="center",
        va="center",
        fontsize=6.4,
        color=CKV,
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=CKV, lw=0.9, connectionstyle="arc3,rad=.20"),
    )

    ttft = [37.81, 44.69, 31.72, 29.41]
    bars = ax_b.bar(x, ttft, width=0.66, color=colors, edgecolor=INK, linewidth=0.45)
    ax_b.set_xticks(x, model_short)
    ax_b.set_ylim(0, 52)
    ax_b.set_ylabel("Reduction (%)")
    grid_y(ax_b)
    panel(ax_b, "b", "Net TTFT")
    for bar, value in zip(bars, ttft):
        ax_b.text(bar.get_x() + bar.get_width() / 2, value + 1.2, f"{value:.0f}", ha="center", fontsize=5.9, fontweight="bold")

    prefill = [59.13, 60.57, 39.46, 30.97]
    bars = ax_c.bar(x, prefill, width=0.66, color=[SAFE, SAFE, SAFE_LIGHT, SAFE_LIGHT], edgecolor=INK, linewidth=0.45)
    ax_c.set_xticks(x, model_short)
    ax_c.set_ylim(0, 70)
    ax_c.set_ylabel("Reduction (%)")
    grid_y(ax_c)
    panel(ax_c, "c", "New-prefill")
    for bar, value in zip(bars, prefill):
        ax_c.text(bar.get_x() + bar.get_width() / 2, value + 1.5, f"{value:.0f}", ha="center", fontsize=5.9, fontweight="bold")

    coverage = np.array([[100, 70, 50, 70, 50], [100, 70, 60, 10, 10], [100, 90, 60, 0, 0]])
    levels = np.array([["L3*", "L3*", "L3*", "L3*", "L3*"], ["L3*", "L3*", "L3*", "L3*", "L3*"], ["L3", "L2", "L2", "L0", "L0"]])
    ax_d.imshow(coverage, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    panel(ax_d, "d", "Qualification")
    ax_d.set_xticks(range(5), ["R", "H", "N", "Q", "RB"])
    ax_d.set_yticks(range(3), ["Qw", "Mi", "Ll"])
    ax_d.tick_params(length=0)
    for r in range(3):
        for c in range(5):
            color = "white" if coverage[r, c] >= 55 else INK
            label = f"{levels[r, c]}\n{coverage[r, c]}%"
            ax_d.text(c, r, label, ha="center", va="center", fontsize=5.15, color=color, fontweight="bold", linespacing=0.88)
    for spine in ax_d.spines.values():
        spine.set_visible(False)

    fig.text(0.5, 0.012, "Global rows include frozen L0 and runtime fallback; all four remain net-positive.", ha="center", fontsize=6.2, color=MUTED)
    fig.subplots_adjust(left=0.13, right=0.985, top=0.965, bottom=0.09)
    finish(fig, "fig2_global_benefit")


def figure3_llama_baselines():
    """Make the performance-risk frontier and tail attribution visually explicit."""
    set_style()
    fig = plt.figure(figsize=(3.5, 4.10))
    outer = fig.add_gridspec(2, 1, height_ratios=[1.05, 1.20], hspace=0.48)
    top = outer[0].subgridspec(1, 2, width_ratios=[1.28, 1.0], wspace=0.08)
    ax_speed = fig.add_subplot(top[0, 0])
    ax_risk = fig.add_subplot(top[0, 1], sharey=ax_speed)
    ax_tail = fig.add_subplot(outer[1, 0])

    methods = ["ContractKV\n(vLLM)", "CacheBlend\n(LMCache)", "Manual upper\nbound (vLLM)", "Frozen layout\n(SGLang)"]
    reduction = np.array([29.16, 26.96, 37.87, 26.60])
    regression = np.array([0.089, 9.956, 1.733, 0.089])
    colors = [CKV, RISK, UNSAFE, SAFE]
    y = np.arange(4)

    # One highlight band visually anchors the method-of-interest across both metrics.
    for ax in (ax_speed, ax_risk):
        ax.axhspan(-0.43, 0.43, color=PALE_BLUE, zorder=0)

    bars = ax_speed.barh(y, reduction, color=colors, height=0.55, edgecolor=INK, linewidth=0.5, zorder=2)
    ax_speed.set_yticks(y, methods)
    ax_speed.invert_yaxis()
    ax_speed.set_xlim(0, 45)
    ax_speed.set_xlabel("Matched TTFT reduction (%)")
    grid_x(ax_speed)
    ax_speed.set_title("(a)  Matched-runtime gain vs. observed risk", loc="left", pad=5, fontweight="bold", fontsize=8.0)
    for bar, value in zip(bars, reduction):
        ax_speed.text(value + 0.7, bar.get_y() + bar.get_height() / 2, f"{value:.1f}%", va="center", fontsize=6.2, fontweight="bold", color=bar.get_facecolor())

    ax_risk.set_xscale("log")
    ax_risk.set_xlim(0.045, 20)
    ax_risk.scatter(regression, y, s=[72, 58, 58, 48], c=colors, marker="o", edgecolor=INK, linewidth=0.65, zorder=3)
    ax_risk.set_xlabel("Regression rate >0.03 (%)")
    ax_risk.tick_params(axis="y", left=False, labelleft=False)
    grid_x(ax_risk)
    for value, yi, color in zip(regression, y, colors):
        ax_risk.text(value * 1.18, yi, f"{value:.3g}%", va="center", fontsize=6.0, fontweight="bold", color=color)
    ax_speed.text(2.0, 0, "0/1,125 admitted\ncompiled regressions", ha="left", va="center", fontsize=5.5, color="white", fontweight="bold")
    ax_risk.text(0.98, 0.985, "← lower risk", transform=ax_risk.transAxes, ha="right", va="top", fontsize=5.8, color=MUTED)
    ax_risk.spines["left"].set_visible(False)

    # Tail panel: full p99 bar, with mean and p95 as visible internal milestones.
    classes = ["Compiled (50%)", "L0 direct (40%)", "Fallback (10%)", "Overall"]
    mean = np.array([263.29, 1261.76, 865.68, 722.92])
    p95 = np.array([699.50, 1778.89, 1125.58, 1716.74])
    p99 = np.array([898.96, 2311.01, 1129.17, 2306.46])
    attainment = [100.0, 71.1, 100.0, 88.4]
    row_colors = [CKV, NATIVE, RISK, CKV_LIGHT]
    yy = np.arange(4)
    ax_tail.barh(yy, p99, height=0.52, color=[PALE_BLUE, "#ECECEC", "#FCE8DC", "#DCEAF7"], edgecolor=row_colors, linewidth=1.0, zorder=1)
    ax_tail.scatter(mean, yy, marker="o", s=26, c=row_colors, edgecolor=INK, linewidth=0.55, zorder=4, label="mean")
    ax_tail.scatter(p95, yy, marker="|", s=150, c=row_colors, linewidth=2.2, zorder=4, label="p95")
    ax_tail.scatter(p99, yy, marker="s", s=25, c=row_colors, edgecolor=INK, linewidth=0.55, zorder=4, label="p99")
    ax_tail.axvline(1500, color=UNSAFE, linestyle=(0, (4, 2)), linewidth=1.0, zorder=2)
    ax_tail.text(1518, -0.40, "SLO", color=UNSAFE, fontsize=5.9, fontweight="bold", va="center")
    ax_tail.set_yticks(yy, classes)
    ax_tail.invert_yaxis()
    ax_tail.set_xlim(0, 3300)
    ax_tail.set_xlabel("TTFT distribution by request class (ms)")
    grid_x(ax_tail)
    panel(ax_tail, "b", "Tail is concentrated in deliberate raw L0")
    for yi, p99v, att in zip(yy, p99, attainment):
        ax_tail.text(p99v + 55, yi, f"p99 {p99v:.0f}", va="center", fontsize=5.7, color=INK)
        ax_tail.text(3250, yi, f"{att:.0f}% SLO", ha="right", va="center", fontsize=5.8, fontweight="bold", color=row_colors[yi])
    fig.subplots_adjust(left=0.23, right=0.975, top=0.97, bottom=0.075)
    finish(fig, "fig3_llama_baselines")


def figure4_verification_economics():
    """Explain D0/D1/D2 before presenting the same-engine and scope gains."""
    set_style()
    fig = plt.figure(figsize=(3.5, 4.20))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.05, 0.90, 1.10], hspace=0.62)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_c = fig.add_subplot(gs[2, 0])

    policies = ["D0 native", "D1 frozen", "D2 full CKV"]
    sublabels = ["raw APC", "safe layout only", "in-engine certificate"]
    goodput = [0.066, 1.472, 1.428]
    x = np.arange(3)
    colors = [NATIVE, SAFE, CKV]
    bars = ax_a.bar(x, goodput, width=0.58, color=colors, edgecolor=INK, linewidth=0.6)
    ax_a.set_xticks(x, [f"{p}\n{s}" for p, s in zip(policies, sublabels)])
    ax_a.set_ylim(0, 1.72)
    ax_a.set_ylabel("500-ms goodput (req/s)")
    grid_y(ax_a)
    panel(ax_a, "a", "Full ContractKV preserves layout-only goodput")
    label_vertical_bars(ax_a, bars, "{:.3f}", 0.045)
    ax_a.annotate("21.5×", xy=(2, 1.428), xytext=(1.55, 1.62), fontsize=8.0, fontweight="bold", color=CKV, arrowprops=dict(arrowstyle="->", color=CKV, lw=1.0, connectionstyle="arc3,rad=.18"))
    ax_a.text(2, 0.12, "4 verifier calls\n4 commits\n0 failures", ha="center", va="bottom", fontsize=5.15, color="white", fontweight="bold")

    mean = [2742.83, 194.95, 194.72]
    p99 = [7531.79, 935.86, 935.86]
    y = np.arange(3)
    for i, color in enumerate(colors):
        ax_b.hlines(i, mean[i], p99[i], color=color, linewidth=7.5, alpha=0.72, zorder=1)
        ax_b.scatter(mean[i], i, s=28, marker="o", color=color, edgecolor=INK, linewidth=0.55, zorder=3)
        ax_b.scatter(p99[i], i, s=30, marker="s", color=color, edgecolor=INK, linewidth=0.55, zorder=3)
        mean_x = mean[i] * (0.88 if i == 0 else 1.08)
        mean_ha = "right" if i == 0 else "left"
        ax_b.text(mean_x, i, f"mean {mean[i]:.0f}", ha=mean_ha, va="center", fontsize=5.7, color=color, fontweight="bold")
        ax_b.text(p99[i] * 1.07, i, f"p99 {p99[i]:.0f}", va="center", fontsize=5.7, color=color, fontweight="bold")
    ax_b.set_xscale("log")
    ax_b.set_xlim(110, 10000)
    ax_b.set_yticks(y, policies)
    ax_b.invert_yaxis()
    ax_b.set_xlabel("TTFT (ms, log scale)")
    grid_x(ax_b)
    panel(ax_b, "b", "D2 closes the path with no added tail penalty")
    ax_b.text(0.98, 0.08, "circle: mean    square: p99", transform=ax_b.transAxes, ha="right", va="bottom", fontsize=5.8, color=MUTED)

    metrics = ["Verifier calls", "Unhidden\nms/request"]
    session = [125, 25.05]
    template = [5, 3.24]
    xx = np.arange(2)
    width = 0.30
    b1 = ax_c.bar(xx - width / 2, session, width, color=NATIVE_LIGHT, edgecolor=INK, linewidth=0.55, label="Session certificate")
    b2 = ax_c.bar(xx + width / 2, template, width, color=CKV, edgecolor=INK, linewidth=0.55, label="Template certificate")
    ax_c.set_yscale("log")
    ax_c.set_ylim(1, 220)
    ax_c.set_xticks(xx, metrics)
    ax_c.set_ylabel("Count or ms/request (log)")
    grid_y(ax_c)
    panel(ax_c, "c", "Template scope amortizes the same safe layout")
    for bars, values, color in ((b1, session, MUTED), (b2, template, CKV)):
        for bar, value in zip(bars, values):
            ax_c.text(bar.get_x() + bar.get_width() / 2, value * 1.12, f"{value:g}", ha="center", fontsize=5.9, fontweight="bold", color=color)
    ax_c.text(-0.03, 47, "25×", color=SAFE, fontsize=6.4, fontweight="bold", ha="center")
    ax_c.text(0.97, 8.8, "7.7×", color=SAFE, fontsize=6.4, fontweight="bold", ha="center")
    ax_c.legend(loc="upper right", ncol=2, columnspacing=0.8)

    fig.text(0.5, 0.011, "Quality audit: 1,350/1,350 complete, zero >0.03 drops, zero unauthorized or dynamic-suffix reuse.", ha="center", fontsize=5.8, color=MUTED)
    fig.subplots_adjust(left=0.18, right=0.985, top=0.97, bottom=0.085)
    finish(fig, "fig4_verification_economics")


def figure5_service_locality():
    """Show absolute service goodput and allocator-observed physical dedup."""
    set_style()
    fig = plt.figure(figsize=(3.5, 4.10))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.12, 0.92, 0.82], hspace=0.58)
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_c = fig.add_subplot(gs[2, 0])

    loads = np.array([60, 80, 100, 120, 140])
    raw = np.array([0.1434, 0.1727, 0.1718, 0.1530, 0.1088])
    ckv = np.array([0.6230, 0.8307, 1.0382, 1.2458, 1.4534])
    ax_a.fill_between(loads, raw, ckv, color=CKV_LIGHT, alpha=0.18, zorder=0)
    ax_a.plot(loads, raw, "o--", color=NATIVE, markersize=4.0, label="Native APC")
    ax_a.plot(loads, ckv, "s-", color=CKV, markersize=4.2, linewidth=1.8, label="ContractKV")
    ax_a.set_xlim(56, 144)
    ax_a.set_ylim(0, 1.62)
    ax_a.set_xlabel("Offered load (% of raw calibration)")
    ax_a.set_ylabel("500-ms SLO goodput (req/s)")
    grid_y(ax_a)
    panel(ax_a, "a", "Absolute compliant throughput grows under load")
    ax_a.legend(loc="upper left")
    ax_a.annotate("80% load\n0.173 → 0.831 req/s\n4.81× [2.85, 12.61]", xy=(80, 0.831), xytext=(104, 0.53), fontsize=6.1, color=CKV, fontweight="bold", bbox=dict(boxstyle="round,pad=.3", fc="white", ec=CKV, lw=0.7), arrowprops=dict(arrowstyle="->", color=CKV, lw=0.8, connectionstyle="arc3,rad=.15"))

    tenants = np.array([10, 20, 30, 40, 60, 80])
    raw_density = np.array([0.900, 1.032, 1.059, 1.073, 1.112, 1.152])
    ckv_density = np.array([9.408, 10.781, 10.532, 11.057, 11.072, 11.033])
    ax_b.fill_between(tenants, raw_density, ckv_density, color=SAFE_LIGHT, alpha=0.16)
    ax_b.plot(tenants, raw_density, "o--", color=NATIVE, markersize=3.8)
    ax_b.plot(tenants, ckv_density, "s-", color=SAFE, markersize=4.0, linewidth=1.7)
    ax_b.set_xlim(6, 84)
    ax_b.set_ylim(0, 12.4)
    ax_b.set_xlabel("Authorized tenants")
    ax_b.set_ylabel("SLO goodput (req/s)")
    grid_y(ax_b)
    panel(ax_b, "b", "Template consolidation sustains about 11 req/s")
    ax_b.text(78, 8.15, "20–80 tenants\nContractKV: 10.5–11.1 req/s\nNative: 1.0–1.2 req/s", ha="right", va="center", fontsize=6.0, color=SAFE, fontweight="bold", bbox=dict(boxstyle="round,pad=.28", fc="white", ec=SAFE, lw=0.65))

    # Physical block-pool bars retain the observed total pool of 2,386 blocks.
    total = 2386
    used = [530, 149]
    free = [1856, 2237]
    y = [1, 0]
    labels = ["Native APC", "ContractKV"]
    for yi, used_i, free_i, color in zip(y, used, free, [NATIVE, CKV]):
        ax_c.barh(yi, used_i, height=0.48, color=color, edgecolor=INK, linewidth=0.55)
        ax_c.barh(yi, free_i, left=used_i, height=0.48, color="#EEF1F3", edgecolor=INK, linewidth=0.55)
        if used_i >= 300:
            ax_c.text(used_i / 2, yi, f"used {used_i}", ha="center", va="center", fontsize=6.0, color=INK, fontweight="bold")
        else:
            ax_c.text(used_i + 35, yi, f"used {used_i}", ha="left", va="center", fontsize=5.9, color=CKV, fontweight="bold")
        ax_c.text(used_i + free_i / 2, yi, f"free {free_i}", ha="center", va="center", fontsize=6.0, color=MUTED)
    ax_c.set_yticks(y, labels)
    ax_c.set_xlim(0, total)
    ax_c.set_xlabel("GPU KV block pool (2,386 blocks)")
    ax_c.set_xticks([0, 600, 1200, 1800, 2386])
    grid_x(ax_c)
    panel(ax_c, "c", "Physical dedup frees allocator headroom at 80 tenants")
    ax_c.text(0.98, 0.50, "72% fewer used blocks\n+381 free blocks\ndynamic suffix reuse = 0", transform=ax_c.transAxes, ha="right", va="center", fontsize=6.0, color=CKV, fontweight="bold", bbox=dict(boxstyle="round,pad=.28", fc="white", ec=CKV, lw=0.7, alpha=0.93))

    fig.subplots_adjust(left=0.18, right=0.985, top=0.97, bottom=0.08)
    finish(fig, "fig5_service_locality")


def figure6_operating_region():
    """Expose the locality/residency regime and prospective benefit gate."""
    set_style()
    fig = plt.figure(figsize=(3.5, 3.80))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.02, 1.0], width_ratios=[0.92, 1.28], hspace=0.52, wspace=0.48)
    ax_a = fig.add_subplot(gs[0, :])
    ax_b = fig.add_subplot(gs[1, 0])
    ax_c = fig.add_subplot(gs[1, 1])

    sharing = np.array([0, 25, 50, 75, 100])
    reduction = np.array([0.0, 21.7, 43.6, 93.4, 93.4])
    colors = [NATIVE_LIGHT, NATIVE, SAFE, CKV, CKV]
    bars = ax_a.bar(sharing, reduction, width=15, color=colors, edgecolor=INK, linewidth=0.55)
    ax_a.axvspan(50, 75, color=PALE_RED, alpha=0.55, zorder=0)
    ax_a.set_xticks(sharing)
    ax_a.set_ylim(0, 105)
    ax_a.set_xlabel("Authorized sharing (%)")
    ax_a.set_ylabel("Mean TTFT reduction (%)")
    grid_y(ax_a)
    panel(ax_a, "a", "Measured locality knee appears between 50% and 75% sharing")
    label_vertical_bars(ax_a, bars, "{:.1f}%", 2.0)
    ax_a.annotate("residency knee", xy=(65, 68), xytext=(44, 78), fontsize=6.2, color=UNSAFE, fontweight="bold", arrowprops=dict(arrowstyle="->", color=UNSAFE, lw=0.8))

    data = np.array([[93.69, 94.26], [0.36, 84.63], [0.64, 73.40]])
    ax_b.imshow(data, cmap="YlGnBu", aspect="auto", vmin=0, vmax=100)
    ax_b.set_xticks([0, 1], ["Round-robin", "Zipf"], rotation=18, ha="right")
    ax_b.set_yticks([0, 1, 2], ["5", "25", "50"])
    ax_b.set_ylabel("Active templates")
    panel(ax_b, "b", "Residency")
    ax_b.tick_params(length=0)
    for r in range(3):
        for c in range(2):
            color = "white" if data[r, c] > 55 else INK
            ax_b.text(c, r, f"{data[r, c]:.0f}%", ha="center", va="center", color=color, fontsize=6.5, fontweight="bold")
    for spine in ax_b.spines.values():
        spine.set_visible(False)

    lane_labels = ["3k / 12", "5k / 10", "1.5k / 8", "3.5k / 6"]
    benefits = [7044.76, 10842.68, np.nan, np.nan]
    yy = np.arange(4)
    for i, value in enumerate(benefits):
        if np.isfinite(value):
            ax_c.barh(i, value, height=0.48, color=CKV, edgecolor=INK, linewidth=0.55)
            ax_c.text(value - 240, i, "PASS", ha="right", va="center", fontsize=6.3, color="white", fontweight="bold")
            ax_c.text(value + 220, i, f"+{value / 1000:.2f}s", va="center", fontsize=5.8, color=CKV, fontweight="bold")
        else:
            ax_c.add_patch(Rectangle((0, i - 0.22), 360, 0.44, facecolor=NATIVE_LIGHT, edgecolor=NATIVE, linewidth=0.7))
            ax_c.text(500, i, "raw fallback", va="center", fontsize=5.9, color=MUTED, style="italic")
    ax_c.set_yticks(yy, lane_labels)
    ax_c.invert_yaxis()
    ax_c.set_xlim(0, 13000)
    ax_c.set_xlabel("Held-out net benefit (ms)")
    grid_x(ax_c)
    panel(ax_c, "c", "Frozen gate: 2/4 admitted; both net-positive")

    fig.subplots_adjust(left=0.17, right=0.985, top=0.97, bottom=0.08)
    finish(fig, "fig6_operating_region")


if __name__ == "__main__":
    figure2_global_benefit()
    figure3_llama_baselines()
    figure4_verification_economics()
    figure5_service_locality()
    figure6_operating_region()
    print(f"Generated Fig. 2--Fig. 6 in {OUT}")
