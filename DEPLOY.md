# 部署文档（DEPLOY.md）

Python 在线编程与自动判题平台（COBEBUDDY）的完整部署指南。

- 技术栈：Flask + SQLAlchemy + Gunicorn + Docker（判题沙箱）+ PostgreSQL 数据库容器
- 仓库：https://github.com/Yunye211/panti
- 线上环境：阿里云轻量应用服务器（成都 2C2G），`http://47.108.187.168:5000`

## 架构（当前线上形态）

```
浏览器 ──> 公网 IP:5000 ──> docker-compose
                              ├── cobebuddy：Flask 应用（gunicorn 多线程）
                              │     └── 判题沙箱（app/sandbox.py，子进程 + 模块拦截 + resource 限制）
                              └── db：PostgreSQL（与 Web 同机，数据卷持久化）
```

数据库采用**同机 PostgreSQL 容器**（早期用 Supabase 欧洲节点时跨洲延迟明显，11 个页面平均响应约 14ms 的问题已通过本地化消除）。
Web 容器无状态，可随时重建；数据都在 `db` 容器的数据卷里。

## 一、本地开发运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量（复制示例并填写）
#    cp .env.example .env

# 3. 初始化演示数据（首次或需要重置时）
python seed.py

# 4. 启动
python run.py
# 访问 http://127.0.0.1:5000
```

`.env` 位于项目根目录，已被 `.gitignore` 忽略（不会提交到仓库），由 `run.py` 启动时自动加载（python-dotenv）。

## 二、本地 Docker 部署（Docker Desktop）

```bash
docker compose up -d --build
# 访问 http://127.0.0.1:5000
```

- 镜像基于 `python:3.12-slim`，以非 root 用户 `judge` 运行
- 环境变量通过 `env_file: .env` 注入容器
- 容器 `restart: unless-stopped`，Docker 重启后自动恢复

## 三、云服务器部署（推荐，公网访问）

已实测于阿里云轻量应用服务器（Ubuntu 24.04，2C2G）。

```bash
# 1. 安装 Docker 与 Compose（Ubuntu）
apt-get update && apt-get install -y git docker.io docker-compose-v2

# 2.（可选）配置镜像加速，国内拉取更快
cat > /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://docker.m.daocloud.io", "https://docker.nju.edu.cn"]
}
EOF
systemctl restart docker

# 3. 拉取代码
git clone https://github.com/Yunye211/panti.git /root/panti && cd /root/panti

# 4. 配置 .env（数据库连接串、SECRET_KEY 等，见下表）
vim .env

# 5. 构建并启动
docker compose up -d --build
```

放行防火墙：云厂商控制台 → 防火墙/安全组 → 入方向放行 **TCP 5000**（公网建议 5000/80/443，HTTPS 方案见下）。

### .env 配置项

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | ✅ | SQLAlchemy 连接串。同机 PG 容器（推荐，docker-compose 内置）：`postgresql+psycopg://cobebuddy:密码@db:5432/cobebuddy`；Supabase 云端：`postgresql+psycopg://postgres.项目引用:密码@aws-0-区域.pooler.supabase.com:6543/postgres`；本地开发 SQLite：`sqlite:///instance/judge.db` |
| `SECRET_KEY` | ✅ | 会话加密密钥，生产环境必须设置为随机长字符串 |
| `JUDGE_MAX_CONCURRENCY` | 否 | 同时判题进程数，默认 4；2G 内存服务器建议设为 2 |
| `JUDGE_TIME_LIMIT` | 否 | 单测试点超时（秒），默认 2 |
| `JUDGE_TOTAL_TIME` | 否 | 单份代码总运行时间上限（秒），默认 15 |
| `JUDGE_MEMORY_MB` | 否 | 内存上限 MB，默认 256 |
| `TEACHER_INVITE_CODE` | 否 | 教师注册码，默认 teacher2024（建议生产修改） |
| `PORT` | 否 | 启动端口，默认 5000 |

## 四、HTTPS（公网必做）

登录密码以明文传输，公网暴露必须启用 HTTPS。推荐二选一：

