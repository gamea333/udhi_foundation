# Science Diagram Maker

Asks Gemini to draw 5 animated GCSE science diagrams as SVG, checks each one in code,
retries once with the failure reasons, and shows them on a page where a reviewer can
approve or reject them.

**Live app:** https://science-diagram-maker-jf6k.onrender.com
(Render free tier: the first load after ~15 min idle can take ~50 s while the server wakes up.)

**Models:** `gemini-3.5-flash-lite` first, falling back to `gemini-3.5-flash` when Flash-Lite
is overloaded (both free tier). See "What failed" for why.

## Live link

🔗 **https://science-diagram-maker-jf6k.onrender.com**

- Opens in any browser, nothing to install.
- The 5 saved diagrams load straight away, with no API call.
- **Generate** runs the pipeline live for one concept (takes 1–3 minutes because of Gemini free-tier limits).
- Hosted on Render's free tier: if nobody has opened it for ~15 minutes, the first load can take ~50 seconds while the server wakes up.

## How to run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your key in .env (it is git-ignored)
python generate.py            # Part A: generates all 5 -> results.json
python generate.py 3          # regenerate just one concept
python generate.py --recheck  # re-run the checks on saved SVGs (no API call)
uvicorn app:app --reload      # Part B: open http://localhost:8000
```

To deploy: `render.yaml` describes the service. On Render, choose New → Blueprint, pick the
repo, and paste `GEMINI_API_KEY` when asked. The key exists only as an environment variable
on the host and in my local `.env`. It is never in the code or in git.

## How it works

| File | What it does |
|---|---|
| `concepts.py` | The 5 concepts and the key terms each diagram must label |
| `checks.py` | The 6 code checks; each returns pass/fail + a reason |
| `pipeline.py` | Calls Gemini, backs off on 429/503/504 (3 attempts per model, then falls back to the next model), runs the checks, retries once with the reasons, computes cost |
| `generate.py` | CLI that runs the pipeline and writes `results.json`; `--recheck` re-runs checks only |
| `app.py` | FastAPI: serves the page, `GET /api/results` (saved file, no model call), `POST /api/generate/{id}` (live run) |
| `static/index.html` | The table, Approve/Reject + note, Generate button, enlarge view, summary bar |

**Flow for one concept:** prompt → Gemini → pull out the `<svg>` → run all checks → if any
fail, send the model the exact failure reasons plus its previous SVG and ask for a fix (once)
→ run checks again → save the result with tokens, cost, retries and every check's reason.

### Checks
1. **Valid**: parses as XML and the root is `<svg>`.
2. **Inside viewBox**: reads coordinates of rect, circle, ellipse, line, text, polygon, polyline and absolute paths, applies every `transform` (translate, rotate, scale, matrix, skew, including nested groups) and fails if any resulting point is outside the viewBox (1 unit tolerance).
3. **Title + 3 labels**: a non-empty `<title>` and at least 3 non-empty `<text>` elements.
4. **Animation**: SMIL (`animate`, `animateTransform`, `animateMotion`, `set`) or CSS `@keyframes` used by an `animation` property.
5. **Key terms (my own check)**: every key science term for the concept (e.g. *hypotenuse, radius, chlorophyll*) appears as a label (whole-word match). A diagram can pass checks 1–4 and still teach nothing, so this checks the content.
6. **No label overlap (my own, added after reviewing)**: estimates each `<text>` box from font-size (attribute, inline style, or CSS rule), text length and `text-anchor`, applies transforms, and fails if two labels share more than 15% of the smaller box.

**Known limits:**
- The viewBox check skips paths with relative or arc commands, checks only a text label's anchor point (not its width), and checks shapes at rest, not where a CSS animation moves them. It can miss some overflow, but it shouldn't give false failures.
- The overlap check estimates glyph width as 0.55 × font-size, and it only compares text with text, not text with lines or shapes.
- No check can tell whether the science is *right*. For example, a check can't confirm that the a² square really sits on side a. That is what the human Approve/Reject step is for.

### Cost
The free tier costs $0. `cost_usd` is an **estimate at Gemini's paid standard-tier price**
(`PRICES` in `pipeline.py`), summed over every call including retries. Thinking tokens are
counted as output because Google bills them that way. The rates I used (Nov 2026):

| Model | Input / 1M | Output / 1M | Source |
|---|---|---|---|
| gemini-3.5-flash-lite | $0.30 | $2.50 | Several pricing write-ups agree |
| gemini-3.5-flash | $1.50 | $9.00 | Third-party write-ups only; I could not confirm it on Google's page |

The saved results were first costed with placeholder prices that were too low. I recomputed
them from the logged token counts after looking up real prices. For Pythagoras, the first
(failed) attempt came from Flash-Lite and the retry from Flash, but all its tokens are
priced at the Flash rate, so that row is slightly overstated.

### Where Approve/Reject is saved
**Browser `localStorage`**, keyed by concept id (`review-1` … `review-5`), storing the
decision, the note and a timestamp.

Why: the app is hosted on Render's free tier, whose disk is wiped on every restart and
redeploy, so a JSON file on the server would silently lose decisions. A real database
(Supabase, Postgres) is extra setup and another secret to manage for a single-reviewer demo.
localStorage survives page refreshes and browser restarts with zero infrastructure.

Trade-off: decisions are per browser. A second reviewer, or the same reviewer on another
device, won't see them, and clearing site data erases them. For a real team I would move
this to a database (see "With one more day").

## Results

| Concept | Pass/Fail (checks) | Model | Est. cost (USD) | Check retries | API retries (429/503/504) |
|---|---|---|---|---|---|
| Pythagoras' theorem | ✅ Pass (6/6) | gemini-3.5-flash | $0.031952 | 1 | 4 |
| Parts of a circle | ✅ Pass (6/6) | gemini-3.5-flash | $0.017399 | 0 | 3 |
| Series circuit | ✅ Pass (6/6) | gemini-3.5-flash | $0.020364 | 0 | 4 |
| Photosynthesis | ✅ Pass (6/6) | gemini-3.5-flash-lite | $0.005338 | 0 | 2 |
| States of matter | ✅ Pass (6/6) | gemini-3.5-flash | $0.034098 | 0 | 3 |
| **Total** | | | **$0.109151** | **1** | **16** |

"Check retries" is the one allowed retry after a failed check. "API retries" counts
429/503/504 waits, including the switch from Flash-Lite to Flash. The raw run logs are in
`generate_log*.txt`. Their cost figures use the old placeholder prices.

## What failed and how I fixed it

In the order I hit them:

1. **Flash-Lite returned 503 on every call.** The error was Google's own: *"This model is currently experiencing high demand."* A tiny "say hi" prompt worked, so the key was fine; the model was just overloaded. **Fix:** after 3 backoff attempts (5 s, 10 s) on one model, the pipeline falls back to `gemini-3.5-flash`. The `model` field records which model actually produced each SVG. Photosynthesis was the only diagram Flash-Lite managed to serve.

2. **Flash took 212 seconds for one diagram.** That is too slow for a live Generate button. It was spending most of the time "thinking". **Fix:** `thinking_level="low"` brought it down to about 64 s, and the diagrams still pass. I also set a 180 s request timeout so a hung call can't block forever.

3. **Thinking tokens weren't in the cost.** Google bills them as output tokens. **Fix:** cost now uses `candidates_token_count + thoughts_token_count`.

4. **Pythagoras: invalid XML.** In the first full run, attempt 1 drew a square off the bottom edge (y = 420 in a 400-high box). The viewBox check caught it, and the retry fixed the square but wrote a CSS comment `/* Animated Squares & Lines */`. A bare `&` is illegal in XML, so the whole SVG failed to parse. Browsers might render it anyway, but a strict parser later in a video pipeline would not. **Fix:** the prompt now requires strict XML (`&amp;`, `<![CDATA[ ]]>` around CSS).

5. **Pythagoras: a check that said ✅ was wrong.** On screen, the c² square was tilted the wrong way and cut off at the top, yet every check passed. The SVG put the square inside `rotate(-36.87)`, but the hypotenuse slopes at **+36.87°**. The sign error pushed a corner to y = −60. My viewBox check skipped anything inside a `transform`, so it never looked at that square. **Fix:** the check now parses transforms into a matrix and applies them, including nested groups. It then reported exactly (240, −60), the corner I worked out by hand. On the rerun, the check caught Gemini's first attempt going off-canvas in 3 places, and the retry produced a passing diagram.

6. **Series circuit: overlapping labels.** The "cell" label was printed on top of the subtitle, and all 5 checks passed. **Fix:** I added check 6 (label overlap). Run against the saved results, it flagged only that diagram. I regenerated it and it now passes. I also added `generate.py --recheck`, so a new check can be applied to saved SVGs without spending API calls.

7. **A 504 crashed the run.** Google returned *"Deadline expired"*, which I wasn't retrying. **Fix:** 504 is now retried like 429/503. On the next run it hit a 504 and recovered.

**Lesson:** passing checks is not the same as looking right. Two of the bugs above (5 and 6) were found by looking at the page, not by the code. Each time, I turned what I saw into a new or stronger check, so the code would catch it next time.

## With one more day

- **Shared review storage:** move Approve/Reject to a small database (e.g. Supabase or SQLite on a persistent disk), so decisions are shared between reviewers, with who reviewed and when.
- **Render-based checks:** rasterise each SVG in a headless browser and check the real bounding boxes of every element, including text width and arc paths. This would replace my coordinate estimates, and it could also take frames over time to confirm the animation actually moves something visible.
- **Science-correctness checks per concept:** for example, for Pythagoras, check that the three squares' side lengths match the triangle's sides, and that the circuit has exactly one closed loop.
- **Save live Generate results:** today a live Generate result shows on the page but isn't persisted. I would store versions with history, so a reviewer can compare attempts.
- **Smarter rate-limit handling:** honour the `retryDelay` that Gemini returns in 429 responses instead of a fixed backoff, and stream progress to the page instead of a long spinner.
- **Tests:** unit tests for each check, using small hand-written SVGs that should pass and fail.

## AI tools used

- **Claude Code (Anthropic):** I used it as a pair programmer throughout. It scaffolded the project structure, wrote the first versions of the checks, the pipeline, the FastAPI server and the page, and helped me debug the issues above (reading the raw 503/504 errors, finding the wrong rotation sign in the Pythagoras SVG). It also helped with the Render deployment steps and drafting this README.
- **What I did myself:** reviewed the diagrams on the live page and spotted the cut-off square and overlapping labels that the checks had missed, decided which fixes to make, ran the generations, deployed on Render, and tested the page. I have read through all the code and can explain each part.
