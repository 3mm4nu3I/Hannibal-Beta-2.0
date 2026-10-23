"""Earth-Moon-Earth (moonbounce) link budget for the Orbital Directorate.

The Moon is a passive natural reflector: you transmit at it on an amateur band you are
licensed for, and ~2.5 s later you try to hear your own echo. This module does the sums
behind that -- path loss, dish gain, two-way Doppler, the thermal noise floor and the
processing gain you need to pull the echo out of it -- and reads the Moon's live range and
range-rate over your home station from JPL Horizons (menu [5] / the same source as the sky page).

Everything here is ordinary radar / radio-astronomy physics. The functions are pure (no
network, no globals) so they are easy to test; only current_moon() touches the network, through
hannibal_net's masked, cached, rate-limited layer like every other client.

References for the model:
  * EME path loss between isotropic antennas  L = (4*pi)^3 * R^4 / (lambda^2 * sigma)
  * parabolic-dish gain                        G = eta * (pi * D / lambda)^2
  * two-way Doppler                            f_d = -2 * f0 * v_radial / c   (v>0 = receding)
  * thermal noise                              N = k_B * T_sys * B
  * coherent processing gain                   G_p = 10*log10(B * tau)  (a theoretical ceiling only)
  * Yagi array gain                            G = G_1 + 10*log10(N) - phasing loss
  * system noise                               T_sys = T_receiver + T_sky + T_moon + T_ground
  * galactic sky noise                         T_sky = 2.7 K + T_144 * (f / 144 MHz)^-2.55
SNR is reported in a 2500 Hz reference bandwidth, the WSJT-X convention, so the verdict can be
compared against the published decode thresholds of the modes EME actually uses. Those thresholds
already include what the decoder gains from averaging, which is why the processing-gain figure is
shown for interest and never added to the SNR.

Antennas: a dish (prime-focus, offset or mesh) or an array of Yagis, on any band. Typical EME
stations use Yagi arrays on 6 m, 2 m and 70 cm and dishes from 23 cm up, so those are the defaults.
"""
import math
import os

C = 299_792_458.0            # m/s
K_B = 1.380649e-23           # J/K
R_MOON_KM = 1737.4           # volumetric mean radius
MOON_ALBEDO = 0.065          # radar albedo (frequency dependent, ~0.05-0.07; 6-7% reflective, and rough)
WSJT_REF_BW = 2500.0         # Hz: the reference bandwidth WSJT-X reports SNR in

# Amateur bands commonly used for EME: name -> representative frequency (Hz).
BANDS = {
    "6m": 50.2e6, "2m": 144.1e6, "70cm": 432.1e6, "23cm": 1296.1e6, "13cm": 2320.1e6, "3cm": 10368.1e6,
}

# Published WSJT-X / operator decode thresholds, SNR in a 2500 Hz reference bandwidth (dB).
# Approximate and mode-dependent; used only to label the verdict, never as a guarantee.
MODE_THRESHOLDS = [
    ("Q65 (digital)", -25.0),
    ("JT65 (digital)", -24.0),
    ("FT8 (digital)", -21.0),
    ("CW by ear", -15.0),
    ("SSB voice", 3.0),
]


def wavelength(f_hz):
    return C / float(f_hz)


def moon_rcs_m2(albedo=MOON_ALBEDO, r_moon_km=R_MOON_KM):
    """Radar cross-section of the Moon: albedo x its geometric cross-section (pi r^2)."""
    r = r_moon_km * 1000.0
    return albedo * math.pi * r * r


def path_loss_db(f_hz, range_km, albedo=MOON_ALBEDO, r_moon_km=R_MOON_KM):
    """Two-way EME path loss between isotropic antennas (dB). The R^4 is the reflector round trip."""
    lam = wavelength(f_hz)
    r = range_km * 1000.0
    sigma = moon_rcs_m2(albedo, r_moon_km)
    loss = ((4 * math.pi) ** 3) * (r ** 4) / (lam * lam * sigma)
    return 10.0 * math.log10(loss)


def dish_gain_dbi(diameter_m, f_hz, efficiency=0.55):
    """Gain of a parabolic dish (dBi): G = eta (pi D / lambda)^2. Scales as f^2 for fixed D."""
    lam = wavelength(f_hz)
    g = efficiency * (math.pi * diameter_m / lam) ** 2
    return 10.0 * math.log10(g)


