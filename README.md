# Science Diagram Maker

Asks Gemini to draw 5 animated GCSE science diagrams as SVG, checks each one in code,
retries once with the failure reasons, and shows them on a page where a reviewer can
approve or reject them.

**Live app:** https://science-diagram-maker-jf6k.onrender.com  
(Render free tier: the first load after ~15 min idle can take ~50 s while the server wakes up.)
**Model:** `gemini-3.5-flash-lite` (free tier)

## How to run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your key in .env (it is git-ignored)
python generate.py            # Part A: generates all 5 -> results.json
python generate.py 3          # regenerate just one concept
uvicorn app:app --reload      # Part B: open http://localhost:8000
```

## How it works

| File | What it does |
|---|---|
| `concepts.py` | The 5 concepts and the key terms each diagram must label |
| `checks.py` | The 5 code checks; each returns pass/fail + a reason |
| `pipeline.py` | Calls Gemini, backs off on 429/503 (3 attempts), runs checks, retries once with the reasons, computes cost |
| `generate.py` | CLI that runs the pipeline for all concepts and writes `results.json` |
| `app.py` | FastAPI: serves the page, `GET /api/results`, `POST /api/generate/{id}` |
| `static/index.html` | The table, Approve/Reject + note, Generate button |

### Checks
1. **Valid**: parses as XML and the root is `<svg>`.
2. **Inside viewBox**: reads coordinates of rect, circle, ellipse, line, text, polygon, polyline and absolute paths, applies every `transform` (translate, rotate, scale, matrix, skew, including nested groups) and fails if any resulting point is outside the viewBox (1 unit tolerance).
3. **Title + 3 labels**: a non-empty `<title>` and at least 3 non-empty `<text>` elements.
4. **Animation**: SMIL (`animate`, `animateTransform`, `animateMotion`, `set`) or CSS `@keyframes` used by an `animation` property.
5. **Key terms (my own check)**: every key science term for the concept (e.g. *hypotenuse, radius, chlorophyll*) appears as a label. A diagram can pass checks 1–4 and still teach nothing, so this checks the content.
6. **No label overlap (my own, added after reviewing)**: estimates each `<text>` box from font-size (attribute, inline style, or CSS class rule), text length and `text-anchor`, applies transforms, and fails if two labels share more than 15% of the smaller box. I added it after seeing the series circuit's "cell" label printed on top of its subtitle while every other check passed. It is an estimate: glyph width is taken as 0.55 × font-size.

**Known limits (honest):** the viewBox check skips paths with relative or arc commands, ignores the width of text (only the anchor point is checked), and ignores CSS animation movement (only the resting position is checked). It can miss overflow; it shouldn't give false failures.

**Why transforms matter:** the first version skipped anything inside a `transform`. Gemini drew the Pythagoras c² square inside `rotate(-36.87)`, which is the wrong sign (the hypotenuse is at +36.87°), so the square pointed off the top of the canvas to y = -60. It passed every check but looked broken on the page. After adding transform maths, the check caught it, and the retry produced a correct diagram.

### Cost
The free tier costs $0. `cost_usd` is an **estimate at Gemini's paid list price**
(`PRICE_PER_M_INPUT` / `PRICE_PER_M_OUTPUT` in `pipeline.py`), summed over every attempt including retries.

### Where Approve/Reject is saved
**Browser localStorage.** TODO: write your reasoning, e.g. the free Render server's disk
is wiped on every restart/deploy, so a file on the server would lose decisions; a database
is extra setup for a single-reviewer demo. Trade-off: decisions are per-browser, not shared
between reviewers.

## Results

| Concept | Pass/Fail (checks) | Model | Est. cost (USD) | Check retries | API retries (429/503/504) |
|---|---|---|---|---|---|
| Pythagoras' theorem | ✅ Pass (6/6) | gemini-3.5-flash | $0.005461 | 1 | 4 |
| Parts of a circle | ✅ Pass (6/6) | gemini-3.5-flash | $0.004801 | 0 | 3 |
| Series circuit | ✅ Pass (6/6) | gemini-3.5-flash | $0.005621 | 0 | 4 |
| Photosynthesis | ✅ Pass (6/6) | gemini-3.5-flash-lite | $0.000868 | 0 | 2 |
| States of matter | ✅ Pass (6/6) | gemini-3.5-flash | $0.009440 | 0 | 3 |
| **Total** | | | **$0.026191** | | |

## What failed and how I fixed it
TODO: keep real notes as you go.

## With one more day
TODO

## AI tools used
TODO: be specific (e.g. Claude Code to scaffold the project and checks; what you changed yourself).
