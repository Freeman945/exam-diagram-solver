# 示例

本目录中的所有题目与图片均为本仓库自编内容，可自由用于文档、测试与演示。

## `problems/` — 题目图片

由 `python scripts/make_example_problems.py` 生成（Matplotlib，无第三方素材）：

| 文件 | 内容 | 用途 |
|---|---|---|
| `math_quadratic.png` | 一元二次方程 + 两根平方和 | 演示“不需要作图”的判定 |
| `geometry_proof.png` | 等腰三角形、中点、垂直证明 | 演示图形重建与几何校验 |
| `physics_force.png` | 粗糙水平面上的物块受力 | 演示受力图与量纲校验 |

## `diagrams/` — 渲染器输出

由 `python scripts/make_example_diagrams.py` 调用真实 Renderer 生成，每个图同时提供 SVG（规范输出）与 PNG（预览）：

| 文件 | 类型 | 展示内容 |
|---|---|---|
| `geometry_triangle.*` | geometry | 等腰三角形、中线、直角/等长标记、标签避让 |
| `geometry_circle.*` | geometry | 圆、内接三角形、角度标记 |
| `function_parabola.*` | function | SymPy 求根/顶点/截距并标注 |
| `function_rational.*` | coordinate | 双曲线与直线、辅助虚线、交点标注 |
| `force_block.*` | force | 四力受力图 + 加速度矢量 + 坐标 triad |
| `force_incline.*` | force | 斜面受力图 |
| `circuit_series.*` | circuit | 串联回路、电源/电阻/电流表 |
| `circuit_parallel.*` | circuit | 并联支路与节点 |
| `optics_mirror.*` | optics | 平面镜、法线、入射/反射光线 |
| `optics_lens.*` | optics | 凸透镜、光轴、焦点、折射光线 |
| `chart_experiment.*` | chart | 实验数据折线图 |

重新生成：

```bash
python scripts/make_example_diagrams.py
```

## 用法

```
solve_exam_image(imagePaths=["<repo>/examples/problems/geometry_proof.png"])
```

或把图片拖进对话后直接调用 `solve_exam_image()`。
