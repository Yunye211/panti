# Python 在线编程与自动判题平台

基于 **Flask + SQLite + 子进程沙箱** 的 Python 编程练习与作业平台。
学生和教师**不需要在本地安装 Python**，只要用浏览器访问服务器网址、登录账号即可使用：
在线写代码 → 提交 → 服务器沙箱运行 → 自动返回判题结果（通过 / 答案错误 / 语法错误 / 运行时错误 / 运行超时）。

## 一、功能一览

### 学生
- 注册 / 登录（用户名 + 密码）
- 浏览题库（按知识点、难度、关键字筛选，显示“是否已通过”）
- **专项练习**：自主勾选知识点（if、循环、字符串…）与难度、设定题量，系统随机抽题组成练习
- 网页内在线编写 Python 代码（CodeMirror 编辑器，行号、缩进、语法高亮）
- 一键提交自动判题，逐测试点查看输入 / 期望输出 / 实际输出 / 错误信息
- 自定义输入运行（stdin 调试），无需判题
- 查看个人提交与练习记录（可按结果、来源筛选，查看历史源代码）
- 用班级码加入班级 → 完成教师布置的作业（含截止时间、逾期标记）

### 教师
- 登录管理题库：录入/编辑/删除题目，绑定知识点标签、难度、初始代码、参考答案
- 为每个题目配置**多个测试用例**（标准输入 + 期望输出，可标记为样例展示给学生）
- 录入题目后可直接在页面“试做验证”，用参考代码跑通所有测试点
- 创建班级（自动生成班级码），查看/移除班级学生
- 创建作业：选择班级、题目、截止时间
- 查看作业提交情况（学生 × 题目矩阵）、每位学生的**源代码**与判题结果
- 学情统计：题目通过率、知识点正确率、学生通过率排行、提交结果分布

### 判题核心
- 代码在服务器**独立子进程沙箱**中运行：
  - 独立临时目录（cwd 与 sys.path 均指向该目录）
  - 审计钩子拦截 `import` 事件，屏蔽 `socket / _socket / subprocess / os.system / ctypes / multiprocessing` 等危险模块与底层实现
  - 文件审计：写入只允许落到临时目录，读取只允许临时目录与 Python 安装目录，`os.open` 的写标志同样受控
  - 单测试点超时（默认 2s）与总超时（默认 15s），类 Unix 限 CPU/内存/文件大小，Windows 用 Job Object 限制进程内存与子进程数
  - 输出直接落临时文件，父进程只读取前 64KB，防止刷屏拖垮判题服务
  - 子进程环境变量最小化，不继承服务端 `SECRET_KEY` 等配置
  - 并发闸门：同时最多 4 个判题进程，其余排队
- 判题结果：`AC 通过`、`WA 答案错误`、`RE 运行时错误`、`CE 语法错误`、`TLE 运行超时`

### Web 安全
- 全站 CSRF 防护（会话 token，表单隐藏域 + AJAX `X-CSRF-Token` 头）
- 角色与越权控制：学生/教师路由隔离，教师只能查看本班学生源代码，只能删除自己创建的题目
- 登录失败限流（同账号+IP 连续失败 5 次锁定 1 分钟）、用户名格式校验、教师注册码恒定时间比较
- 题目描述等富文本输出做 HTML 转义，防存储型 XSS；登录跳转做站内限制，防开放重定向
- 判题超时/内存/代码长度一律取服务端配置，客户端参数无法放大资源占用

## 二、快速开始

```bash
# 1. 安装依赖（服务器/教师机执行一次即可）
pip install -r requirements.txt

# 2. 初始化演示数据（知识点、示例账号、14 道示例题、示例班级与作业）
python seed.py

# 3. 启动服务
python run.py
# 浏览器访问 http://127.0.0.1:5000
```

演示账号：

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 学生 | student | 123456 |
| 学生 | student2 | 123456 |
| 教师 | teacher | 123456 |

教师注册需填写注册码（默认 `teacher2024`，可用环境变量 `TEACHER_INVITE_CODE` 修改）；
学生注册无需注册码，注册后用教师提供的班级码（`CLASS1`）加入班级。

## 三、部署为“网址访问”的服务

校内局域网 / 云服务器部署（学生只需浏览器访问，本地无需 Python）：

```bash
pip install -r requirements.txt gunicorn
set SECRET_KEY=your-random-secret          # Linux: export SECRET_KEY=...
python seed.py
gunicorn -w 4 -b 0.0.0.0:8000 "run:app"
```

访问 `http://服务器IP:8000`。生产环境建议：
- 用 Nginx 反向代理 + HTTPS；
- 将 `SECRET_KEY` 设置为随机字符串；
- 判题子进程放在容器/受限用户中运行（本项目已做模块与文件限制，容器可进一步加固）；
- 数据库可替换为 MySQL/PostgreSQL（修改 `DATABASE_URL` 环境变量）。

## 四、目录结构

```
app/
  __init__.py        应用工厂、配置、登录管理
  extensions.py      SQLAlchemy / LoginManager
  models.py          用户、知识点、题目、测试用例、班级、作业、提交
  sandbox.py         代码沙箱（子进程 + 模块屏蔽 + 审计钩子 + 超时）
  judge.py           自动判题（逐测试点比对、状态判定）
  views/
    auth.py          注册、登录、退出
    main.py          首页仪表盘、个人资料、加入班级
    problems.py      题库浏览、专项练习、提交记录
    homework.py      学生作业列表与作答
    teacher.py       题库管理、班级、作业、学情统计、提交查看
    api.py           判题接口 / 自定义运行接口
  templates/         页面模板
  static/            CSS 与前端 JS（编辑器、判题交互）
seed.py              演示数据初始化
run.py               启动入口
tests/
  security_test.py   安全测试（沙箱逃逸 + Web 安全，44 项）
  smoke_test.py      功能回归测试（页面 + 判题五态 + 教师流程，36 项）
```

## 二·补、测试

```bash
python tests/security_test.py   # 沙箱逃逸、文件越权、资源滥用、CSRF、越权、XSS
python tests/smoke_test.py      # 业务功能回归
```

安全测试覆盖示例：`import socket/_socket`、`del sys.modules` 绕过、`importlib` 动态导入、
`os.system/subprocess`、读取 `win.ini`、写系统目录、`os.listdir('C:/')`、环境变量泄露、
死循环、刷屏输出、内存炸弹、无限递归、`input()` 挂起、CSRF 伪造、跨班越权查看源代码、
非本班作业提交、题目描述 XSS、非法用户名与教师注册码。

## 五、配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SECRET_KEY` | 内置开发值 | 会话加密密钥，生产必须修改 |
| `DATABASE_URL` | `sqlite:///instance/judge.db` | 数据库连接 |
| `JUDGE_TIME_LIMIT` | 2 | 单测试点超时（秒） |
| `JUDGE_TOTAL_TIME` | 15 | 单份代码总运行时间上限（秒） |
| `JUDGE_MEMORY_MB` | 256 | 内存上限（类 Unix 用 resource，Windows 用 Job Object） |
| `JUDGE_MAX_CONCURRENCY` | 4 | 同时运行的判题进程数 |
| `MAX_CODE_LENGTH` | 20000 | 单份代码最大字符数 |
| `TEACHER_INVITE_CODE` | teacher2024 | 教师注册码 |
| `PORT` | 5000 | 启动端口 |
