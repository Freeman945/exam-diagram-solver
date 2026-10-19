# Benchmark 与实测结果

> 本文件只记录**实际运行**得到的数据。未运行的指标标记为「未实测」，不估计、不补全。

## 1. 数据集

`benchmark/cases.jsonl`，每行一道题：

| 维度 | 数量 |
|---|---|
| 总题数 | 34 |
| 数学 | 20 |
| 物理 | 14 |
| 需要作图 | 19 |
| 不需要作图 | 15 |

题型覆盖：方程/不等式、三角、函数、导数与积分、平面几何证明、解析几何、概率统计、运动学、动力学、功与能、动量、电路、光学、波动。

图类型覆盖：`geometry`（10）、`function`/`coordinate`（7）、`force`（7）、`circuit`（2）、`optics`（1）。

### 期望值如何被验证

每道题都带 `checks`（可机器验证的断言）。`tests/python/test_benchmark.py` 使用**与插件完全相同的 SymPy / 量纲代码**逐条复核：

- 方程的根必须回代为零；
- 恒等式、导数、积分必须符号成立；
- 数值结果必须在给定容差内；
- 物理量的单位/量纲必须匹配；
- 每条声明必须真的被执行（不允许被静默跳过）。

`tests/node/benchmark.test.mjs` 复核 34 道题的「是否需要作图 / 图类型」标签与规则引擎一致。

因此：**数据集本身的正确性是被测试的**（160 个 Python 测试中包含对 34 题的逐条复核），而不是仅凭人工声称。

## 2. 端到端实测（pilot）

运行环境：DeepSeek Harness `0.2.1-rc.2`，模型 `deepseek-flash`（image + reasoning），Python 3.12.14 + SymPy 1.14.0，Windows 11。

| # | 题目 | 学科/题型 | 作图 | 耗时 | 模型调用 | 程序校验 | 内部估分 | 结果 |
|---|---|---|---|---|---|---|---|---|
| 1 | `examples/problems/math_quadratic.png` | 数学 · 解方程 | 不需要（规则判定） | 14.1 s | 2 | 8/8 | 12/12 | ok |
| 2 | `examples/problems/geometry_proof.png` | 数学 · 几何证明 | 几何辅助图（SVG+PNG） | 53.1 s | 4 | 14/14 | 12/12 | ok |
| 3 | `examples/problems/physics_force.png` | 物理 · 动力学 | 受力图（SVG+PNG） | 51.8 s | 4 | 9/9 | 12/12 | ok |

以上为最终代码（v0.1.0）的实测运行，运行 ID 可在临时目录 `runs/*/summary.json` 中核对。

补充观察（同一批运行）：

- 首次几何题尝试中，作图阶段模型返回空响应，流水线**如实报告**「作图未成功」并继续给出文本证明（`status: partial`），没有伪造图。提高输出预算后重跑成功。
- 每次端到端运行实际发生 **2–4 次模型调用**（识别 / 作图 / 解题；`balanced` 模式下评分不调用模型）。
- 第 1 题被规则正确判定为「不需要作图」，没有为了展示能力强行画图。
- 物理题的受力图中，速度/加速度矢量从独立锚点绘制，不与力箭头重叠。

> 这三题是**代表性 pilot**，不是全量 benchmark。`n=3` 不足以计算有统计意义的准确率。

## 3. 指标定义与状态

| 指标 | 定义 | 当前状态 |
|---|---|---|
| Recognition Accuracy | 识别出的条件/问题/公式与题面一致的比例 | 未实测（需人工标注全量 34 题） |
| Formula Accuracy | 公式转写正确率 | 未实测 |
| Diagram Requirement Accuracy | 作图判断与标签一致率 | **可回归**：34/34 标签与规则一致（规则测试，非模型测试） |
| Diagram Relation Accuracy | `visual_relations` 在图中数值成立的比例 | **可回归**：几何关系验证器单测 + 1 例端到端 14/14 |
| Answer Accuracy | 最终答案正确率 | 未实测（pilot 3/3 正确） |
| Validation Catch Rate | 注入错误被验证器发现的比例 | **单测证据**：错的根、错的导数、错的积分、错的量纲、荒谬量级、垂直关系破坏均被捕获（见 `tests/python/`）；未计算比率 |
| Score Completeness | 关键步骤/单位/图的覆盖情况 | 通过 Examiner 规则输出，未做人工对照 |
| End-to-End Success Rate | 完整跑通且 `status: ok` 的比例 | 未实测（pilot 3/3 ok） |

## 4. 如何跑全量 benchmark

全量跑批需要真实模型调用，因此**不放进 CI**。推荐由 Agent 在具备插件的会话中执行：

1. 对每个 case 用 `problem_type`/`text` 生成对应题目图片（或直接使用 `examples/problems/` 中的样张）；
2. 调用 `solve_exam_image(imagePaths=[...], answerMode="exam", quality="balanced")`；
3. 读取返回的 `validation.checks`、`finalAnswer` 与 `status`；
4. 用 `benchmark/cases.jsonl` 的 `checks` 复核最终答案（可直接复用 `validate_solution`）；
5. 汇总 Recognition / Diagram / Answer / E2E 四项指标，写入本文件并附运行 ID。

在完成第 1–5 步之前，README 与本文件都不会给出全量准确率数字。

## 5. 已知失败模式（实测或单测观察）

| 现象 | 触发条件 | 当前行为 |
|---|---|---|
| 模型输出为空 | 推理占满输出预算 | 明确报错 `LLM_TRUNCATED`，可重试；不会静默生成空图 |
| 坐标不满足关系 | 模型给出近似但错误的坐标 | 关系校验给出数值证据并触发修复提示 |
| 未定义点 | DiagramSpec 引用不存在的点 | Schema 之后的结构检查给出路径级错误 |
| 单位错误 | 如 `v = 10 N` | 量纲校验判为 error |
| 数量级荒谬 | 如 `v = 1e20 m/s` | 硬上限判为 error |
| 图不符合“要证明的结论” | 把待证结论预标为已知 | 提示词要求不预标；当前版本仍依赖模型遵守，尚未程序化检测 |
