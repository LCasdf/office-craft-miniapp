# Office Craft — API 契约（初稿）

> 文档版本：v0.4-draft  
> 更新日期：2026-09-07  
> 对齐蓝图：`docs/01-项目蓝图.md` 与开发规范；实现进度见 `docs/07-项目进度.md`  
> 协议：HTTPS + JSON（`Content-Type: application/json`）；本地上传另支持 `multipart/form-data`（§3.2）  
> Base URL（示例）：`https://api.example.com`（本地：`http://127.0.0.1:8000`）  
> OpenAPI：本文 §8 含 OpenAPI 3.0 YAML 初稿；§3.2 / §4.7 等以 Markdown 为准，YAML 逐步对齐  
> **已实现（M1）：** 创建/列表/详情、cancel、retry、download、delete；上传凭证 + API 代传；`/healthz`、`/metrics`；鉴权仍为 stub（未强制 JWT）

---

## 1. 通用约定

### 1.1 鉴权

| 项 | 说明 |
|----|------|
| 登录 | `POST /v1/auth/wx-login` 换取 `accessToken`（默认 2h）+ `refreshToken`（默认 30d） |
| 刷新 | `POST /v1/auth/refresh` 使用 refresh 换发新 access（可轮换 refresh） |
| 鉴权头 | `Authorization: Bearer <accessToken>` |
| 免鉴权 | `POST /v1/auth/wx-login`、`POST /v1/auth/refresh`、（可选）运维健康检查 |
| 失效 | `code=41001`；客户端按开发规范 §5.2 **单飞刷新**，失败再清会话重新登录 |
| 限流 | 创建类 1 次/秒、列表 5 次/秒；超限 `40029` + HTTP 429（见开发规范 §5.5） |
| AI 文本 | 设定类输入最大 **2000** 字符（前后端双校验，见开发规范 §8.4） |

### 1.2 统一响应包络

所有业务接口 HTTP 200/201 的 body（或 4xx/5xx 时仍可用包络承载业务码，见实现备注）统一为：

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {},
  "requestId": "req_01HXYZ...",
  "taskId": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | integer | 是 | `0` 成功；非 0 见 §7 |
| `message` | string | 是 | 机器可读 snake_case |
| `user_msg` | string | 是 | **用户可见中文**；前端默认只展示此字段 |
| `data` | object\|array\|null | 是 | 业务数据；失败时多为 `null` |
| `requestId` | string | 是 | 全链路请求 ID |
| `taskId` | string\|null | 否 | 与任务相关时填 `public_id` |

> 蓝图强制含 `user_msg`；成功时 `user_msg` 可为 `"ok"` 或简短中文提示。

**实现备注（初稿约定）：**

- 业务错误优先 HTTP `200` + `code≠0`（小程序易处理）；鉴权失败可用 HTTP `401` + 包络。
- 创建任务首次成功可用 HTTP `201`；幂等重放可用 `200` + 响应头 `Idempotent-Replayed: true`。

### 1.3 公共请求头

| Header | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `Authorization` | string | 除登录外必填 | `Bearer <token>` |
| `Content-Type` | string | POST 必填 | `application/json` |
| `Idempotency-Key` | string (UUIDv4) | 扣费创建类必填 | 见各接口 |
| `X-Request-Id` | string | 否 | 客户端可传；服务端也可生成并回写到 `requestId` |

### 1.4 任务类型与额度（创建任务时）

| `type` | 预扣点数（默认） | 处理超时 |
|--------|------------------|----------|
| `image_to_pdf` | 1 | 60s |
| `pdf_compress` | 1 | 60s |
| `pdf_merge` | 2 | 120s |
| `office_to_pdf` | 2 | 180s |
| `character_card` | 3 | 120s |
| `ppt_generate` | 5 | 120s |
| `novel_chapter` | 4 | 120s |

---

## 2. 认证与用户

### 2.1 微信登录

- **方法 / 路径：** `POST /v1/auth/wx-login`
- **鉴权：** 否
- **幂等键：** 否

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | `wx.login` 取得的临时 code |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "expiresIn": 7200,
    "user": {
      "id": "10001",
      "nickname": null,
      "avatarUrl": null
    }
  },
  "requestId": "req_01LOGIN..."
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 41002 | wx_login_failed | 登录失败，请稍后重试 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---


### 2.1.1 刷新 Token

- **方法 / 路径：** `POST /v1/auth/refresh`
- **鉴权：** 否（凭 refreshToken）
- **幂等键：** 否

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `refreshToken` | string | 是 | 登录下发的 refresh |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "accessToken": "eyJhbGciOiJIUzI1NiIs...",
    "expiresIn": 7200,
    "refreshToken": "rt_new_...",
    "refreshExpiresIn": 2592000
  },
  "requestId": "req_01REFRESH..."
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

### 2.2 当前用户

