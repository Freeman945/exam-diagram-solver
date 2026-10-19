# exam-diagram-solver

[中文](README.md) | English

[![test](https://github.com/Freeman945/exam-diagram-solver/actions/workflows/test.yml/badge.svg)](https://github.com/Freeman945/exam-diagram-solver/actions)

A DeepSeek Harness plugin. It takes a photo of a math or physics problem and returns a structured problem model, a diagram when one is needed, and an answer checked with SymPy and dimensional analysis.

The model recognizes the problem and does the reasoning. Coordinates and layout are computed by code. Claims that can be formalised are re-checked; the rest are reported as skipped.

## Features

- Recognition: the original image goes to the model, which produces a `ProblemSpec` (conditions, questions, equations, visual objects and relations, uncertainties, confidence).
- Diagram reconstruction: points, segments, circles, objects, components and rays, plus collinear / perpendicular / parallel / equal-length / concyclic relations.
- Diagram decision: rule based, returns whether a figure is needed and whether it belongs in the answer.
- Rendering: geometry, functions/coordinates, force, circuit, optics and charts, as SVG and PNG.
- Validation: equation substitution, identities, derivatives, integrals, numeric comparison, units and dimensions, diagram relations.
- Marking: lost points for correctness, steps, expression and diagram; the score is an internal estimate.
- Revision: rewrites the answer when validation or marking finds a concrete problem, with a fixed round limit.

## Example

Input `examples/problems/geometry_proof.png`:

![geometry problem](examples/problems/geometry_proof.png)

```text
solve_exam_image(imagePaths=["<repo>/examples/problems/geometry_proof.png"])
```

The answer contains a full proof, passes 14/14 programmatic checks, and produces:

![generated isosceles triangle](examples/diagrams/geometry_triangle.png)

In the same sample set, a quadratic equation was judged not to need a diagram, and a force problem produced a free-body diagram. See `examples/problems/` and `examples/diagrams/`.

## Requirements

- DeepSeek Harness `0.2.1-rc.2`
- Node.js 20+
- Python 3.10+ with SymPy; Matplotlib is optional and only used for the PNG preview

No API key. Model calls go through the Harness `llm` service and use the model configured in the current profile, which must accept image input.

## Install

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
.venv/bin/pip install -r requirements.txt       # macOS / Linux
```

Then, from the Harness:

```text
plugin_manager  action=install_bundle  target=<absolute path to this repo>
```

`exam_engine_status` should report `features.sympy = true` and `model.acceptsImages = true`. Python is discovered in this order: config `pythonPath`, `EXAM_SOLVER_PYTHON`, `<repo>/.venv`, `python`, `python3`, `py`.

## Usage

After attaching a photo:

```text
solve_exam_image()
```

With explicit paths and an answer style (`concise`, `exam`, `teaching`):

```text
solve_exam_image(imagePaths=["C:\\q\\physics.png"], subjectHint="physics", answerMode="teaching")
```

Stage by stage:

```text
exam_analyze_image → exam_create_diagram_spec → exam_validate_diagram → exam_render_diagram
→ exam_solve_problem → exam_validate_solution → exam_grade_answer → exam_render_answer
```

Draw a diagram directly:

```text
exam_render_diagram(diagram={
  "type": "geometry",
  "points": {"A": [0, 3], "B": [-2, 0], "C": [2, 0], "D": [0, 0]},
  "segments": [["A","B"], ["A","C"], ["B","C"], ["A","D"]],
  "marks": [{"type": "right_angle", "at": "D", "arms": ["A","B"]}]
})
```

The full tool list is in [lib/tools.js](lib/tools.js).

## How it works

```text
image
  → ProblemSpec
  → diagram decision
  → DiagramSpec → schema validation → geometric-relation validation → SVG / PNG
  → AnswerSpec
  → ValidationReport (SymPy / units / geometry)
  → ExamReport → revision when needed (max 2 rounds)
  → final answer
```

The Node side handles Harness integration, model calls and orchestration. All numeric and symbolic work runs in a separate Python process; the two exchange one JSON document over stdin/stdout, so validation results can be reproduced outside the plugin:

```bash
echo '{"op":"validate_solution","payload":{...}}' | python -m exam_solver
```

Data formats are defined in `schemas/`; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Supported diagrams

| Type | Content | Status |
|---|---|---|
| geometry | points, segments, rays, circles, arcs, polygons, right-angle / equal-length / parallel marks, label placement | stable |
| function / coordinate | SymPy roots and extrema, asymptote splitting, axes and ticks, key points | stable |
| force | block, particle, incline; mg/N/f/F arrows; velocity and acceleration drawn separately | stable |
| circuit | series, parallel and loop auto-layout; battery, resistor, meters, switch, lamp, capacitor, inductor, rheostat | experimental |
| optics | normals, mirrors, interfaces, lenses, axis, focal points, rays | experimental |
| chart | line, bar, scatter | experimental |

## What is validated

Programs re-check what can be formalised: substitution into equations, identities, derivatives, integrals, numeric results, units and dimensions, orders of magnitude, and the coordinate-level relations of a diagram.

The logic of a proof is not machine-checked; the marking step applies heuristics only. Every result is passed, failed or skipped, and a skip states its reason rather than counting as a pass.

## Tests

```bash
python -m pytest tests/python -q      # 160
node scripts/run-node-tests.mjs       # 61
node scripts/smoke-engine.mjs         # load the plugin with a stub context
```

`benchmark/cases.jsonl` contains 34 self-authored cases (20 math, 14 physics; 19 require a diagram). The tests re-check every expected answer with the same SymPy and unit code the plugin uses, and the diagram-decision labels have their own 34 rule cases.

Three cases have been run end to end (algebra, geometry proof, force problem). The full sweep has not been run, so no accuracy figures are published. See [docs/BENCHMARK.md](docs/BENCHMARK.md).

The v0.1.0 acceptance run (9 cases, including blurred, rotated, cropped and blank images) and its defect list are in [docs/ACCEPTANCE_TEST.md](docs/ACCEPTANCE_TEST.md).

## Limitations

- Correctness is not guaranteed; validation covers only what can be formalised.
- Handwriting, blur, glare and cropped formulas can defeat recognition. The plugin reports uncertainty instead of inventing conditions.
- Solid geometry is not drawn automatically.
- Circuit and optics renderers are experimental. Complex circuits should provide explicit node coordinates, and Snell's law is not yet checked programmatically.
- The revision loop is implemented but has not been tested end to end with a deliberately wrong answer.
- Scores from the marking step are internal estimates, not exam marks.

## Privacy

The plugin does not copy, cache or persist the source image; it reads it at call time and passes it to the Harness attachment service. Generated diagrams and run summaries go to the system temp directory (`%TEMP%\exam-diagram-solver`, override with `EXAM_SOLVER_OUTPUT_DIR`). Problem text is not logged by default. The plugin does not read any credentials.

See [docs/PRIVACY.md](docs/PRIVACY.md).

## Development

```bash
python scripts/make_example_problems.py
python scripts/make_example_diagrams.py
```

Dependency and license notes are in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md). CI runs the Python and Node suites plus a plugin-loading smoke test on push and pull request, without secrets.

## License

MIT. All example problems and images were authored for this repository.
