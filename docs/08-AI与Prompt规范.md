# Office Craft — AI 与 Prompt 规范

> 文档版本：v0.3  
> 更新日期：2026-09-09  
> 范围：M2a 角色卡 + M2b PPT 大纲（Mock）；真模型接入后只增 Provider

---

## 1. 原则

| 项 | 约定 |
|----|------|
| Provider | 配置 `AI_PROVIDER`（默认 `mock`）；文本经 `build_ai_client`，立绘经 `build_image_client` |
| Prompt 版本 | 字符串常量，写入对应表的 `prompt_version` |
| 输出 | **仅 JSON**，可被 schema 校验；禁止 markdown 围栏 |
| 审核 | 输入 / 大纲字段关键词 stub → `42001` |
| 扣点 | 角色卡草稿/imagine 免费，render 预扣 3；**PPT 大纲免费，generate 预扣 5**；安全拒绝不返还 |

---

## 2. 角色卡 Prompt

| 项 | 值 |
|----|------|
| `promptVersion` | `character_card.v2` |
| 代码 | `oc_core.ai.prompts.CHARACTER_CARD_SYSTEM` / `character_card_messages` |
| 用户输入 | `premise` ≤ 2000 字符（`AI_TEXT_MAX_CHARS`） |

小程序以本地 `Storage.roleCardList` 为主；可选 `POST .../character-card/generate`；演示出图走 `imagine`。

---

## 3. PPT 大纲 Prompt

| 项 | 值 |
|----|------|
| `promptVersion` | `ppt_outline.v1` |
| 代码 | `PPT_OUTLINE_SYSTEM` / `ppt_outline_messages` |
| 页数 | **5–15** |
| 模板 | `tpl_basic_01`（程序化母版：封面 + 要点页） |

输出：

```json
{
  "pages": [
    { "title": "封面", "bullets": ["副标题"] },
    { "title": "目录", "bullets": ["背景", "方案"] }
  ]
}
```

### 字段映射（tpl_basic_01）

| 页 | 形状 | 来源 |
|----|------|------|
| 第 1 页 | 居中大标题 + 副标题 | `pages[0].title` / `pages[0].bullets[0]` |
| 后续页 | 标题 + 项目符号 | `title` / `bullets[]` |

实现：`oc_core.converters.pptx_fill.render_outline_pptx`（python-pptx）。

---

## 4. API 流

**角色卡演示：** 填写描述 → `imagine` → 本地卡集。

**PPT：**

1. `POST /v1/ai/ppt/outline` — 免费；Mock 大纲  
2. `PUT /v1/ai/ppt/outline/{id}` — 乐观锁；冲突 `40012`  
3. `POST /v1/ai/ppt/generate` — 版本必须匹配 → 预扣 5 → `q.ai` 出 pptx  

详情见 [03-API契约](./03-API契约.md) §5.2–5.3。
