# COBEBUDDY 在线判题平台 —— Docker 镜像
FROM python:3.12-slim

WORKDIR /app

# 先装依赖（利用镜像层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码
COPY app ./app
COPY run.py seed.py README.md ./

# 非 root 用户运行（判题沙箱在 Linux 下使用 resource 限制）
RUN useradd --create-home --uid 1000 judge \
    && mkdir -p /app/instance \
    && chown -R judge:judge /app
USER judge

EXPOSE 5000

# gunicorn 生产服务器；--threads 提升并发（应对远端数据库往返延迟）；--timeout 放宽以便长判题队列
CMD ["gunicorn", "-w", "2", "--threads", "8", "-b", "0.0.0.0:5000", "--timeout", "120", "run:app"]
