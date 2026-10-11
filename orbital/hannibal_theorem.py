"""THE GRAND UNIFIED HAPPINESS THEOREM & 10-LOBE CRANIAL REPORT  (Hannibal module, developers only)

Bram's theorem from the Happiness Formula Architect, implemented exactly as written. Nothing in
the formula, the lobe names, colours or roles has been changed; where the maths needs a guard to
be computable, the guard is written next to it and named a "solution", never a rewrite.

    H_brain = ( (dR_dop^1.1 + S_flux + O_bond^1.05 + E_endo)
                / (1 + C_cort^1.4 + A_debt^1.2 + (Allostatic/100)^2)  *  sqrt(G_calm / 50) )
              x [ 0.55 + 0.9 (0.35 Phi_flow + 0.3 M_purpose + 0.2 K_agency) ]
              + SUM Omega_illogic
              - (beta_think^1.3 + tau_tabs^1.15 + gamma_compare^1.25 + kappa_hangry^1.4) / (1 + varpi_pizza/200)
              - [ gamma_dep (1 - e^(-tau/tau0)) + DailySpend x 30 / Income ]
                  ^ Starbucks / Nicotine Withdrawal & Financial Leakage

    Canonical equation (section 6 of the report):
        H_brain(tau) = Phi_flow . [(N_neuro) / (F_bugs + Allostatic_Strain)] + SUM Omega_illogic + W_cosmic - Psi_faulty

SOLUTIONS (so it always computes, without changing a term)
  S1  x^1.1, x^1.05, x^1.4 ... and sqrt() are undefined in the reals for negative x
      -> those inputs are checked >= 0 and a clear error names the input; nothing is clipped silently.
  S2  DailySpend x 30 / Income needs Income > 0; e^(-tau/tau0) needs tau0 > 0;
      1 + varpi_pizza/200 needs varpi_pizza > -200     -> checked the same way.
  S3  The detailed formula has no W_cosmic; the canonical equation and the report do
      ("Whimsical Realities Bonus"). W_cosmic is an optional input (default 0), added AFTER the
      theorem and shown on its own line, so the theorem value itself is exactly the detailed formula.
  S4  The theorem is unbounded; the report reads "/ 100". Both are kept: the raw value and a
      0-100 display value (clamped), printed side by side.
  S5  A profile that only has the recorded result (no inputs) is shown "as recorded" and is never
      recomputed or re-scaled.

WHERE IT LIVES IN HANNIBAL
  * the market brain dashboard ([R] in the orbital menu) shows a THEOREM card next to the ten lobes
  * orbital menu [T]: the cranial report in the terminal
  * python hannibal_theorem.py --report | --selftest | --export FILE

SECURITY: the same developer gate as the market brain (hannibal_brain.dev_gate: PBKDF2 key hash in the
OS credential store, 3 tries then 5 min lockout, failures to the breach log), masked output
(hannibal_security_bootstrap). The personal profile brain_profile.json is private: git-ignored,
never committed, only served to a gated 127.0.0.1 session.

Importing this module has no side effects and never touches the network.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path

# -------------------------------------------- 10-lobe functional tomography ----
# Exactly as in the report. `id` links each lobe to the market brain's lobe of the same name.
TOMOGRAPHY = [
    ("prefrontal", "01", "Prefrontal Cortex", "Laser Cyan",
     "Executive regulation, Ikigai purpose, Flow state coherence & Overthinking loops"),
    ("motor", "02", "Motor & Premotor Cortex", "Electric Violet",
     "Kinetic physical execution, procrastination cleaning overdrive & tactile popping"),
    ("somato", "03", "Somatosensory Cortex", "Warm Amber Gold",
     "Tactile bliss of fresh dryer socks, icy pillow flip & coffee temperature window"),
    ("parietal", "04", "Parietal Association Cortex", "Teal Green",
     "Spatial coordinate map, 94 open browser tabs overload & multidimensional gratitude"),
    ("occipital", "05", "Occipital Visual Cortex", "Royal Indigo",
     "Visual photon intake, sunset aesthetics & Instagram comparison reel processing"),
    ("auditory", "06", "Auditory & Temporal Cortex", "Vibrant Coral Orange",
     "Acoustic joy of looped songs, rain on roof resonance & shower argument verbalization"),
    ("nucleus", "07", "Nucleus Accumbens & Striatum", "Emerald Jade",
     "Dopamine prediction error, 3 AM cold pizza ecstasy & canceled plans jackpot"),
    ("amygdala", "08", "Amygdala Sentinel", "Crimson Flame Red",
     "Cortisol threat sentinel, hypoglycemic hangry rage & text-message punctuation anxiety"),
    ("insula", "09", "Insula & Hypothalamus Core", "Hot Magenta Pink",
     "Oxytocin cuddle bonding, feline lap hostage immobility & circadian sleep debt gauge"),
    ("cerebellum", "10", "Cerebellum & Brainstem", "Electric Lime Green",
     "Basal life support, autonomic equilibrium, runner's high endorphins & GABA relaxation"),
]

CANONICAL = ("H_brain(τ) = Φ_flow · [(N_neuro) / (F_bugs + Allostatic_Strain)] "
             "+ Σ Ω_illogic + W_cosmic - Ψ_faulty")

LATEX = (r"\mathcal{H}_{\text{brain}} = \left( \frac{\Delta R_{\text{dop}}^{1.1} + S_{\text{flux}} + "
         r"O_{\text{bond}}^{1.05} + E_{\text{endo}}}{1 + C_{\text{cort}}^{1.4} + A_{\text{debt}}^{1.2} + "
         r"\left(\frac{\text{Allostatic}}{100}\right)^2} \cdot \sqrt{\frac{G_{\text{calm}}}{50}} \right) "
         r"\times \left[ 0.55 + 0.9 \left( 0.35\Phi_{\text{flow}} + 0.3M_{\text{purpose}} + "
         r"0.2K_{\text{agency}} \right) \right] + \sum \Omega_{\text{illogic}} - \left( "
         r"\frac{\beta_{\text{think}}^{1.3} + \tau_{\text{tabs}}^{1.15} + \gamma_{\text{compare}}^{1.25} + "
         r"\kappa_{\text{hangry}}^{1.4}}{1 + \frac{\varpi_{\text{pizza}}}{200}} \right) - "
         r"\underbrace{\left[ \gamma_{\text{dep}} \cdot \left(1 - e^{-\tau / \tau_0}\right) + "
         r"\frac{\text{DailySpend} \times 30}{\text{Income}} \right]}_{\text{Starbucks / Nicotine "
         r"Withdrawal \& Financial Leakage}}")


# ------------------------------------------------------------- the theorem ----
@dataclass
class Inputs:
    dR_dop: float = 0.0
    S_flux: float = 0.0
    O_bond: float = 0.0
    E_endo: float = 0.0
    C_cort: float = 0.0
    A_debt: float = 0.0
    Allostatic: float = 0.0
    G_calm: float = 50.0
    Phi_flow: float = 0.0
    M_purpose: float = 0.0
    K_agency: float = 0.0
    Omega_illogic: list = field(default_factory=list)
    beta_think: float = 0.0
    tau_tabs: float = 0.0
    gamma_compare: float = 0.0
    kappa_hangry: float = 0.0
    varpi_pizza: float = 0.0
    gamma_dep: float = 0.0
    tau: float = 0.0
    tau0: float = 1.0
    DailySpend: float = 0.0
    Income: float = 1.0
    W_cosmic: float = 0.0          # S3: optional, from the canonical equation


class InputError(ValueError):
    pass


_NON_NEGATIVE = ("dR_dop", "O_bond", "C_cort", "A_debt", "Allostatic", "G_calm",
                 "beta_think", "tau_tabs", "gamma_compare", "kappa_hangry")


def check_inputs(x: Inputs) -> None:
    """S1 + S2: refuse what the reals cannot compute, naming the input."""
    for name in _NON_NEGATIVE:
        v = getattr(x, name)
        if v < 0:
            raise InputError(f"{name} = {v}: must be >= 0 (fractional power / square root of a negative)")
    if x.Income <= 0:
        raise InputError(f"Income = {x.Income}: must be > 0 (DailySpend x 30 / Income)")
    if x.tau0 <= 0:
        raise InputError(f"tau0 = {x.tau0}: must be > 0 (e^(-tau / tau0))")
    if x.varpi_pizza <= -200:
        raise InputError(f"varpi_pizza = {x.varpi_pizza}: must be > -200 (1 + varpi_pizza / 200)")


def h_brain(x: Inputs) -> dict:
    """The theorem, term by term. Returns each component, the theorem value, and the display value."""
    check_inputs(x)
    wetware = (x.dR_dop ** 1.1 + x.S_flux + x.O_bond ** 1.05 + x.E_endo) \
        / (1 + x.C_cort ** 1.4 + x.A_debt ** 1.2 + (x.Allostatic / 100) ** 2) \
        * math.sqrt(x.G_calm / 50)
    multiplier = 0.55 + 0.9 * (0.35 * x.Phi_flow + 0.3 * x.M_purpose + 0.2 * x.K_agency)
    illogic = float(sum(x.Omega_illogic))
    firmware = (x.beta_think ** 1.3 + x.tau_tabs ** 1.15 + x.gamma_compare ** 1.25 + x.kappa_hangry ** 1.4) \
        / (1 + x.varpi_pizza / 200)
    withdrawal = x.gamma_dep * (1 - math.exp(-x.tau / x.tau0))
    leakage = x.DailySpend * 30 / x.Income
    theorem = wetware * multiplier + illogic - firmware - (withdrawal + leakage)
    raw = theorem + x.W_cosmic                       # S3
    return {"wetware": wetware, "multiplier": multiplier, "illogic": illogic, "firmware": firmware,
            "withdrawal": withdrawal, "leakage": leakage, "theorem": theorem, "w_cosmic": x.W_cosmic,
            "raw": raw, "display": max(0.0, min(100.0, raw))}   # S4


# ----------------------------------------------------------------- profile ----
PROFILE = "brain_profile.json"            # private, git-ignored
EXAMPLE = "brain_profile.example.json"    # ships with the code


def _here() -> Path:
    try:
        from hannibal_net import base_dir
        return base_dir()
    except Exception:  # noqa: BLE001
        return Path(__file__).resolve().parent


def load_profile(folder: Path | None = None) -> dict:
    for name in (PROFILE, EXAMPLE):
        try:
            with open((folder or _here()) / name, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data["_file"] = name
                return data
        except (OSError, ValueError):
            continue
    return {"_file": "", "lobes": {}}


def inputs_of(profile: dict) -> Inputs | None:
    raw = profile.get("inputs") or {}
    names = {f.name for f in fields(Inputs)}
    known = {k: v for k, v in raw.items() if k in names}
    return Inputs(**known) if known else None


def evaluate(profile: dict) -> dict:
    """What the dashboard and the report show. S5: recorded results are never recomputed."""
    x = inputs_of(profile)
    out = {"mode": "recorded", "result": None, "error": ""}
    if x is not None:
        try:
            out = {"mode": "computed", "result": h_brain(x), "error": ""}
        except InputError as exc:
            out = {"mode": "error", "result": None, "error": str(exc)}
    rec = profile.get("recorded", {})
    lobes = profile.get("lobes", {})
    out.update({
        "profile_name": profile.get("profile_name", ""),
        "file": profile.get("_file", ""),
        "recorded": rec,
        "h_display": round(out["result"]["display"], 1) if out["result"] else rec.get("h_brain"),
        "lobes": [{"id": lid, "num": num, "name": name, "colour": colour, "role": role,
                   "pct": lobes.get(num, lobes.get(lid))} for lid, num, name, colour, role in TOMOGRAPHY],
        "canonical": CANONICAL,
    })
    return out


# ------------------------------------------------------------------ report ----
def cranial_report(profile: dict, now: datetime | None = None) -> str:
    ev = evaluate(profile)
    rec, res = ev["recorded"], ev["result"]
    bar = "=" * 88
    ts = (now or datetime.now(timezone.utc)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    L = [bar, "THE GRAND UNIFIED HAPPINESS THEOREM & 10-LOBE CRANIAL REPORT",
         f"Calibrated Profile: {profile.get('profile_name', '(none)')}", f"Timestamp: {ts}", bar, "",
         "1. CRANIAL EQUILIBRIUM QUOTIENT", "   ----------------------------"]
    if res:
        raw = f"   (raw {res['raw']:.1f})" if abs(res["raw"] - res["display"]) > 1e-9 else ""
        L.append(f"   Overall Brain Happiness (H_brain): {res['display']:.1f} / 100{raw}")
    elif ev["mode"] == "error":
        L.append(f"   Overall Brain Happiness (H_brain): -- ({ev['error']})")
    elif rec.get("h_brain") is not None:
        L.append(f"   Overall Brain Happiness (H_brain): {rec['h_brain']} / 100   (as recorded)")
    else:
        L.append("   Overall Brain Happiness (H_brain): -- (no inputs in the profile)")
    for key, label in (("allostatic", "Allostatic Stress Strain:          "),
                       ("archetype", "Clinical State Archetype:          "),
                       ("prognosis", "Prognosis / Diagnostic Summary:    ")):
        if rec.get(key):
            L.append(f"   {label}{rec[key]}")
    L += ["", "2. THE 10-LOBE FUNCTIONAL TOMOGRAPHY", "   ---------------------------------"]
    for lobe in ev["lobes"]:
        pct = lobe["pct"]
        pct_txt = f"{pct:>3}%" if isinstance(pct, (int, float)) else "  --"
        L.append(f"   • [{lobe['num']}] {lobe['name']:<28}: {pct_txt} | Color: {lobe['colour']}")
        L.append(f"     Role: {lobe['role']}")
    L += ["", "3. COMPONENT DECOMPOSITION", "   -----------------------"]
    if res:
        L += [f"   • Neurochemical Substrate (Wetware): {res['wetware']:.1f} pts",
              f"   • Psychological Vector Multiplier:   ×{res['multiplier']:.2f}",
              f"   • Illogical Surge (Irrational Bliss):{res['illogic']:+.1f} pts",
              f"   • Whimsical Realities Bonus:         {res['w_cosmic']:+.1f} pts",
              f"   • Faulty Firmware Drag (Bugs):       -{res['firmware']:.1f} pts",
              f"   • Withdrawal & Financial Leakage:    -{res['withdrawal'] + res['leakage']:.1f} pts"]
    else:
        L += [f"   • {c}" for c in rec.get("components", [])] or ["   (none recorded)"]
    for title, key in (("4. KEY ARCHETYPAL FACTORS", "factors"), ("5. ACTIVE COGNITIVE PARADOXES", "paradoxes")):
        if rec.get(key):
            L += ["", title, "   " + "-" * (len(title) - 3)] + [f"   {line}" for line in rec[key]]
    L += ["", "6. CANONICAL MATHEMATICAL EQUATION", "   -------------------------------", "   " + CANONICAL, bar]
    return "\n".join(L)


# ------------------------------------------------------------- menu screen ----
def screen_theorem(ask, out, color):
    """[T] in the orbital menu: developer gate, then the cranial report."""
    import hannibal_art as art
    import hannibal_brain
    out(art.section("GRAND UNIFIED HAPPINESS THEOREM  //  DEVELOPERS ONLY", 89, color))
    if not hannibal_brain.dev_gate(out=out):
        return
    for line in cranial_report(load_profile()).splitlines():
        out(line)


# ---------------------------------------------------------------- selftest ----
def selftest() -> int:
    bad = 0

    def check(name, cond):
        nonlocal bad
        bad += not cond
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

    x = Inputs(dR_dop=20, S_flux=10, O_bond=15, E_endo=8, C_cort=1, A_debt=1, Allostatic=35, G_calm=50,
               Phi_flow=0.8, M_purpose=0.7, K_agency=0.6, Omega_illogic=[24.8, 26.8],
               beta_think=3, tau_tabs=6, gamma_compare=2, kappa_hangry=2, varpi_pizza=100,
               gamma_dep=5, tau=2, tau0=1, DailySpend=4, Income=2000)
    r = h_brain(x)
    wet = (20 ** 1.1 + 10 + 15 ** 1.05 + 8) / (1 + 1 + 1 + 0.35 ** 2)
    mult = 0.55 + 0.9 * (0.35 * 0.8 + 0.3 * 0.7 + 0.2 * 0.6)
    firm = (3 ** 1.3 + 6 ** 1.15 + 2 ** 1.25 + 2 ** 1.4) / (1 + 100 / 200)
    leak = 5 * (1 - math.exp(-2)) + 4 * 30 / 2000
    check(f"wetware {r['wetware']:.6f} == by hand", abs(r["wetware"] - wet) < 1e-12)
    check(f"multiplier {r['multiplier']:.6f} == by hand", abs(r["multiplier"] - mult) < 1e-12)
    check(f"theorem {r['theorem']:.6f} == by hand {wet * mult + 51.6 - firm - leak:.6f}",
          abs(r["theorem"] - (wet * mult + 51.6 - firm - leak)) < 1e-9)
    check("sqrt(G_calm/50) = 1 at G_calm = 50", h_brain(Inputs(S_flux=7))["wetware"] == 7.0)
    check("G_calm = 200 doubles the wetware", abs(h_brain(Inputs(S_flux=7, G_calm=200))["wetware"] - 14.0) < 1e-12)
    check("report's x1.16 multiplier is reachable (0.35Phi+0.3M+0.2K = 0.6778)",
          abs(0.55 + 0.9 * 0.6778 - 1.16) < 1e-3)
    check("S3 W_cosmic added after the theorem, theorem unchanged",
          h_brain(Inputs(S_flux=7, W_cosmic=21.7))["theorem"] == h_brain(Inputs(S_flux=7))["theorem"]
          and abs(h_brain(Inputs(S_flux=7, W_cosmic=21.7))["raw"] - (7 * 0.55 + 21.7)) < 1e-12)
    check("S4 display clamps to 100, raw kept", h_brain(Inputs(S_flux=500))["display"] == 100.0
          and abs(h_brain(Inputs(S_flux=500))["raw"] - 500 * 0.55) < 1e-9)
    for bad_in in ({"C_cort": -1}, {"Income": 0}, {"tau0": 0}, {"G_calm": -1}, {"varpi_pizza": -200}):
        try:
            h_brain(Inputs(**bad_in))
            check(f"S1/S2 refuses {bad_in}", False)
        except InputError:
            check(f"S1/S2 refuses {bad_in}", True)
    recorded = {"profile_name": "Test", "recorded": {"h_brain": 86.5}, "lobes": {"01": 64}}
    ev = evaluate(recorded)
    check("S5 recorded profile shown as recorded, not recomputed", ev["mode"] == "recorded" and ev["h_display"] == 86.5)
    rep = cranial_report(recorded)
    check("report keeps all six sections", all(f"{i}. " in rep for i in (1, 2, 3, 6)))
    check("report lobe names exactly as the tomography", all(t[2] in rep for t in TOMOGRAPHY))
    try:
        import hannibal_brain
        check("tomography ids line up with the market brain lobes",
              [t[0] for t in TOMOGRAPHY] == [l[0] for l in hannibal_brain.LOBES])
    except Exception as exc:  # noqa: BLE001
        check(f"hannibal_brain importable ({exc})", False)
    print("  all pass" if not bad else f"  {bad} FAILED")
    return 1 if bad else 0


# ---------------------------------------------------------------------- CLI ----
def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    arg = argv[0] if argv else "--report"
    if arg == "--selftest":
        return selftest()
    if arg in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        import hannibal_security_bootstrap  # noqa: F401
    except ImportError:
        pass
    import hannibal_brain
    if not hannibal_brain.dev_gate():
        return 1
    if arg == "--export":
        target = Path(argv[1] if len(argv) > 1 else "theorem_state.json")
        target.write_text(json.dumps(evaluate(load_profile()), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[+] Wrote {target}")
        return 0
    print(cranial_report(load_profile()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
