"""Hebrew figures (SVG + PNG fallback) for the Word summary, using the figure style of the acoustics-summary book.
Run with the AcousticMaskingLab venv:  python docs/word/make_figures.py   (needs docs/validation/*.json)."""
import sys, json, pathlib
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOK = ROOT.parent / "acoustics-summary" / "Acoustic_End_to_End" / "scripts"
sys.path.insert(0, str(BOOK / "generate_figures")); sys.path.insert(0, str(BOOK)); sys.path.insert(0, str(ROOT / "backend"))
import numpy as np
import figstyle as fs
from figstyle import plt, H, NAVY, TEAL, ORANGE, RED, GRAY, LIGHT, CYCLE, box, arrow
fs.FIG = HERE / "figures"
from aml import generators as G, units as U, spectra as SP

V = ROOT / "docs" / "validation"
val = json.loads((V / "model_validation.json").read_text())
scn = json.loads((V / "scenario_results.json").read_text())
cv = json.loads((V / "casp_validation.json").read_text())
sim = json.loads((V / "simulated_listener.json").read_text())
FS = 32000
NAMES = {"Pink noise": "רעש ורוד", "White noise": "רעש לבן", "Brown noise": "רעש חום", "Wind with gusts": "רוח עם משבים",
         "Flowing water": "מים זורמים", "Rain": "גשם", "Rustling leaves": "רשרוש עלים", "Crickets chorus": "מקהלת צרצרים",
         "Water + wind + leaves": "מים + רוח + עלים"}
nm = lambda s: NAMES.get(s, s)
CAT = {"Pink noise": "#0072B2", "White noise": "#56B4E9", "Brown noise": "#7A5AA6", "Wind with gusts": "#E69F00", "Flowing water": "#009E73",
       "Rain": "#CC79A7", "Rustling leaves": "#D55E00", "Crickets chorus": "#999999", "Water + wind + leaves": "#882255"}


def fig_architecture():
    fig, ax = plt.subplots(figsize=(10, 5.6)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 5.6); ax.grid(False)
    box(ax, 3.6, 4.5, 2.8, 0.85, "ממשק משתמש (React + Plotly)\nדפדפן מקומי", fc="#D6EEEE", bold=True)
    box(ax, 3.6, 3.45, 2.8, 0.8, "שכבת API (FastAPI)\nסשנים, משימות, ייצוא", fc=LIGHT)
    arrow(ax, (5.0, 4.5), (5.0, 4.27)); arrow(ax, (5.0, 3.45), (5.0, 3.2))
    xs = [0.2, 2.1, 4.0, 5.9, 7.8]
    labs = ["עיבוד שמע\nWAV, כיול, רקע\nמרחק, ספקטרה", "יצירת קול\nרוח, מים, גשם\nעלים, צרצרים", "מודלים\nERB-EDM מהיר\nגשר CASP / AMT",
            "אופטימיזציה\nרמה מינימלית\nצורת ספקטרום", "ניסויי האזנה\n2AFC, מדרגה\nפונקציה פסיכומטרית"]
    for x, l in zip(xs[::-1], labs):
        box(ax, x, 1.55, 1.9, 1.5, l, fc=LIGHT, fs=9.5)
        arrow(ax, (5.0, 3.2), (x + 0.95, 3.07), lw=0.9)
    box(ax, 0.2, 0.2, 4.3, 0.85, "MATLAB R2023a + Auditory Modeling Toolbox 1.6.0\nמודל CASP (paulick2024), ללא שינוי בחזית", fc="#FBF0E1", ec=ORANGE, fs=9.5)
    box(ax, 5.5, 0.2, 4.3, 0.85, "דוחות: PDF, Excel, CSV, WAV, תצורה (JSON)\nשמירת סשנים וניסויים", fc="#E8EEF6", fs=9.5)
    arrow(ax, (2.35, 1.05), (4.95, 1.55), color=ORANGE, lw=1.1, ls="--"); arrow(ax, (7.65, 1.05), (7.65, 1.55), lw=1.1)
    fs.save(fig, "system", "fig_architecture")