- **方法 / 路径：** `GET /v1/me`
- **鉴权：** 是

#### 请求参数

无 Query/Body。

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "id": "10001",
    "nickname": null,
    "avatarUrl": null,
    "status": 1,
    "createdAt": "2026-09-05T10:00:00.000+08:00"
  },
  "requestId": "req_01ME..."
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 2.3 查询额度

- **方法 / 路径：** `GET /v1/me/quota`
- **鉴权：** 是

#### 请求参数

无。

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "dailyQuotaLimit": 20,
    "dailyUsed": 3,
    "dailyUsedDate": "2026-09-05",
    "dailyRemaining": 17,
    "frozenQuota": 2,
    "vipBalance": 0,
    "vipExpireAt": null,
    "totalUsed": 128,
    "available": 15
  },
  "requestId": "req_01QUOTA..."
}
```

> `available = dailyRemaining + vipBalance - frozenQuota`（跨日懒重置后计算）。

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

## 3. 上传

### 3.1 申请上传凭证

- **方法 / 路径：** `POST /v1/uploads/credential`
- **鉴权：** 是
- **说明：** 校验预估额度与进行中任务上限；凭证有效期 ≤ **15 分钟**；余额不足拒发凭证。

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `taskType` | string | 是 | 见 §1.4，用于额度预校验 |
| `fileCount` | integer | 是 | 拟上传文件数，≥1 |
| `totalSizeBytes` | integer | 否 | 预估总字节，用于前置拦截 |
| `filenameHints` | string[] | 否 | 扩展名提示，如 `["a.pdf"]` |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "uploadId": "upl_01ABC...",
    "expireAt": "2026-09-05T10:15:00.000+08:00",
    "cos": {
      "bucket": "office-craft",
      "region": "us-east-1",
      "endpoint": "http://127.0.0.1:9000",
      "pathPrefix": "local/0/uploads/upl_01ABC/",
      "credentials": {
        "tmpSecretId": "...",
        "tmpSecretKey": "...",
        "sessionToken": "...",
        "startTime": 1757040000,
        "expiredTime": 1757040900
      }
    },
    "uploadApiPath": "/v1/uploads/upl_01ABC.../objects",
    "estimatedCostQuota": 2
  },
  "requestId": "req_01UPL..."
}
```

> **本地 / 当前实现：** 小程序与 curl 走 `uploadApiPath`（见 §3.2）把文件交给 API 写入 MinIO，**不必**在客户端直接用 STS 直传。生产可改为真 COS STS，客户端直传 `pathPrefix`。

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 40002 | file_too_large | 文件过大，请压缩后再上传 |
| 40003 | quota_exhausted | 今日额度已用完，明天再来或开通会员 |
| 40005 | too_many_inflight_tasks | 进行中的任务已满（最多3个），请先到任务中心查看 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 3.2 上传对象（本地 / API 代传）

- **方法 / 路径：** `POST /v1/uploads/{uploadId}/objects`
- **鉴权：** 是（当前实现尚未强制 JWT）
- **说明：** `multipart/form-data`；将文件写入 MinIO，键为 `{pathPrefix}{index}_{safeFilename}`。用于本地与小程序，替代浏览器侧 STS 直传。

#### 请求参数

