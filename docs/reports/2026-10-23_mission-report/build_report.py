"""Project Hannibal - mission report and debrief, 22-23 October 2026. Builds one A4 PDF."""
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

HERE = Path(__file__).resolve().parent
OUT = HERE / "Project_Hannibal_Mission_Report_2026-10-23.pdf"

DJ = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", DJ + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Bold", DJ + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Sans-Oblique", DJ + "DejaVuSans-Oblique.ttf"))
pdfmetrics.registerFont(TTFont("Mono", DJ + "DejaVuSansMono.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans-Oblique", boldItalic="Sans-Bold")

INK = colors.HexColor("#0b0b0b")
INK2 = colors.HexColor("#52514e")
MUTED = colors.HexColor("#8a8984")
RULE = colors.HexColor("#e4e3df")
TINT = colors.HexColor("#f5f4f1")
ACCENT = colors.HexColor("#b3261e")     # one restrained accent: section numbers and the title rule
BLUE = colors.HexColor("#2a78d6")

C = json.load(open(HERE / "calcs.json"))
Z = json.load(open(HERE / "zombie_23oct.json"))
A = C["apophis"]
V = C["voyager"]

# ------------------------------------------------------------------ styles ----
base = dict(fontName="Sans", textColor=INK, leading=13.2, fontSize=9.4, alignment=TA_LEFT)
S = {
    "body": ParagraphStyle("body", spaceAfter=6, **base),
    "small": ParagraphStyle("small", **{**base, "fontSize": 8, "leading": 10.6, "textColor": INK2}),
    "cell": ParagraphStyle("cell", **{**base, "fontSize": 8.2, "leading": 10.4}),
    "cellb": ParagraphStyle("cellb", **{**base, "fontSize": 8.2, "leading": 10.4, "fontName": "Sans-Bold"}),
    "h1": ParagraphStyle("h1", **{**base, "fontName": "Sans-Bold", "fontSize": 15, "leading": 19, "spaceBefore": 4,
                                  "spaceAfter": 8}),
    "h2": ParagraphStyle("h2", **{**base, "fontName": "Sans-Bold", "fontSize": 10.6, "leading": 14, "spaceBefore": 8,
                                  "spaceAfter": 4}),
    "bullet": ParagraphStyle("bullet", leftIndent=11, bulletIndent=1, spaceAfter=3.5, **base),
    "srcbullet": ParagraphStyle("srcbullet", leftIndent=10, bulletIndent=1, spaceAfter=0.8, **{**base, "fontSize": 7.8, "leading": 9.8, "textColor": INK2}),
    "mono": ParagraphStyle("mono", **{**base, "fontName": "Mono", "fontSize": 7.8, "leading": 10.2, "textColor": INK2}),
    "caption": ParagraphStyle("caption", **{**base, "fontSize": 7.8, "leading": 10.2, "textColor": INK2,
                                            "spaceBefore": 2, "spaceAfter": 8}),
}


def P(text, style="body"):
    return Paragraph(text, style if isinstance(style, ParagraphStyle) else S[style])


def B(items, style="bullet"):
    return [Paragraph(t, S[style], bulletText="•") for t in items]


def H1(num, text):
    return Paragraph(f'<font color="#b3261e">{num}</font>&nbsp;&nbsp;{text}', S["h1"])


def H2(text):
    return P(text, "h2")


def table(rows, widths, header=True, numeric_cols=(), zebra=False, bold_first_col=False):
    data = []
    for r_i, row in enumerate(rows):
        cells = []
        for c_i, v in enumerate(row):
            st = "cellb" if (header and r_i == 0) or (bold_first_col and c_i == 0 and r_i > 0) else "cell"
            style = S[st]
            if c_i in numeric_cols and not (header and r_i == 0):
                style = ParagraphStyle(st + "r", parent=style, alignment=2)
            cells.append(Paragraph(str(v), style))
        data.append(cells)
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    cmds = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2), ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE)]
    if header:
        cmds += [("LINEBELOW", (0, 0), (-1, 0), 0.9, INK2), ("BACKGROUND", (0, 0), (-1, 0), TINT)]
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fafaf8")))
    t.setStyle(TableStyle(cmds))
    return t


def img(name, width_mm):
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(str(HERE / name))
    w, h = ir.getSize()
    width = width_mm * mm
    return Image(str(HERE / name), width=width, height=width * h / w)


