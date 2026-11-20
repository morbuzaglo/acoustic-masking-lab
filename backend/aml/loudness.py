"""Loudness / sharpness / fluctuation / annoyance PROXIES built on the ERB excitation of ``fastmodel``.

These are engineering proxies in the spirit of Zwicker & Fastl (2007) *Psychoacoustics: Facts and Models*
(specific loudness N' = c (E_TQ)^0.23 [ (0.5+0.5 E/E_TQ)^0.23 - 1 ], von Bismarck/Aures sharpness weighting,
fluctuation strength with a 4 Hz band-pass weighting, psychoacoustic annoyance
PA = N5 (1 + sqrt(w_S^2 + w_FR^2)) with roughness R = 0). They are NOT implementations of ISO 532-1/-2,
DIN 45692 or the standardised PA procedure. Three constants are calibrated numerically against the
defining reference stimuli:
    1 sone  = 1 kHz tone at 40 dB SPL
    1 acum  = critical-band wide noise at 1 kHz, 60 dB SPL
    1 vacil = 1 kHz tone at 60 dB SPL, 100 % AM at 4 Hz
Use for RELATIVE comparisons between maskers; never as absolute sone/acum/vacil statements.
Also: annoyance is a separate construct from detectability; a quieter, more detectable masker can be
more annoying than a louder pleasant one. The optimiser therefore reports both, never merges them silently.
"""
from __future__ import annotations
import numpy as np
from scipy import signal
from . import units as U
from . import fastmodel as F

_CAL: dict = {}
_P = F.Params()


def _bark(f):
    f = np.asarray(f, float)
    return 13 * np.arctan(0.00076 * f) + 3.5 * np.arctan((f / 7500.0) ** 2)


def _cb_hz(f):
    return 25 + 75 * (1 + 1.4 * (np.asarray(f, float) / 1000) ** 2) ** 0.69


def _eq_floor(fc):
    return 0.5 * (U.P0 * 10 ** (U.threshold_in_quiet_db(fc) / 20)) ** 2 / F.K_CAL


def specific_loudness(E, fc):
    """E: (K,) or (K,T) channel power in Pa^2. Returns raw specific loudness per channel (arbitrary scale)."""
    Etq = _eq_floor(fc)
    Etq1k = float(_eq_floor(np.array([1000.0]))[0])
    sh = (Etq / Etq1k) ** 0.23
    if E.ndim == 2:
        Etq = Etq[:, None]; sh = sh[:, None]
    n = sh * ((0.5 + 0.5 * E / Etq) ** 0.23 - 1.0)
    return np.maximum(n, 0.0)


def _dz(fc):
    return U.erb_hz(fc) / _cb_hz(fc)


def _raw_loudness(E, fc):
    n = specific_loudness(E, fc)
    dz = _dz(fc)
    return (n * (dz[:, None] if n.ndim == 2 else dz)).sum(axis=0)


def _raw_sharp(E, fc):
    n = specific_loudness(E, fc)
    z = _bark(fc)
    g = np.where(z < 15.8, 1.0, 0.15 * np.exp(0.42 * (z - 15.8)))
    dz = _dz(fc)
    N = (n * dz).sum()
    return float((n * dz * g * z).sum() / max(N, 1e-12)), float(N)


def _tone(f, spl, dur, fs, am=0.0, am_hz=4.0):
    t = np.arange(int(dur * fs)) / fs
    x = np.sin(2 * np.pi * f * t) * (1 + am * np.sin(2 * np.pi * am_hz * t - np.pi / 2)) * np.sqrt(2) * U.P0 * 10 ** (spl / 20)
    return x


def _calibrate(fs):
    if fs in _CAL:
        return _CAL[fs]
    fc, E, T_k, t = F.channel_power(_tone(1000, 40, 1.0, fs), fs, _P)
    n_raw = _raw_loudness(E[:, len(t) // 2], fc)
    c_N = 1.0 / n_raw
    # sharpness reference: critical-band noise 920-1080 Hz at 60 dB
    rng = np.random.default_rng(7)
    x = rng.standard_normal(fs)
    sos = signal.butter(4, [920, 1080], "band", fs=fs, output="sos")
    x = signal.sosfiltfilt(sos, x)
    x *= U.P0 * 10 ** (60 / 20) / np.sqrt(np.mean(x * x))
    fc, E, _, t = F.channel_power(x, fs, _P)
    s_raw, _ = _raw_sharp(E.mean(axis=1), fc)
    c_S = 1.0 / s_raw
    # fluctuation reference: 1 kHz 60 dB tone, 100% AM at 4 Hz
    x = _tone(1000, 60, 2.0, fs, am=1.0, am_hz=4.0)
    fc, E, _, t = F.channel_power(x, fs, _P)
    Nt = _raw_loudness(E, fc) * c_N
    f_raw = _fluct_raw(Nt, _P.hop_s)
    c_F = 1.0 / f_raw
    _CAL[fs] = (c_N, c_S, c_F)
    return _CAL[fs]


def _fluct_raw(Nt, hop):
    Nt = np.asarray(Nt, float)
    if len(Nt) < 40:
        return 0.0
    x = Nt - Nt.mean()
    w = np.hanning(len(x))
    X = np.abs(np.fft.rfft(x * w)) * 2 / np.sum(w)
    f = np.fft.rfftfreq(len(x), hop)
    sel = (f >= 0.5) & (f <= 20)
    weight = 1.0 / (f[sel] / 4 + 4 / f[sel])
    m = X[sel] / max(Nt.mean(), 1e-9)
    return float(np.sqrt(np.sum((m * weight) ** 2)))


def metrics(x, fs=32000):
    """Return dict with LAeq, loudness proxy N5 (sone), sharpness proxy (acum), fluctuation proxy (vacil) and PA-proxy."""
    c_N, c_S, c_F = _calibrate(fs)
    fc, E, _, t = F.channel_power(np.asarray(x, float), fs, _P)
    Nt = _raw_loudness(E, fc) * c_N
    k = max(1, int(0.1 / _P.hop_s))
    Ns = np.convolve(Nt, np.ones(k) / k, mode="same") if len(Nt) > k else Nt
    N5 = float(np.percentile(Ns, 95))
    s_raw, _ = _raw_sharp(E.mean(axis=1), fc)
    S = s_raw * c_S
    Fv = _fluct_raw(Nt, _P.hop_s) * c_F
    wS = (S - 1.75) * 0.25 * np.log10(N5 + 10) if S > 1.75 else 0.0
    wFR = (2.18 / max(N5, 1e-3) ** 0.4) * 0.4 * Fv
    PA = N5 * (1 + np.sqrt(wS ** 2 + wFR ** 2))
    return {"LAeq": U.laeq(x, fs), "Leq": U.leq(x), "N5_sone": N5, "sharpness_acum": float(S), "fluct_vacil": float(Fv),
            "PA_proxy": float(PA), "N_mean_sone": float(Nt.mean())}


def stationary_N_from_E(E_mean, fc, fs=32000):
    """Loudness proxy (sone) from time-averaged channel power; used inside the optimiser."""
    c_N, _, _ = _calibrate(fs)
    return float(_raw_loudness(np.asarray(E_mean), fc) * c_N)