| 位置 | 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| path | `uploadId` | string | 是 | 凭证返回的 `upl_...` |
| form | `file` | file | 是 | 文件本体 |
| form | `index` | integer | 否 | 多文件序号，默认 0 |
| form | `taskType` | string | 否 | 用于扩展名校验（如 `image_to_pdf` / `office_to_pdf`） |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "uploadId": "upl_01ABC...",
    "cosKey": "local/0/uploads/upl_01ABC.../0_a.png",
    "filename": "a.png",
    "sizeBytes": 128,
    "index": 0
  },
  "requestId": "req_01UPL..."
}
```

创建任务时把返回的 `cosKey` 填入 `inputs[].cosKey`。

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误 / 扩展名不符 |
| 40002 | file_too_large | 文件过大，请压缩后再上传 |
| 50001 | internal_error | 服务繁忙，请稍后重试（含 MinIO 不可达） |

---

## 4. 任务

### 4.1 创建任务

- **方法 / 路径：** `POST /v1/tasks`
- **鉴权：** 是
- **幂等键：** **`Idempotency-Key` 必填**
- **说明：** 创建成功即预扣额度并入队；同 Key 同指纹重放不重复扣费。

#### 请求头

| Header | 必填 | 说明 |
|--------|------|------|
| `Idempotency-Key` | 是 | UUIDv4；24h 内 `(userId, key)` 唯一 |

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | §1.4 任务类型 |
| `uploadId` | string | 条件 | 与 `inputs` 二选一或同时校验归属 |
| `inputs` | object[] | 是 | 输入对象列表，顺序即处理顺序 |
| `inputs[].cosKey` | string | 是 | 已直传的对象键（须属当前用户前缀） |
| `inputs[].filename` | string | 否 | 原始文件名 |
| `inputs[].sizeBytes` | integer | 否 | 字节数 |
| `params` | object | 否 | 类型相关参数，见下表 |

**`params` 按类型：**

| type | params 字段 | 类型 | 必填 | 说明 |
|------|-------------|------|------|------|
| `image_to_pdf` | `orientation` | string | 否 | `auto` \| `portrait`，默认 `auto` |
| `pdf_compress` | `quality` | string | 是 | `high` \| `standard` \| `extreme` |
| `pdf_merge` | （无额外） | — | — | 以 `inputs` 顺序合并 |
| `office_to_pdf` | （无额外） | — | — | V1 可砍 |
| `ppt_generate` | 见 AI §5.3，通常走专用接口 | | | |
| `character_card` / `novel_chapter` | 见 AI 专用接口 | | | |

#### 响应示例（首次创建）

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "任务已提交",
  "data": {
    "taskId": "01HTASKPUBLICIDXXXXX",
    "type": "pdf_compress",
    "status": "queued",
    "progress": 10,
    "costQuota": 1,
    "timeoutAt": "2026-09-05T10:05:00.000+08:00",
    "resultExpiresAt": null,
    "resultExpired": false,
    "retryCount": 0,
    "errorCode": null,
    "errorClass": null,
    "userMsg": null,
    "createdAt": "2026-09-05T10:00:00.000+08:00"
  },
  "requestId": "req_01TASKCREATE...",
  "taskId": "01HTASKPUBLICIDXXXXX"
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 40002 | file_too_large | 文件过大，请压缩后再上传 |
| 40003 | quota_exhausted | 今日额度已用完，明天再来或开通会员 |
| 40005 | too_many_inflight_tasks | 进行中的任务已满（最多3个），请先到任务中心查看 |
| 40007 | idempotency_key_conflict | 重复提交的内容与首次不一致，请勿复用同一幂等键 |
| 40008 | idempotency_key_required | 缺少幂等键，请重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 4.2 任务列表

- **方法 / 路径：** `GET /v1/tasks`
- **鉴权：** 是

#### 请求参数（Query）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `cursor` | string | 否 | 上一页返回的 `nextCursor` |
| `limit` | integer | 否 | 默认 20，最大 50 |
| `status` | string | 否 | `pending`/`queued`/`running`/`succeeded`/`failed`/`cancelled` |
| `type` | string | 否 | 任务类型 |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "items": [
      {
        "taskId": "01HTASKPUBLICIDXXXXX",
        "type": "pdf_merge",
        "status": "succeeded",
        "progress": 100,
        "costQuota": 2,
        "resultExpired": false,
        "createdAt": "2026-09-05T09:00:00.000+08:00",
        "finishedAt": "2026-09-05T09:00:45.000+08:00"
      }
    ],
    "nextCursor": "eyJpZCI6MTIzfQ",
    "hasMore": true
  },
  "requestId": "req_01TASKLIST..."
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 4.3 任务详情

- **方法 / 路径：** `GET /v1/tasks/{taskId}`
- **鉴权：** 是
- **路径参数：** `taskId`（string，**public_id**）必填

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "taskId": "01HTASKPUBLICIDXXXXX",
    "type": "pdf_compress",
    "status": "succeeded",
    "progress": 100,
    "costQuota": 1,
    "timeoutAt": "2026-09-05T10:05:00.000+08:00",
    "resultExpiresAt": "2026-09-06T10:01:00.000+08:00",
    "resultExpired": false,
    "retryCount": 0,
    "errorCode": null,
    "errorClass": null,
    "userMsg": null,
    "inputMeta": { "quality": "standard", "inputBytes": 10485760 },
    "outputMeta": { "outputBytes": 3145728, "ratio": 0.3 },
    "outputs": [
      {
        "assetId": "9001",
        "filename": "compressed.pdf",
        "sizeBytes": 3145728,
        "mime": "application/pdf",
        "downloadUrl": "https://cos.example.com/...?sign=...",
        "downloadExpireAt": "2026-09-05T11:00:00.000+08:00"
      }
    ],
    "createdAt": "2026-09-05T10:00:00.000+08:00",
    "startedAt": "2026-09-05T10:00:05.000+08:00",
    "finishedAt": "2026-09-05T10:00:40.000+08:00"
  },
  "requestId": "req_01TASKDETAIL...",
  "taskId": "01HTASKPUBLICIDXXXXX"
}
```

> `resultExpired=true` 时 `downloadUrl` 为空，`userMsg` 可由客户端展示「已过期，请重新处理」。

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40009 | task_not_found | 任务不存在或无权访问 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 4.4 重试任务

