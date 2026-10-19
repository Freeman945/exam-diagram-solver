# 隐私与数据处理

## 数据流向

```
用户上传的图片
   │
   ├─ 对话附件：由 Harness 的 attachment 服务存储（与普通聊天发图完全一致）
   │
   └─ 插件：
        1. 按路径读取，或直接使用会话中的 image block
        2. 通过 ctx.attachments.saveImage 得到 Harness 的附件引用
        3. 作为 image block 传给当前配置的模型
        ✗ 不复制到插件目录
        ✗ 不写入日志
        ✗ 不上传到任何第三方服务
```

插件不发起任何网络请求。所有模型调用都经过 Harness 的 `llm` 服务，因此数据去向与你在对话中直接发图相同，取决于你所配置的模型提供方。

## 本地写入

| 内容 | 位置 | 说明 |
|---|---|---|
| 生成的图（SVG/PNG） | `%TEMP%\exam-diagram-solver\runs\<runId>\` | 默认临时目录，可用 `EXAM_SOLVER_OUTPUT_DIR` 修改 |
| 运行摘要 `summary.json` | 同上 | 只含题型、耗时、校验计数、估分、文件路径；**不含题干** |
| 日志 `*.jsonl` | `%TEMP%\exam-diagram-solver\logs\` | 只含阶段、耗时、错误码、校验状态；默认不含题干 |

`logProblemText=true` 时，摘要才会包含完整 ProblemSpec。默认关闭。

清理方式：删除该临时目录即可；插件不会在仓库目录中写入任何用户内容。

## 日志中不会出现的内容

- 用户图片本身（不落盘、不 base64 写入日志）
- 姓名、学号、学校等图片中的个人信息（插件不提取这些字段）
- API Key（插件不读取、不保存任何密钥）
- 完整题目文本（除非显式开启 `logProblemText`）

## 仓库卫生

`.gitignore` 已排除 `uploads/`、`temp/`、`output/`、`cache/`、`.env`、`*.log`、`.venv/`、`__pycache__/`、开发脚本临时产物等。

`examples/` 与 `benchmark/` 中的题目全部为仓库自编内容；`examples/problems/*.png` 由 `scripts/make_example_problems.py` 生成，`examples/diagrams/*` 由渲染器生成，均可复现，不包含任何来源不明的教材或题库扫描件。

## 用户须知

- 插件会把图片发送给你在 Harness 中配置的模型；如果该模型由第三方提供，请遵守对应服务的数据条款。
- 如果你不希望题目离开本机，请不要使用需要联网模型的场景（当前版本没有离线解题模式）。
- 生成物默认保存在系统临时目录，可能被操作系统清理；需要长期保留请手动复制。