# ---------------------------------------------------------------- antennas ----
# Typical values, not measurements. Each can be overridden at the [E] prompts or with HANNIBAL_EME_* env vars.
DISH_KINDS = {
    # kind: (aperture efficiency, ground noise picked up past the dish edge, K)
    "prime-focus": (0.55, 20.0),   # feed in front of the dish: some blockage and spillover
    "offset": (0.65, 10.0),        # feed out of the beam: less blockage, spillover mostly sees sky
    "mesh": (0.45, 25.0),          # home-built or mesh surface: rougher, some ground leaks through
}
YAGI_BANDS = ("6m", "2m", "70cm")  # where EME stations normally use Yagi arrays rather than dishes
YAGI_DEFAULT_DBI = {"6m": 12.0, "2m": 15.0, "70cm": 18.0}   # one long-boom Yagi; 20 dBi on higher bands
YAGI_HIGH_BAND_DBI = 20.0
YAGI_DEFAULT_COUNT = 4
YAGI_COMBINE_LOSS_DB = 0.5         # phasing lines and power dividers, when there is more than one Yagi
YAGI_GROUND_K = 30.0               # side and back lobes see the warm ground, worst with the Moon low


def yagi_array_gain_dbi(single_dbi, count=1, combine_loss_db=YAGI_COMBINE_LOSS_DB):
    """Gain of N identical Yagis phased together: +3 dB per doubling, minus the phasing losses."""
    n = max(1, int(count))
    return float(single_dbi) + 10.0 * math.log10(n) - (combine_loss_db if n > 1 else 0.0)


def dish_efficiency(antenna):
    """Aperture efficiency for a dish: an explicit value wins, else the typical value for its kind."""
    eff = antenna.get("efficiency")
    return float(eff) if eff else DISH_KINDS[antenna.get("kind") or "prime-focus"][0]


def antenna_gain_dbi(antenna, f_hz):
    """Gain of a dish {'type': 'dish', 'kind', 'diameter_m'} or a Yagi array {'type': 'yagi', 'gain_dbi', 'count'}."""
    if antenna["type"] == "yagi":
        return yagi_array_gain_dbi(antenna["gain_dbi"], antenna.get("count", 1))
    return dish_gain_dbi(antenna["diameter_m"], f_hz, dish_efficiency(antenna))


def describe_antenna(antenna):
    if antenna["type"] == "yagi":
        n = max(1, int(antenna.get("count", 1)))
        return f"{n} x {antenna['gain_dbi']:.1f} dBi Yagi" + ("s" if n > 1 else "")
    return f"{antenna['diameter_m']:.1f} m {antenna.get('kind') or 'prime-focus'} dish @ {dish_efficiency(antenna):.0%}"


def parse_antenna_answer(text, default_type):
    """'d'/'dish' -> ('dish', None); 'y'/'yagi' -> ('yagi', None); a bare number -> ('dish', diameter).

    The bare number keeps older scripts working: RUN_EME.bat answers the old dish-diameter prompt with '3'.
    Raises ValueError for anything else.
    """
    t = str(text or "").strip().lower()
    if not t:
        return default_type, None
    if t in ("d", "dish"):
        return "dish", None
    if t in ("y", "yagi", "yagis"):
        return "yagi", None
    diameter = float(t)                  # ValueError for nonsense, which the screen reports
    if diameter <= 0:
        raise ValueError("dish diameter must be positive")
    return "dish", diameter


# ------------------------------------------------------------------- noise ----
T_CMB_K = 2.7                      # cosmic microwave background
COLD_SKY_144_K = 200.0             # galactic background at 144 MHz, away from the Milky Way's plane
GALACTIC_SPECTRAL_INDEX = 2.55     # galactic noise falls as f^-2.55
T_MOON_K = 210.0                   # the Moon's own thermal glow at centimetre waves
MOON_DIAMETER_DEG = 0.52
T_RX_K = 40.0                      # a good low-noise preamp (noise figure about 0.55 dB)


def sky_temp_k(f_hz, cold_sky_144_k=COLD_SKY_144_K):
    """Sky noise behind the Moon: CMB plus galactic background, which dominates below ~300 MHz.

    The galactic part can be three times higher or more when the Moon is near the Milky Way's plane.
    """
    return T_CMB_K + float(cold_sky_144_k) * (float(f_hz) / 144e6) ** (-GALACTIC_SPECTRAL_INDEX)


def beamwidth_deg(gain_dbi):
    """Approximate half-power beamwidth of a pencil beam from its gain (G ~ 41253 / theta^2)."""
    return math.sqrt(41253.0 / 10.0 ** (float(gain_dbi) / 10.0))


def moon_noise_k(gain_dbi, t_moon_k=T_MOON_K):
    """The Moon's thermal noise in the beam: its temperature times the share of the beam it fills."""
    fill = min(1.0, (MOON_DIAMETER_DEG / beamwidth_deg(gain_dbi)) ** 2)
    return float(t_moon_k) * fill