- **方法 / 路径：** `POST /v1/tasks/{taskId}/retry`
- **鉴权：** 是
- **幂等键：** **`Idempotency-Key` 必填**（新一次重试须新 Key）
- **说明：** 仅 `failed` 且可重试且未超次数；再次预扣额度。

#### 请求参数

| 位置 | 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| path | `taskId` | string | 是 | public_id |
| header | `Idempotency-Key` | string | 是 | 新 UUID |
| body | — | — | 否 | 可空对象 `{}` |

#### 响应示例

同「创建任务」成功结构（`status` 多为 `queued`，`retryCount` +1）。

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40003 | quota_exhausted | 今日额度已用完，明天再来或开通会员 |
| 40005 | too_many_inflight_tasks | 进行中的任务已满（最多3个），请先到任务中心查看 |
| 40007 | idempotency_key_conflict | 重复提交的内容与首次不一致，请勿复用同一幂等键 |
| 40008 | idempotency_key_required | 缺少幂等键，请重试 |
| 40009 | task_not_found | 任务不存在或无权访问 |
| 40010 | task_not_retryable | 当前任务不可重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 4.5 取消任务

- **方法 / 路径：** `POST /v1/tasks/{taskId}/cancel`
- **鉴权：** 是
- **说明：** 成功取消则 **返还预扣额度**。

#### 请求参数

| 位置 | 字段 | 类型 | 必填 |
|------|------|------|------|
| path | `taskId` | string | 是 |
| body | — | object | 否，可 `{}` |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "任务已取消，额度已返还",
  "data": {
    "taskId": "01HTASKPUBLICIDXXXXX",
    "status": "cancelled",
    "quotaRefunded": true
  },
  "requestId": "req_01TASKCANCEL...",
  "taskId": "01HTASKPUBLICIDXXXXX"
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40009 | task_not_found | 任务不存在或无权访问 |
| 40011 | task_not_cancellable | 任务已结束，无法取消 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---


### 4.6 下载任务结果

- **方法 / 路径：** `GET /v1/tasks/{taskId}/download`
- **鉴权：** 是
- **说明：** 校验归属；仅 `succeeded` 且未过期；返回签名临时 URL（默认 **15 分钟**）。  
  过期返回 `40016`。详情接口在过期时 `outputs=[]` 且 `resultExpired=true`。对象键形如 `{env}/{userId}/results/{taskId}/result.pdf`。

#### 请求参数

| 位置 | 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|------|
| path | `taskId` | string | 是 | public_id |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": {
    "taskId": "01HTASKPUBLICIDXXXXX",
    "filename": "compressed.pdf",
    "sizeBytes": 3145728,
    "downloadUrl": "https://cos.example.com/...?sign=...",
    "expireAt": "2026-09-05T10:15:00.000+08:00"
  },
  "requestId": "req_01DOWNLOAD...",
  "taskId": "01HTASKPUBLICIDXXXXX"
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40009 | task_not_found | 任务不存在或无权访问 |
| 40016 | result_expired | 已过期，请重新处理 |
| 40017 | result_not_ready | 任务未完成，暂不可下载 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 40029 | rate_limited | 请求过于频繁，请稍后再试 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 4.7 删除任务（任务中心）

- **方法 / 路径：** `DELETE /v1/tasks/{taskId}`
- **鉴权：** 是（当前实现尚未强制 JWT；dev `user_id=0`）
- **说明：** 从任务中心移除记录（硬删行）。若仍有未结算预占则先返还再删。

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "ok",
  "data": { "taskId": "01HTASKPUBLICIDXXXXX", "deleted": true },
  "requestId": "req_01TASKDEL...",
  "taskId": "01HTASKPUBLICIDXXXXX"
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40009 | task_not_found | 任务不存在或无权访问 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

## 5. AI 生成

### 5.1 角色卡生成（草稿）

- **方法 / 路径：** `POST /v1/ai/character-card/generate`
- **鉴权：** 是
- **幂等键：** **`Idempotency-Key` 必填**
- **说明：** 生成可编辑草稿（JSON）；出图可同事务异步建 `character_card` 任务或返回 `renderTaskId`。须双向内容审核。

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 角色名；可空由模型补全 |
| `premise` | string | 是 | 设定摘要；**≤ 2000 字符**（前后端双校验） |
| `personality` | string | 否 | 性格 |
| `appearance` | string | 否 | 外貌 |
| `abilities` | string | 否 | 能力 |
| `catchphrase` | string | 否 | 口头禅 |
| `taboos` | string | 否 | 禁忌 |
| `extra` | object | 否 | 扩展字段 |
| `renderImage` | boolean | 否 | 默认 `true`，是否排队出图 |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "角色卡草稿已生成，请确认后保存",
  "data": {
    "cardId": "2001",
    "version": 1,
    "schemaVersion": "1",
    "payload": {
      "name": "林秋",
      "personality": "...",
      "appearance": "...",
      "abilities": "...",
      "catchphrase": "...",
      "taboos": "..."
    },
    "costQuota": 3,
    "renderTaskId": "01HRENDERTASKXXXX"
  },
  "requestId": "req_01CARD...",
  "taskId": "01HRENDERTASKXXXX"
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 40003 | quota_exhausted | 今日额度已用完，明天再来或开通会员 |
| 40005 | too_many_inflight_tasks | 进行中的任务已满（最多3个），请先到任务中心查看 |
| 40007 | idempotency_key_conflict | 重复提交的内容与首次不一致，请勿复用同一幂等键 |
| 40008 | idempotency_key_required | 缺少幂等键，请重试 |
| 42001 | content_blocked | 内容未通过安全审核，请修改后重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 52001 | ai_upstream_failed | AI 服务暂不可用，请稍后重试 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 5.2 PPT 大纲

