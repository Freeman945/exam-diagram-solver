# 贡献指南

感谢你愿意改进这个项目。请先阅读以下约定——它们决定了改动能否被合入。

## 开发环境

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt    # Windows
.venv/bin/pip install -r requirements-dev.txt        # macOS/Linux

python -m pytest tests/python -q
node scripts/run-node-tests.mjs
node scripts/smoke-engine.mjs
```

Node 侧无第三方依赖；请不要为了一件小事引入新的运行时包。

## 设计约束

1. **原图不能丢**：识别与解题阶段都可以再次参考原图，禁止把图片替换成 OCR 文本。
2. **LLM 决定画什么，程序决定怎么画**：不要在提示词里让模型输出图片或坐标绘制指令之外的东西；不要绕过 Renderer。
3. **能验证的必须验证**：新增结论类型时，优先增加可执行断言（`AnswerSpec.verification`），而不是让模型“自己检查”。
4. **允许失败**：无法确认时增加 `uncertainties` 并降低置信度；禁止为了“回答率”编造条件。
5. **诚实的状态标注**：README 只写 `已实现 / 实验性 / 计划中`，且必须与实际测试一致。
6. **隐私默认安全**：不复制用户图片，不记录题干与个人信息，不读取密钥。

## 新增一种图类型

1. 在 `schemas/diagram_spec.schema.json` 中新增变体（`additionalProperties: false`）。
2. 在 `python/exam_solver/diagrams/` 实现 `render_xxx(spec, canvas) -> Stats`。
3. 在 `diagrams/render.py` 注册 dispatch，并在 `check_references` 中补引用检查。
4. 在 `lib/prompts.js` 的 `DIAGRAM_SCHEMA_CARD` 增加最小 JSON 示例。
5. 在 `lib/normalize.js` 增加别名归一化（可选但推荐）。
6. 添加：Schema 测试、Renderer 结构断言、`examples/diagrams/` 示例、README 支持表。

## 新增一种验证断言

1. 在 `schemas/answer_spec.schema.json` 的 `verification.oneOf` 增加 `kind`。
2. 在 `python/exam_solver/validators/math_validator.py` 增加执行分支，并区分 `passed / failed / skipped`。
3. 在 `lib/prompts.js` 的 `ANSWER_SCHEMA_CARD` 说明格式与使用场景。
4. 增加正确与错误两个方向的测试。

## 提交 PR 前

- [ ] `python -m pytest tests/python -q` 全绿
- [ ] `node scripts/run-node-tests.mjs` 全绿
- [ ] `node scripts/smoke-engine.mjs` 通过
- [ ] 新增/修改行为有测试覆盖
- [ ] README / docs 的状态表已同步
- [ ] 没有提交真实试卷、个人信息、API Key 或来源不明的图片
- [ ] 依赖变更已更新 `docs/DEPENDENCIES.md`

## 测试数据

只接受以下来源：

1. 自己编写的题目；
2. 自己生成的合成题目（如 `scripts/make_example_problems.py`）；
3. 自己绘制的图；
4. 明确许可的公开数据（须在 PR 中记录来源、许可证与使用范围）。

## 代码风格

- Python：类型注解、docstring、模块职责单一；每个文件尽量 < 500 行。
- JavaScript：ESM、无构建步骤、显式错误码；不要吞掉异常。
- 提示词：与代码一样接受 review，修改时说明原因。

## 提交信息

使用简短祈使句，例如：

```
fix(validator): handle $ref inside oneOf during sanitisation
feat(diagram): add optics renderer with focal points
docs(readme): mark circuit renderer as experimental
```
