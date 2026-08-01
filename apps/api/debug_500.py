"""Debug: reproduce HTTP 500 with full traceback using TestClient."""
import sys, os, traceback, asyncio

BASE = r"D:\AI编程库\项目库\进行中的项目\xiong bao\xagent"
API = os.path.join(BASE, "apps", "api")
for p in (BASE, API):
    if p not in sys.path:
        sys.path.insert(0, p)

os.chdir(BASE)
print("cwd:", os.getcwd())
print("sys.path[0:3]:", sys.path[:3])

try:
    from xagent.main import create_app
    print("create_app imported OK:", create_app)
except Exception:
    traceback.print_exc()
    sys.exit(1)

try:
    app = create_app()
    print("create_app() OK")
except Exception:
    print("=" * 60)
    print("EXCEPTION DURING create_app()")
    print("=" * 60)
    traceback.print_exc()
    sys.exit(1)

from fastapi.testclient import TestClient

try:
    with TestClient(app) as client:
        print("TestClient context entered (lifespan ran OK)")
        for path in ("/health", "/api/v1/health", "/ready", "/openapi.json", "/docs"):
            try:
                r = client.get(path)
                print(f"GET {path} -> {r.status_code}")
            except Exception:
                print(f"GET {path} -> EXCEPTION:")
                traceback.print_exc()
except Exception:
    print("=" * 60)
    print("EXCEPTION DURING LIFESPAN / TESTCLIENT")
    print("=" * 60)
    traceback.print_exc()
