# G2a Smoke Report

- at: `2026-09-09T15:04:55.096852+00:00`
- base: `http://127.0.0.1:8000`
- passed: **True**

| check | ok | detail |
|-------|----|--------|
| healthz | yes | ok |
| imagine | yes | 角色图片已生成 |
| imagine_png | yes | 22828 |
| imagine_blocked | yes | 内容未通过安全审核，请修改后重试 quota=1999983->1999983 |
| generate_free | yes |  |
| put_conflict | yes | 角色卡已更新，请刷新后重试 |
| put_ok | yes |  |
| render_reserve | yes | 出图任务已提交 |
| render_quota | yes | 1999983->1999980 |
| render_succeeded | yes | task=e8695fa2fbd946ec90216304fb status=succeeded |
| generate_blocked | yes | 内容未通过安全审核，请修改后重试 |

## Demo checklist (miniapp)

1. 首页 → 角色卡集 → 新建
2. 填写描述 →「根据文字生成角色图片」→ 预览 PNG
3.「保存到角色卡集」→ 列表显示已出图
4. 可选：AI 填充人设文字；编辑后再次出图
5. 违禁词提示 `内容未通过安全审核，请修改后重试`
