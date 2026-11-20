"""Spectral analysis: octave / third-octave levels, spectrogram, waveform decimation."""
from __future__ import annotations
import numpy as np
from scipy import signal
from . import units as U


def _band_edges(fc, fraction):
    G = 10 ** 0.3
    k = 1.0 / (2 * fraction)
    return fc / G ** k, fc * G ** k


def band_levels(x, fs, centres, fraction=3):
    """Band SPL (dB re 20 uPa) of a pressure signal using FFT power integration.

    The power spectrum is computed over the *whole* signal (Welch, 50 % overlap, Hann) so the
    band level equals the Leq contribution of the band. Exact base-10 band edges (IEC 61260-1).
    Bands whose upper edge exceeds Nyquist are returned as NaN.
    """
    x = np.asarray(x, float)
    nper = int(min(len(x), 2 ** int(np.floor(np.log2(max(256, min(len(x), fs * 0.5)))))))
    nper = max(nper, 256)
    f, pxx = signal.welch(x, fs, nperseg=nper, noverlap=nper // 2, window="hann", scaling="density")
    df = f[1] - f[0]
    exact = U.exact_centres(centres, fraction)
    out = np.full(len(centres), np.nan)
    for i, (fc_nom, fc) in enumerate(zip(centres, exact)):
        lo, hi = _band_edges(fc, fraction)
        if hi > fs / 2:
            continue
        # integrate with fractional edge bins for low-frequency accuracy
        p = 0.0
        sel = (f + df / 2 > lo) & (f - df / 2 < hi)
        for fj, pj in zip(f[sel], pxx[sel]):
            w = min(fj + df / 2, hi) - max(fj - df / 2, lo)
            p += pj * max(w, 0.0)
        out[i] = U.db(p / U.P0 ** 2)
    return out


def third_octave_levels(x, fs, centres=None):
    centres = U.third_octave_centres(25, 16000) if centres is None else centres
    return band_levels(x, fs, centres, 3)


def octave_levels(x, fs, centres=None):
    centres = U.octave_centres(31.5, 8000) if centres is None else centres
    return band_levels(x, fs, centres, 1)


def spectra_payload(x, fs):
    """Third-octave + octave levels (Z and A weighted totals) for the JSON API."""
    c3 = U.third_octave_centres(25, min(16000, fs / 2 / 1.12))
    c1 = U.octave_centres(31.5, min(16000, fs / 2 / 1.42))
    L3 = band_levels(x, fs, c3, 3)
    L1 = band_levels(x, fs, c1, 1)
    return {
        "third_octave": {"fc": c3.tolist(), "L": _clean(L3), "LA": _clean(L3 + U.a_weight_db(U.exact_centres(c3, 3)))},
        "octave": {"fc": c1.tolist(), "L": _clean(L1), "LA": _clean(L1 + U.a_weight_db(U.exact_centres(c1, 1)))},
        "Leq": U.leq(x), "LAeq": U.laeq(x, fs),
        "Lpeak": float(U.spl_from_pa_rms(np.max(np.abs(x)))) if len(x) else None,
    }


def _clean(a):
    return [None if not np.isfinite(v) else round(float(v), 2) for v in a]


def spectrogram_db(x, fs, win_s=0.032, hop_s=0.008, fmax=None, max_frames=900, max_bins=200):
    """Spectrogram in dB SPL per bin (re 20 uPa, band-power per bin), returned decimated for plotting."""
    nper = int(2 ** np.round(np.log2(win_s * fs)))
    hop = max(1, int(hop_s * fs))
    hop = max(hop, int(np.ceil(len(x) / max_frames)))
    f, t, S = signal.spectrogram(x, fs, nperseg=nper, noverlap=max(0, nper - hop), window="hann", scaling="spectrum", mode="psd")
    S = S * (f[1] - f[0])  # power per bin (Pa^2)
    fmax = fmax or min(fs / 2, 16000)
    sel = f <= fmax
    f, S = f[sel], S[sel]
    L = U.db(S / U.P0 ** 2)
    if len(f) > max_bins:  # log-ish decimation by max over groups keeps tonal peaks visible
        edges = np.unique(np.round(np.geomspace(1, len(f), max_bins)).astype(int))
        rows, fc = [], []
        for a, b in zip(edges[:-1], edges[1:]):
            rows.append(U.db(np.sum(S[a:b + 1], axis=0) / U.P0 ** 2) if b > a else L[a])
            fc.append(f[a:b + 1].mean())
        L = np.array(rows); f = np.array(fc)
    return t, f, L


def waveform_envelope(x, fs, n=2000):
    """Min/max decimation for plotting a long waveform."""
    x = np.asarray(x, float)
    N = len(x)
    if N <= 2 * n:
        t = np.arange(N) / fs
        return t.tolist(), x.tolist(), x.tolist()
    k = N // n
    xr = x[: k * n].reshape(n, k)
    t = (np.arange(n) * k + k / 2) / fs
    return t.tolist(), xr.min(axis=1).tolist(), xr.max(axis=1).tolist()


def short_time_level(x, fs, win_s=0.125, hop_s=0.0625, weighting="A"):
    y = U.apply_a_weighting(x, fs) if weighting == "A" else x
    w = max(1, int(win_s * fs)); h = max(1, int(hop_s * fs))
    idx = np.arange(0, max(1, len(y) - w + 1), h)
    L = np.array([U.leq(y[i:i + w]) for i in idx])
    return (idx + w / 2) / fs, L