def fig_validation_curves():
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.9))
    a = axs[0]; d = val["cr_vs_freq"]
    a.semilogx(d["f"], d["cr_db"], "o-", color=NAVY, lw=2); a.set_xticks(d["f"]); a.set_xticklabels([str(f) for f in d["f"]])
    a.axhline(18, color=ORANGE, ls="--", lw=1); a.text(d["f"][-1], 18.3, H("עוגן: 18 dB ב-1 kHz"), ha="right", color=ORANGE, fontsize=10)
    a.set_xlabel(H("תדר (Hz)")); a.set_ylabel(H("יחס קריטי CR (dB)")); a.set_title(H("יחס קריטי לפי תדר"))
    b = axs[1]; d = val["duration"]
    b.semilogx(np.array(d["dur_s"]) * 1000, d["threshold_rel_db"], "s-", color=TEAL, lw=2)
    b.set_xlabel(H("משך הצליל (ms)")); b.set_ylabel(H("סף יחסי (dB)")); b.set_title(H("אינטגרציה בזמן"))
    c = axs[2]; d = val["psychometric"]
    c.plot(d["gain_db"], d["p"], color=NAVY, lw=2); c.axhline(0.5, color=GRAY, ls=":", lw=1); c.axhline(0.75, color=ORANGE, ls="--", lw=1)
    c.set_xlabel(H("רמת המטרה יחסית לסף (dB)")); c.set_ylabel(H("P(נכון), 2AFC")); c.set_title(H("פונקציה פסיכומטרית של המודל")); c.set_ylim(0.45, 1.02)
    fs.save(fig, "validation", "fig_fast_validation")


def fig_forward():
    fig, ax = plt.subplots(figsize=(6.4, 3.8)); d = val["forward_masking"]
    ax.plot(np.array(d["gap_s"]) * 1000, d["threshold_rel_db"], "o-", color=NAVY, lw=2)
    ax.set_xlabel(H("השהיה בין סוף המסכה לבדיקה (ms)")); ax.set_ylabel(H("סף הבדיקה (dB יחסית)")); ax.set_title(H("הסוואה לאחור בזמן: דעיכה")); fs.save(fig, "validation", "fig_forward")


def fig_casp():
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.9))
    for ax, key, ttl in zip(axs, ("tone1k", "tone4k"), ("1 kHz (עוגן הכיול)", "4 kHz (בדיקה בלתי תלויה)")):
        d = cv[key]; gm = d["gm_db"]
        ax.plot(gm, d["casp_P_cal"], "o-", color=NAVY, lw=2, label=H("CASP, שונות מכוילת"))
        ax.plot(gm, d["casp_P_raw_amt_invar"], "o:", color=GRAY, lw=1.4, label=H("CASP, שונות AMT (40)"))
        ax.plot(gm, d["fast_P"], "s--", color=ORANGE, lw=2, label=H("מודל מהיר ERB-EDM"))
        ax.axhline(0.75, color="#bbb", lw=0.8, ls=":"); ax.set_ylim(0.45, 1.02)
        ax.set_xlabel(H("הסטת רמת הרעש מהעוגן (dB)")); ax.set_ylabel(H("הסתברות לתשובה נכונה")); ax.set_title(H(ttl)); ax.legend(loc="upper right")
    fs.save(fig, "validation", "fig_casp_vs_fast")


def fig_maskers():
    fig, axs = plt.subplots(2, 4, figsize=(13, 7.2), sharey=True); fig.subplots_adjust(hspace=0.62)
    for ax, (typ, lab) in zip(axs.ravel(), [("white", "לבן"), ("pink", "ורוד"), ("brown", "חום"), ("wind", "רוח"), ("water", "מים"), ("rain", "גשם"), ("leaves", "עלים"), ("crickets", "צרצרים")]):
        x = G.render_component({"type": typ, "level": 40, "weighting": "A"}, 12, FS, 3)
        c = U.third_octave_centres(50, 12500); L = SP.third_octave_levels(x, FS, c)
        ax.bar(range(len(c)), L, color="#4fb0e8"); ax.set_xticks(range(0, len(c), 3)); ax.set_xticklabels([f"{f:g}" for f in c[::3]], rotation=70, fontsize=8)
        ax.set_title(H(lab)); ax.set_ylim(0, 55)
        if ax in axs[:, 0]: ax.set_ylabel(H("רמת פס (dB)"))
    for ax in axs[1]: ax.set_xlabel(H("תדר (Hz)"))
    fs.save(fig, "maskers", "fig_masker_spectra")


def fig_target():
    fig, axs = plt.subplots(1, 2, figsize=(12, 3.8))
    x = G.synth_target("hammer", 4.0, FS, 1, 60.0); t = np.arange(len(x)) / FS
    axs[0].plot(t, x, color=ORANGE, lw=0.6); axs[0].set_xlabel(H("זמן (s)")); axs[0].set_ylabel(H("לחץ (Pa)")); axs[0].set_title(H("הכאה: צורת גל סינתטית ב-7 מ'"))
    c = U.third_octave_centres(50, 12500)
    for kind, col in (("hammer", ORANGE), ("drill", TEAL), ("jackhammer", RED), ("grinder", GRAY)):
        y = G.synth_target(kind, 4.0, FS, 1, 60.0); axs[1].semilogx(c, SP.third_octave_levels(y, FS, c), color=col, lw=1.8, label=H({"hammer": "הכאה", "drill": "קידוח", "jackhammer": "פטיש אוויר", "grinder": "משחזת"}[kind]))
    axs[1].set_xlabel(H("תדר (Hz)")); axs[1].set_ylabel(H("dB")); axs[1].set_title(H("ספקטרום שליש אוקטבה, כולם 60 dBA")); axs[1].legend()
    fs.save(fig, "targets", "fig_targets")


