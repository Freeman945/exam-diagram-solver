# 依赖与许可证审计

本仓库以 **MIT** 许可发布。下表列出运行与开发依赖，以及它们与 MIT 的兼容性。

## 运行时依赖

| 依赖 | 版本范围 | 许可证 | MIT 兼容 | 用途 |
|---|---|---|---|---|
| [SymPy](https://www.sympy.org/) | `>=1.12,<2` | BSD-3-Clause | ✅ 是 | 符号解析、求导、积分、方程求解、数值化简 |
| [Matplotlib](https://matplotlib.org/) | `>=3.7` | PSF-based（BSD 兼容） | ✅ 是 | 仅 PNG 预览（可选；缺失时降级为只有 SVG） |

## 开发依赖

| 依赖 | 版本范围 | 许可证 | 用途 |
|---|---|---|---|
| [pytest](https://pytest.org/) | `>=8,<10` | MIT | 测试运行器 |

## Node.js 侧

**零运行时依赖**。插件只使用 Node 内置模块（`fs`、`path`、`child_process`、`url`、`os`）与 Harness 提供的 Host 服务接口。

## 未引入的候选依赖及原因

| 候选 | 未采用原因 |
|---|---|
| `jsonschema` (Python) | 为避免运行时依赖，项目自带严格校验器（约 400 行，含 `$ref`/`oneOf`/`const` 支持），并有完整测试覆盖 |
| `schemdraw` | 电路图用自研 SVG Renderer 实现，避免额外依赖与许可证审查成本；复杂电路仍是实验性 |
| `pint` | 量纲校验用自研的维度向量表（覆盖中学物理常见单位），足够且可控 |
| `cairosvg` / `svglib` | PNG 预览使用 Matplotlib；SVG 是规范输出，无需额外转换链 |
| 任何前端框架 | 插件无 UI，只注册工具 |

## 题目与图片的版权

- `examples/problems/*.png`：由 `scripts/make_example_problems.py` 生成，题目内容为本仓库自编。
- `examples/diagrams/*`：由 `scripts/make_example_diagrams.py` 调用本项目 Renderer 生成。
- `benchmark/cases.jsonl`：全部为自编题目与自算答案。
- 仓库中**不包含**任何来源不明的教材扫描件、商业题库或第三方数据集。

## 许可证一致性检查清单

- [x] MIT 允许再分发、修改、商用；上述依赖均为宽松许可（BSD/MIT/PSF）。
- [x] Node 侧无第三方运行时依赖，不存在传递性许可证风险。
- [x] 未复制任何 GPL/AGPL 代码或素材。
- [x] 图标 `icon.svg` 为本项目原创。
- [x] 无 API Key、无账号凭据、无个人数据进入仓库。

> 本审计基于人工核对依赖官方许可证声明；发布前建议再次运行 `pip-licenses` 或其他工具做自动化复核。
