"""Masker level and spectrum optimisation on top of the fast detectability model.

Problem solved:  minimise  J = LAeq(masker) + lambda * 10 log10(N_masker / 1 sone)
                 subject to  P_2AFC(target | masker) <= P_crit            (detectability target)
over a smooth spectral shape defined by band gains g_j (dB) of a chosen base masker.
Detectability, additional dBA and loudness/annoyance proxies are reported separately; the result is a
*model-based estimate with uncertainty*, never a guarantee of inaudibility.

Band decomposition: power-complementary weights  sum_j u_j(f)^2 = 1  (triangular in log f), so the
excitation of the shaped masker is the exact power sum  E_k(t) = sum_j g_j^2 Eb_j(k,t)  and no re-filtering
is needed during optimisation (a few ms per evaluation).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize
from . import units as U
from . import fastmodel as F
from . import loudness as LD

N_BANDS = 12


def band_centres(n=N_BANDS, fmin=100.0, fmax=10000.0):
    return np.geomspace(fmin, fmax, n)


def band_weights(f, centres):
    """u_j(f)^2 : triangular partition of unity in log2(f); first/last band are flat (=1) beyond the outer centres."""
    lf = np.log2(np.maximum(f, 1.0))
    lc = np.log2(centres)
    J = len(centres)
    W = np.zeros((J, len(f)))
    for j in range(J):
        if j == 0:
            W[j] = np.interp(lf, [lc[0], lc[1]], [1.0, 0.0])
        elif j == J - 1:
            W[j] = np.interp(lf, [lc[-2], lc[-1]], [0.0, 1.0])
        else:
            W[j] = np.interp(lf, [lc[j - 1], lc[j], lc[j + 1]], [0.0, 1.0, 0.0], left=0.0, right=0.0)
    return W


def split_bands(x, fs, centres):
    n = len(x)
    nfft = int(2 ** np.ceil(np.log2(n)))
    X = np.fft.rfft(x, nfft)
    f = np.fft.rfftfreq(nfft, 1 / fs)
    W = band_weights(f, centres)
    return [np.fft.irfft(X * np.sqrt(W[j]), nfft)[:n] for j in range(len(centres))]


def shaping_filter(x, fs, centres, g_db):
    """Apply the shaped masker gain sqrt(sum_j g_j^2 u_j^2) to a signal (zero-phase)."""
    n = len(x)
    nfft = int(2 ** np.ceil(np.log2(n)))
    X = np.fft.rfft(x, nfft)
    f = np.fft.rfftfreq(nfft, 1 / fs)
    W = band_weights(f, centres)
    g2 = (10 ** (np.asarray(g_db, float) / 10))[:, None]
    return np.fft.irfft(X * np.sqrt((W * g2).sum(axis=0)), nfft)[:n]


def build_scene(target, masker, fs, params: F.Params | None = None, centres=None):
    p = params or F.Params()
    centres = band_centres() if centres is None else centres
    n = min(len(target), len(masker))
    target = np.asarray(target[:n], float); masker = np.asarray(masker[:n], float)
    bands = split_bands(masker, fs, centres)
    fc, Et, T_k, t = F.channel_power(target, fs, p)
    Eb = np.stack([F.channel_power(b, fs, p)[1] for b in bands])
    PA = np.array([np.mean(U.apply_a_weighting(b, fs) ** 2) for b in bands])
    PZ = np.array([np.mean(b ** 2) for b in bands])
    if p.use_quiet_floor:
        E_int = 0.5 * (U.P0 * 10 ** ((U.threshold_in_quiet_db(fc) + p.quiet_offset_db) / 20)) ** 2
    else:
        E_int = np.full(len(fc), 1e-30)
    eta = p.eta if p.eta is not None else F.default_eta(p, fs)
    sc = Scene(fs=fs, centres=centres, fc=fc, t=t, T_k=T_k, W=U.erb_hz(fc), Et=Et, Eb=Eb, E_int=E_int, PA=PA, PZ=PZ,
               p=p, eta=eta)
    return sc


@dataclass
class Scene:
    fs: int
    centres: np.ndarray
    fc: np.ndarray
    t: np.ndarray
    T_k: np.ndarray
    W: np.ndarray
    Et: np.ndarray
    Eb: np.ndarray
    E_int: np.ndarray
    PA: np.ndarray
    PZ: np.ndarray
    p: F.Params
    eta: float

    def analysis(self, g_db):
        g2 = 10 ** (np.asarray(g_db, float) / 10)
        Em = np.tensordot(g2, self.Eb, axes=(0, 0))
        Em = F._forward_mask(Em, self.p.hop_s, self.p.tau_fm)
        return F.Analysis(fc=self.fc, t=self.t, T_k=self.T_k, W=self.W, E_t=self.Et, E_m=Em, E_int=self.E_int,
                          p=self.p, eta=self.eta, hop_s=self.p.hop_s)

    def laeq(self, g_db):
        return float(U.db(np.sum(10 ** (np.asarray(g_db) / 10) * self.PA) / U.P0 ** 2))

    def leq(self, g_db):
        return float(U.db(np.sum(10 ** (np.asarray(g_db) / 10) * self.PZ) / U.P0 ** 2))

    def loudness(self, g_db):
        g2 = 10 ** (np.asarray(g_db, float) / 10)
        Em = np.tensordot(g2, self.Eb, axes=(0, 0)).mean(axis=1)
        return LD.stationary_N_from_E(Em, self.fc, self.fs)

    def d_prime(self, g_db):
        return self.analysis(g_db).dprime()


# ------------------------------------------------------------------ solvers
def min_flat_level(scene: Scene, p_crit=0.60, lo=-80.0, hi=80.0):
    """Uniform masker gain (dB re the base masker's level) meeting P <= p_crit. Returns dict."""
    n = len(scene.centres)
    g0 = np.zeros(n)
    a = scene.analysis(g0)
    P_quiet = a.p2afc(0.0, -200.0)   # no masker at all: detection by the absolute threshold alone
    if P_quiet <= p_crit:
        return {"gain_db": -np.inf, "already_inaudible": True, "P_without_masker": P_quiet}
    g = a.solve(p_crit, "masker", lo=lo, hi=hi)
    return {"gain_db": g, "already_inaudible": False, "P_without_masker": P_quiet,
            "LAeq": scene.laeq(g0 + g) if np.isfinite(g) else float("nan"),
            "Leq": scene.leq(g0 + g) if np.isfinite(g) else float("nan")}


def optimise_shape(scene: Scene, p_crit=0.60, lam=0.5, la_cap=None, seed=0, below=45.0, above=25.0):
    """SLSQP shape optimisation with a final uniform rescale to hit the criterion exactly."""
    n = len(scene.centres)
    d_crit = float(F.dprime_from_p2afc(p_crit))
    flat = min_flat_level(scene, p_crit)
    if flat["already_inaudible"] or not np.isfinite(flat["gain_db"]):
        return {"ok": False, "reason": "already inaudible without masker" if flat["already_inaudible"] else "criterion not reachable",
                "flat": flat}
    N0 = 1.0
    g_min, g_max = flat["gain_db"] - below, flat["gain_db"] + above

    def J(g):
        return scene.laeq(g) + lam * 10 * np.log10(max(scene.loudness(g), 1e-3) / N0)

    def cons(g):
        return d_crit - scene.d_prime(g)

    start = np.full(n, flat["gain_db"])
    best = None
    rng = np.random.default_rng(seed)
    for trial in range(2):
        x0 = start + (0 if trial == 0 else rng.normal(0, 4, n))
        res = minimize(J, x0, method="SLSQP", bounds=[(g_min, g_max)] * n,
                       constraints=[{"type": "ineq", "fun": cons}], options={"maxiter": 70, "ftol": 1e-5, "eps": 0.4})
        g = np.clip(res.x, g_min, g_max)
        # re-establish the criterion by a uniform offset (bisection on d')
        lo, hi = -30.0, 30.0
        if scene.d_prime(g + hi) > d_crit:
            continue
        for _ in range(40):
            m = 0.5 * (lo + hi)
            if scene.d_prime(g + m) > d_crit:
                lo = m
            else:
                hi = m
        g = g + hi
        val = J(g)
        if (best is None or val < best[0]) and (la_cap is None or scene.laeq(g) <= la_cap):
            best = (val, g)
    if best is None:
        return {"ok": False, "reason": "no feasible shape under the LAeq cap", "flat": flat}
    g = best[1]
    return {"ok": True, "gains_db": g.tolist(), "centres": scene.centres.tolist(), "LAeq": scene.laeq(g), "Leq": scene.leq(g),
            "N_sone": scene.loudness(g), "P2AFC": float(scene.analysis(g).p2afc()), "J": best[0],
            "flat": {**flat, "N_sone": scene.loudness(np.full(n, flat["gain_db"]))}}


def level_uncertainty(levels, sigma_model=F.SIGMA_CAL_DB):
    """Combine Monte-Carlo spread (masker realisations) and model-form uncertainty into a 95 % interval (dB)."""
    lv = np.asarray([l for l in levels if np.isfinite(l)], float)
    if len(lv) == 0:
        return {"mean": float("nan"), "sd_mc": float("nan"), "sd_total": float("nan"), "lo95": float("nan"), "hi95": float("nan")}
    sd_mc = float(lv.std(ddof=1)) if len(lv) > 1 else 0.0
    sd = float(np.sqrt(sd_mc ** 2 + sigma_model ** 2))
    m = float(lv.mean())
    return {"mean": m, "sd_mc": sd_mc, "sd_model": float(sigma_model), "sd_total": sd,
            "lo95": m - 1.96 * sd, "hi95": m + 1.96 * sd}
