"""Code checks run on every SVG before we accept it.

Each check returns (passed: bool, reason: str). The reason is shown on the
web page and sent back to the model on a retry, so it should say exactly what
is wrong.
"""
import re
import xml.etree.ElementTree as ET

NUM = r"-?\d*\.?\d+(?:[eE][-+]?\d+)?"
TOLERANCE = 1.0  # allow 1 unit of overhang for stroke widths / rounding


def local(tag: str) -> str:
    """'{http://www.w3.org/2000/svg}rect' -> 'rect'"""
    return tag.split("}")[-1]


def nums(s: str) -> list[float]:
    return [float(n) for n in re.findall(NUM, s or "")]


def all_text(root) -> str:
    """All visible text in <text>, <tspan> and <title>, lower-cased."""
    parts = []
    for el in root.iter():
        if local(el.tag) in ("text", "tspan", "title"):
            parts.append("".join(el.itertext()))
    return " ".join(parts).lower()


# ---------- Check 1: valid and parseable ----------
def check_valid(svg: str):
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        return False, f"SVG is not valid XML: {e}", None
    if local(root.tag) != "svg":
        return False, f"Root element is <{local(root.tag)}>, expected <svg>", None
    return True, "Parsed OK", root


# ---------- Check 2: nothing outside the viewBox ----------
def points_of(el) -> list[tuple[float, float]]:
    """Return the (x, y) points an element touches, as far as we can tell cheaply."""
    tag, a = local(el.tag), el.attrib
    g = lambda k: float(nums(a.get(k, "0"))[0]) if nums(a.get(k, "0")) else 0.0
    if tag == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        return [(x, y), (x + w, y + h)]
    if tag == "circle":
        cx, cy, r = g("cx"), g("cy"), g("r")
        return [(cx - r, cy - r), (cx + r, cy + r)]
    if tag == "ellipse":
        cx, cy, rx, ry = g("cx"), g("cy"), g("rx"), g("ry")
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if tag == "line":
        return [(g("x1"), g("y1")), (g("x2"), g("y2"))]
    if tag == "text":
        return [(g("x"), g("y"))]
    if tag in ("polygon", "polyline"):
        n = nums(a.get("points", ""))
        return list(zip(n[0::2], n[1::2]))
    if tag == "path":
        d = a.get("d", "")
        # Only absolute M/L/C/Q/Z paths: relative commands (lower case) or
        # H/V/A/S/T would need a real path parser, so we skip those.
        # ('e' is excluded because it appears in numbers like 1e-3.)
        if re.search(r"[a-df-zHVAST]", d):
            return []
        n = nums(d)
        return list(zip(n[0::2], n[1::2]))
    return []


def check_in_viewbox(root):
    vb = nums(root.get("viewBox", ""))
    if len(vb) != 4:
        return False, "Missing or malformed viewBox attribute"
    minx, miny, w, h = vb
    maxx, maxy = minx + w, miny + h
    problems = []

    def walk(el, transformed: bool):
        # Coordinates inside a transform are not in viewBox space; skip them
        # rather than give a false failure.
        transformed = transformed or "transform" in el.attrib
        if not transformed and local(el.tag) not in ("defs", "clipPath", "mask", "marker", "pattern"):
            for x, y in points_of(el):
                if not (minx - TOLERANCE <= x <= maxx + TOLERANCE and
                        miny - TOLERANCE <= y <= maxy + TOLERANCE):
                    problems.append(f"<{local(el.tag)}> has point ({x:g}, {y:g})")
                    break
        if local(el.tag) in ("defs", "clipPath", "mask", "marker", "pattern"):
            return
        for child in el:
            walk(child, transformed)

    walk(root, False)
    if problems:
        return False, (f"Drawn outside viewBox {minx:g} {miny:g} {w:g} {h:g}: "
                       + "; ".join(problems[:5]))
    return True, f"All checked shapes inside viewBox {minx:g} {miny:g} {w:g} {h:g}"


# ---------- Check 3: title and at least 3 text labels ----------
def check_title_and_labels(root):
    titles = [t for t in root.iter() if local(t.tag) == "title" and "".join(t.itertext()).strip()]
    labels = [t for t in root.iter() if local(t.tag) == "text" and "".join(t.itertext()).strip()]
    if not titles:
        return False, "No non-empty <title> element"
    if len(labels) < 3:
        return False, f"Only {len(labels)} non-empty <text> labels, need at least 3"
    return True, f"Title present, {len(labels)} text labels"


# ---------- Check 4: at least one animation ----------
SMIL = {"animate", "animateTransform", "animateMotion", "set"}


def check_animation(root):
    smil = [el for el in root.iter() if local(el.tag) in SMIL]
    css = " ".join("".join(el.itertext()) for el in root.iter() if local(el.tag) == "style")
    inline = " ".join(el.get("style", "") for el in root.iter())
    has_css = "@keyframes" in css and re.search(r"animation(-name)?\s*:", css + " " + inline)
    if smil or has_css:
        kinds = (["SMIL"] if smil else []) + (["CSS"] if has_css else [])
        return True, f"Animation found ({' + '.join(kinds)})"
    return False, "No animation: add <animate>/<animateTransform> or CSS @keyframes + animation"


# ---------- Check 5 (my own): key science terms are labelled ----------
def check_key_terms(root, key_terms: list[str]):
    text = all_text(root)
    missing = []
    for term in key_terms:
        # whole-word match so 'a' doesn't match inside 'hypotenuse'
        if not re.search(rf"(?<![a-z]){re.escape(term.lower())}(?![a-z])", text):
            missing.append(term)
    if missing:
        return False, f"Missing key term label(s): {', '.join(missing)}"
    return True, f"All key terms labelled: {', '.join(key_terms)}"


CHECK_NAMES = ["valid", "in_viewbox", "title_and_labels", "animation", "key_terms"]


def run_checks(svg: str, key_terms: list[str]) -> dict:
    """Run every check. If the SVG doesn't parse, the rest fail automatically."""
    ok, reason, root = check_valid(svg)
    results = {"valid": {"passed": ok, "reason": reason}}
    if root is None:
        for name in CHECK_NAMES[1:]:
            results[name] = {"passed": False, "reason": "Skipped: SVG did not parse"}
        return results
    for name, (passed, why) in [
        ("in_viewbox", check_in_viewbox(root)),
        ("title_and_labels", check_title_and_labels(root)),
        ("animation", check_animation(root)),
        ("key_terms", check_key_terms(root, key_terms)),
    ]:
        results[name] = {"passed": passed, "reason": why}
    return results


def all_passed(results: dict) -> bool:
    return all(r["passed"] for r in results.values())