- **方法 / 路径：** `POST /v1/ai/ppt/outline`
- **鉴权：** 是
- **幂等键：** 建议可选（大纲默认不扣或少扣，见蓝图待决策）
- **说明：** 仅生成可编辑大纲，**不**直接出 pptx。

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `topic` | string | 是 | 主题 |
| `pageCount` | integer | 是 | 5–15 |
| `templateId` | string | 是 | 模板 ID |
| `audience` | string | 否 | 受众说明 |
| `language` | string | 否 | 默认 `zh-CN` |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "大纲已生成，请编辑确认后再导出 PPT",
  "data": {
    "outlineId": "out_01XYZ",
    "outlineVersion": 1,
    "templateId": "tpl_basic_01",
    "pages": [
      { "title": "封面", "bullets": ["副标题"] },
      { "title": "目录", "bullets": ["背景", "方案", "总结"] }
    ],
    "costQuota": 0
  },
  "requestId": "req_01PPTOUTLINE..."
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 42001 | content_blocked | 内容未通过安全审核，请修改后重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 52001 | ai_upstream_failed | AI 服务暂不可用，请稍后重试 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 5.3 PPT 生成

- **方法 / 路径：** `POST /v1/ai/ppt/generate`
- **鉴权：** 是
- **幂等键：** **`Idempotency-Key` 必填**
- **说明：** **必须**携带用户确认后的 `outlineId` + `outlineVersion`；创建异步任务并预扣额度。

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `outlineId` | string | 是 | 大纲 ID |
| `outlineVersion` | integer | 是 | 用户编辑确认后的版本号 |
| `templateId` | string | 是 | 须与大纲一致或允许的模板 |
| `pages` | object[] | 是 | 用户最终确认的页面内容（防服务端旧缓存） |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "PPT 生成任务已提交",
  "data": {
    "taskId": "01HPPTTASKXXXX",
    "type": "ppt_generate",
    "status": "queued",
    "progress": 10,
    "costQuota": 5,
    "timeoutAt": "2026-09-05T10:10:00.000+08:00"
  },
  "requestId": "req_01PPTGEN...",
  "taskId": "01HPPTTASKXXXX"
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 40003 | quota_exhausted | 今日额度已用完，明天再来或开通会员 |
| 40005 | too_many_inflight_tasks | 进行中的任务已满（最多3个），请先到任务中心查看 |
| 40007 | idempotency_key_conflict | 重复提交的内容与首次不一致，请勿复用同一幂等键 |
| 40008 | idempotency_key_required | 缺少幂等键，请重试 |
| 40012 | outline_version_mismatch | 大纲已变更，请重新确认后再生成 |
| 42001 | content_blocked | 内容未通过安全审核，请修改后重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 52001 | ai_upstream_failed | AI 服务暂不可用，请稍后重试 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 5.4 小说大纲

- **方法 / 路径：** `POST /v1/ai/novel/outline`
- **鉴权：** 是
- **说明：** 创建设定/总纲；输入长度受蓝图 token 上限约束。

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 作品标题；建议 ≤ 200 字 |
| `premise` | string | 是 | 设定；**≤ 2000 字符** |
| `style` | string | 否 | 文风 |
| `targetChapters` | integer | 否 | 规划章数，≤30 |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "大纲已生成，请确认后再写正文",
  "data": {
    "projectId": "3001",
    "version": 1,
    "title": "星港夜航",
    "outline": "……总纲文本……",
    "chapterOutlines": [
      { "chapterNo": 1, "title": "靠港", "summary": "..." }
    ],
    "costQuota": 0
  },
  "requestId": "req_01NOVELOUT..."
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 40013 | input_too_long | 设定过长，请精简后再试 |
| 42001 | content_blocked | 内容未通过安全审核，请修改后重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 52001 | ai_upstream_failed | AI 服务暂不可用，请稍后重试 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

### 5.5 小说章节生成

- **方法 / 路径：** `POST /v1/ai/novel/chapter`
- **鉴权：** 是
- **幂等键：** **`Idempotency-Key` 必填**
- **说明：** `max_output_tokens` ≤ 2048；异步任务预扣 4 点。

