# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.0] — 2026-10-19

首个可安装版本。目标是把「题目图片 → 识别 → 按需作图 → 解题 → 验证 → 高质量答案」做成可运行、可测试、可长期维护的 Harness 插件。

### Added

- **Harness 集成**：12 个工具，主入口 `solve_exam_image`；无参数时自动使用当前会话最新上传的题目图片。
- **ProblemSpec**：结构化题目表示（学科、题型、条件、问题、公式、图中对象与关系、不确定项、置信度）。
- **图形重建**：`exam_reconstruct_diagram` 输出结构化 `visual_objects` / `visual_relations`。
- **作图判定**：`exam_decide_diagram` 规则引擎，区分辅助图 / 正式作答图 / 不需要图，返回命中规则。
- **DiagramSpec 与 Renderer**：几何、函数/坐标、受力、电路、光路、数据图 6 类；SVG 为规范输出，PNG 为预览。
- **严格校验**：自研 JSON Schema 校验器（支持 `$ref`、`oneOf`、`const`），外加未定义点/零长线段等结构检查。
- **几何关系验证**：垂直、平行、共线、等长、共圆、点在线上、点在圆上、中点、直角；误差阈值随图形尺寸自适应。
- **SymPy 验证**：方程回代、恒等式、导数、积分、数值比对；无法符号证明时给出数值证据并标注。
- **物理验证**：单位缺失、量纲不匹配、荒谬数量级。
- **模拟阅卷**：规则评分（正确性/步骤/表达/作图）+ 可选模型阅卷；估分明确标注为内部估计。
- **自动修正循环**：有轮次上限，失败即停并保留已有结果。
- **答案模式**：`concise` / `exam` / `teaching`。
- **数据契约**：5 份 JSON Schema，位于 `schemas/`。
- **测试**：Python 157 项、Node 61 项；含 34 道自编题的 benchmark 与期望值复核。
- **文档**：中文 README、英文 README、架构、隐私、基准、依赖审计、贡献指南、安全策略、CI。

### Known limitations

- 立体几何不自动作图（明确拒绝而不是画错）。
- 电路与光路为实验性；复杂拓扑建议显式提供节点坐标。
- 未对折射定律、电路方程做程序化校验。
- 全量 34 题端到端跑批尚未执行；仅完成 3 题 pilot（全部 `status: ok`）。
- Examiner 分数只是内部估计，不代表真实考试评分。

### Fixed during development

- `fit()` 的 y 方向偏移错误导致图形跑出画布。
- Matplotlib 缺少 CJK 字体导致的“豆腐块”。
- 几何标签的世界坐标/屏幕坐标混用。
- `oneOf` 分支 sanitize 时 `$ref` 无法解析。
- Examiner 中 `str >= float` 的类型错误。
- 运行时指标累积而非按次统计。
- 受力图中速度/加速度箭头与力箭头重叠。
