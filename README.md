# Interview-XeroDemo

这是一个用于 Xero 面试演示的 Python Web 应用，集成 Xero OAuth2 授权流程。

## 目录结构

- `pyproject.toml`：项目元数据与依赖管理
- `src/xerodemo/`：Python 包代码
- `tests/`：单元测试
- `db/`：SQLite 数据库文件（自动创建，已 gitignore）
- `docs/openapi.yaml`：OpenAPI/Swagger 接口文档

## 快速开始

1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

python -m pip install -U pip
python -m pip install -e .
```

2. 配置 Xero OAuth2 凭证

```bash
cp .env.example .env
# 编辑 .env，填入你的 XERO_CLIENT_ID 和 XERO_CLIENT_SECRET
```

### 环境变量

| 变量 | 说明 | 必需 |
|-----|------|-----|
| `XERO_CLIENT_ID` | 应用 Client ID | ✓ |
| `XERO_CLIENT_SECRET` | 应用 Client Secret | ✓ |
| `XERO_REDIRECT_URI` | 回调 URL | ✓ Web 需设为 `http://localhost:5000/auth/xero/callback`） |
| `DATABASE_URL` | 数据库连接字符串 | ✗（默认 `sqlite:///db/xerodemo.db`，首次启动自动创建 `db/` 目录和数据库文件） |
| `SECRET_KEY` | Flask 会话密钥 | ✗（生产环境必须设置。生成方式：`python3 -c "import secrets; print(secrets.token_hex(32))"`） |

### Web 应用使用

启动 Web 服务器：

```bash
xerodemo web --port 5000
```

然后在浏览器中打开 `http://localhost:5000`：

1. **主页**：显示登录/注册选项，或已登录用户的仪表板链接
2. **登录**：输入邮箱和密码，或点击"使用 Xero 登录"（OAuth）
3. **注册**：创建新账户，选择邮箱/密码或 OAuth 自动填充
4. **OAuth 流程**（Web）：
   - 点击"使用 Xero 登录"
   - 跳转到 Xero 授权页面
   - 授权后自动返回到应用
   - 自动登录或显示带 Xero 信息预填的注册表单
5. **仪表板**：显示用户信息、Xero 连接状态
6. **登出**：导航栏和仪表板均有登出按钮，登出时清理 OAuth token

### Docker 运行

1. 配置环境变量（确保 `.env` 文件存在，同上）

2. 构建并启动

```bash
docker compose up --build
```

3. 打开 `http://localhost:5000`

停止服务：`docker compose down`
停止并清除数据：`docker compose down -v`

### API 文档

接口文档使用 OpenAPI 3.0 规范，位于 [`docs/openapi.yaml`](docs/openapi.yaml)。

## 数据存储

### SQLite 数据库

Web 应用使用 SQLite 存储数据，数据库文件位于 `db/xerodemo.db`（首次启动自动创建）。

**数据模型**：

| 模型 | 说明 |
|------|------|
| `User` | 用户账户（邮箱、密码哈希、Xero 关联信息） |
| `OAuthToken` | OAuth2 令牌持久化（access_token、refresh_token、过期时间等） |

### OAuth Token 持久化

Web 流程中的 OAuth token 持久化到 SQLite，而非文件：

- **已有用户**：OAuth 回调后 token 直接存入 `oauth_tokens` 表
- **新用户**：token 先存为 pending 记录（`user_id=NULL`），通过 `session_key` 临时关联；注册或登录后绑定到用户
- **Token 刷新**：token 过期时自动使用 `refresh_token` 获取新 token（`get_valid_token` 工具函数）
- **登出清理**：用户登出时删除其所有 OAuth token 记录

## 安全设计

### State 参数校验

OAuth 回调中的 `state` 参数使用时序安全比较（`hmac.compare_digest`），防止 timing attack。State 值使用 `secrets.token_urlsafe(32)` 生成，且单次使用（`session.pop`）防止 replay attack。

### Client Secret 保护

`XERO_CLIENT_SECRET` 仅在服务端 token exchange 和 refresh 时使用，绝不传入模板或 API 响应，不会暴露到前端。

### Token 不返回前端

OAuth token（access_token、refresh_token）仅存储在服务端 SQLite 数据库中。Flask session 中只保留 `user_id` 和 `email`，不包含任何 token 数据。新用户注册时通过 `session_key`（随机字符串）关联 pending token，避免将 token 编码进签名 cookie。

### 密码强度要求

注册密码必须至少 8 位字符，且同时包含字母和数字。

## 开发进度

### Phase 1: 基础架构 ✅
- [x] 实现 OAuth2 Authorization Code Flow（Web）
- [x] 实现 Token 存储与读取

### Phase 2: Web 应用 ✅
- [x] 创建 Flask 应用工厂与蓝图结构
- [x] 实现 SQLAlchemy User 和 OAuthToken 模型
- [x] 创建认证路由（登录、注册、登出）
- [x] 实现 OAuth2 Web 流程（XeroOAuth2 类）
- [x] OAuth 回调处理与用户自动创建/预填
- [x] 创建 HTML 模板（5 个：base, index, login, signup, dashboard）
- [x] 实现用户仪表板与 Xero 连接显示
- [x] 创建 `xerodemo web` 命令启动 Flask 服务

### Phase 3: 数据持久化与安全加固 ✅
- [x] SQLite 数据库移至 `db/` 目录，自动创建
- [x] 新增 `OAuthToken` 模型，OAuth token 持久化到 SQLite
- [x] 实现 pending token 机制（新用户注册前 token 安全暂存）
- [x] 实现 Refresh Token 自动刷新逻辑
- [x] 登出时清理 OAuth token 记录
- [x] Dashboard 添加登出按钮
- [x] State 参数时序安全校验（`hmac.compare_digest`）
- [x] 确保 Client Secret 不暴露到前端
- [x] 确保 Token 不返回前端（session 仅存 user_id）
- [x] 重复注册处理（提示登录以绑定 Xero）
- [x] 登录后自动绑定 pending Xero token
- [x] 密码强度校验（8 位以上，字母+数字）
- [x] 清理 `web/__init__.py` 重复模型定义
- [x] OpenAPI 接口文档
