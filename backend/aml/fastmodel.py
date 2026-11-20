"""Fast screening detectability model: "ERB-EDM" (ERB excitation + energy-detector model).

THIS IS NOT CASP. CASP / Paulick2024 is run separately through MATLAB + the Auditory Modeling Toolbox
(``casp_bridge.py``). ERB-EDM exists because CASP needs seconds per stimulus pair, which is too slow for
interactive sliders, optimisation and Monte-Carlo uncertainty. Its calibration is checked against CASP
(see docs/validation) and its limitations are listed in the research review.

Structure (each stage has a literature precedent, see docs/research):
 1. ERB-spaced 4th-order gammatone filterbank (Patterson et al. 1987; Glasberg & Moore 1990 ERB scale).
 2. Channel power in short windows T_k = max(10 ms, 1.5/ERB_k)  -> excitation E(k,t) in Pa^2.
 3. Internal noise floor from the absolute threshold in quiet (Terhardt 1979 approx.), expressed as the
    tone power at threshold in each channel (so quiet and masked thresholds share one K).
 4. Non-simultaneous (forward) masking: exponential decay of the masker excitation, tau = 30 ms.
 5. Energy detector per cell with relative std  sqrt(1/(T_k W_k) + eps^2)  (chi-square fluctuation of
    noise energy + a level-resolution floor eps ~ 0.1, i.e. ~0.4 dB, cf. intensity discrimination).
 6. Optimal combination over channels and a sliding temporal integration window (300 ms):
    d'^2 = max_t  sum_k sum_{cells in window} (eta*dE/sigma)^2 .
 7. 2AFC mapping  P = Phi(d'/sqrt(2)).
 eta is calibrated once so that a 500 ms, 1 kHz tone in white noise reaches P = 0.75 at the
 critical ratio CR = 18 dB (power ratio tone / noise spectral density), cf. Hawkins & Stevens 1950.

Because target and masker excitation are computed once and enter the formulas through simple power
gains, detection curves versus target level or masker level are obtained without re-filtering.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from scipy import signal
from scipy.stats import norm
from . import units as U

HOP_S = 0.005
TAU_FM = 0.030
T_INT = 0.300
EPS_REL = 0.10
CR_CAL_DB = 18.0
P_CAL = 0.75
K_CAL = 10 ** 1.8 / (1.019 * 132.6)   # tone/noise-in-channel power ratio at threshold implied by CR = 18 dB at 1 kHz (-3.3 dB)
SIGMA_CAL_DB = 3.0           # model-form uncertainty of a masked-threshold estimate (documented in research review)


def phi(x):
    return norm.cdf(x)


def p2afc_from_dprime(d):
    return phi(np.asarray(d, float) / np.sqrt(2.0))


def dprime_from_p2afc(p):
    return np.sqrt(2.0) * norm.ppf(np.clip(p, 1e-9, 1 - 1e-9))


@dataclass
class Params:
    fmin: float = 50.0
    fmax: float = 12000.0
    spacing_erb: float = 1.0
    hop_s: float = HOP_S
    tau_fm: float = TAU_FM
    t_int: float = T_INT
    eps_rel: float = EPS_REL
    eta: float | None = None          # None -> calibrated default
    use_quiet_floor: bool = True
    quiet_offset_db: float = 0.0      # participant-specific shift of the absolute threshold


_BANK_CACHE: dict = {}


def filterbank(fs, p: Params):
    key = (int(fs), p.fmin, p.fmax, p.spacing_erb)
    if key in _BANK_CACHE:
        return _BANK_CACHE[key]
    e0, e1 = U.hz_to_erb_number(p.fmin), U.hz_to_erb_number(min(p.fmax, 0.45 * fs))
    n = int(np.floor((e1 - e0) / p.spacing_erb)) + 1
    fc = U.erb_number_to_hz(e0 + p.spacing_erb * np.arange(n))
    # 4th-order gammatone as a cascade of four complex one-pole low-pass filters on the demodulated signal
    # (Hohmann 2002 style; numerically stable at any fs, unlike the direct-form IIR). b = 1.019 ERB.
    coefs = [float(np.exp(-2 * np.pi * 1.019 * U.erb_hz(f) / fs)) for f in fc]
    _BANK_CACHE[key] = (fc, coefs)
    return fc, coefs


def channel_power(x, fs, p: Params):
    """Smoothed channel power E[k, i] (Pa^2) on a common grid with hop p.hop_s. Returns (fc, E, T_k, t).

    Frequency-domain implementation: for every channel the analytic gammatone-cascade output is computed
    on a decimated grid (only the +-8 b bins around the channel are inverse-transformed), then the power
    2|z|^2 is averaged over T_k with an interpolated cumulative integral. Equivalent to the time-domain
    cascade of four complex one-pole filters (verified in tests/test_fastmodel.py)."""
    fc, coefs = filterbank(fs, p)
    hop = max(1, int(round(p.hop_s * fs)))
    x = np.asarray(x, float)
    N = len(x)
    centres = np.arange(hop // 2, N, hop)
    tc = centres / fs
    W = U.erb_hz(fc)
    T_k = np.maximum(0.010, 1.5 / W)
    E = np.zeros((len(fc), len(centres)))
    from scipy import fft as sfft
    nfft = int(sfft.next_fast_len(N + 4096))
    X = sfft.fft(x, nfft)
    for k, a in enumerate(coefs):
        b = 1.019 * W[k]
        M = int(min(nfft // 2 - 1, np.ceil(6.0 * b / fs * nfft)))
        n_small = int(sfft.next_fast_len(2 * M + 1))
        M = (n_small - 1) // 2
        n_small = 2 * M + 1 if (2 * M + 1) == n_small else n_small
        m = np.arange(-M, M + 1) if n_small == 2 * M + 1 else np.arange(-M, n_small - M)
        s0 = int(round(fc[k] / fs * nfft))
        H = ((1.0 - a) / (1.0 - a * np.exp(-2j * np.pi * m / nfft))) ** 4
        Z = X[(s0 + m) % nfft] * H
        z = sfft.ifft(sfft.ifftshift(Z)) * (n_small / nfft)
        p_d = 2.0 * (z.real ** 2 + z.imag ** 2)
        fs_d = fs * n_small / nfft
        t_d = np.arange(n_small) / fs_d
        cum = np.concatenate([[0.0], np.cumsum(p_d) / fs_d])
        t_edges = np.concatenate([t_d, [t_d[-1] + 1 / fs_d]])
        lo = np.clip(tc - T_k[k] / 2, 0, N / fs)
        hi = np.clip(tc + T_k[k] / 2, 0, N / fs)
        E[k] = (np.interp(hi, t_edges, cum) - np.interp(lo, t_edges, cum)) / np.maximum(hi - lo, 1e-9)
    return fc, E, T_k, tc


def _forward_mask(E, hop_s, tau):
    out = E.copy()
    d = np.exp(-hop_s / tau)
    for i in range(1, out.shape[1]):
        np.maximum(out[:, i], out[:, i - 1] * d, out=out[:, i])
    return out


@dataclass
class Analysis:
    fc: np.ndarray
    t: np.ndarray
    T_k: np.ndarray
    W: np.ndarray
    E_t: np.ndarray            # target channel power (reference gain), Pa^2
    E_m: np.ndarray            # masker channel power incl. forward masking spread
    E_int: np.ndarray          # internal noise (absolute threshold) per channel
    p: Params
    eta: float
    hop_s: float

    # ---------------------------------------------------------------- core
    def cell_d2(self, gt_db=0.0, gm_db=0.0):
        """Squared d' contribution of each (channel, frame) cell, with the overlap correction hop/T_k."""
        gt = 10 ** (gt_db / 10)
        gm = 10 ** (gm_db / 10)
        denom = gm * self.E_m + self.E_int[:, None]
        r = gt * self.E_t / np.maximum(denom, 1e-300)
        sig2 = 1.0 / (self.T_k * self.W) + self.p.eps_rel ** 2
        w = (self.hop_s / self.T_k)[:, None]
        return (self.eta ** 2) * w * r ** 2 / sig2[:, None]

    def dprime(self, gt_db=0.0, gm_db=0.0, full=False):
        c2 = self.cell_d2(gt_db, gm_db)
        series = c2.sum(axis=0)
        L = max(1, int(round(self.p.t_int / self.hop_s)))
        cs = np.concatenate([[0.0], np.cumsum(series)])
        if len(series) <= L:
            win = np.array([cs[-1]])
            idx = np.array([len(series) // 2])
        else:
            win = cs[L:] - cs[:-L]
            idx = np.arange(len(win)) + L // 2
        j = int(np.argmax(win))
        d = float(np.sqrt(max(win[j], 0.0)))
        if not full:
            return d
        return {"d": d, "t_peak": float(self.t[min(idx[j], len(self.t) - 1)]), "series": series,
                "win": win, "win_t": self.t[np.minimum(idx, len(self.t) - 1)], "c2": c2}

    def p2afc(self, gt_db=0.0, gm_db=0.0):
        return float(p2afc_from_dprime(self.dprime(gt_db, gm_db)))

    # --------------------------------------------------------- inversions
    def solve(self, p_target=0.75, var="target", lo=-80.0, hi=80.0):
        """Gain (dB, relative to the analysed levels) at which P_2AFC = p_target.

        var='target': find target gain; var='masker': find masker gain. Returns nan when not bracketed.
        """
        f = (lambda g: self.p2afc(g, 0.0) - p_target) if var == "target" else (lambda g: self.p2afc(0.0, g) - p_target)
        a, b = lo, hi
        fa, fb = f(a), f(b)
        if fa * fb > 0:
            return float("nan")
        for _ in range(60):
            m = 0.5 * (a + b)
            fm = f(m)
            if fa * fm <= 0:
                b, fb = m, fm
            else:
                a, fa = m, fm
        return 0.5 * (a + b)

    def snr_map_db(self, gt_db=0.0, gm_db=0.0):
        """Per-cell target-to-(masker+internal noise) ratio in dB, for the masking map."""
        denom = 10 ** (gm_db / 10) * self.E_m + self.E_int[:, None]
        return U.db(10 ** (gt_db / 10) * self.E_t / denom)

    def channel_contrib(self, gt_db=0.0, gm_db=0.0):
        """Share of d'^2 carried by each channel (for the 'where is it detected' plot)."""
        c2 = self.cell_d2(gt_db, gm_db).sum(axis=1)
        return c2 / max(c2.sum(), 1e-30)


def default_eta(p: Params | None = None, fs=32000):
    return _calibrate(p or Params(), fs)


_ETA = {}


def _calibrate(p: Params, fs):
    key = (p.hop_s, p.tau_fm, p.t_int, p.eps_rel, p.spacing_erb, p.fmin, p.fmax, p.use_quiet_floor, p.quiet_offset_db, fs)
    if key in _ETA:
        return _ETA[key]
    rng = np.random.default_rng(12345)
    dur = 1.0
    n = int(dur * fs)
    t = np.arange(n) / fs
    # white noise with one-sided spectral density N0 (Pa^2/Hz) high enough that quiet floor is negligible
    N0_db = 30.0 + 10 * np.log10(1.0)  # dB re (20uPa)^2/Hz -> large vs. threshold in quiet at 1 kHz
    sigma2 = U.P0 ** 2 * 10 ** (N0_db / 10) * fs / 2
    noise = rng.standard_normal(n) * np.sqrt(sigma2)
    # 500 ms 1 kHz tone with 20 ms ramps, power set via the critical ratio at threshold
    tone = np.zeros(n)
    i0, i1 = int(0.25 * fs), int(0.75 * fs)
    ramp = np.ones(i1 - i0)
    nr = int(0.02 * fs)
    ramp[:nr] = np.linspace(0, 1, nr); ramp[-nr:] = np.linspace(1, 0, nr)
    tone[i0:i1] = ramp * np.sin(2 * np.pi * 1000 * t[i0:i1])
    N0 = U.P0 ** 2 * 10 ** (N0_db / 10)
    P_tone = N0 * 10 ** (CR_CAL_DB / 10)          # tone power (Pa^2) at threshold
    tone *= np.sqrt(2 * P_tone)
    q = Params(**{**p.__dict__, "eta": 1.0})
    an = analyse(tone, noise, fs, q, calibrate=False)
    d1 = an.dprime()
    target_d = float(dprime_from_p2afc(P_CAL))
    eta = target_d / d1
    _ETA[key] = eta
    return eta


def analyse(target, masker, fs, p: Params | None = None, calibrate=True) -> Analysis:
    """Filter target and masker once. Signals in Pa, same length and fs."""
    p = p or Params()
    n = min(len(target), len(masker))
    target = np.asarray(target[:n], float)
    masker = np.asarray(masker[:n], float)
    fc, Et, T_k, t = channel_power(target, fs, p)
    _, Em, _, _ = channel_power(masker, fs, p)
    Em = _forward_mask(Em, p.hop_s, p.tau_fm)
    if p.use_quiet_floor:
        Lq = U.threshold_in_quiet_db(fc) + p.quiet_offset_db
        E_int = 0.5 * (U.P0 * 10 ** (Lq / 20)) ** 2 / K_CAL
    else:
        E_int = np.full(len(fc), 1e-30)
    eta = p.eta if p.eta is not None else (_calibrate(p, fs) if calibrate else 1.0)
    return Analysis(fc=fc, t=t, T_k=T_k, W=U.erb_hz(fc), E_t=Et, E_m=Em, E_int=E_int, p=p, eta=eta, hop_s=p.hop_s)