def system_temp_k(f_hz, antenna, gain_dbi, t_rx_k=T_RX_K, t_ground_k=None, cold_sky_144_k=COLD_SKY_144_K):
    """Total system noise temperature and its parts: receiver + sky + Moon + ground. Returns (total, parts)."""
    if t_ground_k is None:
        t_ground_k = (YAGI_GROUND_K if antenna["type"] == "yagi"
                      else DISH_KINDS[antenna.get("kind") or "prime-focus"][1])
    parts = {"receiver": float(t_rx_k), "sky": sky_temp_k(f_hz, cold_sky_144_k),
             "moon": moon_noise_k(gain_dbi), "ground": float(t_ground_k)}
    return sum(parts.values()), parts


def two_way_doppler_hz(f_hz, range_rate_kms):
    """Doppler on your own echo. range_rate>0 = receding -> echo comes back LOWER (negative)."""
    v = range_rate_kms * 1000.0
    return -2.0 * float(f_hz) * v / C


def round_trip_s(range_km):
    return 2.0 * range_km * 1000.0 / C


def echo_depth_ms(r_moon_km=R_MOON_KM):
    """Near-limb vs far-limb delay spread of the echo: ~2 r_moon / c. Caps the coherent bandwidth."""
    return 2.0 * r_moon_km * 1000.0 / C * 1000.0


def watts_to_dbm(watts):
    return 10.0 * math.log10(float(watts) * 1000.0)


def noise_density_dbm_hz(t_sys_k):
    """Thermal noise power spectral density k*T_sys, in dBm/Hz."""
    return 10.0 * math.log10(K_B * float(t_sys_k)) + 30.0


def noise_power_dbm(t_sys_k, bandwidth_hz):
    """N = k*T_sys*B, in dBm."""
    return noise_density_dbm_hz(t_sys_k) + 10.0 * math.log10(float(bandwidth_hz))


def processing_gain_db(bandwidth_hz, integ_s):
    """Coherent time-bandwidth product 10*log10(B*tau). The theoretical DSP gain."""
    return 10.0 * math.log10(float(bandwidth_hz) * float(integ_s))


def link_budget(f_hz, range_km, range_rate_kms, pt_w, dish_m, efficiency=0.55,
                t_sys_k=100.0, bw_hz=WSJT_REF_BW, integ_s=60.0, l_misc_db=4.0,
                g_tx_dbi=None, g_rx_dbi=None, albedo=MOON_ALBEDO):
    """Full EME budget for one band and station. Returns a dict of every term plus a verdict.

    g_tx_dbi / g_rx_dbi override the dish gain (e.g. an array, or different Tx/Rx antennas).
    SNR is reported in a 2500 Hz reference bandwidth so it can be read against MODE_THRESHOLDS.
    """
    pt_dbm = watts_to_dbm(pt_w)
    g = dish_gain_dbi(dish_m, f_hz, efficiency)
    g_tx = g if g_tx_dbi is None else g_tx_dbi
    g_rx = g if g_rx_dbi is None else g_rx_dbi
    l_path = path_loss_db(f_hz, range_km, albedo)
    pr_dbm = pt_dbm + g_tx + g_rx - l_path - l_misc_db
    n0 = noise_density_dbm_hz(t_sys_k)                 # dBm/Hz
    n_bw = n0 + 10.0 * math.log10(bw_hz)               # noise in the receiver bandwidth
    snr_bw = pr_dbm - n_bw                             # SNR in the receiver passband
    snr_ref = pr_dbm - (n0 + 10.0 * math.log10(WSJT_REF_BW))   # SNR in the 2500 Hz reference
    best = None
    for name, thr in MODE_THRESHOLDS:
        if snr_ref >= thr:
            best = (name, thr)
            break
    return {
        "f_hz": f_hz, "range_km": range_km, "range_rate_kms": range_rate_kms,
        "pt_dbm": pt_dbm, "g_tx_dbi": g_tx, "g_rx_dbi": g_rx, "l_path_db": l_path,
        "l_misc_db": l_misc_db, "pr_dbm": pr_dbm, "t_sys_k": t_sys_k, "bw_hz": bw_hz,
        "n0_dbm_hz": n0, "n_bw_dbm": n_bw, "snr_bw_db": snr_bw, "snr_ref_db": snr_ref,
        "integ_s": integ_s, "proc_gain_db": processing_gain_db(bw_hz, integ_s),
        "doppler_hz": two_way_doppler_hz(f_hz, range_rate_kms), "round_trip_s": round_trip_s(range_km),
        "echo_depth_ms": echo_depth_ms(), "best_mode": best[0] if best else None,
        "best_threshold_db": best[1] if best else None,
        "verdict": "echo detectable" if best else "echo below every mode threshold",
    }


