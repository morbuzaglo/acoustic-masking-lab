"""WAV input/output, amplitude calibration, resampling, background subtraction.

Calibration modes (``Calibration.mode``)
  pa_float     samples are already pascal (typical for float WAV exported by measurement software)
  fullscale_pa digital full scale (+-1.0) corresponds to ``value`` Pa peak
  known_level  scale so that the Leq (or LAeq, ``weighting='A'``) of [t0,t1] equals ``value`` dB
  calibrator   a calibrator tone is present in [t0,t1]; its RMS corresponds to ``value`` dB SPL (default 94 dB)
"""
from __future__ import annotations
import io
from dataclasses import dataclass, field, asdict
import numpy as np
import soundfile as sf
from scipy import signal
from . import units as U


@dataclass
class Calibration:
    mode: str = "pa_float"
    value: float = 1.0
    t0: float = 0.0
    t1: float | None = None
    weighting: str = "Z"

    def to_dict(self):
        return asdict(self)


def read_wav_bytes(data: bytes):
    """Return (samples float64 mono [raw file units], fs, meta). Multi-channel -> channel 0."""
    x, fs = sf.read(io.BytesIO(data), dtype="float64", always_2d=True)
    info = sf.info(io.BytesIO(data))
    meta = {"channels": int(x.shape[1]), "subtype": info.subtype, "duration_s": float(len(x) / fs)}
    return x[:, 0].copy(), int(fs), meta


def write_wav_bytes(x, fs, subtype="FLOAT"):
    buf = io.BytesIO()
    sf.write(buf, np.asarray(x, float), int(fs), format="WAV", subtype=subtype)
    return buf.getvalue()


def resample(x, fs_in, fs_out):
    if int(fs_in) == int(fs_out):
        return np.asarray(x, float).copy()
    from math import gcd
    g = gcd(int(fs_in), int(fs_out))
    return signal.resample_poly(np.asarray(x, float), int(fs_out) // g, int(fs_in) // g)


def calibration_gain(x, fs, cal: Calibration):
    """Linear factor converting raw file units to pascal."""
    if cal.mode == "pa_float":
        return 1.0
    if cal.mode == "fullscale_pa":
        return float(cal.value)
    i0 = int(max(0.0, cal.t0) * fs)
    i1 = len(x) if cal.t1 is None else int(min(len(x) / fs, cal.t1) * fs)
    seg = np.asarray(x[i0:i1], float)
    if len(seg) < 16:
        raise ValueError("calibration segment is empty")
    if cal.mode == "known_level":
        cur = U.laeq(seg, fs) if cal.weighting.upper() == "A" else U.leq(seg)
        return float(10 ** ((cal.value - cur) / 20))
    if cal.mode == "calibrator":
        # band-limit around 1 kHz so that background noise does not bias the calibrator level
        sos = signal.butter(4, [800, 1250], btype="bandpass", fs=fs, output="sos")
        seg_f = signal.sosfiltfilt(sos, seg)
        cur = U.leq(seg_f)
        return float(10 ** ((cal.value - cur) / 20))
    raise ValueError(f"unknown calibration mode {cal.mode}")


def apply_calibration(x, fs, cal: Calibration):
    g = calibration_gain(x, fs, cal)
    return np.asarray(x, float) * g, g


def remove_dc_and_highpass(x, fs, fc=20.0):
    sos = signal.butter(4, fc, btype="highpass", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, np.asarray(x, float))


# ---------------------------------------------------------- background removal
def level_subtract(total_db, background_db):
    """ISO 1996-1 style energy subtraction of a residual level; NaN when the margin is < 3 dB
    is *not* applied here: callers decide (see ``margin_db``)."""
    d = 10 ** (total_db / 10) - 10 ** (background_db / 10)
    return float(10 * np.log10(d)) if d > 0 else float("nan")


def spectral_subtract(x, fs, noise, over=1.0, floor_db=-25.0, nperseg=4096):
    """Power spectral subtraction of a background recording from a target recording.

    x      : target + background (Pa)
    noise  : background only (Pa), any length
    over   : over-subtraction factor (1 = exact power subtraction)
    floor  : spectral floor relative to the noisy bin power (limits musical noise)

    Returns the estimate of the *specific* source signal (Pa). This is an estimate: where the
    background is within ~3 dB of the total the result is unreliable (reported by ``margin_by_band``).
    """
    x = np.asarray(x, float)
    noise = np.asarray(noise, float)
    f, _, Z = signal.stft(x, fs, nperseg=nperseg, noverlap=nperseg * 3 // 4, window="hann")
    _, pn = signal.welch(noise, fs, nperseg=nperseg, noverlap=nperseg * 3 // 4, window="hann", scaling="spectrum")
    # STFT |Z|^2 with the same window/scaling expectation as welch "spectrum"
    nz = pn[:, None]
    # scale: welch 'spectrum' returns power per bin = |X|^2 * 2 / (sum w)^2 ; STFT default scaling is 1/sum(w)
    pz = (np.abs(Z) ** 2) * 2.0
    clean = np.maximum(pz - over * nz, pz * 10 ** (floor_db / 10))
    gain = np.sqrt(clean / np.maximum(pz, 1e-300))
    _, y = signal.istft(Z * gain, fs, nperseg=nperseg, noverlap=nperseg * 3 // 4, window="hann")
    y = y[: len(x)]
    if len(y) < len(x):
        y = np.pad(y, (0, len(x) - len(y)))
    return y


def margin_by_band(x, noise, fs, centres):
    """Per 1/3-octave band: level of (target+background) minus level of background (dB). < 3 dB = unreliable."""
    from .spectra import third_octave_levels
    Lt = third_octave_levels(x, fs, centres)
    Ln = third_octave_levels(noise, fs, centres)
    return Lt - Ln