def note_box(paragraphs, width=170 * mm):
    t = Table([[p] for p in paragraphs], colWidths=[width], hAlign="LEFT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT)]))
    return t


def m(x, nd=1, sign=False):
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace("-", "−")


def pct(d):
    return f"{d['p']*100:.1f}% <font color='#52514e'>(95% range {d['lo']*100:.1f}–{d['hi']*100:.1f}%)</font>"


# ------------------------------------------------------------- page chrome ----
W, Hh = A4
LM = RM = 20 * mm
TM, BM = 20 * mm, 18 * mm


def chrome(canvas, doc):
    canvas.saveState()
    canvas.setFont("Sans", 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(LM, Hh - 12 * mm, "PROJECT HANNIBAL  ·  ORBITAL DIRECTORATE  ·  Mission report and debrief, 22–23 October 2026")
    canvas.drawRightString(W - RM, 10 * mm, f"{doc.page}")
    canvas.drawString(LM, 10 * mm, "Bram Noffels, Antwerp")
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(LM, Hh - 13.8 * mm, W - RM, Hh - 13.8 * mm)
    canvas.restoreState()


def cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(ACCENT)
    canvas.rect(LM, Hh - 33 * mm, 34 * mm, 1.6 * mm, stroke=0, fill=1)
    canvas.setFont("Sans", 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(LM, 10 * mm, "Receive-only. Every figure in this report can be re-run from the public sources and commands in section 12.")
    canvas.restoreState()


doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM,
                      title="Project Hannibal - Mission report and debrief, 22-23 October 2026",
                      author="Bram Noffels", subject="Zombie-satellite check, Apophis exclusion, moonbounce and Voyager 1 link budgets",
                      creator="Project Hannibal (Orbital Directorate)")
frame = Frame(LM, BM, W - LM - RM, Hh - TM - BM, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate("cover", [frame], onPage=cover), PageTemplate("body", [frame], onPage=chrome)])

story = []
FULL = W - LM - RM

# ------------------------------------------------------------------- cover ----
heard = C["heard_of_148"]
story += [Spacer(1, 18 * mm),
          P("PROJECT HANNIBAL  ·  ORBITAL DIRECTORATE", ParagraphStyle("k", **{**base, "fontSize": 9, "textColor": INK2})),
          Spacer(1, 4 * mm),
          P("Mission report and debrief", ParagraphStyle("t", **{**base, "fontName": "Sans-Bold", "fontSize": 25, "leading": 30})),
          P("Which satellites are still alive? A zombie-satellite check over Antwerp, with the Apophis, moonbounce and "
            "Voyager 1 calculations that came with it.",
            ParagraphStyle("st", **{**base, "fontSize": 12.5, "leading": 17, "textColor": INK2, "spaceBefore": 6})),
          Spacer(1, 13 * mm),
          P("Bram Noffels  ·  Antwerp, Belgium  ·  22–23 October 2026",
            ParagraphStyle("au", **{**base, "fontSize": 10, "textColor": INK})),
          Spacer(1, 12 * mm)]

hero = [["148", "2", "1966", "0"],
        ["military objects over Antwerp, checked", "heard by ground stations in the last 30 days",
         "launch year of ERS 15, one of the two", "with an uplink: nothing here can relay a signal"]]
ht = Table([[Paragraph(v, ParagraphStyle("hv", **{**base, "fontName": "Sans-Bold", "fontSize": 26, "leading": 30}))
             for v in hero[0]],
            [Paragraph(v, ParagraphStyle("hl", **{**base, "fontSize": 8, "leading": 10.4, "textColor": INK2})) for v in hero[1]]],
           colWidths=[FULL / 4] * 4, hAlign="LEFT")
ht.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK)]))
story += [ht, Spacer(1, 14 * mm)]

story += [H2("Abstract"),
          P("A list of 148 objects that N2YO tagged as military and placed above Antwerp on 17 October 2026 was checked against "
            "reception evidence from SatNOGS, the worldwide network of volunteer ground stations. Positions alone cannot tell a "
            "working satellite from one that died decades ago; reception can. Six of the 148 have a transmitter known to the "
            "amateur network, and two were heard in the 30 days before the check: COSMOS 2488 (2013) on UHF, and ERS 15, a "
            "4.5 kg research satellite launched on 19 August 1966 that still sends a carrier at 136.44 MHz. Neither has an "
            "uplink on record, so neither can pass a signal on. The same two days produced an Earth-impact exclusion check for "
            "asteroid 99942 Apophis (excluded, in agreement with NASA/JPL), a moonbounce link-budget planner for a home "
            "station, and a link budget for receiving Voyager 1, calibrated against JPL's own design tables. All of it is "
            "receive-only and built on public data."),
          NextPageTemplate("body"), PageBreak()]

# ----------------------------------------------------------------- 1 summary ----
story += [H1("1", "Summary of findings")]
story += B([
    f"<b>2 of 148 heard</b> in the 30 days before the check: {pct(heard)}. Re-run on 23 October: unchanged.",
    "<b>0 of the 2 have an uplink on record.</b> Hearing a satellite and sending it something are different things; a relay "
    "needs both. The idea that started this, using dormant satellites to relay toward Voyager 1, does not hold, and the "
    "reasons are in section 3.",
    "<b>ERS 15 is a genuine survivor.</b> Launched in 1966, it is still heard by volunteer stations: 632 vetted good "
    "observations since 21 October 2020 by at least 96 different stations, most recently on 26 September 2026. Over the last "
    f"365 days stations heard it on {pct(C['ers15_365d'])} of vetted passes.",
    "<b>Apophis is excluded.</b> Every Earth approach to 2200 clears the atmosphere at the near edge of JPL's 3-sigma "
    "uncertainty, and JPL's Sentry system removed Apophis from its risk list on 21 February 2021. The 13 April 2029 "
    "flyby passes 38,011 km from Earth's centre, with an uncertainty window of 6.6 km.",
    "<b>Moonbounce is within reach of a home station</b>, transmitter licence permitting: on paper, a 3 m dish on 23 cm "
    "with 300 W can just hear its own echo by ear, and four Yagis on 2 m can decode theirs digitally.",
    "<b>Voyager 1 can be heard, not contacted.</b> At 25.8 billion km its carrier was detected in 2024 with the "
    "25 m Dwingeloo telescope, run by amateurs. An ideal-case budget shows what a smaller dish would need (section 9).",
])

