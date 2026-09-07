# PPT 模板 POC — Go / No-Go

> 日期：2026-09-07  
> 方法：`uv run --with python-pptx python scripts/ppt_poc/fill_demo.py`  
> 产物：`scripts/ppt_poc/out/demo.pptx`

## 结论：**条件 Go（M2b 可开做，范围收窄）**

| 检查项 | 结果 |
|--------|------|
| 程序化生成空白版式 + 文本框 | **通过**（python-pptx） |
| 占位符 `{{title}}` / `{{subtitle}}` 替换 | **通过**（run 级字符串替换） |
| 多套精美商业模板 | **未验证** — 采购/设计成本未知 |
| 图片/表格/图表复杂布局自动适配 | **未验证** — 高风险 |
| LibreOffice / 在线渲染预览 | **未做**（小程序可直接下载 pptx） |

## 建议（对齐蓝图「1–2 套基础模板」）

1. **Go**：M2b 用 **自研 1–2 套简单母版**（标题页 + 要点页 + 结尾），字段映射写死；不做精美商用库。
2. **No-Go 触发**：若产品坚持「多套精美模板且必须自动排版复杂图」→ 记入已知问题，跳过 M2b 或降级为「仅大纲导出」。
3. 当前 POC **不阻塞** G1；正式 M2b 开工前再锁一版母版文件进仓。

## 复现

```bash
uv run --with python-pptx python scripts/ppt_poc/fill_demo.py
# open scripts/ppt_poc/out/demo.pptx
```
