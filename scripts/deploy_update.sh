#!/usr/bin/env bash
# 服务器上更新部署（在 /root/panti 目录执行）：拉代码 -> 重建容器 -> 初始化管理员 -> 自测
set -e

APP_DIR="${APP_DIR:-/root/panti}"
COMPOSE="${COMPOSE:-docker compose}"
URL="${URL:-http://127.0.0.1:5000}"

cd "$APP_DIR"

echo "==> 1/5 拉取最新代码"
git pull --ff-only

echo "==> 2/5 重建并启动容器"
$COMPOSE up -d --build

echo "==> 3/5 等待服务就绪"
for i in $(seq 1 40); do
  if curl -sf "$URL/auth/login" > /dev/null; then
    echo "    服务已就绪"
    break
  fi
  sleep 2
done

echo "==> 4/5 初始化/补齐演示数据与管理员账号（幂等）"
$COMPOSE exec -T cobebuddy python seed.py || echo "    seed 跳过（已存在数据）"

echo "==> 5/5 自测：管理员登录与控制台"
COOKIE=$(mktemp)
CSRF=$(curl -s -c "$COOKIE" "$URL/auth/login" | grep -o 'name="csrf-token" content="[^"]*"' | sed 's/.*content="//;s/"//')
if [ -z "$CSRF" ]; then
  echo "    无法获取 CSRF Token，请检查服务日志"
  exit 1
fi
curl -s -b "$COOKIE" -c "$COOKIE" -o /tmp/login_resp.html \
  -w "    登录响应: %{http_code}\n" \
  -X POST -d "username=admin&password=admin123&csrf_token=$CSRF" "$URL/auth/login"
curl -s -b "$COOKIE" -o /tmp/admin_page.html -w "    管理控制台: %{http_code}\n" "$URL/admin/"
curl -s -b "$COOKIE" -o /tmp/users_page.html -w "    用户管理: %{http_code}\n" "$URL/admin/users"
rm -f "$COOKIE"

echo "==> 完成"
echo "    站点：$URL  （公网：http://服务器IP:5000）"
echo "    管理员：admin / admin123 —— 公网环境请登录后立即修改密码"
