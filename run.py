import os

from dotenv import load_dotenv

load_dotenv()  # 读取项目根目录的 .env（若存在）

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    print(" * 服务已启动：http://127.0.0.1:%d" % port)
    print(" * 演示账号：学生 student/123456、教师 teacher/123456（如未初始化数据请先执行 python seed.py）")
    app.run(host="0.0.0.0", port=port, debug=debug)