1. **Nginx + Let's Encrypt**：域名 A 记录指向服务器 → nginx 反代 `127.0.0.1:5000` → `certbot --nginx` 签发证书 → 自动续期。
2. **Caddy**：更简单，配置 `域名 { reverse_proxy localhost:5000 }`，Caddy 自动申请并续期 Let's Encrypt 证书。

> 注意：中国大陆服务器（如阿里云成都节点）上，域名解析到服务器并通过 80/443 提供网站服务需要 **ICP 备案**（通常 1~2 周）。未备案前可先用 `IP:5000` 访问，或将站点部署在境外节点。

## 五、判题沙箱说明

- 用户代码在**独立子进程**中运行：独立临时目录、模块黑名单 + 审计钩子、文件读写限制
- Linux（含容器）用 `resource` 限制 CPU/内存/文件大小，Windows 用 Job Object
- 单测试点 2s 超时、总 15s 超时、并发闸门（默认 4）
- 公网公开使用建议进一步加固：限制注册、降低并发、必要时"每次提交跑独立临时容器"

## 六、运维命令（服务器上执行）

```bash
docker compose logs -f          # 查看实时日志
docker compose ps               # 容器状态
docker compose down             # 停止
docker compose up -d --build    # 更新代码后重建
docker compose exec cobebuddy python /tmp/verify.py   # 进容器调试
```

### 一键更新（服务器上执行）

```bash
cd /root/panti && bash scripts/deploy_update.sh
```

脚本依次完成：拉取最新代码 → 重建容器 → 等待服务就绪 → 幂等初始化数据与管理员账号 →
自测管理员登录、`/admin/`、`/admin/users` 三个关键请求并打印状态码。

## 七、数据库

- 本地开发：`sqlite:///instance/judge.db`（默认）
- 生产：**同机 PostgreSQL 容器**（`docker-compose.yml` 的 `db` 服务，数据卷持久化，与 Web 同机避免跨洲延迟）
- 远端 PostgreSQL（如 Supabase）仍可用，只需改 `DATABASE_URL`；跨洲部署时页面延迟会明显上升，不推荐
- SQLite → PostgreSQL 迁移脚本：`instance/_pg_migrate.py`（读取 `DATABASE_URL` 环境变量执行，自动按外键顺序导入并核对行数）
- 轻量迁移：应用启动时 `_ensure_schema()` 会自动为旧库补列（如 `users.is_active`），兼容 SQLite 与 PostgreSQL，无需 Alembic

## 七·补、管理员账号

- 初始化演示数据时自动创建管理员：`admin / admin123`（`python seed.py`，幂等，已存在则跳过）
- 线上升级（已有库）只需重新构建容器：应用启动时自动补充管理员所需的表字段；随后在服务器执行下列命令创建管理员：

```bash
docker compose exec cobebuddy python seed.py      # 初始化/补齐演示数据与管理员账号
docker compose exec cobebuddy python - <<'PY'      # 仅创建管理员（不改动其它数据）
from app import create_app
from app.extensions import db
from app.models import User
app = create_app()
with app.app_context():
    if not User.query.filter_by(username="admin").first():
        u = User(username="admin", display_name="系统管理员", role="admin")
        u.set_password("改成强密码")
        db.session.add(u); db.session.commit()
        print("管理员已创建")
PY
```

- 管理员能力：管理控制台（账号/题目/班级/作业/提交统计）、用户管理（按角色与关键字查询学生/教师/管理员）、
  新增与编辑账号、重置密码（默认 `123456`）、停用/启用、删除账号（连带清理提交与所带班级），且系统始终至少保留一个管理员
- 管理员同时拥有教师端访问权；注册页不开放管理员角色，避免提权

## 八、安全清单

- [ ] `SECRET_KEY` 已改为随机值
- [ ] 已启用 HTTPS（证书自动续期）
- [ ] 修改默认演示账号密码 / `TEACHER_INVITE_CODE`
- [ ] 修改默认管理员密码（演示默认 `admin/admin123`，上线必须改）
- [ ] 云服务器 SSH 密码使用强密码，必要时改密钥登录
- [ ] 公网部署时限制注册或控制判题并发
