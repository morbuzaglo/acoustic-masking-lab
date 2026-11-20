"""Units, level arithmetic, weighting and atmospheric absorption.

Conventions used everywhere in Acoustic Masking Lab
---------------------------------------------------
* Pressure signals are in **pascal (Pa)**, level reference p0 = 20 uPa.
* "Receiver level" = the physical sound pressure level at the listener's position (outdoors).
* "Playback level" = the level produced in a headphone coupler; different quantity (see ``calibration``).
* Band levels are in dB re 20 uPa; spectral densities in dB re (20 uPa)^2/Hz.
"""
from __future__ import annotations
import numpy as np
from scipy import signal

P0 = 20e-6  # Pa


def db(x, floor=1e-30):
    """10*log10 of a power-like quantity, floored to avoid -inf."""
    return 10.0 * np.log10(np.maximum(np.asarray(x, float), floor))


def undb(level_db):
    return 10.0 ** (np.asarray(level_db, float) / 10.0)


def spl_from_pa_rms(p_rms):
    return db((np.asarray(p_rms, float) / P0) ** 2)


def pa_rms_from_spl(spl):
    return P0 * 10.0 ** (np.asarray(spl, float) / 20.0)


def rms(x):
    x = np.asarray(x, float)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def leq(x):
    """Equivalent continuous level (dB re 20 uPa, unweighted) of a pressure signal in Pa."""
    return float(spl_from_pa_rms(rms(x)))


def dbsum(levels):
    return float(db(np.sum(undb(levels))))


# ------------------------------------------------------------------ weighting
def a_weight_db(f):
    """Analytic A-weighting (IEC 61672-1:2013, Annex E), dB, 0 dB at 1 kHz."""
    f = np.asarray(f, float)
    f2 = np.maximum(f, 1e-3) ** 2
    ra = (12194.0 ** 2 * f2 ** 2) / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194.0 ** 2))
    return 20 * np.log10(ra) + 2.00


def c_weight_db(f):
    f = np.asarray(f, float)
    f2 = np.maximum(f, 1e-3) ** 2
    rc = (12194.0 ** 2 * f2) / ((f2 + 20.6 ** 2) * (f2 + 12194.0 ** 2))
    return 20 * np.log10(rc) + 0.06


_FIR_CACHE: dict = {}


def a_weighting_fir(fs, ntaps=2049):
    """Linear-phase FIR approximating the analytic A-weighting (avoids the bilinear-IIR error near Nyquist)."""
    key = (int(fs), ntaps)
    if key not in _FIR_CACHE:
        f = np.linspace(0, fs / 2, 4096)
        g = 10 ** (a_weight_db(f) / 20)
        g[0] = 0.0
        _FIR_CACHE[key] = signal.firwin2(ntaps, f / (fs / 2), g, window="hann")
    return _FIR_CACHE[key]


def apply_a_weighting(x, fs):
    h = a_weighting_fir(fs)
    return signal.fftconvolve(np.asarray(x, float), h, mode="same")


def laeq(x, fs):
    """A-weighted equivalent level (dBA) of a pressure signal in Pa."""
    return leq(apply_a_weighting(x, fs))


# ----------------------------------------------------- atmospheric absorption
def alpha_iso9613_1(f, T_C=20.0, RH=70.0, pa_kPa=101.325):
    """Pure-tone atmospheric absorption coefficient, dB/m (ISO 9613-1:1993, eq. 3-5)."""
    f = np.asarray(f, float)
    T = T_C + 273.15
    T0, T01, pr = 293.15, 273.16, 101.325
    pa_r = pa_kPa / pr
    C = -6.8346 * (T01 / T) ** 1.261 + 4.6151
    h = RH * (10 ** C) / pa_r
    frO = pa_r * (24 + 4.04e4 * h * (0.02 + h) / (0.391 + h))
    frN = pa_r * (T / T0) ** -0.5 * (9 + 280 * h * np.exp(-4.170 * ((T / T0) ** (-1 / 3) - 1)))
    return 8.686 * f ** 2 * (
        1.84e-11 / pa_r * (T / T0) ** 0.5
        + (T / T0) ** -2.5 * (0.01275 * np.exp(-2239.1 / T) / (frO + f ** 2 / frO)
                              + 0.1068 * np.exp(-3352.0 / T) / (frN + f ** 2 / frN)))


