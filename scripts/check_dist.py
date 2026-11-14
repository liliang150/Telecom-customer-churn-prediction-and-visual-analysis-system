"""dist 过期检测：后端代码比 dist/index.html 新则输出 NEED_BUILD，否则输出 OK。"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dist_index = root / "frontend" / "dist" / "index.html"

if not dist_index.is_file():
    print("NEED_BUILD")
    sys.exit(0)

dist_mtime = dist_index.stat().st_mtime
backend_dir = root / "backend"

for py in backend_dir.rglob("*.py"):
    if "__pycache__" in str(py):
        continue
    if py.stat().st_mtime > dist_mtime:
        print("NEED_BUILD")
        sys.exit(0)

print("OK")