story += [Spacer(1, 3 * mm), H2("What this report is, and is not")]
story += [P("It is a record of what was checked, how, and with what result, with every calculation shown and every "
            "source named so the work can be repeated. It is <i>not</i> a claim that Hannibal itself received a satellite "
            "signal: the reception evidence comes from SatNOGS volunteer stations, and Hannibal's contribution is asking "
            "the question of a whole list at once and reading the answer carefully. Receiving ERS 15 with Hannibal's own "
            "radio is the first next step (section 10).")]

# --------------------------------------------------------------- 2 timeline ----
story += [H1("2", "Timeline"), P("Times are Antwerp local time (CEST, UTC+2). Times marked ~ are approximate; all others "
                                 "come from the GitHub commit log or from the tools' own timestamps.", "small"), Spacer(1, 2 * mm)]
tl = [["When", "What happened", "Evidence"],
      ["30 Sep, 08:21", "Hannibal repository created on GitHub; first files uploaded.", "commits 94568dc–31f70f6"],
      ["11 Oct, 21:10–22:19", "Evidence-gated SatNOGS link health (telemetry 1.1 and 1.2) and the Orbital Directorate merged into the main terminal.", "PRs #1–#3"],
      ["16 Oct, 01:07", "Fix: “overhead now” is no longer silently computed for 0° N 0° E when no home is set.", "eb39a4c"],
      ["16 Oct, 02:12", "<b>[E] Moonbounce</b> link budget added.", "f3427e5"],
      ["17 Oct, 19:48", "Satellite detail export over Antwerp: <b>148 objects tagged military</b> (N2YO).", "export PDF"],
      ["17 Oct, 20:03", "Altitude guard: physically impossible N2YO altitudes are rejected.", "0ca928d"],
      ["22 Oct, 19:36", "<b>[D] Debris cascade</b> (Kessler watch) added.", "31a8084, PR #6"],
      ["22 Oct, 19:51", "<b>[W] Where it won't be</b>: Apophis checked live against NASA/JPL: EXCLUDED.", "dcb6cfa, PR #8"],
      ["22 Oct, 20:11", "Idea raised: relay a signal toward Voyager 1 through dormant satellites. Assessed against the physics and "
                        "ruled out; turned into a question that can be measured: are any of the 148 still transmitting?", "conversation"],
      ["22 Oct, ~20:40", "<b>[Z] Zombie check</b> built and run live: <b>2 of 148 heard</b>, 0 with an uplink.", "da7f9e9"],
      ["22 Oct, 20:54", "ERS 15 added to Hannibal's fleet watch list; every telemetry scan now checks it.", "d0c5078"],
      ["23 Oct, 17:58", "Receive-only legal note (Belgium) added; zombie check merged.", "181405a, PR #9"],
      ["23 Oct, 18:00", "Laptop and GitHub copies merged back into one (EME, altitude guard, home fix).", "PRs #10, #11"],
      ["23 Oct, 18:05", "Apophis re-checked (EXCLUDED); automatic updates every 6 hours scheduled.", "JPL query 16:05 UTC"],
      ["23 Oct, 18:28", "[E] upgraded: choice of dish or Yagi array, noise worked out per band.", "654952d, PR #12"],
      ["23 Oct, ~18:50", "All calculations for this report re-run; zombie check unchanged.", "this report"]]
story += [table(tl, [30 * mm, 106 * mm, 34 * mm], zebra=True)]

story += [H2("Intervals worked out from the timeline")]
iv = [["Interval", "Length"],
      ["N2YO export → zombie check", "5 d 0 h 52 min"],
      ["Idea raised → first measured answer", "about 29 min"],
      ["ERS 15's last confirmed catch (26 Sep, 14:40) → check", "26 d 6 h"],
      ["ERS 15's first SatNOGS catch (21 Oct 2020) → check", "2,192 days (6.0 years)"],
      ["ERS 15 launch (19 Aug 1966) → check", "21,979 days (60.2 years)"],
      ["Apophis orbit: span of observations behind it", "6,599 days (18.1 years), last on 9 Apr 2022"],
      ["Today → Apophis flyby (13 Apr 2029, 21:46 UTC)", "903 days (2.47 years)"],
      [f"Moon echo round trip (23 Oct, 18:20, {C['eme_range_km']:,.0f} km)", f"{C['eme_rtt_s']:.2f} s"],
      [f"Voyager 1 one-way light time (23 Oct, 18:00, {V['au']:.2f} au)", "23 h 56 min"]]
