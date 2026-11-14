"""一键启动脚本：端口检查 → 依赖检查 → dist → bootstrap → uvicorn。"""
from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

HOST = os.getenv("CHURN_HOST", "127.0.0.1")
PORT = int(os.getenv("CHURN_PORT", os.getenv("PORT", "8000")))
HEADLESS = os.getenv("CHURN_HEADLESS") == "1" or HOST != "127.0.0.1"

REQUIRED = ["fastapi", "uvicorn", "xgboost", "shap", "sklearn", "sqlalchemy", "jwt", "multipart"]


def pause(message: str) -> None:
    if not HEADLESS:
        input(message)


def step(title: str):
    print(f"\n{'=' * 55}\n {title}\n{'=' * 55}")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) != 0


def check_deps() -> bool:
    missing = [m for m in REQUIRED if importlib.util.find_spec(m) is None]
    if missing:
        print(f"  缺失依赖: {missing}")
        print("  正在安装 ...")
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        if result.returncode != 0:
            print("  [错误] 依赖安装失败")
            return False
    print("  依赖就绪。")
    return True


def check_dist() -> bool:
    dist_index = ROOT / "frontend" / "dist" / "index.html"
    if not dist_index.is_file():
        print("  前端产物不存在，首次构建 ...")
        return subprocess.run(["npm.cmd", "run", "build"], cwd=ROOT / "frontend").returncode == 0
    # 检测后端代码是否比 dist 新
    dist_mtime = dist_index.stat().st_mtime
    for py in (ROOT / "backend").rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        if py.stat().st_mtime > dist_mtime:
            print("  后端代码已更新，重新构建前端 ...")
            return subprocess.run(["npm.cmd", "run", "build"], cwd=ROOT / "frontend").returncode == 0
    print("  产物已就绪。")
    return True


def main() -> int:
    step(f"Step 1/5: 检查端口 {PORT}")
    if not port_free(PORT):
        print(f"  [错误] 端口 {PORT} 被占用。请先关闭占用进程后重试。")
        pause("  按回车键退出 ...")
        return 1
    print("  端口空闲。")

    step("Step 2/5: 检查依赖")
    if not check_deps():
        pause("  按回车键退出 ...")
        return 1

    step("Step 3/5: 检查前端产物")
    if not check_dist():
        print("  [错误] 前端构建失败")
        pause("  按回车键退出 ...")
        return 1

    step("Step 4/5: 检查模型与缓存")
    if subprocess.run([sys.executable, "scripts/bootstrap.py"]).returncode != 0:
        print("  [错误] 初始化失败")
        pause("  按回车键退出 ...")
        return 1

    step("Step 5/5: 启动服务")
    print(f"\n  访问:   http://{HOST}:{PORT}")
    print("  管理员: admin / admin123")
    print("  关闭:   Ctrl+C\n")

    # 本地启动时自动打开浏览器
    if not HEADLESS:
        import threading
        threading.Timer(2.0, lambda: os.system(f"start http://127.0.0.1:{PORT}")).start()

    try:
        return subprocess.call([
            sys.executable, "-m", "uvicorn", "backend.main:app",
            "--host", HOST, "--port", str(PORT), "--log-level", "info",
        ])
    except KeyboardInterrupt:
        print("\n  服务已停止。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
