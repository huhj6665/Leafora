# Leafora 农业助手协议补充 v1

日期：2026-10-01。适用范围仅为 Web 助手；补充三方通信基线 0.2，不改变设备、MQTT、任务启停、身份及归属规则。根协议及集成登记由项目总监窗口负责，本文件提供可登记的完整增量。

所有接口要求用户 JWT，归属由服务器解析；不接受 user_id。普通响应继续使用 `{code,message,data}`。业务查询只读；新增写入仅限助手会话、运行、附件、资料和农业背景。

## 新增 HTTP

前缀 `/api/platform/assistant`：

- GET `/capabilities`：返回配置可用性，不返回凭据。
- GET/POST `/conversations`：列出/创建会话。
- GET/PATCH/DELETE `/conversations/{id}`：详情、修改标题/上下文、删除会话。
- POST `/conversations/{id}/runs`：`question,client_request_id,attachment_ids,web_enabled,image_enabled,context,regenerate_message_id`。同一会话及 client_request_id 幂等，重复请求内容不同返回409。question 2–4000字，最多3张图片及5份文档。
- GET `/runs/{id}`：运行与已保存回答。
- GET `/runs/{id}/events?after=N`：鉴权 SSE，持久事件序号用于重连；事件为 status/delta/evidence/done/error。运行结束状态为 COMPLETED/FAILED/CANCELLED/INTERRUPTED。
- POST `/runs/{id}/cancel`：取消运行，幂等。
- POST `/attachments`：multipart 文件上传，JPEG/PNG/WebP及文字型PDF/DOCX/TXT/MD。
- GET/DELETE `/attachments/{id}`：私有文件读取/软删除，删除即停止检索。
- GET `/attachments`：用户文档列表。
- GET/PATCH `/field-context/{field_id}`：助手专用作物、生育期、真实天气位置，不修改烟田或快照。
- GET `/runs/{id}/export?format=md|csv`：下载报告或证据表格。

context 可包含 field_id、inspection_id、crop、variety、growth_stage、location（用户明确指定的地区）；服务端先检查所有平台对象归属。模拟烟田位置不得自动作真实天气地点。

## 兼容与运行约束

旧 POST `/ask` 保持原请求及 answer/provider/model 返回结构；使用原有权限限定的结构化摘要。原 `/analysis/overview` 不变。新增接口不供设备及小程序调用。新增表使用独立 Alembic 0008 迁移，不删除现有表或记录。

同一会话只允许一个活跃运行，通过数据库条件更新取得执行权。网络断开不代表取消；事件可重读。进程重启后过期运行转为 INTERRUPTED，不自动重新调用收费模型。事件流使用 Bearer fetch，不在 URL 中传 JWT。

模型、天气、搜索均为后端调用，未配置时工具返回明确不可用结果，禁止捏造实时信息。工具输出视为资料不是指令。外部搜索不得发送私人数据。引用由后端证据注册表生成；未知引用不可变成链接。
