"""Soviet-space-programme styled ASCII art for the Hannibal orbital modules.

All art here is original. Pieces are plain strings so they can be printed anywhere;
colour is applied by helper functions and is skipped automatically when stdout is not
a terminal. Set HANNIBAL_ASCII_ONLY=1 for a pure-ASCII fallback (no block glyphs, no
star/hammer-and-sickle symbols) if your console font lacks them.
"""
import os
import random
import re
import sys
import time

RESET = "\033[0m"
RED_BG = "\033[41m"
RED = "\033[91m"
GOLD = "\033[1;33m"
WHITE = "\033[1;37m"
GREEN = "\033[92m"
GRAY = "\033[90m"
CYAN = "\033[96m"
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def ascii_only():
    if os.environ.get("HANNIBAL_ASCII_ONLY") == "1":
        return True
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8").lower()
    try:
        "☭█★▶•°".encode(enc)
        return False
    except (UnicodeEncodeError, LookupError):
        return True


def sym(name):
    """Symbols with an ASCII fallback."""
    table = {"hs": ("☭", "*"), "star": ("★", "*"), "block": ("█", "#"),
             "dot": ("•", "o"), "arrow": ("▶", ">"), "deg": ("°", "d")}
    uni, asc = table[name]
    return asc if ascii_only() else uni


def strip_ansi(text):
    return _ANSI.sub("", text)


def paint(text, *codes, enabled=None):
    """Wrap text in ANSI codes unless colour is off (not a TTY / NO_COLOR)."""
    if enabled is None:
        enabled = hasattr(sys.stdout, "isatty") and (sys.stdout.isatty() or os.environ.get("HANNIBAL_COLOR") == "1") \
                  and not os.environ.get("NO_COLOR")
    if not enabled or not codes:
        return text
    return "".join(codes) + text + RESET