story += [table(iv, [110 * mm, 60 * mm])]
story += [P("Positions go stale within minutes, but the check does not use them: transmitters and reception records belong to "
            "the satellite, not to where it was on 17 October. The five-day gap therefore does not affect the result.", "caption")]

# ---------------------------------------------------------- 3 question/method ----
story += [Spacer(1, 4 * mm), H1("3", "The question, and how it was answered")]
story += [H2("From an idea that does not work to a question that can be measured")]
story += [P("The session started with an ambitious idea: find enough dormant Cold War satellites to relay a signal toward "
            "Voyager 1. Checked against the physics, it does not work, for three independent reasons:")]
story += B(["<b>Silent hardware cannot relay.</b> A satellite whose power and electronics have failed has nothing to "
            "amplify or retransmit with, and an object with no receiver cannot hear an uplink.",
            "<b>Wrong place, wrong scale.</b> Earth-orbiting satellites are 25.8 billion km from Voyager 1, the same distance as "
            "the ground. A relay there gains nothing on the distance, and their small antennas are far weaker than the 70 m "
            "dishes of NASA's Deep Space Network.",
            "<b>Positions are not evidence of life.</b> A catalogue lists where an object is, whether it works or not."])
story += [P("The last point turned into the real question: <b>of the 148, how many still transmit anything at all?</b> "
            "That can be measured.")]

story += [H2("Method")]
flow = [["Step", "Source", "What it gives"],
        ["1  Targets", "N2YO “above” query, category Military, Antwerp, 17 Oct 19:48 (Hannibal export, section A)", "148 NORAD ids and names"],
        ["2  Transmitters on record", "SatNOGS DB: full satellite and transmitter lists (cached 24 h)", "which objects have a known transmitter, active or not, and whether any has an uplink"],
        ["3  Reception evidence", "SatNOGS Network: vetted observations, last 30 days (cached 1 h)", "“good” = a volunteer station saw the signal; “bad” = it listened and heard nothing"],
        ["4  Verdict per object", "Hannibal [Z] (hannibal_zombie.py)", "one of the tiers below"]]
story += [table(flow, [36 * mm, 70 * mm, 64 * mm])]
story += [Spacer(1, 2 * mm)]
tiers = [["Tier", "Meaning"],
         ["HEARD", "at least one vetted good observation in the window"],
         ["LISTED, NOT HEARD", "an active transmitter is on record, but nothing good in the window (or no station scheduled a pass)"],
         ["NO ACTIVE TX", "on record, but every known transmitter is marked inactive"],
         ["NOT IN SATNOGS", "no transmitter of this object is known to the amateur network"],
         ["NOT CHECKED", "the network could not be asked; the verdict then becomes a lower bound and never a clean zero"]]
story += [table(tiers, [36 * mm, 134 * mm], bold_first_col=True)]
story += [P("Safeguards built in: filters are re-applied locally (status, object, time window), so a server that ignored one "
            "could not inflate a count; a full results page is reported as “25+”; a database outage is an error, never a "
            "silent zero. Offline tests use trimmed copies of real SatNOGS records.", "caption")]

# ------------------------------------------------------------------ 4 results ----
story += [KeepTogether([H1("4", "Results: the 148"), img("chart_funnel.png", 165), P("From 148 positions to 0 possible relays. Each bar is a subset of the one above.", "caption")])]
rows = [["NORAD", "Name", "Launch", "Transmitters (active)", "Good / bad, 30 d", "Last good (UTC)", "Tier"]]
for r in Z["rows"]:
    if not r["in_satnogs"]:
        continue
    rows.append([r["norad"], r["name"], r["launched"] or "–", f"{r['transmitters']} ({r['active_transmitters']})",
                 f"{r['good']} / {r['bad']}", r["last_good"] or "–",
                 r["tier"] + (f": {r['heard_on'].replace('Unknown', 'unknown')}" if r["tier"] == "HEARD" else "")])
story += [table(rows, [15 * mm, 27 * mm, 17 * mm, 24 * mm, 20 * mm, 24 * mm, 43 * mm], numeric_cols=(0, 2, 4))]
story += [P(f"The other 142 have no transmitter known to SatNOGS. Run of 23 October 2026, window from "
            f"{Z['since'].replace('T', ' ')[:16]} UTC. Share heard: {pct(heard)}; share with any transmitter on record: "
            f"{pct(C['insatnogs_of_148'])}. Ranges are 95% Wilson intervals (section 8).", "caption")]

# ------------------------------------------------------------------- 5 ERS 15 ----
story += [PageBreak(), H1("5", "ERS 15: a 60-year-old satellite that still transmits")]
facts = [["", ""],
         ["Identity", "ERS 15 (Environmental Research Satellite), also ORS 1; NORAD 2412, COSPAR 1966-077C"],
         ["Launched", "19 August 1966, as a piggyback payload alongside Midas 10 and SECOR 7"],
         ["Purpose", "cold-welding experiments: eight metal-to-metal tests in vacuum"],
         ["Build", "4.5 kg, octahedral"],
         ["Signal today", "136.440 MHz, AM with a 1.3 kHz tone (Orbital Focus); SatNOGS logs it as a CW carrier at 136.439 MHz"],
         ["Catalogue note", "Orbital Focus records that NORAD once catalogued it incorrectly as SECOR 7"],
         ["On record since", "SatNOGS: first vetted good observation 21 October 2020; Orbital Focus listing last updated 2014"]]
