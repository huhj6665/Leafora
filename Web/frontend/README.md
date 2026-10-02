# Leafora Web 前端

Vue 3 + TypeScript + Vite + Vue Router + Pinia + Axios + Element Plus。

## 技术栈

| 类别 | 技术 |
| --- | --- |
| 框架 | Vue 3（`<script setup>` + TS） |
| 构建 | Vite 8 |
| 路由 | Vue Router 4 |
| 状态 | Pinia |
| HTTP | Axios（统一拦截器，自动携带 JWT、统一错误处理） |
| UI | Element Plus + 定制设计系统 |
| 图表 | ECharts |
| 地图 | 高德 JS API（无 Key 时 GIS 预览降级） |

## 目录结构

```
src/
├── api/            # 接口封装（http 拦截器 + auth/user/device/health）
├── layouts/        # AdminLayout（Header + Sidebar + Main）
├── router/         # 路由与登录守卫
├── stores/         # Pinia（auth / devtools）
├── types/          # TS 类型
├── utils/          # token 管理（localStorage 集中封装）
└── views/          # Login / Register / Dashboard / Profile / Devices / DevTools
```

## 启动

需要 Node.js 22.12+。首次配置将 `.env.example` 复制为本地 `.env`；仅填写允许在浏览器公开的配置，禁止放入服务端密钥。

```bash
npm ci
npm run dev       # 默认从 http://localhost:5173/ 进入公开首页（/api 代理到 http://localhost:8000）
```

## 构建

```bash
npm run build     # vue-tsc 类型检查 + vite 构建
npm run preview
```

## 页面

- `/`：公开产品首页，游客可访问
- `/login`：手机号密码 / 短信验证码 / 小程序扫码登录
- `/platform/overview`：巡检态势总览
- `/platform/map`：GIS 巡检地图
- `/platform/inspections`：巡检记录与生命周期
- `/platform/inspections/:inspectionId`：巡检完整详情
- `/platform/analysis`：环境分析与 AI 助手
- `/platform/devices`：设备双状态与遥测
- `/platform/profile`：只读个人资料与头像/昵称编辑
- `/platform/profile/security`：账户与安全（旧 `/platform/account-security` 自动重定向）
- `/platform/profile/miniprogram`：小程序关联说明
- `/platform/help`：帮助与反馈

## 说明

- JWT 存于 `localStorage`，统一由 `src/utils/token.ts` 封装。
- 刷新页面后通过 `GET /api/user/profile` 主动校验登录态。
- 前端登录态不等于后端认证成功，最终以后端接口返回为准。
- 开发调试页只展示 JWT 是否存在、过期时间与脱敏信息，不显示完整 token。