def fig_scenarios():
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    for ax, pc in zip(axs, ("0.6", "0.75")):
        rows = [r for r in scn["hammer"]["criteria"][pc] if r["required_masker_LAeq"] is not None]
        names = [nm(r["name"]) for r in rows]; v = [r["required_masker_LAeq"] for r in rows]
        err = [[r["required_masker_LAeq"] - r["uncertainty"]["lo95"] for r in rows], [r["uncertainty"]["hi95"] - r["required_masker_LAeq"] for r in rows]]
        ax.barh(range(len(rows)), v, xerr=err, color=[CAT[r["name"]] for r in rows], error_kw=dict(ecolor=GRAY, lw=1.2, capsize=3))
        ax.set_yticks(range(len(rows))); ax.set_yticklabels([H(n) for n in names])
        ax.axvline(scn["hammer"]["target_LAeq"], color=ORANGE, ls="--", lw=1.4)
        ax.set_xlabel(H("רמת מסכה נדרשת במקלט (dBA)")); ax.set_title(H(f"קריטריון P = {pc}"))
    axs[0].invert_yaxis()
    fs.save(fig, "scenario", "fig_required_levels")


def fig_curves():
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    for name, c in scn["hammer"]["curves"].items():
        if not c: continue
        ax.plot(c["level"], c["p"], color=CAT[name], lw=2, label=H(nm(name)))
    ax.axhline(0.6, color="k", ls="--", lw=0.8); ax.axhline(0.5, color=GRAY, lw=0.6)
    ax.set_xlabel(H("רמת המסכה במקלט (dBA)")); ax.set_ylabel(H("P(נכון), 2AFC")); ax.set_ylim(0.47, 1.02); ax.set_title(H("גילוי הכאה סינתטית (60 dBA) כפונקציה של רמת המסכה")); ax.legend(ncol=2, fontsize=9)
    fs.save(fig, "scenario", "fig_detection_curves")


def fig_map():
    m = scn["hammer"]["map"]
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    z = np.array(m["snr_db"]); t = np.array(m["t"]); f = np.array(m["fc"])
    im = ax.pcolormesh(t, np.arange(len(f)), z, cmap="viridis", vmin=-40, vmax=30, shading="auto")
    ax.set_yticks(np.arange(len(f))[::5]); ax.set_yticklabels([f"{v:.0f}" for v in f[::5]]); ax.grid(False)
    ax.set_xlabel(H("זמן (s)")); ax.set_ylabel(H("תדר מרכזי של ערוץ ERB (Hz)")); ax.set_title(H("מפת הסוואה: יחס מטרה למסכה (רעש ורוד 40 dBA) בכל תא זמן-תדר"))
    cb = fig.colorbar(im, ax=ax); cb.set_label(H("יחס (dB)"))
    fs.save(fig, "scenario", "fig_masking_map")


def fig_optimised():
    rows = [r for r in scn["hammer"]["criteria"]["0.6"] if r.get("optimised")]
    if not rows: return
    fig, axs = plt.subplots(1, 2, figsize=(12, 4))
    names = [nm(r["name"]) for r in rows]; flat = [r["required_masker_LAeq"] for r in rows]; opt = [r["optimised"]["LAeq"] for r in rows]
    y = np.arange(len(rows))
    for yi, f_, o_ in zip(y, flat, opt): axs[0].plot([o_, f_], [yi, yi], color=GRAY, lw=2, zorder=1)
    axs[0].scatter(flat, y, s=90, color="#4fb0e8", zorder=3, label=H("ספקטרום מקורי")); axs[0].scatter(opt, y, s=90, color=TEAL, zorder=3, label=H("ספקטרום מותאם"))
    axs[0].set_yticks(y); axs[0].set_yticklabels([H(n) for n in names]); axs[0].invert_yaxis(); axs[0].set_xlabel(H("רמה נדרשת (dBA)")); axs[0].set_title(H("חיסכון ברמה מוספת")); axs[0].legend(loc="lower left")
    r = next((x for x in rows if x["name"] == "Flowing water"), rows[0]); c = r["optimised"]["centres"]; g = np.array(r["optimised"]["gains_db"]); g = g - g.max()
    axs[1].bar(range(len(c)), g, color=TEAL); axs[1].set_xticks(range(len(c))); axs[1].set_xticklabels([f"{v:.0f}" for v in c], rotation=60, fontsize=9)
    axs[1].set_xlabel(H("תדר מרכזי של רצועה (Hz)")); axs[1].set_ylabel(H("הגברה יחסית (dB)")); axs[1].set_title(H("צורת הספקטרום המותאמת: " + nm(r["name"])))
    fs.save(fig, "scenario", "fig_optimised")


