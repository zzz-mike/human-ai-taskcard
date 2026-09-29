# 秘书接口协议

方向：浏览器 → 莱茵生命同源接口桥 → `127.0.0.1:8866` 秘书后端。响应必须是 JSON，成功响应 `schema_version` 为 `"1.0"`。桥拒绝重定向、任意目标地址及非白名单路由；请求超时 10 秒，桥的上游响应上限 2 MiB，浏览器客户端接收上限 1 MiB，因此后端应控制在 1 MiB 内。

## 读取

浏览器路径前缀 `/api/secretary/widgets/v1/` 映射为后端 `/api/widgets/v1/`，请求需带 `X-Rhine-Local: 1`。

| 路由 | 用途与查询参数 |
| --- | --- |
| catalog | 组件目录，无查询参数 |
| revision | 轻量版本号，无查询参数；返回 revision、poll_seconds: 2 |
| priorities、todo、triage、projects、today、schedule | 秘书主题；project_id、limit（1–100）、offset、snapshot_revision |
| item | 单事项；item_id |
| items | 事项搜索；query、status、project_id、limit（1–50）、offset、snapshot_revision |
| item-detail | 事项详情；item_id、section（overview/evidence/history）、limit（1–30）、offset、snapshot_revision |
| project-detail | 项目详情；project_id、section（overview/progress/items/conversation/files/finance）、limit（1–30）、offset、snapshot_revision |

`catalog` 必须包含六个秘书主题；旧的 priorities 保留协议兼容，前端 offeredWidgetIds 不再推荐它。桥会过滤目录中的其他主题。`timezone` 固定为 `Asia/Shanghai`。条目、目录和分页响应的准确字段与类型见 secretary-client.ts 中 WidgetCatalog、WidgetResponse、WidgetItem；详情接口返回未知类型，由宿主的详情解析器进一步验证。

主题响应需包含 schema_version、widget_id、title、status、generated_at、data_updated_at、timezone、message、items、metrics、points、total、truncated、source。metrics/points 可为空数组。source 至少含 id、label。空数据应使用 status: empty 并给出正确时间和说明；不能假装已读取真实资料。

## 可选人工分类

浏览器读取 `/api/local/v1/capabilities` 获得 secretary_review、secretary_details、secretary_project_review。仅启用写入时提供 secretary_review_token。浏览器 POST 须带同源 Origin、X-Rhine-Local、X-Rhine-Action-Token 和 application/json 正文。

- POST `review`：精确包含 request_id（UUID）、item_id、expected_revision、action，以及对应字段。action=status 时提供 status（active/completed/cancelled/observing）；action=project 时提供 project；action=undo 时提供 field（status/project）。上限 4 KiB。
- POST `project-review`：精确包含 request_id、project_id、expected_revision、action，以及 note 或 pinned。action=note 时 note 精确包含 stage、blocker、next_step、owner 四个文本；action=pin 时 pinned 为布尔值。上限 16 KiB。

接口桥在服务端调用后端 GET `/api/widgets/v1/review-session`，携带 X-Rhine-Bridge: 1；后端返回 schema_version、scope: widgets:review、review_token。随后桥向后端同名 POST 接口发送 X-Widget-Review-Token。后端令牌不会返回浏览器。

后端负责真正的事务、持久化、权限、expected_revision 冲突检查及 request_id 幂等校验，接口桥本身不实现业务数据库。事项写入成功应返回 ok: true、duplicate、schema_version、item、revision。冲突返回 HTTP 409 和 code: revision_conflict，可携带 current_item 或 current_project；客户端重新读取后再决定操作。

源码由已有接口实现分离并收窄范围。包内不包含后端业务程序；仅有此协议或接口桥不能代替兼容后端。