story += [table(facts[1:], [32 * mm, 138 * mm], header=False, bold_first_col=True)]
story += [Spacer(1, 3 * mm), img("chart_ers15_years.png", 165),
          P("Vetted good SatNOGS observations of ERS 15 per year: 632 in total, by at least 96 different stations. 2020 and 2026 "
            "are partial years. Fewer catches recently can reflect fewer stations scheduling it as well as the satellite itself.",
            "caption")]
story += [H2("How often is it heard?")]
er = [["Window", "Good", "Bad", "Share heard (95% range)"],
      ["30 days to 23 Oct", "2", "5", f"{C['ers15_30d']['p']*100:.1f}% ({C['ers15_30d']['lo']*100:.1f}–{C['ers15_30d']['hi']*100:.1f}%)"],
      ["365 days to 23 Oct", "71", "158", f"{C['ers15_365d']['p']*100:.1f}% ({C['ers15_365d']['lo']*100:.1f}–{C['ers15_365d']['hi']*100:.1f}%)"]]
story += [table(er, [45 * mm, 20 * mm, 20 * mm, 85 * mm], numeric_cols=(1, 2))]
story += [P("Seven vetted passes in 30 days are too few for a firm figure, which is why Hannibal's fleet scan marks ERS 15 as "
            "LOW SAMPLE. The 365-day figure is the one to quote: roughly one pass in three.", "caption")]
story += [H2("Why would it still transmit?")]
story += [P("The usual explanation for zombie satellites is that their batteries failed long ago and the transmitter now "
            "runs directly from the solar panels, so it comes on in sunlight and goes quiet in Earth's shadow; a slowly "
            "tumbling satellite also turns its panels toward and away from the Sun. That pattern fits ERS 15's on-and-off "
            "record, but the sources checked for this report do not describe its power system, so it remains the likely "
            "explanation rather than a confirmed one. Other documented zombies include LES-1 (1965, heard again from 2012), "
            "AMSAT-OSCAR 7 (1974, back in 2002) and LES-5 (contact regained in 2020 by amateur Scott Tilley).")]

# ------------------------------------------------------------------ 6 Apophis ----
story += [PageBreak(), H1("6", "Apophis: where it won't be")]
o = A["orbit"]
story += [P(f"Hannibal's [W] check asks NASA/JPL for every Earth approach of 99942 Apophis up to 2200 and tests the near edge "
            f"of JPL's 3-sigma uncertainty against Earth's radius plus 100 km of atmosphere. The overall verdict always defers to "
            f"JPL Sentry, because a pass that clears Earth can still steer an asteroid through a “keyhole” toward a later "
            f"impact. Orbit solution {o['orbit_id']}, condition code {o['condition_code']} (0 is best, 9 worst), "
            f"{o['n_obs']:,} observations over {int(o['data_arc_days']):,} days, last on {o['last_obs']}. "
            f"Sentry: removed {A['sentry'].get('removed', '')[:10]}.")]
ap = [["Approach (UTC)", "Distance (km)", "Nearest 3σ edge (km)", "Window (km)", "Above atmosphere (km)", "This pass"]]
for p in A["passes"]:
    ap.append([p["date"], f"{p['distance_km']:,.0f}", f"{p['min_km']:,.0f}", f"{p['window_km']:,.1f}",
               f"{p['clearance_above_atmosphere_km']:,.0f}",
               p["verdict"] + (" (inside GEO)" if p["inside_geo"] else "") + (" ~rough" if p["rough"] else "")])
story += [table(ap, [32 * mm, 25 * mm, 30 * mm, 24 * mm, 29 * mm, 30 * mm], numeric_cols=(1, 2, 3, 4))]
story += [P("Distances from Earth's centre. “~rough”: the uncertainty window is wider than the distance itself, so that row "
            "is only a guide and Sentry decides. Query of 23 October 2026, 16:05 UTC.", "caption")]
story += [note_box([P(f"<b>Verdict: {A['verdict']}.</b> {A['reason']} Apophis passes inside the ring of geostationary "
                      "satellites in 2029, about 31,500 km above the atmosphere, and the uncertainty on that distance is "
                      "only a few kilometres.", "cell")])]
story += [H2("Worked check of the 2029 numbers")]
p29 = A["passes"][0]
story += [P(f"Clearance above the atmosphere = nearest 3σ edge − Earth's equatorial radius − 100 km = "
            f"{p29['min_km']:,.1f} − 6,378.1 − 100 = <b>{p29['clearance_above_atmosphere_km']:,.0f} km</b>. "
            f"The margin is {p29['clearance_above_atmosphere_km'] / p29['window_km']:,.0f} times the width of the uncertainty "
            f"window. Automatic re-checks now run every 6 hours and report any change, which in practice means a new JPL orbit "
            f"solution.")]

