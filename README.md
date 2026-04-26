# Proxy2Panel

黑红风代理管理台，面向 Argosbx / Xray 的服务器运维场景。

## 功能
- 总览看板
- 节点切换、收藏、改名
- 节点全测速与健康度分级
- 流量走势
- Xray / Argo 控制动作
- 单节点诊断与主流站点测速
- Clash / Shadowrocket 订阅中心
- 登录失败锁定

## 本地开发

### 后端
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
$env:PROXY_ADMIN_DEMO='1'
$env:PROXY_ADMIN_DEFAULT_PASSWORD='admin'
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8781
```

### 前端
```powershell
cd frontend
npm install
npm run dev
```

## 前端构建
```powershell
cd frontend
npm run build
Copy-Item -Path .\dist -Destination ..ackend\static -Recurse -Force
```

## 服务器部署
- 部署模板见 `deploy/proxy-admin.service`
- 固定域名 tunnel 模板见 `deploy/proxy-admin-fixed-tunnel.service`
- 环境变量模板见 `deploy/proxy-admin.env.example`
- 安装脚本示例见 `deploy/server_install.sh`

## 订阅接口
- Clash: `/api/subscriptions/clash?token=<token>`
- Shadowrocket: `/api/subscriptions/shadowrocket?token=<token>`

## 兼容提示
Shadowrocket 对较新的 VLESS 加密能力支持可能不完整，出现“导入成功但节点不可用”时，优先检查客户端兼容性，而不是直接判断订阅失败。

## Shadowrocket 专用兼容方案
- 推荐通过单独的 Shadowrocket 订阅入口导入
- 该入口预留给不带新型 VLESS 加密能力的兼容节点
- 服务模板见 `deploy/proxy-admin-shadowrocket-tunnel.service`