# ---------------------------------------------------------------- live Moon ----
def current_moon(lat=None, lon=None, alt_km=None):
    """Moon az/el, range (km) and range-rate (km/s) over home, from JPL Horizons.

    Returns a dict (or {"error": ...}). Uses hannibal_nasa so the call is masked, cached and
    rate-limited like the sky page; needs no key.
    """
    try:
        from hannibal_nasa import Horizons, _pick, num, AU_KM
        from hannibal_net import home_location
    except ImportError as exc:  # pragma: no cover
        return {"error": f"EME needs the orbital modules: {exc}"}
    h = home_location()
    lat = h["lat"] if lat is None else lat
    lon = h["lon"] if lon is None else lon
    alt_km = h["alt_km"] if alt_km is None else alt_km
    res = Horizons().observer("moon", lat, lon, alt_km, quantities="4,20")
    if not res.ok:
        return {"error": res.error, "home": h}
    row = res.data[0]
    delta = num(_pick(row, "delta"))
    return {
        "az": num(_pick(row, "azi")), "el": num(_pick(row, "elev")),
        "range_km": delta * AU_KM if delta is not None else None,
        "range_rate_kms": num(_pick(row, "deldot")),
        "as_of": _pick(row, "date") or "", "stale": res.stale, "home": h,
    }


# ---------------------------------------------------------------- defaults ----
def _envf(name, default):
    try:
        return float(os.getenv(name, "").strip())
    except ValueError:
        return default


def station_defaults():
    """A reasonable serious-amateur 23 cm station; override with HANNIBAL_EME_* env vars.

    t_sys_k is None unless HANNIBAL_EME_TSYS_K is set: then the system noise is worked out for the
    band and antenna (system_temp_k) instead of one fixed figure for every band.
    """
    band = os.getenv("HANNIBAL_EME_BAND", "23cm").strip().lower()
    f_hz = BANDS.get(band, BANDS["23cm"])
    return {
        "band": band if band in BANDS else "23cm", "f_hz": _envf("HANNIBAL_EME_FREQ_HZ", f_hz),
        "pt_w": _envf("HANNIBAL_EME_PT_W", 300.0), "dish_m": _envf("HANNIBAL_EME_DISH_M", 3.0),
        "efficiency": _envf("HANNIBAL_EME_EFF", None), "t_sys_k": _envf("HANNIBAL_EME_TSYS_K", None),
        "t_rx_k": _envf("HANNIBAL_EME_TRX_K", T_RX_K), "t_ground_k": _envf("HANNIBAL_EME_TGROUND_K", None),
        "sky_144_k": _envf("HANNIBAL_EME_SKY144_K", COLD_SKY_144_K),
        "bw_hz": _envf("HANNIBAL_EME_BW_HZ", WSJT_REF_BW), "integ_s": _envf("HANNIBAL_EME_INTEG_S", 60.0),
        "l_misc_db": _envf("HANNIBAL_EME_LMISC_DB", 4.0),
    }


def antenna_defaults(band):
    """What the [E] prompts offer for a band: Yagi arrays on 6 m / 2 m / 70 cm, a dish from 23 cm up.

    HANNIBAL_EME_ANTENNA (dish/yagi), _DISH_KIND, _DISH_M, _EFF, _YAGI_DBI and _YAGI_N override.
    """
    typ = os.getenv("HANNIBAL_EME_ANTENNA", "").strip().lower()
    if typ not in ("dish", "yagi"):
        typ = "yagi" if band in YAGI_BANDS else "dish"
    kind = os.getenv("HANNIBAL_EME_DISH_KIND", "").strip().lower()
    return {
        "type": typ, "dish_kind": kind if kind in DISH_KINDS else "prime-focus",
        "dish_m": _envf("HANNIBAL_EME_DISH_M", 3.0), "efficiency": _envf("HANNIBAL_EME_EFF", None),
        "yagi_dbi": _envf("HANNIBAL_EME_YAGI_DBI", YAGI_DEFAULT_DBI.get(band, YAGI_HIGH_BAND_DBI)),
        "yagi_n": int(_envf("HANNIBAL_EME_YAGI_N", YAGI_DEFAULT_COUNT)),
    }


def default_antenna(band):
    """The antenna dict antenna_defaults(band) describes, ready for antenna_gain_dbi()."""
    a = antenna_defaults(band)
    if a["type"] == "yagi":
        return {"type": "yagi", "gain_dbi": a["yagi_dbi"], "count": a["yagi_n"]}
    return {"type": "dish", "kind": a["dish_kind"], "diameter_m": a["dish_m"], "efficiency": a["efficiency"]}
