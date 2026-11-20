"""Bridge to the real CASP model (AMT 1.6.0 ``paulick2024``) running in MATLAB.

The Python side only prepares calibrated stimuli, launches ``matlab -batch casp_run(...)`` and reads the
JSON result. No CASP stage is reimplemented in Python. If MATLAB or the AMT folder is missing the bridge
reports ``available() == False`` and the application keeps working with the fast ERB-EDM model, while
labelling every result with the model that produced it.
"""
from __future__ import annotations
import json, os, shutil, subprocess, tempfile, time, pathlib, threading
import numpy as np
from scipy.io import savemat
from . import audio_io

CASP_FS = 44100
ROOT = pathlib.Path(__file__).resolve().parents[2]
MATLAB_DIR = ROOT / "matlab"


def amt_root():
    env = os.environ.get("AML_AMT_ROOT")
    cands = [env] if env else []
    la = os.environ.get("LOCALAPPDATA", "")
    cands += [os.path.join(la, "AcousticMaskingLab", "amt", "amtoolbox-1.6.0"), str(ROOT / "tools" / "amtoolbox-1.6.0")]
    for c in cands:
        if c and os.path.isfile(os.path.join(c, "models", "paulick2024.m")):
            return c
    return None


def matlab_exe():
    exe = os.environ.get("AML_MATLAB") or shutil.which("matlab")
    if exe:
        return exe
    for base in (r"C:\Program Files\MATLAB",):
        if os.path.isdir(base):
            for v in sorted(os.listdir(base), reverse=True):
                p = os.path.join(base, v, "bin", "matlab.exe")
                if os.path.isfile(p):
                    return p
    return None


def available():
    return bool(amt_root() and matlab_exe())


def status():
    return {"available": available(), "matlab": matlab_exe(), "amt_root": amt_root(), "model": "paulick2024",
            "amt_version": "1.6.0"}


class CaspRun:
    """One background CASP job. ``progress`` in [0,1]; ``result`` filled when done."""

    def __init__(self, workdir=None):
        self.dir = pathlib.Path(workdir or tempfile.mkdtemp(prefix="aml_casp_"))
        self.job = self.dir / "job.mat"
        self.out = self.dir / "result.json"
        self.log = self.dir / "matlab.log"
        self.proc = None
        self.result = None
        self.error = None
        self.state = "pending"
        self.t0 = None

    def start(self, target, maskers, fs, gm_db, labels, sup_db=6.0, model="paulick2024"):
        """target: 1-D Pa; maskers: list over M of arrays (R, n) in Pa. All at ``fs``; resampled here to 44.1 kHz."""
        if not available():
            raise RuntimeError("MATLAB or AMT 1.6.0 not found (set AML_MATLAB / AML_AMT_ROOT)")
        tgt = audio_io.resample(target, fs, CASP_FS)
        n = len(tgt)
        mk = np.zeros((n, len(maskers[0]), len(maskers)))
        for m, reps in enumerate(maskers):
            for r, x in enumerate(reps):
                y = audio_io.resample(x, fs, CASP_FS)[:n]
                mk[: len(y), r, m] = y
        savemat(self.job, {"fs": float(CASP_FS), "target": tgt[:, None], "maskers": mk, "gm_db": np.asarray(gm_db, float),
                           "sup_db": float(sup_db), "model": model, "labels": np.array(labels, dtype=object)})
        cmd = [matlab_exe(), "-batch",
               f"addpath('{MATLAB_DIR}'); casp_run('{self.job}','{self.out}','{amt_root()}')"]
        self.state = "running"
        self.t0 = time.time()
        with open(self.log, "wb") as lf:
            self.proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=str(self.dir))
        threading.Thread(target=self._wait, daemon=True).start()

    def _wait(self):
        rc = self.proc.wait()
        if rc == 0 and self.out.exists():
            try:
                self.result = json.loads(self.out.read_text(encoding="utf-8"))
                self.state = "done"
            except Exception as e:  # noqa
                self.error = f"bad result file: {e}"
                self.state = "error"
        else:
            tail = self.log.read_text(errors="replace")[-1500:] if self.log.exists() else ""
            self.error = f"MATLAB exited with code {rc}\n{tail}"
            self.state = "error"

    def progress(self):
        p = self.out.with_suffix(".json.progress")
        if not p.exists():
            return 0.0
        lines = [l for l in p.read_text().splitlines() if l.strip()]
        if not lines:
            return 0.0
        if lines[-1].startswith("DONE"):
            return 1.0
        try:
            d, t, _ = lines[-1].split()
            return min(0.99, float(d) / float(t))
        except Exception:
            return 0.0

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.state = "cancelled"

    def info(self):
        return {"state": self.state, "progress": self.progress(), "error": self.error,
                "elapsed_s": (time.time() - self.t0) if self.t0 else 0.0}


INVAR_AMT = 40.0          # internal-noise variance of paulick2024_decision (calibrated by the authors for intensity discrimination)
_CAL_FILE = ROOT / "docs" / "validation" / "casp_calibration.json"


def invar_calibrated():
    """Decision-variance used for NOISE-masker predictions. AMT 1.6 contains the CASP front end and the
    intensity-discrimination back end only; for noise maskers the variance is re-calibrated (see
    docs/validation/casp_calibration.json), the front end is untouched. Falls back to the AMT default."""
    try:
        return float(json.loads(_CAL_FILE.read_text())["in_var"])
    except Exception:
        return INVAR_AMT


def p_from_mu(mu, in_var):
    """paulick2024_decision, nAFC = 2:  P = Phi(0.707 * mu / sqrt(in_var))."""
    from scipy.stats import norm
    return norm.cdf(0.707 * np.asarray(mu, float) / np.sqrt(in_var))


def p_table(result, in_var=None):
    """P(2AFC) per masker x level from the per-realisation correlation values (mean over realisations)."""
    mur = np.asarray(result["mu_r"], float)
    if mur.ndim == 2:
        mur = mur[None]
    return p_from_mu(mur, in_var or invar_calibrated()).mean(axis=-1)


def interpolate_threshold(gm_db, P, p_crit=0.75):
    """Masker level offset (dB) at which P(gm) crosses p_crit (P decreases with masker level). nan if not bracketed."""
    gm = np.asarray(gm_db, float); P = np.asarray(P, float)
    for i in range(len(gm) - 1):
        a, b = P[i] - p_crit, P[i + 1] - p_crit
        if a == 0:
            return float(gm[i])
        if a * b < 0:
            return float(gm[i] + (gm[i + 1] - gm[i]) * a / (a - b))
    return float("nan")
