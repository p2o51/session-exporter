# Token 与成本

Session Exporter 将每种工具记录的原始用量，转化为按会话和按选区的 **token 核算**与**成本估算** —— 并且正确处理了 prompt 缓存。

## Token 核算

对每条会话，它都会聚合服务商实际记录的用量：

| 字段 | 含义 |
| --- | --- |
| **输入（Input）** | 按完整输入费率计费的 prompt token |
| **输出（Output）** | 生成的 token（对 OpenAI 而言包含推理 token） |
| **缓存读取（Cache read）** | 由 prompt 缓存提供的 token（大幅折扣） |
| **缓存写入（Cache write）** | 写入缓存的 token（Claude） |
| **推理（Reasoning）** | 思考 / 推理 token（Codex） |
| **缓存命中率（Cache-hit rate）** | `cache_read / (input + cache_write + cache_read)` |

这些直接来自会话日志 —— 它们是**实测的，而非估算的**（Cursor 除外，见下文）。

## Token 依据

每条会话都会标注其数字是如何获得的：

- **`recorded`** —— Claude Code 和 Codex 会逐轮记录真实用量。完全准确。
- **`context-snapshot`** —— Cursor 只记录最终上下文窗口的大小，而非累计花费或缓存活动。这类数字会用 `~` 标记，并且**不为其计算成本**（参见 [数据与隐私](/zh/guide/data-sources)）。

## 成本估算

每条 `recorded` 会话都根据其 token × 各模型费率来定价。缓存则按各服务商实际的计费方式计费：

- **缓存读取** —— 输入费率的 `0.1×`。
- **Anthropic 缓存写入** —— 5 分钟缓存为 `1.25×`，1 小时缓存为 `2×`。Session Exporter 会从 Claude 的日志中读取 5 分钟 / 1 小时的拆分，因此写入成本是精确的，而非近似的。
- **Codex / OpenAI** —— 记录的 `input` 已经包含了缓存部分，因此成本使用 `(input − cached) × input_rate + cached × cache_read_rate + output × output_rate`。

成本会以表格中的**成本（Cost）**列、详情抽屉中的一个磁贴，以及选择栏和顶栏上的实时合计形式呈现。

## Stats 面板

点击工具栏中的 **Stats** 可打开针对**当前筛选**的拆解：

- **概要磁贴** —— 会话数、token、估算成本和缓存命中率。
- **按模型** —— 一张列出每个模型及其会话数、token 和成本的表格，带成本条形图，按成本最高优先排序。
- **按日期** —— 同上，按天分组（最新在前）。

由于它尊重当前生效的筛选，诸如*「最近 3 天花了多少？」*或*「我在 gpt-5.5 上花了多少？」*这类问题一眼即可看出：设置日期范围或来源筛选，打开 Stats，读取合计即可。

使用**估算**费率的行（即未公布确切价格的模型）会用 `~` 标记。Cursor 会话被排除在成本之外，显示为 `—`。

## 编辑价格 —— `pricing.json`

价格保存在应用旁边一个可编辑的 [`pricing.json`](https://github.com/p2o51/session-exporter/blob/main/pricing.json) 中。费率为**每 1,000,000 token 的美元数**：

```json
{
  "models": {
    "claude-opus-4-8": {
      "input": 5, "output": 25, "cache_read": 0.5,
      "cache_write_5m": 6.25, "cache_write_1h": 10
    },
    "gpt-5.5": { "input": 5.0, "output": 30.0, "cache_read": 0.5 }
  },
  "aliases": { "openai": "gpt-5.5" }
}
```

- `cache_read` —— 打折后的缓存输入费率。
- `cache_write_5m` / `cache_write_1h` —— Anthropic 缓存写入费率（其他服务商不对缓存写入计费；可省略）。
- `aliases` —— 将某个原始模型字符串（例如服务商的回退名称）映射到一个已定价的模型。
- 在某个模型上设置 `"estimated": true` 会在 UI 中用 `~` 标记它。

模型键在匹配时**不区分大小写**。`pricing.json` 中缺失的模型会显示为 `—`（未定价），而不会去猜测 —— 因此一个短横线始终意味着「未配置价格」，绝不意味着「免费」。

出厂时已填入费率：**Claude** 来自 Anthropic 官方定价；**OpenAI、Z.ai (GLM)、Moonshot (Kimi)** 来自其公开定价。你可以修改任意数字以匹配你自己的合约，然后点击 Stats 面板里的 **↻ Reload prices** —— 它会立即生效，无需重新扫描你的数据。
