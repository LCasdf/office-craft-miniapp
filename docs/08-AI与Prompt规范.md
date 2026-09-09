# Office Craft — AI 与 Prompt 规范

> 文档版本：v0.2  
> 更新日期：2026-09-09  
> 范围：M2a 角色卡（Mock AI / Mock 文生图）；真模型接入后只增 Provider，不改本 schema 契约

---

## 1. 原则

| 项 | 约定 |
|----|------|
| Provider | 配置 `AI_PROVIDER`（默认 `mock`）；文本经 `build_ai_client`，立绘经 `build_image_client` |
| Prompt 版本 | 字符串常量，写入 `character_cards.prompt_version` |
| 输出 | **仅 JSON**，可被 `schemaVersion` 校验；禁止 markdown 围栏 |
| 审核 | 输入 premise / 文生图 prompt / 输出 payload **双向**关键词 stub → `42001` |
| 扣点 | **草稿与 imagine 免费**；确认出图 `POST .../render` 预扣 3 点；安全拒绝不返还 |

---

## 2. 角色卡 Prompt

| 项 | 值 |
|----|------|
| `promptVersion` | `character_card.v1` |
| 代码 | `oc_core.ai.prompts.CHARACTER_CARD_SYSTEM` / `character_card_messages` |
| 用户输入 | `premise` ≤ 2000 字符（`AI_TEXT_MAX_CHARS`） |

系统提示要点：输出 schemaVersion=2 的 JSON；字段长度上限见 schema。

---

## 3. Payload schema（`schemaVersion=2`）

```json
{
  "schemaVersion": "2",
  "name": "林秋",
  "title": "纸鸢客",
  "avatarDesc": "青衫薄影…",
  "personality": "沉默寡言",
  "story": "雨巷中卖纸鸢…",
  "ability": "手巧、观气",
  "weakness": "不善言辞",
  "remark": ""
}
```

小程序编辑器以本地 `Storage.roleCardList` 为主；可选调 `POST /v1/ai/character-card/generate` 自动填表。

---

## 4. 出图

### 4.1 演示主路径（文生图）

| 项 | 约定 |
|----|------|
| API | `POST /v1/ai/character-card/imagine` |
| 实现 | `oc_core.ai.image_gen` Mock 风格化立绘 PNG |
| 尺寸 | 768×1024 |
| 产物 | MinIO `imageUrl`；小程序下载后写入本地卡集 |

### 4.2 服务端任务路径（可选）

| 项 | 约定 |
|----|------|
| API | `POST .../render` → Worker `q.ai` |
| 实现 | Pillow 单模板 PNG（非文生图） |
| 尺寸 | 1080×1440 |
| 产物 | `output_meta.cosKey`；回写 `character_cards.cover_cos_key`；预扣 3 点 |

---

## 5. API 流

**小程序演示：** 填写描述 → `imagine` → 本地保存卡集（可再 `generate` 填人设）。

**服务端草稿出图：**

1. `POST /v1/ai/character-card/generate` — 审核 premise → Mock complete → 落 draft（不扣点）  
2. `PUT /v1/ai/character-card/{id}` — `If-Match` / `version` 乐观锁；冲突 `40015`  
3. `POST /v1/ai/character-card/{id}/render` — 输出审核 → 预扣 3 → 建 `character_card` 任务  

详情见 [03-API契约](./03-API契约.md) §5.1。
