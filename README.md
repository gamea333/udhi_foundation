# Science Diagram Maker

Asks Gemini to draw 5 animated GCSE science diagrams as SVG, checks each one in code,
retries once with the failure reasons, and shows them on a page where a reviewer can
approve or reject them.

**Live app:** TODO
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
2. **Inside viewBox**: reads coordinates of rect, circle, ellipse, line, text, polygon, polyline and absolute paths, and fails if any point is outside the viewBox (1 unit tolerance).
3. **Title + 3 labels**: a non-empty `<title>` and at least 3 non-empty `<text>` elements.
4. **Animation**: SMIL (`animate`, `animateTransform`, `animateMotion`, `set`) or CSS `@keyframes` used by an `animation` property.
5. **Key terms (my own check)**: every key science term for the concept (e.g. *hypotenuse, radius, chlorophyll*) appears as a label. A diagram can pass checks 1–4 and still teach nothing, so this checks the content.

**Known limits (honest):** the viewBox check ignores elements under a `transform`, relative or arc path commands, and the width of text (it only checks the text anchor point). It can miss overflow; it shouldn't give false failures.

### Cost
The free tier costs $0. `cost_usd` is an **estimate at Gemini's paid list price**
(`PRICE_PER_M_INPUT` / `PRICE_PER_M_OUTPUT` in `pipeline.py`), summed over every attempt including retries.

### Where Approve/Reject is saved
**Browser localStorage.** TODO: write your reasoning, e.g. the free Render server's disk
is wiped on every restart/deploy, so a file on the server would lose decisions; a database
is extra setup for a single-reviewer demo. Trade-off: decisions are per-browser, not shared
between reviewers.

## Results

TODO: fill in after running `generate.py`.

| Concept | Pass/Fail | Cost (USD) | Retries |
|---|---|---|---|
| Pythagoras' theorem | | | |
| Parts of a circle | | | |
| Series circuit | | | |
| Photosynthesis | | | |
| States of matter | | | |

## What failed and how I fixed it
TODO: keep real notes as you go.

## With one more day
TODO

## AI tools used
TODO: be specific (e.g. Claude Code to scaffold the project and checks; what you changed yourself).