# ---------------------------------------------------------------- 7 moonbounce ----
story += [H1("7", "Moonbounce: what a home station could do")]
story += [P("Earth–Moon–Earth (EME) uses the Moon as a passive mirror: transmit at it, and about 2.5 seconds later the echo "
            "comes back, very faint. Hannibal's [E] planner works out the budget with the Moon's live distance from JPL Horizons. "
            "The figures below are for each band's default station, 300 W, the Moon at 379,310 km (23 October, 18:20).")]
story += [img("chart_eme.png", 165),
          P("Echo signal-to-noise ratio by band against two decode thresholds. Above −25 dB the Q65 digital mode can decode "
            "the echo; above −15 dB it can be heard by ear in Morse (CW).", "caption")]
eme = [["Band", "Antenna", "Gain (dBi)", "System noise (K)", "Echo SNR (dB)", "Verdict"]]
for r in C["eme"]:
    pr = r["parts"]
    eme.append([r["band"], r["antenna"].replace(" x ", " × "), m(r["gain"]),
                f"{r['tsys']:,.0f} <font size=6.6 color='#52514e'>= {pr['receiver']:.0f} rx + {pr['sky']:,.0f} sky + "
                f"{pr['moon']:.0f} Moon + {pr['ground']:.0f} ground</font>", m(r["snr"], sign=True),
                ("by ear (CW)" if r["cw"] else ("digital" if r["best"] else "below threshold"))])
story += [KeepTogether([table(eme, [14 * mm, 43 * mm, 17 * mm, 52 * mm, 20 * mm, 24 * mm], numeric_cols=(2, 4)), P("The system noise is the key correction made on 23 October: on 2 m and 6 m the galaxy itself is louder than the "
            "receiver, which a fixed 100 K had hidden (a 4-Yagi 2 m station had looked 4.3 dB better than it is). Transmitting "
            "needs an amateur licence that covers the band and power; BIPT sets the limits for each licence class.", "caption")])]

# ------------------------------------------------------------- 8 calculations ----
story += [H1("8", "Calculations")]
story += [H2("Counting with small numbers: the Wilson interval")]
story += [P("With small counts a plain percentage overstates certainty, so every share in this report carries a 95% Wilson "
            "score interval. For k successes in n trials, with p = k/n and z = 1.96:")]
story += [P("centre = (p + z²/2n) / (1 + z²/n)     half-width = z·√(p(1−p)/n + z²/4n²) / (1 + z²/n)", "mono")]
wl = [["Quantity", "k / n", "Share", "95% range"]]
for name, key in (("Objects heard, of 148", "heard_of_148"), ("Objects with any transmitter on record", "insatnogs_of_148"),
                  ("ERS 15 passes heard, 30 days", "ers15_30d"), ("ERS 15 passes heard, 365 days", "ers15_365d")):
    d = C[key]
    wl.append([name, f"{d['k']} / {d['n']}", f"{d['p']*100:.1f}%", f"{d['lo']*100:.1f}–{d['hi']*100:.1f}%"])
story += [table(wl, [80 * mm, 25 * mm, 25 * mm, 40 * mm], numeric_cols=(1, 2, 3))]
story += [H2("Radio link budgets")]
story += [P("Moonbounce uses the radar equation, because the Moon reflects only about 6.5% of what reaches it and spreads "
            "the echo back over the whole sky. Voyager uses the one-way free-space equation. In decibels:")]
story += [P("EME path loss = 10·log10( (4π)³ R⁴ / (λ² σ) ),  σ = 0.065 · π r_Moon²<br/>"
            "Free-space loss = 20·log10( 4π d / λ )<br/>"
            "Dish gain = 10·log10( η (π D / λ)² )      Yagi array = G1 + 10·log10(N) − 0.5 dB<br/>"
            "Noise density N0 = 10·log10( k_B · T_sys ) + 30 dBm/Hz<br/>"
            "Sky noise T_sky = 2.7 K + 200 K · (f / 144 MHz)^−2.55", "mono")]
story += [P("Check against NASA: for Voyager's design point (48.62 au, 8,415 MHz) the free-space formula gives 308.18 dB; "
            "JPL's published design table gives 308.19 dB. The Voyager figures in section 9 are scaled from that table to "
            f"today's {V['au']:.2f} au, a space loss of {V['space_loss_db']:.1f} dB.")]
story += [H2("Distances and times")]
dt = [["Quantity", "Value", "Source"],
      ["Moon distance, 23 Oct 16:20 UT", f"{C['eme_range_km']:,.0f} km; echo round trip {C['eme_rtt_s']:.2f} s", "JPL Horizons"],
      ["Voyager 1 distance, 23 Oct 16:00 UT", f"{V['au']:.4f} au = {V['d_km']/1e9:.2f} billion km", "JPL Horizons (target −31)"],
      ["Voyager 1 one-way light time", f"{V['lt_h']:.2f} h (23 h 56 min)", "JPL Horizons"],
      ["Apophis 2029 approach", f"{p29['distance_km']:,.0f} km from Earth's centre", "NASA/JPL CNEOS close-approach data"],
      ["ERS 15 in orbit", "60.2 years (21,979 days) at the time of the check", "launch date, Wikipedia"]]
