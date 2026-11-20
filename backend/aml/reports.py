"""CSV / Excel / PDF / WAV exports. Every export carries the model identity and the limitations text."""
from __future__ import annotations
import csv, io, json, datetime
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import audio_io

LIMITS = [
    "Fast model (ERB-EDM) is a screening model calibrated to the critical ratio; CASP (AMT paulick2024) is the reference model but was run only where its result is shown.",
    "Results are model predictions of energetic masking detectability for a listener with normal hearing, not a guarantee of inaudibility.",
    "Masker level at the receiver is physical SPL; headphone playback in the listening test is separate and depends on the entered headphone calibration.",
    "Attentional distraction, informational masking and annoyance are not predicted by the detectability model; annoyance indices are proxies for relative comparison.",
    "Synthetic targets and maskers are labelled SYNTHETIC and are not substitutes for calibrated field recordings.",
]


def _f(v, nd=2):
    return "" if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), nd)


def compare_rows_flat(rows):
    out = []
    for r in rows:
        u = r.get("uncertainty") or {}
        m = r.get("metrics") or {}
        o = r.get("optimised") or {}
        out.append({
            "masker": r["name"], "category": r["category"],
            "required_LAeq_dB": _f(r.get("required_masker_LAeq")), "ci95_lo_dB": _f(u.get("lo95")), "ci95_hi_dB": _f(u.get("hi95")),
            "snr_at_threshold_dB": _f(r.get("snr_at_threshold")),
            "loudness_N5_sone_proxy": _f(m.get("N5_sone")), "PA_proxy": _f(m.get("PA_proxy")),
            "sharpness_acum_proxy": _f(m.get("sharpness_acum")), "fluctuation_vacil_proxy": _f(m.get("fluct_vacil")),
            "optimised_LAeq_dB": _f(o.get("LAeq")), "optimised_saving_dB": _f(o.get("saving_dBA")),
        })
    return out