#### 请求参数（Body）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `projectId` | string | 是 | 小说项目 ID |
| `projectVersion` | integer | 是 | 乐观锁，防大纲过期 |
| `chapterNo` | integer | 是 | 章序号 |
| `chapterTitle` | string | 否 | 章标题 |
| `instruction` | string | 否 | 本章额外写作要求 |
| `maxOutputTokens` | integer | 否 | 默认 2048，且不得超过 2048 |

#### 响应示例

```json
{
  "code": 0,
  "message": "ok",
  "user_msg": "章节生成任务已提交",
  "data": {
    "taskId": "01HNOVELCHXXXX",
    "type": "novel_chapter",
    "status": "queued",
    "progress": 10,
    "costQuota": 4,
    "projectId": "3001",
    "chapterNo": 1,
    "timeoutAt": "2026-09-05T10:10:00.000+08:00"
  },
  "requestId": "req_01NOVELCH...",
  "taskId": "01HNOVELCHXXXX"
}
```

#### 错误码

| code | message | user_msg |
|------|---------|----------|
| 40001 | param_invalid | 参数有误，请检查后重试 |
| 40003 | quota_exhausted | 今日额度已用完，明天再来或开通会员 |
| 40005 | too_many_inflight_tasks | 进行中的任务已满（最多3个），请先到任务中心查看 |
| 40007 | idempotency_key_conflict | 重复提交的内容与首次不一致，请勿复用同一幂等键 |
| 40008 | idempotency_key_required | 缺少幂等键，请重试 |
| 40014 | chapter_limit_exceeded | 章节数量已达上限 |
| 40015 | project_version_mismatch | 作品已更新，请刷新后重试 |
| 42001 | content_blocked | 内容未通过安全审核，请修改后重试 |
| 41001 | unauthorized | 登录已失效，请重新登录 |
| 52001 | ai_upstream_failed | AI 服务暂不可用，请稍后重试 |
| 50001 | internal_error | 服务繁忙，请稍后重试 |

---

## 6. 任务终态常见错误（轮询详情时）

任务 `status=failed` 时，详情中的 `errorCode` / `errorClass` / 客户端应展示的文案：

| errorCode | errorClass | 建议 user_msg |
|-----------|------------|---------------|
| 40004 | user | 含加密 PDF，请先解除保护（**释放预占、不扣费**） |
| 42001 | safety | 内容未通过安全审核，请修改后重试（默认不返还额度） |
| 50001 | system | 服务繁忙，请稍后重试 |
| 50002 | system | 排队超时，额度已返还，请稍后重试 |
| 53001 | timeout | 处理超时，额度已返还，请稍后重试 |

---

## 7. 错误码总表（初稿）

| code | message | 典型 user_msg | 分类 |
|------|---------|---------------|------|
| 0 | ok | ok | — |
| 40001 | param_invalid | 参数有误，请检查后重试 | user |
| 40002 | file_too_large | 文件过大，请压缩后再上传 | user |
| 40003 | quota_exhausted | 今日额度已用完，明天再来或开通会员 | user |
| 40004 | pdf_encrypted | 含加密 PDF，请先解除保护 | user |
| 40005 | too_many_inflight_tasks | 进行中的任务已满（最多3个），请先到任务中心查看 | user |
| 40007 | idempotency_key_conflict | 重复提交的内容与首次不一致，请勿复用同一幂等键 | user |
| 40008 | idempotency_key_required | 缺少幂等键，请重试 | user |
| 40009 | task_not_found | 任务不存在或无权访问 | user |
| 40010 | task_not_retryable | 当前任务不可重试 | user |
| 40011 | task_not_cancellable | 任务已结束，无法取消 | user |
| 40012 | outline_version_mismatch | 大纲已变更，请重新确认后再生成 | user |
| 40013 | input_too_long | 设定过长，请精简后再试 | user |
| 40014 | chapter_limit_exceeded | 章节数量已达上限 | user |
| 40015 | project_version_mismatch | 作品已更新，请刷新后重试 | user |
| 40016 | result_expired | 已过期，请重新处理 | user |
| 40017 | result_not_ready | 任务未完成，暂不可下载 | user |
| 40029 | rate_limited | 请求过于频繁，请稍后再试 | user |
| 41001 | unauthorized | 登录已失效，请重新登录 | auth |
| 41002 | wx_login_failed | 登录失败，请稍后重试 | auth |
| 42001 | content_blocked | 内容未通过安全审核，请修改后重试 | safety |
| 50001 | internal_error | 服务繁忙，请稍后重试 | system |
| 50002 | queue_wait_timeout | 排队超时，额度已返还，请稍后重试 | system |
| 52001 | ai_upstream_failed | AI 服务暂不可用，请稍后重试 | system |
| 53001 | task_timeout | 处理超时，额度已返还，请稍后重试 | timeout |