story += [table(dt, [55 * mm, 70 * mm, 45 * mm])]

# --------------------------------------------------------------- 9 Voyager 1 ----
story += [PageBreak(), H1("9", "The long-term dream: Voyager 1, in numbers")]
story += [P("Contacting Voyager 1 means transmitting to it, and that belongs to NASA's Deep Space Network alone. "
            "<b>Hearing</b> it is a different matter. In 2024 the amateur-run CAMRAS foundation detected Voyager 1's carrier "
            "with the 25 m Dwingeloo telescope in the Netherlands, after fitting new 8.4 GHz receiving equipment and correcting for "
            "Doppler with orbital predictions. That detection is the real frontier for amateurs, and it is the honest version "
            "of this project's dream.")]
story += [P(f"The budget below uses JPL's own Voyager design figures (12 W into the antenna, a 3.66 m dish with 48.2 dBi of "
            f"gain, about 6.2 dB of the power left in the carrier, 0.4 dB of pointing, atmosphere and polarisation losses), Voyager 1's "
            f"distance today ({V['d_km']/1e9:.2f} billion km) and its downlink at 8,420.43 MHz. The receiving stations are "
            "the Deep Space Network's 70 m dish (JPL's figures), a 25 m dish like Dwingeloo, and a 3 m home dish (the last "
            "two assume 50–55% efficiency and 50 K of system noise).")]
vt = [["Receiving dish", "Gain (dBi)", "System noise (K)", "Carrier power (dBm)", "Carrier C/N0 (dB-Hz)", "Integration for SNR 10"]]
for label, key in (("Deep Space Network, 70 m", "dsn70"), ("Dwingeloo-class, 25 m", "dwingeloo25"), ("Home dish, 3 m", "home3")):
    d = V[key]
    tau = d["tau_snr10_s"]
    tau_s = f"{tau*1000:.0f} ms" if tau < 1 else f"{tau:.0f} s"
    vt.append([label, m(d["g_r"]), f"{d['tsys']:.0f}", m(d["pc_dbm"]), m(d["cn0_dbhz"], sign=True), tau_s])
story += [table(vt, [43 * mm, 20 * mm, 24 * mm, 28 * mm, 28 * mm, 27 * mm], numeric_cols=(1, 2, 3, 4, 5))]
story += [P("C/N0 is the carrier power over the noise in 1 Hz. “Integration for SNR 10” is the coherent averaging time needed "
            "for the carrier to stand ten times above the noise in a single narrow frequency bin, in the ideal case.", "caption")]
story += [H2("What the numbers say, and what they leave out")]
story += B([f"A 25 m dish has {V['area_ratio_25_3']:.0f} times the collecting area of a 3 m dish, which is the 18 dB gap between "
            "the two rows.",
            "On paper, a 3 m dish would need about a minute and a half of perfectly coherent integration. In practice that is "
            f"very hard: Earth's rotation alone sweeps the carrier by up to {V['doppler_rate_hz_s']:.2f} Hz per second, so the "
            "Doppler must be removed to a few millihertz from JPL's ephemeris; the receiver needs a GPS-locked reference with "
            f"very low phase noise; and the dish must hold Voyager inside a beam about {V['beam_3m_deg']:.1f}° wide.",
            "Real-world losses not modelled here (feed and polarisation losses, interference, a noisier receiver) eat into "
            "the margin. No detection with a home-sized dish was found in the sources checked; Dwingeloo's 25 m is the "
            "confirmed amateur result.",
            "So the dream is grounded, and the path to it runs through the steps in the next section: hear ERS 15, then the "
            "Moon, then deep space."])

# ------------------------------------------------------------ 10 next steps ----
story += [H1("10", "Next steps and vision")]
ns = [["Step", "What it takes", "Why it matters"],
      ["1  Hear ERS 15 yourself", "An RTL-SDR, a simple 136 MHz antenna, and Hannibal's radio-pass times for NORAD 2412", "Turns a SatNOGS record into Hannibal's own reception; receive-only, no licence needed"],
      ["2  Join SatNOGS", "Run a ground station and share its observations", "Adds Antwerp to the network this whole result rests on"],
      ["3  Listen to the Moon", "Decode other stations' moonbounce echoes on 2 m with a Yagi and free WSJT-X software", "Real signals after 768,000 km, before any transmitter licence"],
      ["4  Licence, then echoes", "An amateur licence that covers the band and power, then the antenna the [E] planner points to", "Hearing your own echo off the Moon"],
      ["5  Deep space", "X-band reception, a stable reference, Doppler correction from JPL; or work with CAMRAS", "The road toward hearing Voyager 1"]]
story += [table(ns, [37 * mm, 70 * mm, 63 * mm], bold_first_col=True)]