def fig_experiment():
    fig, axs = plt.subplots(1, 3, figsize=(14, 4))
    tr = sim["staircase_trials"]
    for k, col in ((0, NAVY), (1, TEAL)):
        pts = [(i, t["snr"], t["correct"]) for i, t in enumerate(tr) if t["track"] == k]
        axs[0].plot([p[0] + 1 for p in pts], [p[1] for p in pts], "-", color=col, lw=1, alpha=.8)
        axs[0].scatter([p[0] + 1 for p in pts], [p[1] for p in pts], c=["#3fcf8e" if p[2] else RED for p in pts], s=22, zorder=3)
    axs[0].axhline(sim["true_threshold_db"], color=ORANGE, ls="--", lw=1.2); axs[0].set_xlabel(H("מספר ניסיון")); axs[0].set_ylabel(H("SNR (dB)")); axs[0].set_title(H("שתי מדרגות משולבות (מאזין מדומה)"))
    pm = sim["constant"]["psychometric"]
    axs[1].plot(pm["curve"]["x"], pm["curve"]["p"], color=RED, lw=2, label=H("התאמה"))
    axs[1].errorbar(pm["levels"], np.array(pm["k"]) / np.array(pm["n"]), fmt="o", color=RED)
    axs[1].plot(sim["model_curve"]["x"], sim["model_curve"]["p"], "--", color=NAVY, lw=2, label=H("מודל מהיר"))
    axs[1].axvline(sim["true_threshold_db"], color=ORANGE, ls=":", lw=1); axs[1].set_xlabel(H("SNR (dB)")); axs[1].set_ylabel(H("P(נכון)")); axs[1].set_title(H("עקומה פסיכומטרית: התאמה מול מודל")); axs[1].legend(); axs[1].set_ylim(0.4, 1.02)
    pmc = sim["constant"]["psychometric"]
    vals = [sim["true_threshold_db"], sim["staircase"].get("staircase_threshold"), pmc["threshold"]]
    errs = [[0, 0], [sim["staircase"].get("staircase_sd") or 0, sim["staircase"].get("staircase_sd") or 0], [pmc["threshold"] - pmc["ci95"][0], pmc["ci95"][1] - pmc["threshold"]]]
    for i, (v, e, c) in enumerate(zip(vals, errs, (ORANGE, NAVY, TEAL))):
        axs[2].errorbar([i], [v], yerr=[[e[0]], [e[1]]], fmt="o", color=c, ms=9, capsize=5, lw=2)
    axs[2].set_xlim(-0.6, 2.6); axs[2].set_xticks(range(3)); axs[2].set_xticklabels([H("אמת (הדמיה)"), H("מדרגה"), H("התאמה פסיכומטרית")], fontsize=10)
    axs[2].set_ylabel(H("סף (dB SNR)")); axs[2].set_title(H("שחזור הסף המדומה (עם טווח)"))
    fs.save(fig, "experiment", "fig_experiment")


def fig_2afc():
    fig, ax = plt.subplots(figsize=(10, 3.4)); ax.axis("off"); ax.set_xlim(0, 10); ax.set_ylim(0, 3.4); ax.grid(False)
    box(ax, 7.4, 1.2, 2.4, 1.2, "מסכה (קטע אקראי 1)\n+ מטרה בסף SNR", fc="#FDE9D3", ec=ORANGE, fs=10)
    box(ax, 4.5, 1.2, 2.4, 1.2, "מסכה (קטע אקראי 2)\nללא מטרה", fc=LIGHT, fs=10)
    box(ax, 1.5, 1.2, 2.4, 1.2, "המאזין בוחר A או B\nמדרגה מעדכנת את ה-SNR", fc="#D6EEEE", fs=10)
    ax.text(8.6, 2.65, H("מרווח A או B (אקראי, בצד השרת)"), ha="center", color=NAVY, fontsize=10)
    arrow(ax, (7.35, 1.8), (6.95, 1.8)); arrow(ax, (4.45, 1.8), (3.95, 1.8))
    ax.text(5.0, 0.55, H("מפתח התשובה לעולם אינו נשלח לדפדפן; ההשמעה דרך כיול אוזניות ותקרת רמה"), ha="center", fontsize=10, color=RED)
    fs.save(fig, "experiment", "fig_2afc")


if __name__ == "__main__":
    for f in (fig_architecture, fig_validation_curves, fig_forward, fig_casp, fig_maskers, fig_target, fig_scenarios, fig_curves, fig_map, fig_optimised, fig_experiment, fig_2afc):
        f()
