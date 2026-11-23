"""Code checks run on every SVG before we accept it.

Each check returns (passed: bool, reason: str). The reason is shown on the
web page and sent back to the model on a retry, so it should say exactly what
is wrong.
"""
import math
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


# --- transforms: a 2D affine matrix (a, b, c, d, e, f) maps (x, y) to
#     (a*x + c*y + e,  b*x + d*y + f), the same as SVG's matrix().
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def mat_mul(m, n):
    """Matrix for 'apply n first, then m'."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return (a * A + c * B, b * A + d * B,
            a * C + c * D, b * C + d * D,
            a * E + c * F + e, b * E + d * F + f)


def apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def parse_transform(s: str):
    """Turn 'translate(210,150) rotate(-36.87)' into one matrix."""
    m = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s or ""):
        v = nums(args)
        if name == "translate" and v:
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale" and v:
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "rotate" and v:
            r = math.radians(v[0])
            t = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            if len(v) == 3:  # rotate(angle, cx, cy) = translate, rotate, translate back
                t = mat_mul(mat_mul((1, 0, 0, 1, v[1], v[2]), t), (1, 0, 0, 1, -v[1], -v[2]))
        elif name == "matrix" and len(v) == 6:
            t = tuple(v)
        elif name == "skewX" and v:
            t = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif name == "skewY" and v:
            t = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        m = mat_mul(m, t)  # SVG applies the list right-to-left
    return m


def corners(pts):
    """For boxes (rect/circle/ellipse) use all 4 corners so rotation is handled."""
    if len(pts) == 2:
        (x1, y1), (x2, y2) = pts
        return [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
    return pts


SKIP = ("defs", "clipPath", "mask", "marker", "pattern", "symbol")


def check_in_viewbox(root):
    vb = nums(root.get("viewBox", ""))
    if len(vb) != 4:
        return False, "Missing or malformed viewBox attribute"
    minx, miny, w, h = vb
    maxx, maxy = minx + w, miny + h
    problems = []

    def walk(el, m):
        if local(el.tag) in SKIP:
            return
        # combine this element's transform with all its parents' transforms
        m = mat_mul(m, parse_transform(el.get("transform", "")))
        pts = points_of(el)
        if local(el.tag) in ("rect", "circle", "ellipse"):
            pts = corners(pts)
        for x, y in pts:
            X, Y = apply(m, x, y)
            if not (minx - TOLERANCE <= X <= maxx + TOLERANCE and
                    miny - TOLERANCE <= Y <= maxy + TOLERANCE):
                problems.append(f"<{local(el.tag)}> has point ({X:.0f}, {Y:.0f})")
                break
        for child in el:
            walk(child, m)

    walk(root, IDENTITY)
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


# ---------- Check 6 (my own): text labels don't overlap each other ----------
CHAR_WIDTH = 0.55     # average glyph width as a fraction of font-size (sans-serif)
OVERLAP_LIMIT = 0.15  # fail if two labels share more than 15% of the smaller box


def css_rules(root) -> dict:
    """Very small CSS reader: {'.label': {'font-size': '14px', ...}, 'text': {...}}"""
    css = " ".join("".join(el.itertext()) for el in root.iter() if local(el.tag) == "style")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # drop comments
    rules = {}
    for selectors, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        props = dict(
            (k.strip().lower(), v.strip())
            for k, v in (p.split(":", 1) for p in body.split(";") if ":" in p)
        )
        for sel in selectors.split(","):
            rules.setdefault(sel.strip(), {}).update(props)
    return rules


def text_style(el, rules, inherited: dict) -> dict:
    """font-size and text-anchor from: parent <g>, CSS (tag, then class), attribute, style=."""
    style = dict(inherited)
    style.update(rules.get(local(el.tag), {}))
    for cls in el.get("class", "").split():
        style.update(rules.get("." + cls, {}))
    for k in ("font-size", "text-anchor"):
        if el.get(k):
            style[k] = el.get(k)
    for part in el.get("style", "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            style[k.strip().lower()] = v.strip()
    return {k: style[k] for k in ("font-size", "text-anchor") if k in style}


def text_boxes(root):
    """Estimated (x1, y1, x2, y2, label) for every <text>, in viewBox coordinates."""
    rules = css_rules(root)
    boxes = []

    def walk(el, m, inherited):
        if local(el.tag) in SKIP:
            return
        m = mat_mul(m, parse_transform(el.get("transform", "")))
        style = text_style(el, rules, inherited)
        if local(el.tag) == "text":
            label = " ".join("".join(el.itertext()).split())
            if label:
                size = (nums(style.get("font-size", "16")) or [16])[0]
                x = (nums(el.get("x", "0")) or [0])[0]
                y = (nums(el.get("y", "0")) or [0])[0]
                w = len(label) * size * CHAR_WIDTH
                anchor = style.get("text-anchor", "start")
                x1 = x - w / 2 if anchor == "middle" else x - w if anchor == "end" else x
                # y is the baseline; letters sit roughly 0.8em above it
                pts = [apply(m, px, py) for px, py in
                       [(x1, y - size * 0.8), (x1 + w, y - size * 0.8), (x1, y + size * 0.2), (x1 + w, y + size * 0.2)]]
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                boxes.append((min(xs), min(ys), max(xs), max(ys), label))
            return  # don't descend into tspans separately
        for child in el:
            walk(child, m, style)

    walk(root, IDENTITY, {})
    return boxes


def check_no_overlap(root):
    boxes = text_boxes(root)
    clashes = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ix = min(a[2], b[2]) - max(a[0], b[0])
            iy = min(a[3], b[3]) - max(a[1], b[1])
            if ix <= 0 or iy <= 0:
                continue
            smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
            if smaller and ix * iy / smaller > OVERLAP_LIMIT:
                clashes.append(f"'{a[4][:30]}' overlaps '{b[4][:30]}'")
    if clashes:
        return False, "Text labels overlap: " + "; ".join(clashes[:4])
    return True, f"No overlapping labels ({len(boxes)} checked)"


CHECK_NAMES = ["valid", "in_viewbox", "title_and_labels", "animation", "key_terms", "no_overlap"]


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
        ("no_overlap", check_no_overlap(root)),
    ]:
        results[name] = {"passed": passed, "reason": why}
    return results


def all_passed(results: dict) -> bool:
    return all(r["passed"] for r in results.values())
