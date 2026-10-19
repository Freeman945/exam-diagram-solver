# exam-diagram-solver

中文 | [English](README_EN.md)

[![test](https://github.com/Freeman945/exam-diagram-solver/actions/workflows/test.yml/badge.svg)](https://github.com/Freeman945/exam-diagram-solver/actions)

DeepSeek Harness 插件。输入数学或物理题的照片，输出题目结构、按需生成的图，以及经过 SymPy 与量纲校验的解答。

模型负责识别和推理；图形的坐标与排版由程序生成。能形式化的结论交给程序复核，不能形式化的会标为跳过。

## 功能

- 识别：原图直接送入模型，产出 `ProblemSpec`（条件、问题、公式、图中对象与关系、不确定项、置信度）。
- 图形重建：从题图中提取点、线、圆、物体、元件、光线，以及共线、垂直、平行、等长、共圆等关系。
- 作图判断：按题型与题干规则决定是否需要图，区分辅助图与作答图，返回命中的规则。
- 绘制：几何、函数/坐标、受力、电路、光路、数据图，输出 SVG 与 PNG。
- 校验：方程回代、恒等式、导数、积分、数值比对、单位与量纲、图形的坐标关系。
- 评分：按正确性、步骤、表达、作图给出失分点，估分只作内部参考。
- 修正：验证或评分发现明确问题时重写答案，轮数有上限。

## 示例

输入 `examples/problems/geometry_proof.png`：

![几何证明题](examples/problems/geometry_proof.png)

调用：

```text
solve_exam_image(imagePaths=["<repo>/examples/problems/geometry_proof.png"])
```

返回的答案包含完整证明链，程序校验 14/14 通过，并生成这张图：

![自动生成的等腰三角形](examples/diagrams/geometry_triangle.png)

同一批示例中，一元二次方程被判定为不需要作图，物理受力题生成了受力图。输入与结果分别见 `examples/problems/` 与 `examples/diagrams/`。

## 安装

要求：

- DeepSeek Harness `0.2.1-rc.2`
- Node.js 20+
- Python 3.10+，需 SymPy；Matplotlib 仅用于 PNG 预览

不需要 API Key。模型调用走 Harness 的 `llm` 服务，使用当前 profile 已配置的模型，该模型需支持图片输入。

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
.venv/bin/pip install -r requirements.txt       # macOS / Linux
```

然后在 Harness 中安装：

```text
plugin_manager  action=install_bundle  target=<仓库绝对路径>
```

用 `exam_engine_status` 检查：`features.sympy` 与 `model.acceptsImages` 应为 true。插件按以下顺序探测 Python：配置 `pythonPath` → `EXAM_SOLVER_PYTHON` → `<repo>/.venv` → `python` → `python3` → `py`。

## 用法

直接上传照片后调用，自动取当前会话最新图片：

```text
solve_exam_image()
```

指定图片与答案风格（`concise` / `exam` / `teaching`）：

```text
solve_exam_image(imagePaths=["C:\\q\\physics.png"], subjectHint="physics", answerMode="teaching")
```

分阶段调用：

```text
exam_analyze_image → exam_create_diagram_spec → exam_validate_diagram → exam_render_diagram
→ exam_solve_problem → exam_validate_solution → exam_grade_answer → exam_render_answer
```

只画图：

```text
exam_render_diagram(diagram={
  "type": "geometry",
  "points": {"A": [0, 3], "B": [-2, 0], "C": [2, 0], "D": [0, 0]},
  "segments": [["A","B"], ["A","C"], ["B","C"], ["A","D"]],
  "marks": [{"type": "right_angle", "at": "D", "arms": ["A","B"]}]
})
```

完整工具列表见 [lib/tools.js](lib/tools.js)。

## 工作方式

```text
image
  → ProblemSpec
  → 作图判断
  → DiagramSpec → Schema 校验 → 几何关系校验 → SVG / PNG
  → AnswerSpec
  → ValidationReport（SymPy / 量纲 / 图形）
  → ExamReport →（有问题则修正，最多 2 轮）
  → 最终答案
```

Node 侧负责 Harness 集成、模型调用与流程编排；数值与符号计算在独立的 Python 进程中完成，两边通过 stdin/stdout 交换一个 JSON 文档，因此校验结果可以脱离插件复现：

```bash
echo '{"op":"validate_solution","payload":{...}}' | python -m exam_solver
```

数据格式定义在 `schemas/`，架构说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 支持的图

| 类型 | 内容 | 状态 |
|---|---|---|
| geometry | 点、线段、射线、圆、弧、多边形、直角/等长/平行标记、标签避让 | 稳定 |
| function / coordinate | SymPy 求零点与极值、渐近线拆分、坐标轴与刻度、关键点标注 | 稳定 |
| force | 物块、质点、斜面；mg/N/f/F 箭头；速度与加速度独立绘制 | 稳定 |
| circuit | 串联、并联、环状自动布局；电源、电阻、电表、开关、灯泡、电容、电感、变阻器 | 实验性 |
| optics | 法线、镜面、界面、透镜、光轴、焦点、光线 | 实验性 |
| chart | 折线、柱状、散点 | 实验性 |

图类型由 `DiagramSpec.type` 决定，模型只输出结构化描述。

## 校验范围

程序复核可以形式化的部分：方程回代、恒等式、导数、积分、数值结果、单位与量纲、数量级，以及图中的共线、垂直、平行、等长、共圆等关系。

证明的逻辑链不在程序校验范围内，评分环节只能做启发式检查。每条结果分为通过、失败、跳过；跳过会给出原因，不计为通过。

## 测试

```bash
python -m pytest tests/python -q      # 160
node scripts/run-node-tests.mjs       # 61
node scripts/smoke-engine.mjs         # 离线加载插件并探测 Python 桥
```

`benchmark/cases.jsonl` 有 34 道自编题（数学 20、物理 14，其中 19 道需要作图）。测试用与插件相同的代码复核每道题的期望值，作图判断另有 34 条规则用例。

端到端目前跑了 3 道题（代数、几何证明、受力分析），全部完成；全量跑批尚未进行，因此不公布准确率。过程数据见 [docs/BENCHMARK.md](docs/BENCHMARK.md)。

v0.1.0 的系统验收（9 个用例，含模糊、倾斜、裁切、空白图片）与缺陷清单见 [docs/ACCEPTANCE_TEST.md](docs/ACCEPTANCE_TEST.md)。

## 已知限制

- 不保证答案正确，校验只覆盖可形式化的部分。
- 手写、模糊、反光、裁切的图片可能识别失败。此时返回不确定项，不补条件。
- 立体几何不自动作图。
- 电路与光路为实验性。复杂电路建议显式给出节点坐标，折射定律尚未程序化校验。
- 自动修正循环已实现，但没有用故意出错的样本做端到端验证。
- 估分只是内部估计，不代表真实考试评分。

## 隐私

插件不复制、不缓存、不落盘原始题目图片，只在调用时读取并交给 Harness 的 attachment 服务。生成的图与运行摘要写入系统临时目录（`%TEMP%\exam-diagram-solver`，可用 `EXAM_SOLVER_OUTPUT_DIR` 修改）。默认不记录题干，日志只含阶段、耗时与校验状态。插件不读取任何密钥。

详见 [docs/PRIVACY.md](docs/PRIVACY.md)。

## 开发

```bash
python scripts/make_example_problems.py    # 重新生成示例题目图片
python scripts/make_example_diagrams.py    # 重新生成图库
```

依赖与许可证见 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。CI 在 push 与 PR 时运行 Python、Node 测试和插件加载冒烟，不需要密钥。

## License

MIT。示例题目与图片均为本仓库自编自绘。