def propagate(x, fs, d_from, d_to, T_C=20.0, RH=70.0, atmosphere=True):
    """Re-reference a free-field point-source recording from distance d_from to d_to (metres).

    Spherical spreading 20 log10(d_to/d_from) plus (optionally) excess atmospheric absorption
    alpha(f)*(d_to-d_from), applied as a zero-phase magnitude filter. Ground and barrier effects are
    NOT included (use the noise-box / ISO 9613-2 tools for that).
    """
    x = np.asarray(x, float)
    if abs(d_to - d_from) < 1e-9:
        return x.copy()
    g = d_from / d_to
    y = x * g
    if atmosphere:
        n = len(y)
        nfft = int(2 ** np.ceil(np.log2(max(n, 8))))
        Y = np.fft.rfft(y, nfft)
        f = np.fft.rfftfreq(nfft, 1 / fs)
        att = alpha_iso9613_1(np.maximum(f, 1.0), T_C, RH) * (d_to - d_from)
        Y *= 10 ** (-att / 20)
        y = np.fft.irfft(Y, nfft)[:n]
    return y


# ------------------------------------------------------------- band centres
def third_octave_centres(fmin=25.0, fmax=16000.0):
    """Preferred nominal 1/3-octave centres (ISO 266) between fmin and fmax."""
    nominal = np.array([20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800,
                        1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000])
    return nominal[(nominal >= fmin * 0.999) & (nominal <= fmax * 1.001)]


def octave_centres(fmin=31.5, fmax=16000.0):
    nominal = np.array([31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000])
    return nominal[(nominal >= fmin * 0.999) & (nominal <= fmax * 1.001)]


def exact_centres(nominal, fraction):
    """Exact base-10 centres (IEC 61260-1) for nominal values: fc = 1000 * G^(k/b)."""
    nominal = np.asarray(nominal, float)
    G = 10 ** 0.3
    k = np.round(fraction * np.log(nominal / 1000.0) / np.log(G))
    return 1000.0 * G ** (k / fraction)


# ---------------------------------------------------------------- ERB scale
def erb_hz(f):
    """Equivalent rectangular bandwidth (Glasberg & Moore 1990): 24.7 (4.37 f/1000 + 1)."""
    return 24.7 * (4.37 * np.asarray(f, float) / 1000.0 + 1.0)


def hz_to_erb_number(f):
    return 21.4 * np.log10(4.37 * np.asarray(f, float) / 1000.0 + 1.0)


def erb_number_to_hz(e):
    return (10 ** (np.asarray(e, float) / 21.4) - 1.0) * 1000.0 / 4.37


def erb_space(fmin, fmax, n):
    return erb_number_to_hz(np.linspace(hz_to_erb_number(fmin), hz_to_erb_number(fmax), n))


def threshold_in_quiet_db(f):
    """Terhardt (1979) approximation of the absolute threshold in quiet, dB SPL (free field, ~18-25 yr, binaural-ish).

    Used only as an *internal-noise floor* for the fast detectability model; it is clamped to
    a max of 90 dB and has an accuracy of a few dB between 100 Hz and 10 kHz.
    """
    fk = np.maximum(np.asarray(f, float), 20.0) / 1000.0
    t = 3.64 * fk ** -0.8 - 6.5 * np.exp(-0.6 * (fk - 3.3) ** 2) + 1e-3 * fk ** 4
    return np.minimum(t, 90.0)
