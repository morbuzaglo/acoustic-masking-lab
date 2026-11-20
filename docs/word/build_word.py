"""Build docs/Acoustic_Masking_Lab_Summary_HE.docx (Hebrew, RTL, David) with the acoustics-summary Book builder.
Run with the book's environment:  %LOCALAPPDATA%\\AcousticBook\\venv\\Scripts\\python.exe docs\\word\\build_word.py
Needs figures from make_figures.py and the JSON files in docs/validation."""
import sys, json, pathlib
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BOOK = ROOT.parent / 'acoustics-summary' / 'Acoustic_End_to_End' / 'scripts'
sys.path.insert(0, str(BOOK)); sys.path.insert(0, str(HERE))
import numpy as np
from docbuilder import Book as _Book
import docx
from docx.shared import Pt
import ch_a, ch_b, ch_c
from refs_aml import REFS

V = ROOT / 'docs' / 'validation'
val = json.loads((V / 'model_validation.json').read_text(encoding='utf-8'))
scn = json.loads((V / 'scenario_results.json').read_text(encoding='utf-8'))
cv = json.loads((V / 'casp_validation.json').read_text(encoding='utf-8'))
cal = json.loads((V / 'casp_calibration.json').read_text(encoding='utf-8'))
sim = json.loads((V / 'simulated_listener.json').read_text(encoding='utf-8'))


def interp_thr(gm, P, p=0.75):
    for i in range(len(gm) - 1):
        a, b_ = P[i] - p, P[i + 1] - p
        if a == 0: return gm[i]
        if a * b_ < 0: return gm[i] + (gm[i + 1] - gm[i]) * a / (a - b_)
    return float('nan')


h = scn['hammer']
pink = next(r for r in h['criteria']['0.6'] if r['name'] == 'Pink noise')
d4 = cv['tone4k']
D = {
    'eta': val['eta'], 'cr': val['cr_vs_freq']['cr_db'],
    'dur_drop': val['duration']['threshold_rel_db'][1] - val['duration']['threshold_rel_db'][5],
    'invar': cal['in_var'], 'casp4': d4['casp_thr_gm_db'], 'fast4': d4['fast_thr_gm_db'], 'casp4_diff': abs(d4['casp_thr_gm_db'] - d4['fast_thr_gm_db']),
    'raw4': interp_thr(d4['gm_db'], d4['casp_P_raw_amt_invar']),
    'crest': h['target_Lpeak'] - h['target_LAeq'], 'pink06': pink['required_masker_LAeq'], 'scn': scn, 'sim': sim,
}


class Book(_Book):
    def _fill(self, p, text, **fmt):
        super()._fill(p, text.replace('`', ''), **fmt)


TITLE = 'Acoustic Masking Lab'
SUB = 'מערכת לחיזוי ולבדיקה ניסויית של גילוי רעש תעשייתי על רקע צלילי טבע'
CHAPTERS = [ch_a.ch1, ch_a.ch2, ch_a.ch3, ch_b.ch4, ch_b.ch5, ch_b.ch6, ch_b.ch7, ch_c.ch8, ch_c.ch9, ch_c.ch10, ch_c.ch11, ch_c.ch12]


def make(labels):
    b = Book(labels, TITLE + ' — סיכום מחקר ועבודה')
    b.header_footer(TITLE + ' — סיכום המחקר והמערכת')
    p = b.para(TITLE, align='center', bold=True, size=36, color='12264A'); p.paragraph_format.space_before = Pt(120)
    p = b.para(SUB, align='center', bold=True, size=15, color='0F8B8D'); p.paragraph_format.space_before = Pt(18)
    b.para('סיכום מחקר ופיתוח: ספרות, מודלים, מימוש, אימות ותוצאות', align='center', size=11.5, color='B8312F')
    ch_a.abstract(b, D)
    b.page_break(); b.toc()
    for c in CHAPTERS:
        c(b, D)
    b.heading_plain('ביבליוגרפיה')
    for i, r in enumerate(REFS, 1):
        b.bib_entry(i, r)
    return b


if __name__ == '__main__':
    b1 = make({})
    b2 = make(b1.new_labels)
    out = ROOT / 'docs' / 'Acoustic_Masking_Lab_Summary_HE.docx'
    b2.save(out)
    print('saved', out, 'labels', len(b2.new_labels))
