# Leafora农业助手：启动、配置与验收

交付日期：2026-10-01。入口：Web管理端「智能分析」(`/platform/analysis`)。
本次只开发Web助手；不修改首页、登录、设备启停、Jetson或小程序协议。
烟田详情与巡检详情各增加一个带当前对象的助手分析入口。

## 当前已交付

- DeepSeek V4.1 Flash流式问答、白名单工具调用、多轮会话与持久化历史。
- 16个限定工具：自己的烟田、设备状态、巡检筛选、识别统计、环境统计、风险分区、同田巡检比较、地点确认、天气与预警、知识检索、联网检索、授权图片观察。
- 当前天气、24小时预报、1–7天每日预报及官方预警；保留服务单位与归因链接。部分天气接口失败仍展示可用部分，并明确缺失。
- 私有文档与图片上传。文字型PDF最多200页；DOCX/TXT/MD支持中文关键词检索。文档20MB、图片10MB，每次最多5份文档与3张图片；扫描PDF不提供OCR。
- 证据引用与原始查询结果，分类表、温湿度独立曲线、天气卡片；Markdown和CSV导出。
- 取消、重连与持久SSE事件回放；重复请求幂等；超时和失败保留部分回答；关闭服务时取消后台回答并保留记录。
- 每用户默认每日100次、已记录500000 tokens上限，最多2个活跃回答；单会话只允许1个回答；单次180秒、6轮、最多12次工具查询、2次联网搜索。
- 无模型配置时仅展示明确标注的结构化读取结果，不假装完成知识推理或天气查询。

未实现自动控制、无人机运动控制、模型训练、向量数据库、扫描件OCR、定时自主监控、自动病害确诊或农药处方。这些不属于本版只读助手。

## 开发机状态

已安装新增前后端依赖；本机数据库已迁移到`0008`，仅新增六张`assistant_*`表；已幂等导入3条起步知识摘要。
已配置的DeepSeek连接通过一次无私人数据的真实请求测试。天气和联网搜索未配置，暂未做真实服务验收。
没有填写、展示或改写你的密钥。代码改动后请按你原有方式重启后端，前端开发服务器会热更新；没有替你停止原有进程。

检查时本机8000端口的新增助手接口仍返回404，说明运行进程尚未加载这版代码；验收前需重启原后端。

## 在其他环境启动