# ----------------------------------------------------------- 11 regulatory ----
story += [PageBreak(), H1("11", "Receive-only and the law (Belgium)")]
story += [P("From the project's regulatory memo of 22 October 2026, checked against the pages of BIPT, the Belgian telecoms "
            "regulator, on 22–23 October. This is not legal advice; BIPT is the authority.")]
story += B(["<b>No licence to listen.</b> Owning and using a receiver (an SDR, a scanner, a satellite antenna) needs no "
            "permit, exam or licence. BIPT states that buying and owning a scanner or receiver is allowed.",
            "<b>Licences are for transmitting.</b> Operator certificates and station authorisations are needed only to "
            "transmit. Nothing in Hannibal transmits.",
            "<b>The ONL listener number is voluntary.</b> It is a club matter through the UBA, the Belgian amateur radio union, "
            "not a state requirement.",
            "<b>What you may listen to is limited.</b> BIPT allows listening only to frequencies open to everyone, or ones the "
            "frequency holder has authorised. ERS 15's carrier, amateur and weather satellites and the ISS are fine; "
            "deliberately listening in on or decoding military satellite traffic is not; TETRA and speed-radar detectors are "
            "banned outright."])
story += [P("Hannibal's [Z] check stays on the right side of this line: it reads public SatNOGS records and never decodes "
            "any satellite's traffic itself.")]

story += [H1("12", "What Hannibal can do now")]
mods = [["Key", "Module", "What it does", "Verified result"],
        ["[Z]", "Zombie check", "which satellites on a list still transmit, from SatNOGS evidence", "2 of 148 heard (22–23 Oct)"],
        ["[W]", "Where it won't be", "Earth-impact exclusion for any asteroid or comet, deferring to JPL Sentry", "Apophis EXCLUDED; Bennu NOT EXCLUDED (Sentry lists it)"],
        ["[D]", "Debris cascade", "tracked objects per altitude shell and a Kessler cascade index (CelesTrak)", "35,046 objects in orbit on 22 Oct; 450–500 km shell index 0.06"],
        ["[E]", "Moonbounce", "EME link budget with dish or Yagi choice and per-band noise", "section 7"],
        ["[1]", "Fleet telemetry", "evidence-gated link health of a watch list, now including ERS 15", "ERS 15: LOW SAMPLE, 2 of 7 (30 d)"]]
story += [table(mods, [11 * mm, 30 * mm, 74 * mm, 55 * mm])]
story += [P("Every module is receive-only, uses public data, sends its network calls through one masked, cached, rate-limited "
            "layer, and ships with offline tests (five test files, all passing on 23 October).", "caption")]

story += [P("Reproduce the results", ParagraphStyle("h2t", parent=S["h2"], spaceBefore=4, spaceAfter=2))]
story += [P("git clone https://github.com/3mm4nu3I/Hannibal-Beta-2.0<br/>"
            "cd Hannibal-Beta-2.0/orbital<br/>"
            "python hannibal_zombie.py                 # the 148, from zombie_targets_2026-10-17.json<br/>"
            "python hannibal_zombie.py --ids 2412      # ERS 15 alone<br/>"
            "python hannibal_neo.py 99942              # Apophis<br/>"
            "python hannibal_orbital.py --eme          # moonbounce planner<br/>"
            "python test_hannibal_zombie.py            # and the other test_hannibal_*.py files", "mono")]

# -------------------------------------------------------------- sources ----
story += [H1("13", "Sources")]
src = [
    "SatNOGS DB and Network (Libre Space Foundation): db.satnogs.org/satellite/2412, network.satnogs.org — transmitters and vetted observations, queried 22–23 Oct 2026.",
    "N2YO REST API, “above” category 30 (Military) — the 17 Oct 2026 Hannibal satellite detail export for Antwerp.",
    "NASA/JPL: Horizons (Moon, Voyager 1), CNEOS close-approach data, Sentry, Small-Body Database — ssd.jpl.nasa.gov, ssd-api.jpl.nasa.gov.",
    "JPL DESCANSO, Article 4: Voyager Telecommunications — X-band power, high-gain antenna, 70 m station, Table 5-3 design control table.",
    "CAMRAS, “Dwingeloo telescope receives signals from Voyager 1”, 10 December 2024 — camras.nl.",
    "Orbital Focus, Satellite Radio Frequencies, 136–138 MHz band — orbitalfocus.uk (ERS 15: 136.440 MHz, AM with 1.3 kHz tone).",
    "Wikipedia: Environmental Research Satellite (ERS-15 / ORS 1); Zombie satellite.",
    "BIPT: Forbidden and/or special equipment; Radio amateurs; General authorisations — bipt.be.",
    "Hannibal source code, changelogs and tests: github.com/3mm4nu3I/Hannibal-Beta-2.0 (pull requests #6–#12).",
]
story += B(src, "srcbullet")
story += [Spacer(1, 1.5 * mm),
          P("Prepared by Bram Noffels. Code, calculations and this report were developed with the help of Claude, an AI "
            "assistant made by Anthropic; every number was produced by running code against the sources above.", "small")]

doc.build(story)
print("written", OUT)