def to_csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(payload: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    head = PatternFill("solid", fgColor="12304A"); hf = Font(color="FFFFFF", bold=True)

    def sheet(name, rows, first=False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = name[:31]
        if not rows:
            ws.append(["(no data)"]); return
        keys = list(rows[0].keys())
        ws.append(keys)
        for c in ws[1]:
            c.fill, c.font = head, hf
            c.alignment = Alignment(horizontal="center")
        for r in rows:
            ws.append([r.get(k) for k in keys])
        for i, k in enumerate(keys, 1):
            ws.column_dimensions[get_column_letter(i)].width = max(12, min(40, len(str(k)) + 3))
        ws.freeze_panes = "A2"

    meta = [{"item": k, "value": json.dumps(v) if isinstance(v, (dict, list, tuple)) else v} for k, v in payload.get("meta", {}).items()]
    meta += [{"item": "limitation", "value": s} for s in LIMITS]
    sheet("Summary", meta, first=True)
    sheet("Maskers", compare_rows_flat(payload.get("compare", [])))
    curves = []
    for c in payload.get("curves", []):
        for lv, p in zip(c["level"], c["p"]):
            curves.append({"masker": c["name"], "masker_LAeq_dB": _f(lv), "P_2AFC": _f(p, 4)})
    sheet("Detection curves", curves)
    sheet("Experiment trials", payload.get("trials", []))
    sheet("Psychometric", payload.get("psychometric", []))
    sheet("Model vs human", payload.get("model_vs_human", []))
    bio = io.BytesIO(); wb.save(bio)
    return bio.getvalue()


def _fig_png(fig):
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=160, bbox_inches="tight"); plt.close(fig); return b.getvalue()


def to_pdf(payload: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title="Acoustic Masking Lab report")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=22, textColor=colors.HexColor("#12304A"), alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.HexColor("#12304A"))
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#555555"))
    S = []
    meta = payload.get("meta", {})
    S += [Paragraph("Acoustic Masking Lab", h1), Paragraph("Detectability of industrial noise in natural and synthetic maskers", ss["Heading3"]),
          Paragraph(datetime.datetime.now().strftime("Generated %Y-%m-%d %H:%M"), small), Spacer(1, 10)]
    mt = [[k, str(v)[:90]] for k, v in meta.items()]
    if mt:
        t = Table(mt, colWidths=[5 * cm, 11.5 * cm])
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#12304A")),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        S += [t, Spacer(1, 10)]
    # figures
    sp = payload.get("spectra")
    if sp:
        fig, ax = plt.subplots(figsize=(7.4, 3.0))
        fc = np.array(sp["third_octave"]["fc"], float); L = np.array([np.nan if v is None else v for v in sp["third_octave"]["L"]], float)
        ax.bar(range(len(fc)), L, color="#2A7F9E"); ax.set_xticks(range(len(fc))[::2]); ax.set_xticklabels([f"{f:g}" for f in fc[::2]], rotation=60, fontsize=7)
        ax.set_ylabel("dB re 20 µPa"); ax.set_title("Target 1/3-octave spectrum at the receiver"); ax.grid(alpha=.3)
        S += [Paragraph("1. Target", h2), Image(io.BytesIO(_fig_png(fig)), width=16.5 * cm, height=6.7 * cm)]
    curves = payload.get("curves") or []
    if curves:
        fig, ax = plt.subplots(figsize=(7.4, 3.4))
        for c in curves:
            ax.plot(c["level"], c["p"], label=c["name"], lw=1.6)
        ax.axhline(payload["meta"].get("criterion_P2AFC", 0.6), ls="--", c="k", lw=.8); ax.axhline(.5, c="#888", lw=.6)
        ax.set_xlabel("Masker LAeq at receiver (dBA)"); ax.set_ylabel("P(correct), 2AFC"); ax.set_ylim(.45, 1.01); ax.grid(alpha=.3)
        ax.legend(fontsize=6, ncol=2, loc="upper right"); ax.set_title("Predicted detection versus masker level (fast model)")
        S += [Paragraph("2. Predicted detectability", h2), Image(io.BytesIO(_fig_png(fig)), width=16.5 * cm, height=7.6 * cm)]
    rows = compare_rows_flat(payload.get("compare", []))
    if rows:
        S.append(Paragraph("3. Minimum masker level and cost", h2))
        hdr = ["Masker", "Cat.", "Req. LAeq", "95 % range", "N5 proxy", "PA proxy", "Opt. LAeq"]
        data = [hdr] + [[r["masker"][:26], r["category"][:5], r["required_LAeq_dB"], f'{r["ci95_lo_dB"]}…{r["ci95_hi_dB"]}', r["loudness_N5_sone_proxy"], r["PA_proxy"], r["optimised_LAeq_dB"]] for r in rows]
        t = Table(data, repeatRows=1, colWidths=[4.6 * cm, 1.4 * cm, 2 * cm, 3 * cm, 1.9 * cm, 1.8 * cm, 1.8 * cm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12304A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTSIZE", (0, 0), (-1, -1), 8), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3F6")])]))
        S += [t, Paragraph("Required levels are the A-weighted equivalent masker level at the receiver for which the predicted 2AFC proportion correct equals the criterion; the range combines masker-realisation spread and model-form uncertainty. N5 and PA are proxies for relative comparison only.", small)]
    ex = payload.get("psychometric_curve")
    if ex:
        fig, ax = plt.subplots(figsize=(7.4, 3.4))
        ax.plot(ex["x"], ex["p"], c="#C2410C", label="Human fit")
        ax.errorbar(ex["levels"], np.array(ex["k"]) / np.array(ex["n"]), fmt="o", c="#C2410C")
        if ex.get("model"):
            ax.plot(ex["model"]["x"], ex["model"]["p"], c="#2A7F9E", label="Model")
        ax.set_xlabel("SNR (dB)"); ax.set_ylabel("P(correct)"); ax.grid(alpha=.3); ax.legend(); ax.set_ylim(.4, 1.02)
        S += [Paragraph("4. Listening experiment", h2), Image(io.BytesIO(_fig_png(fig)), width=16.5 * cm, height=7.6 * cm)]
        for k, v in (payload.get("experiment_text") or {}).items():
            S.append(Paragraph(f"<b>{k}</b>: {v}", body))
    S += [Paragraph("Limitations", h2)] + [Paragraph("• " + s, body) for s in LIMITS]
    doc.build(S)
    return buf.getvalue()


def mix_wav(target_pa, masker_pa, fs, as_pascal=True):
    n = min(len(target_pa), len(masker_pa))
    mix = np.asarray(target_pa[:n]) + np.asarray(masker_pa[:n])
    if as_pascal:
        return audio_io.write_wav_bytes(mix.astype(np.float32), fs, "FLOAT")
    pk = np.max(np.abs(mix)) + 1e-12
    return audio_io.write_wav_bytes((mix / pk * 0.89).astype(np.float32), fs, "PCM_24")