在`Web/backend`执行：

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m alembic upgrade 0008
.venv/Scripts/python.exe scripts/import_assistant_knowledge.py
.venv/Scripts/python.exe scripts/check_assistant.py
```

在`Web/frontend`执行`npm install`，开发用`npm run dev`，生产构建用`npm run build`。继续使用原有登录和部署方式。

`scripts/check_assistant.py --live-model`会发出一次简短收费模型请求；不发送平台记录或私有资料。默认检查不调用外部服务。

## 只在后端本地.env填写

| 能力 | 配置项 | 说明 |
| --- | --- | --- |
| 模型 | `DEEPSEEK_API_KEY` | API Key只保存在后端 |
| 模型名称 | `DEEPSEEK_MODEL=deepseek-flash` | 官方V4.1 Flash的API名称；不要填写产品展示名称 |
| 模型地址 | `DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions` | 默认已提供 |
| 天气 | `QWEATHER_API_HOST` | 和风控制台分配的专属API Host，不是官网地址 |
| 天气认证 | `QWEATHER_API_KEY`，或`QWEATHER_KEY_ID`、`QWEATHER_PROJECT_ID`、`QWEATHER_PRIVATE_KEY_PATH` | 有私钥路径时优先JWT；私钥文件保持受限权限，不入Git |
| 联网资料 | `TAVILY_API_KEY` | 默认优先农业农村部、农科院等权威域名；工具有公共知识搜索开关 |
| 文件 | `ASSISTANT_STORAGE_ROOT` | 默认`Web/backend/storage/assistant`；需持久卷、备份及受限文件权限 |

官方接口参考：[DeepSeek模型与能力](https://api-docs.deepseek.com/quick_start/pricing/)、[工具调用](https://api-docs.deepseek.com/guides/function_calling)、[和风实时天气](https://dev.qweather.com/docs/api/weather/weather-current/)、[每日预报](https://dev.qweather.com/docs/api/weather/weather-daily-forecast/)、[逐小时预报](https://dev.qweather.com/docs/api/weather/weather-hourly-forecast/)、[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search)。

天气套餐需能访问Geo城市查询、实时、逐小时、每日和预警接口。套餐缺少某项权限会被明确报告，不能靠填写模型Key代替天气数据服务。

## 数据与隐私边界

平台数据的权限来自现有用户JWT。工具只能读取当前用户拥有的对象，不接收客户端`user_id`，不提供任意SQL、HTTP、命令执行或业务写入能力。

启用模型后，问题、限量对话历史、查到的结构化摘要和相关私有文档片段会发送给模型服务；开启图片分析后，授权图片也会发送给模型。联网搜索只允许公共农业知识关键词，拦截对象编号、手机号、精细坐标和已知私有对象名称；不要在问题中要求联网搜索私人内容。搜索与天气属于其他独立外部服务。

新增助手DB会话不记录SQL参数或私有资料正文；密钥不进入工具结果、前端或对话。回答HTML净化、外部模型生成链接不直接变成交互链接，只有后端注册的证据可跳转；CSV对公式前缀转义。

私有附件删除是软删除：停止后续读取和检索，但既有回答中保存的引用片段不会自动抹除，原文件留在存储中以便人工恢复。会话删除移除助手记录，不删除业务巡检或附件；用户可另行删除资料。不包含自动物理清理任务，生产需自行制定保留与备份策略。

天气地点由用户明确提供，不使用模拟田块坐标。图像只辅助观察；无效环境记录不参与统计；失败或未完成识别不能解释为健康；目标数量、置信度、空间风险分均不是病害发生率。药剂或精确栽培阈值需要审核来源与当地农技人员复核。

## 扩充知识库

起步知识库只是少量平台解释和一条可追溯烟草研究摘要，不是完整农业百科。用户上传资料默认仅自己可检索，不会公开。

公共知识由维护者人工审阅后，通过`knowledge/assistant_starter.json`格式导入：

```powershell
.venv/Scripts/python.exe scripts/import_assistant_knowledge.py --manifest path/to/reviewed-summary.json
```

每项包含`id`（唯一KNOW_开头）、`title`、`publisher`、`reviewed_at`、`text`，有外部依据时填`url`和`published_at`。保持简短原创摘要、真实来源与明确适用作物；不要把私有资料或整篇受版权保护的文章放入公共清单。相同ID重复导入会更新自己的公共知识，内容未变不会重复入库。当前中文BM25检索最多选最近100份资料、10000个片段、返回6个相关片段；大规模语料再升级索引服务。

## 部署注意

数据库0008迁移不会清空现有表。不要执行降级以“刷新”页面，降级会移除助手表。此前的`/platform/assistant/ask`与`/platform/analysis/overview`仍兼容。

反向代理必须允许20MB文件、关闭SSE缓冲并延长读取超时。可将`Web/infrastructure/assistant.nginx.conf`中的助手专用location放入现有server中，调整upstream地址；没有自动改写现有代理配置。前缀/api不能被剥离。代理与应用限流、TLS和存储权限仍需按正式部署规范设置。

首版不依赖Redis/Celery：回答是Web进程内的有限异步任务，事件与内容存入数据库。取消当前进程任务可立即生效；另一进程会在查询或流式输出边界发现取消。进程重启后超过运行时限加30秒的未完成回答转为中断，不自动重复收费模型请求。token限额按供应商实际返回usage累计，是应用预算护栏，不是结算硬上限；异常未返回usage、正在运行的请求仍可能产生费用，请同时设置供应商额度。

## 验收清单

1. 打开「智能分析」，问普通烟草知识，检查中文回答和会话刷新后保留。
2. 选择自己的烟田/巡检，让助手汇总。点数字引用核对有效样本、缺失记录及识别来源；点击对应记录返回原详情。
3. 比较同田两次巡检，检查差值与可比性说明；不同烟田应拒绝直接比较。
4. 明确地区查询天气，核对温度单位、湿度百分比、预报时间、官方预警及归因链接；重名地区应先确认。
5. 上传文字PDF/DOCX/TXT/MD，问相关内容，检查片段和页码/段落。另一账号不能下载、检索或引用这份文件。
6. 开启图片分析上传图片，只给辅助观察，不自动改写任何检测记录；关闭图片分析时图片不能发出。
7. 断开网页连接后重开会话，查看保存内容；停止回答和重试提交不应生成重复收费运行。
8. 导出Markdown/CSV，核对来源与结构化值。恶意HTML不执行、虚构来源不能成为链接。
9. 天气/搜索未配置或接口失败时说明缺少能力，不编造数据。

自动验证：首次完整后端回归130项通过；最新助手23项加旧platform API3项共26项通过，覆盖超时与农业背景权限；前端生产构建、原有详情逻辑6项和隔离浏览器8组检查通过；一次真实模型连接通过。并行通信窗口改动后，全量回归曾发现任务模块3项时区比较错误（command_delivery.py），对应窗口已修补并继续通信契约联调，将自行完成最终全量回归；本窗口不跨模块修改。天气/搜索真实服务、农业建议质量与生产部署负载仍需你配置后验收。前端现有大依赖分包警告保留，未为助手重构全站。

新增API字段、幂等与兼容规则详见`ASSISTANT_API_CONTRACT.md`。三方根协议集成登记仍由项目总监窗口处理，本次不修改根目录协调文档。