权威实现应落在 `packages/oc_shared/error_codes.py`，与本文及开发规范 §5.4 同步演进。

---

## 8. OpenAPI 3.0（YAML）

以下为与上文等价的 OpenAPI 3.0 初稿，可导入 Swagger UI / Stoplight；字段以契约为准，落地时由 FastAPI 生成并对照 diff。

```yaml
openapi: 3.0.3
info:
  title: Office Craft API
  description: |
    文匠工具 / Office Craft 小程序后端 API 契约初稿。
    统一包络：code / message / user_msg / data / requestId / taskId。
  version: 0.2.0
servers:
  - url: https://api.example.com
    description: production-placeholder
  - url: http://127.0.0.1:8000
    description: local
tags:
  - name: auth
  - name: me
  - name: uploads
  - name: tasks
  - name: ai

paths:
  /v1/auth/wx-login:
    post:
      tags: [auth]
      summary: 微信登录
      operationId: wxLogin
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [code]
              properties:
                code:
                  type: string
                  description: wx.login 临时 code
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"
              examples:
                success:
                  value:
                    code: 0
                    message: ok
                    user_msg: ok
                    data:
                      accessToken: eyJhbGciOiJIUzI1NiIs...
                      expiresIn: 7200
                      refreshToken: rt_...
                      refreshExpiresIn: 2592000
                      user:
                        id: "10001"
                        nickname: null
                        avatarUrl: null
                    requestId: req_01LOGIN


  /v1/auth/refresh:
    post:
      tags: [auth]
      summary: 刷新 accessToken
      operationId: refreshToken
      security: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [refreshToken]
              properties:
                refreshToken: { type: string }
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/tasks/{taskId}/download:
    get:
      tags: [tasks]
      summary: 获取签名下载 URL
      operationId: downloadTaskResult
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/TaskId"
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/me:
    get:
      tags: [me]
      summary: 当前用户
      operationId: getMe
      security:
        - bearerAuth: []
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/me/quota:
    get:
      tags: [me]
      summary: 查询额度
      operationId: getMyQuota
      security:
        - bearerAuth: []
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/uploads/credential:
    post:
      tags: [uploads]
      summary: 申请上传凭证
      operationId: createUploadCredential
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [taskType, fileCount]
              properties:
                taskType:
                  type: string
                  enum:
                    - image_to_pdf
                    - pdf_compress
                    - pdf_merge
                    - office_to_pdf
                    - character_card
                    - ppt_generate
                    - novel_chapter
                fileCount:
                  type: integer
                  minimum: 1
                totalSizeBytes:
                  type: integer
                  minimum: 1
                filenameHints:
                  type: array
                  items:
                    type: string
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/tasks:
    post:
      tags: [tasks]
      summary: 创建任务（预扣额度）
      operationId: createTask
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/IdempotencyKeyRequired"
        - $ref: "#/components/parameters/XRequestId"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateTaskRequest"
      responses:
        "200":
          description: 幂等重放或业务结果
          headers:
            Idempotent-Replayed:
              schema:
                type: string
                enum: ["true"]
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"
        "201":
          description: 首次创建成功
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"
    get:
      tags: [tasks]
      summary: 任务列表（cursor 分页）
      operationId: listTasks
      security:
        - bearerAuth: []
      parameters:
        - name: cursor
          in: query
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
            minimum: 1
            maximum: 50
        - name: status
          in: query
          schema:
            $ref: "#/components/schemas/TaskStatus"
        - name: type
          in: query
          schema:
            $ref: "#/components/schemas/TaskType"
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/tasks/{taskId}:
    get:
      tags: [tasks]
      summary: 任务详情
      operationId: getTask
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/TaskId"
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"
    delete:
      tags: [tasks]
      summary: 删除任务（任务中心）
      operationId: deleteTask
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/TaskId"
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/tasks/{taskId}/retry:
    post:
      tags: [tasks]
      summary: 重试任务
      operationId: retryTask
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/TaskId"
        - $ref: "#/components/parameters/IdempotencyKeyRequired"
      requestBody:
        required: false
        content:
          application/json:
            schema:
              type: object
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/tasks/{taskId}/cancel:
    post:
      tags: [tasks]
      summary: 取消任务（返还预扣）
      operationId: cancelTask
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/TaskId"
      requestBody:
        required: false
        content:
          application/json:
            schema:
              type: object
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/ai/character-card/generate:
    post:
      tags: [ai]
      summary: 生成角色卡草稿（可含出图任务）
      operationId: generateCharacterCard
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/IdempotencyKeyRequired"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [premise]
              properties:
                name: { type: string }
                premise: { type: string }
                personality: { type: string }
                appearance: { type: string }
                abilities: { type: string }
                catchphrase: { type: string }
                taboos: { type: string }
                extra: { type: object, additionalProperties: true }
                renderImage: { type: boolean, default: true }
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/ai/ppt/outline:
    post:
      tags: [ai]
      summary: 生成 PPT 大纲（须二次编辑）
      operationId: generatePptOutline
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [topic, pageCount, templateId]
              properties:
                topic: { type: string }
                pageCount: { type: integer, minimum: 5, maximum: 15 }
                templateId: { type: string }
                audience: { type: string }
                language: { type: string, default: zh-CN }
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/ai/ppt/generate:
    post:
      tags: [ai]
      summary: 确认大纲后生成 PPT 任务
      operationId: generatePpt
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/IdempotencyKeyRequired"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [outlineId, outlineVersion, templateId, pages]
              properties:
                outlineId: { type: string }
                outlineVersion: { type: integer, minimum: 1 }
                templateId: { type: string }
                pages:
                  type: array
                  items:
                    type: object
                    required: [title]
                    properties:
                      title: { type: string }
                      bullets:
                        type: array
                        items: { type: string }
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/ai/novel/outline:
    post:
      tags: [ai]
      summary: 生成小说大纲/项目
      operationId: generateNovelOutline
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [title, premise]
              properties:
                title: { type: string }
                premise: { type: string }
                style: { type: string }
                targetChapters: { type: integer, minimum: 1, maximum: 30 }
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

  /v1/ai/novel/chapter:
    post:
      tags: [ai]
      summary: 生成小说章节任务
      operationId: generateNovelChapter
      security:
        - bearerAuth: []
      parameters:
        - $ref: "#/components/parameters/IdempotencyKeyRequired"
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [projectId, projectVersion, chapterNo]
              properties:
                projectId: { type: string }
                projectVersion: { type: integer, minimum: 1 }
                chapterNo: { type: integer, minimum: 1 }
                chapterTitle: { type: string }
                instruction: { type: string }
                maxOutputTokens: { type: integer, minimum: 1, maximum: 2048, default: 2048 }
      responses:
        "200":
          description: 包络响应
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiEnvelope"

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  parameters:
    IdempotencyKeyRequired:
      name: Idempotency-Key
      in: header
      required: true
      schema:
        type: string
        format: uuid
      description: 客户端生成的幂等键，24h 内同用户唯一
    XRequestId:
      name: X-Request-Id
      in: header
      required: false
      schema:
        type: string
    TaskId:
      name: taskId
      in: path
      required: true
      schema:
        type: string
      description: 任务 public_id

  schemas:
    ApiEnvelope:
      type: object
      required: [code, message, user_msg, data, requestId]
      properties:
        code:
          type: integer
          description: 0 成功，非 0 见错误码表
        message:
          type: string
        user_msg:
          type: string
          description: 用户可见中文
        data:
          nullable: true
          description: 业务载荷
        requestId:
          type: string
        taskId:
          type: string
          nullable: true

    TaskType:
      type: string
      enum:
        - image_to_pdf
        - pdf_compress
        - pdf_merge
        - office_to_pdf
        - character_card
        - ppt_generate
        - novel_chapter

    TaskStatus:
      type: string
      enum:
        - pending
        - queued
        - running
        - succeeded
        - failed
        - cancelled

    CreateTaskRequest:
      type: object
      required: [type, inputs]
      properties:
        type:
          $ref: "#/components/schemas/TaskType"
        uploadId:
          type: string
        inputs:
          type: array
          minItems: 1
          items:
            type: object
            required: [cosKey]
            properties:
              cosKey: { type: string }
              filename: { type: string }
              sizeBytes: { type: integer }
        params:
          type: object
          additionalProperties: true
          description: |
            pdf_compress.quality: high|standard|extreme;
            image_to_pdf.orientation: auto|portrait

    ErrorCode:
      type: integer
      description: |
        0,40001,40002,40003,40004,40005,40007,40008,40009,40010,40011,
        40012,40013,40014,40015,40016,40017,40029,41001,41002,42001,50001,50002,52001,53001
```

---

## 9. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1-draft | 2026-09-05 | 初稿：覆盖蓝图 API 面全部接口；含 Markdown + OpenAPI 3.0 |
| v0.2-draft | 2026-09-05 | 对齐双 Token/refresh、download、限流 40029、AI 2000 字限制 |
| v0.3-draft | 2026-09-07 | 本地上传代传、实现备注 |
| v0.4-draft | 2026-09-07 | download/retry 已落地说明；补 DELETE 任务；对齐进度 |

## 10. 相关文档

- [项目蓝图](./01-项目蓝图.md)
- [开发规范](./02-开发规范.md)
- [数据模型](./04-数据模型.md)
- [启动步骤](./05-启动步骤.md)
- [排期与测试](./06-排期与测试.md)
- [项目进度](./07-项目进度.md)
