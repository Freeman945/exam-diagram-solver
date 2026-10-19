# exam-diagram-solver

> Photograph a math or physics problem; get a diagram-backed, programmatically verified, exam-style solution.

A [DeepSeek Harness](https://github.com/deepseek-ai) Host plugin. It is not a
"image → OCR → chat" wrapper: it runs an explicit pipeline with independent
verification stages.

```
image
  → multimodal ProblemSpec (the original image is never discarded)
  → rule-based diagram decision (auxiliary vs. answer figure)
  → DiagramSpec (the model decides WHAT to draw)
  → strict schema + geometric-relation validation
  → programmatic SVG/PNG rendering (the program decides HOW to draw it)
  → AnswerSpec with machine-checkable claims
  → SymPy / unit / dimension / magnitude validation
  → simulated marking → targeted revision (bounded) → final answer
```

## Features

- Native multimodal recognition with structured `ProblemSpec` output (conditions, questions, equations, visual objects/relations, uncertainties, confidence).
- Reconstruction of an existing figure into machine-checkable relations (collinear, perpendicular, parallel, equal length, point-on-segment/circle, concyclic, midpoint, right angle).
- Explainable diagram decision; the plugin never draws just to show off.
- Strict Diagram DSL (6 variants, `additionalProperties: false`) with a dependency-free validator.
- Deterministic renderers for geometry, functions/coordinates, force diagrams, circuits, optics and charts.
- Independent validation: equation substitution, identities, derivatives, integrals, numeric comparison, physical units/dimensions/orders of magnitude, diagram relations.
- Simulated marking with a transparent rubric plus optional model examiner; scores are explicitly an **internal estimate**.
- Automatic revision with a hard round limit; honest `status: partial` when something cannot be resolved.
- Three answer modes: `concise`, `exam` (default), `teaching`.
- Zero-config main entry: call `solve_exam_image` right after attaching a photo.

## Requirements

- DeepSeek Harness `0.2.1-rc.2` (verified; uses only public Host services: `tools`, `llm`, `attachments`, `sessions`, `agents`).
- Node.js >= 20 (verified on 24.16.0).
- Python >= 3.10 with SymPy; Matplotlib optional (PNG preview only).
- No API key: model calls use the Harness `llm` service and the model already configured in the profile. The model must accept image input.

## Install

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # Windows
.venv/bin/pip install -r requirements.txt         # macOS/Linux
```

Then, from the Harness:

```
plugin_manager  action=install_bundle  target=<absolute path to this repo>
```

Verify with `exam_engine_status` (expects `features.sympy = true`,
`model.acceptsImages = true`).

## Usage

```
solve_exam_image()                                         # uses the latest image in the chat
solve_exam_image(imagePaths=["C:\\q\\physics.png"], subjectHint="physics")
exam_analyze_image(...) → exam_create_diagram_spec(...) → exam_render_diagram(...)
                        → exam_solve_problem(...) → exam_validate_solution(...) → exam_grade_answer(...)
exam_render_diagram(diagram={...})                          # draw any valid DiagramSpec
```

Tool names: `solve_exam_image`, `exam_analyze_image`, `exam_reconstruct_diagram`,
`exam_decide_diagram`, `exam_create_diagram_spec`, `exam_validate_diagram`,
`exam_render_diagram`, `exam_solve_problem`, `exam_validate_solution`,
`exam_grade_answer`, `exam_render_answer`, `exam_engine_status`.

## Supported diagrams

| Type | Status | Notes |
|---|---|---|
| geometry | stable | points, segments, rays, circles, arcs, polygons, marks, labels, auto-fit |
| function / coordinate | stable | SymPy roots/extrema, asymptote splitting, axes, key points |
| force | stable | block/dot/incline, mg/N/f/F, velocity/acceleration anchors |
| circuit | experimental | series/parallel/loop auto-layout; explicit `nodes` recommended for complex topologies |
| optics | experimental | mirrors, lenses, rays, normals, focal points; Snell's law not yet verified |
| chart | experimental | line/bar/scatter |

## Validation scope

Programs verify what can be formalised: substitutions, identities, derivatives,
integrals, numerics, units/dimensions, magnitudes, and coordinate-level diagram
relations. Proof *logic* cannot be fully machine-verified; the examiner applies
heuristics. Skips are reported as skips, never as passes.

## Tests

```
python -m pytest tests/python -q        # 160 tests
node scripts/run-node-tests.mjs         # 61 tests
node scripts/smoke-engine.mjs           # offline plugin wiring smoke test
```

The benchmark contains 34 self-authored cases (20 math, 14 physics; 19 need a
diagram) whose expected answers are re-verified by the same SymPy/unit code the
plugin uses. Three representative cases were run end-to-end for real (algebra,
geometry proof, force problem: 8/8, 14/14 and 9/9 checks passed). The full
34-case end-to-end sweep has **not** been run yet; no unmeasured numbers are
published. See [docs/BENCHMARK.md](docs/BENCHMARK.md).

## Privacy

The plugin never copies or stores the source image; it reads it at call time and
hands it to the Harness attachment service (the same store used by chat
uploads). Generated diagrams and run summaries go to the OS temp directory.
Problem text is not logged unless `logProblemText=true`.

## Limitations

- Correctness is not guaranteed; "near full marks" is an objective, not a promise.
- Handwriting, blur, glare, cropped formulas can defeat recognition; the plugin
  reports uncertainty instead of inventing conditions.
- Solid geometry is deliberately not auto-drawn.
- Circuit/optics renderers are experimental.
- Examiner scores are internal estimates only.

## License

MIT. See [LICENSE](LICENSE) and [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).
All example images were authored for this repository.