# ----------------------------------------------------------------- block font ----
_FONT = {
    "A": [" ### ", "#   #", "#####", "#   #", "#   #"], "B": ["#### ", "#   #", "#### ", "#   #", "#### "],
    "C": [" ####", "#    ", "#    ", "#    ", " ####"], "D": ["#### ", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#### ", "#    ", "#####"], "F": ["#####", "#    ", "#### ", "#    ", "#    "],
    "G": [" ####", "#    ", "#  ##", "#   #", " ####"], "H": ["#   #", "#   #", "#####", "#   #", "#   #"],
    "I": ["#####", "  #  ", "  #  ", "  #  ", "#####"], "J": ["  ###", "   # ", "   # ", "#  # ", " ##  "],
    "K": ["#   #", "#  # ", "###  ", "#  # ", "#   #"], "L": ["#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "#   #", "#   #"], "N": ["#   #", "##  #", "# # #", "#  ##", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", " ### "], "P": ["#### ", "#   #", "#### ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "# # #", "#  # ", " ## #"], "R": ["#### ", "#   #", "#### ", "#  # ", "#   #"],
    "S": [" ####", "#    ", " ### ", "    #", "#### "], "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", " ### "], "V": ["#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "# # #", "## ##", "#   #"], "X": ["#   #", " # # ", "  #  ", " # # ", "#   #"],
    "Y": ["#   #", " # # ", "  #  ", "  #  ", "  #  "], "Z": ["#####", "   # ", "  #  ", " #   ", "#####"],
    "0": [" ### ", "#  ##", "# # #", "##  #", " ### "], "1": ["  #  ", " ##  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "  ## ", " #   ", "#####"], "3": ["#### ", "    #", " ### ", "    #", "#### "],
    "4": ["#  # ", "#  # ", "#####", "   # ", "   # "], "5": ["#####", "#    ", "#### ", "    #", "#### "],
    "6": [" ### ", "#    ", "#### ", "#   #", " ### "], "7": ["#####", "    #", "   # ", "  #  ", "  #  "],
    "8": [" ### ", "#   #", " ### ", "#   #", " ### "], "9": [" ### ", "#   #", " ####", "    #", " ### "],
    "-": ["     ", "     ", "#####", "     ", "     "], ".": ["     ", "     ", "     ", " ##  ", " ##  "],
    ":": ["     ", " ##  ", "     ", " ##  ", "     "], "/": ["    #", "   # ", "  #  ", " #   ", "#    "],
    "!": ["  #  ", "  #  ", "  #  ", "     ", "  #  "], " ": ["   ", "   ", "   ", "   ", "   "],
}


def big_text(text, gap=1):
    """Render `text` (A-Z 0-9 - . : / !) as 5-row block letters. Unknown characters are skipped."""
    block = sym("block")
    rows = [""] * 5
    for ch in str(text).upper():
        glyph = _FONT.get(ch)
        if glyph is None:
            continue
        for i in range(5):
            rows[i] += glyph[i].replace("#", block) + " " * gap
    return "\n".join(r.rstrip() for r in rows)


# ------------------------------------------------------------------- the art ----
SPUTNIK = r'''
     ====================.
     =====================\      ___....___
     ======================`--.-'  .--.   `-.
     ========================--|  ( {s} )   |   CCCP-1
     ======================.--'-.  `--'   .-'
     =====================/      `-......-'
     ====================.
'''

LAUNCH = r"""
              /\
             /  \
            | {s}   |
            | CCCP |
            |      |
            |______|
         /| |      | |\
        / | |      | | \
       /__| |      | |__\
          | |______| |
         /_/  /||\  \_\
             /_||||_\
            ^^^^^^^^^^
           ^^ ^^^^^^ ^^
"""

RED_STAR = r"""
                 /\
                /  \
               /    \
   ___________/      \___________
   \                            /
    \          {s}               /
     \                        /
      \        ______        /
       \      /      \      /
        \    /        \    /
         \  /          \  /
          \/            \/
"""

DISH = r"""
           _,.--~~~--.._
        ,-'    _,.--.   `-.
      ,'   _,-'      `.    `.
     /   ,'   .--.     \     \
    ;   /    ( {s} )     ;     ;
    |  |      `--'      |     |
     \  \              /     /
      `. `-.__    __,-'    ,'
        `-._  `~~'  _,-'-'
            `~~----~~'
              |    |
          ____|____|____
"""

ORBIT = r"""
                  .  *   .      {s}
          .  *        _____         .
       *         .-'''     '''-.  *
         .     .'               '.     .
             /      E A R T H     \
      .     |     ~~~~~~~~~~~     |    .
             \                    /
        *     '.               .'      *
                '-.._______..-'     .
        .   *       .       *    .
"""

SLOGANS = [
    "VPERED, K ZVEZDAM!",         # "Forward, to the stars!"
    "KOSMOS NASH!",               # "Space is ours!"
    "POYEKHALI!",                 # "Let's go!"
    "ORBITA ZHDET!",              # "The orbit awaits!"
    "ZEMLYA - ZVEZDA - ZEMLYA",   # a loop: earth - star - earth
]


def _art(template):
    return template.replace("{s}", sym("hs")).strip("\n")


def sputnik():
    return _art(SPUTNIK)


def launch():
    return _art(LAUNCH)


def red_star():
    return _art(RED_STAR)


def dish():
    return _art(DISH)


def orbit():
    return _art(ORBIT)


def slogan(rng=None):
    return (rng or random).choice(SLOGANS)


def stars(n=24):
    return " ".join([sym("star")] * n)


# ------------------------------------------------------------------- chrome ----
def banner(title, subtitle="", width=78, color=True):
    """Red/gold banner bar with the title centred, e.g. for the top of a screen."""
    hs = sym("hs")
    lines = [f"{hs} {title} {hs}"]
    if subtitle:
        lines.append(subtitle)
    out = []
    bar = "=" * width
    out.append(paint(bar.ljust(width), RED_BG, GOLD, enabled=color))
    for l in lines:
        out.append(paint(l.center(width), RED_BG, GOLD, enabled=color))
    out.append(paint(bar.ljust(width), RED_BG, GOLD, enabled=color))
    return "\n".join(out)


def title_card(title, width=78, color=True, tag="PROJECT HANNIBAL // ORBITAL DIRECTORATE"):
    """Big block-letter title with a banner tag, plus a random slogan."""
    big = big_text(title)
    body = "\n".join(paint(l, RED, enabled=color) for l in big.splitlines())
    return "\n".join([banner(tag, width=width, color=color), "", body, "",
                      paint(f"  {sym('star')} {slogan()} {sym('star')}", GOLD, enabled=color)])


def section(title, width=89, color=True):
    hs = sym("hs")
    return paint(f"{hs} {title}".ljust(width), WHITE, enabled=color) + "\n" + paint("-" * width, RED, enabled=color)


def bar(frac, width=24, color=True):
    """Progress/health bar: [#####-----]."""
    frac = 0.0 if frac is None else max(0.0, min(1.0, float(frac)))
    filled = int(round(frac * width))
    block = sym("block")
    return "[" + paint(block * filled, GREEN if frac >= 0.75 else (GOLD if frac >= 0.25 else RED), enabled=color) + \
           "-" * (width - filled) + "]"


def compass(az):
    """16-point compass label for an azimuth in degrees."""
    if az is None:
        return "--"
    names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return names[int((az % 360) / 22.5 + 0.5) % 16]


def elevation_bar(el, width=18, color=True):
    """-90..+90 degrees as a bar centred on the horizon: below horizon = dim, above = bright."""
    if el is None:
        return " " * (width * 2 + 3)
    el = max(-90.0, min(90.0, el))
    half = width
    n = int(round(abs(el) / 90.0 * half))
    block = sym("block")
    left = " " * (half - (n if el < 0 else 0)) + (block * n if el < 0 else "")
    right = (block * n if el >= 0 else "") + " " * (half - (n if el >= 0 else 0))
    return paint(left, GRAY, enabled=color) + "|" + paint(right, GOLD if el > 0 else GRAY, enabled=color)


# ---------------------------------------------------------------- animation ----
_ORBIT_FRAMES = [
    ("          .  .  .            ", "       .             .       ", "      .       E       .      ", "       .             .       ", "          .  .  {s}            "),
    ("          .  .  .            ", "       .             {s}       ", "      .       E       .      ", "       .             .       ", "          .  .  .            "),
    ("          .  .  {s}            ", "       .             .       ", "      .       E       .      ", "       .             .       ", "          .  .  .            "),
    ("          .  .  .            ", "       {s}             .       ", "      .       E       .      ", "       .             .       ", "          .  .  .            "),
]


def boot_animation(out=None, delay=0.12, loops=2, enabled=None):
    """Tiny orbiting-satellite animation. Does nothing when output is not a terminal."""
    out = out or sys.stdout
    if enabled is None:
        enabled = hasattr(out, "isatty") and out.isatty() and not os.environ.get("HANNIBAL_NO_ANIM")
    if not enabled:
        return
    hs = sym("hs")
    frames = [[l.replace("{s}", hs) for l in f] for f in _ORBIT_FRAMES]
    h = len(frames[0])
    out.write("\n" * h)
    for i in range(loops * len(frames)):
        out.write(f"\033[{h}A")
        for l in frames[i % len(frames)]:
            out.write(paint("  " + l, GOLD, enabled=True) + "\033[K\n")
        out.flush()
        time.sleep(delay)
    out.write(f"\033[{h}A" + ("\033[K\n" * h) + f"\033[{h}A")
    out.flush()
