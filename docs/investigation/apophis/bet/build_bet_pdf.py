"""Apophis 2029 prediction record (the bet): one A4 PDF for the study file. Rebuild: python build_bet_pdf.py"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
OUT = HERE / "Apophis_2029_Prediction_Record.pdf"
DJ = Path("/usr/share/fonts/truetype/dejavu/")
pdfmetrics.registerFont(TTFont("Sans", str(DJ / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Sans-Bold", str(DJ / "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Mono", str(DJ / "DejaVuSansMono.ttf")))
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold", italic="Sans", boldItalic="Sans-Bold")

INK, INK2, RULE, TINT = (colors.HexColor(c) for c in ("#0b0b0b", "#52514e", "#e4e3df", "#f5f4f1"))
ACCENT = colors.HexColor("#b3261e")
body = ParagraphStyle("b", fontName="Sans", fontSize=9.2, leading=13, textColor=INK)
small = ParagraphStyle("s", parent=body, fontSize=7.6, leading=10, textColor=INK2)
mono = ParagraphStyle("m", parent=body, fontName="Mono", fontSize=7.2, leading=9.6)
h1 = ParagraphStyle("h1", parent=body, fontName="Sans-Bold", fontSize=17, leading=21)
h2 = ParagraphStyle("h2", parent=body, fontName="Sans-Bold", fontSize=10.5, leading=14, spaceBefore=9, spaceAfter=3,
                    textColor=ACCENT)
cell = ParagraphStyle("c", parent=body, fontSize=8.4, leading=11)
cellb = ParagraphStyle("cb", parent=cell, fontName="Sans-Bold")

REPO = "github.com/3mm4nu3I/Hannibal-Beta-2.0"
BRANCH = "reports/daily"
COMMITS = [
    ("36f3703", "2026-10-23 21:03 UTC", "Pre-registration, baseline, JPL vs ESA cross-check, evidence run 2026-10-23_2103"),
    ("5ed4897", "2026-10-23 21:24 UTC", "Hypothesis H-A and criteria C6 to C8"),
    ("5466d4a", "2026-10-23 21:30 UTC", "Worst-case rule"),
    ("65431af", "2026-10-23 21:42 UTC", "2029 model test: JPL and ESA predictions frozen"),
    ("d0b7730", "2026-10-23 21:46 UTC", "The bet recorded (section 4d)"),
    ("8bf1987", "2026-10-23 21:47 UTC", "Section headings cite their commits"),
]


def P(text, style=body):
    return Paragraph(text, style)


def table(rows, widths, header=True):
    t = Table([[P(c, cellb if (header and i == 0) else cell) if isinstance(c, str) else c for c in r]
               for i, r in enumerate(rows)], colWidths=[w * mm for w in widths])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, -1), (-1, -1), 0.4, RULE),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
             ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [colors.white, TINT])]
    if header:
        style.append(("LINEBELOW", (0, 0), (-1, 0), 0.7, INK))
    t.setStyle(TableStyle(style))
    return t


s = [P("APOPHIS 2029: PREDICTION RECORD", h1),
     P("Project Hannibal study file · record of two competing predictions for the 13 April 2029 close approach of "
       "asteroid 99942 Apophis · prepared 23 October 2026", small), Spacer(1, 6),
     P("This document records two predictions, made before the event, for how close Apophis will come to Earth on "
       "13 April 2029. The authoritative record is the git history of the repository below; this PDF is a readable "
       "copy of it. Both predictions are timestamped by commit and are scored against the reconstructed orbit "
       "published after the flyby.")]

s += [P("1  The predictions", h2),
      table([["Party", "Prediction (distance from Earth's centre at closest approach)", "Basis"],
             ["Bram, investigator, Project Hannibal", "<b>28,000 to 29,000 km</b><br/>(\"the model is off\")",
              "The investigators' hypothesis"],
             ["Claude, AI assistant (Anthropic)", "<b>38,008 to 38,015 km</b>, closest approach at 21:45 UTC ± 1 minute",
              "NASA/JPL orbit solution 220, 3-sigma window, confirmed independently by ESA NEOCC"]], [44, 70, 60]),
      Spacer(1, 4),
      P("Recorded in <font name='Mono'>docs/investigation/apophis/PREREGISTRATION.md</font>, section 4d, commit "
        "<font name='Mono'>d0b7730</font> (23 Oct 2026, 21:46:07 UTC). Stake: reputation only. No money, goods or "
        "services are involved.", small)]

s += [P("2  Scoring rules (fixed in advance)", h2),
      table([["Outcome (reconstructed closest-approach distance)", "Result"],
             ["38,008 to 38,015 km", "Claude's prediction correct; the orbit models confirmed"],
             ["28,000 to 29,000 km", "Bram's prediction correct; the orbit models were wrong"],
             ["Anywhere else", "Neither wins. A value outside 38,008 to 38,015 km still shows the models were wrong."]],
            [84, 90]),
      Spacer(1, 4),
      P("Deciding source: NASA/JPL's post-flyby orbit solution (JPL Small-Body Database / CNEOS close-approach data), "
        "checked against ESA NEOCC's reconstruction. If the two disagree by more than their stated uncertainties, both "
        "values are reported and the record says so."),
      P("Both predictions are misses. At 28,000 km Apophis would still pass about 21,500 km above Earth's surface. "
        "Neither prediction describes an impact.", small)]

s += [P("3  Data the predictions were made against", h2),
      table([["Quantity (as of 23 Oct 2026)", "NASA/JPL", "ESA NEOCC"],
             ["Orbit solution", "220 (condition code 0), 7,370 observations, last 2022-04-09",
              "independent fit, 9,577 observations on file, last 2022-04-09"],
             ["2029 closest approach", "38,011 km; 3-sigma window 38,008 to 38,015 km; 21:44:50 UTC",
              "38,014 km (1-sigma 1.3 km); 21:45:03 UTC"],
             ["Agreement", "2.3 km apart = 1.4 combined sigma", ""],
             ["Yarkovsky push A2", "−2.9018e−14 ± 1.9e−16 au/d²", "−2.9001e−14 ± 2.3e−16 au/d²"],
             ["Impact-risk list", "Sentry: removed 2021-02-21", "not listed"]], [44, 70, 60]),
      Spacer(1, 4),
      P("Raw replies from both agencies, fetched live and hashed, are in "
        "<font name='Mono'>docs/investigation/apophis/evidence/2026-10-23_2103/</font>:", small),
      P("fc23f64a…bfb024  jpl_cad.json<br/>ee5ae262…13b373fc  jpl_sentry.json<br/>"
        "4b7720e8…6f552f  jpl_sbdb.json<br/>bce0af62…cee5ebe8  esa_clolin.txt<br/>"
        "a51f86d0…47e7465d  manifest.json", mono)]

s += [P("4  What would show up before 2029", h2),
      P("Moving the closest approach by 9,000 to 10,000 km is several thousand times JPL's stated uncertainty, so it would "
        "not stay hidden until the day. The study's daily brief (three times a day) raises an alert on the first new "
        "orbit solution that moves the 2029 distance by more than 3.3 km (criterion C5), or if a push the Yarkovsky model "
        "doesn't explain is measured (C6). Apophis is observable again from about 20 December 2026, and every night from "
        "7 October 2028 to the flyby.")]

s += [KeepTogether([P("5  Audit trail", h2),
                    table([["Commit", "Time (UTC)", "What it recorded"]] + [list(c) for c in COMMITS], [20, 36, 118]),
                    Spacer(1, 4),
                    P(f"Repository: {REPO}, branch {BRANCH} (pull request #15). To verify: <font name='Mono'>git show "
                      "d0b7730:docs/investigation/apophis/PREREGISTRATION.md</font>; evidence: <font name='Mono'>cd "
                      "docs/investigation/apophis/evidence/2026-10-23_2103 &amp;&amp; sha256sum -c SHA256SUMS</font>.",
                      small)])]

s += [P("6  Disclosures and compliance notes", h2),
      table([["Item", "Statement"],
             ["Nature", "A scientific prediction record between an investigator and an AI assistant. Not a wager: no "
                        "money or other consideration changes hands."],
             ["AI involvement", "Claude (Anthropic) built the analysis software and wrote this record at the "
                                "investigator's request. Its prediction comes from public agency data, not "
                                "independent knowledge."],
             ["Data sources", "Public NASA/JPL APIs (ssd-api.jpl.nasa.gov, ssd.jpl.nasa.gov/api/horizons.api) and ESA "
                              "NEOCC public downloads (neo.ssa.esa.int). No authentication, no restricted data."],
             ["Personal data", "None beyond the investigator's first name. No location, contact or identity data of "
                               "third parties."],
             ["Activities", "Receive-only. No radio transmission. Any optical or radio observations are passive."],
             ["Limitations", "Agency figures use linearised 3-sigma uncertainties. The scoring depends on the post-flyby "
                             "reconstruction, which will itself carry an uncertainty of order kilometres."],
             ["Pre-registration", "Criteria and predictions were committed before any data testing them existed. Later "
                                  "changes are new commits with a stated reason."]], [32, 142])]

s += [Spacer(1, 10), P("Prepared from the repository state at commit 8bf1987 (23 Oct 2026, 21:47 UTC). If this PDF and "
                       "the repository ever disagree, the repository's git history is authoritative.", small)]

SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                  bottomMargin=16 * mm, title="Apophis 2029 Prediction Record", author="Project Hannibal",
                  subject="Pre-registered predictions for the 13 April 2029 close approach of 99942 Apophis").build(s)
print(OUT)
