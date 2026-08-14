#!/usr/bin/env python3
"""X-Agent 多机 HA 演练脚本（零第三方依赖，stdlib only）。

在两台（或同机两个端口）共享同一 Postgres/Redis 的 X-Agent 实例上执行，
验证商用交付的 HA 关键合同：

  1. 双实例健康探针可用
  2. A 实例签发的 JWT 在 B 实例直接可用（无状态会话）
  3. A 实例写入的数据在 B 实例可读（共享 Postgres）
  4. A 实例触发的登录锁定在 B 实例同样生效（共享 Redis，可选检查）

用法：
  python scripts/ha_drill.py --a http://host-a:8000 --b http://host-b:8000 \
      --username drill_ha --password 'Drill#2026x'

退出码：0 = 全部通过/明确跳过；1 = 任一硬性检查失败。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid


def call(method: str, url: str, body: dict | None = None, token: str | None = None,
         timeout: float = 15.0) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:200]}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {"error": str(exc)}


def report(ok: bool, name: str, detail: str, failures: list[str]) -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name} — {detail}")
    if not ok:
        failures.append(name)


def main() -> int:
    parser = argparse.ArgumentParser(description="X-Agent multi-instance HA drill")
    parser.add_argument("--a", required=True, help="实例 A 基础 URL，如 http://host-a:8000")
    parser.add_argument("--b", required=True, help="实例 B 基础 URL")
    parser.add_argument("--username", default=f"ha_drill_{uuid.uuid4().hex[:8]}")
    parser.add_argument("--password", default=f"Drill#{uuid.uuid4().hex[:10]}")
    parser.add_argument("--expect-shared-lock", action="store_true",
                        help="两实例已配置共享 Redis 时传入；未传入则锁定共享仅作信息提示")
    args = parser.parse_args()
    a, b = args.a.rstrip("/"), args.b.rstrip("/")
    failures: list[str] = []

    # 1. 双实例健康
    for name, base in (("A", a), ("B", b)):
        code, body = call("GET", f"{base}/health")
        report(code == 200 and body.get("status") == "ok",
               f"health-{name}", f"HTTP {code} {body.get('status', body)}", failures)

    # 2. 注册 + A 登录签发 JWT
    code, body = call("POST", f"{a}/api/v1/auth/register",
                      {"username": args.username, "password": args.password})
    if code not in (200, 201, 409):
        report(False, "register-on-A", f"HTTP {code} {body}", failures)
        return finish(failures)
    code, login = call("POST", f"{a}/api/v1/auth/login",
                       {"username": args.username, "password": args.password})
    token = login.get("access_token")
    report(code == 200 and bool(token), "login-on-A", f"HTTP {code}", failures)
    if not token:
        return finish(failures)

    # 3. A 签发的 JWT 在 B 直接可用（JWT 无状态会话跨实例）
    code, me = call("GET", f"{b}/api/v1/auth/me", token=token)
    report(code == 200, "jwt-A-accepted-by-B",
           f"HTTP {code} user={me.get('user_id', me)}", failures)

    # 4. A 写 / B 读（共享数据库一致性；用关系型路径——工作流模板，
    #    向量检索在 lite 模式无 Qdrant 时不可用，不能作为 HA 判据）
    marker = f"ha-drill-{uuid.uuid4().hex[:12]}"
    code, saved = call("POST", f"{a}/api/v1/workflows/templates/save",
                       {"name": marker, "nodes": [], "edges": [], "template_id": marker},
                       token=token)
    write_ok = code in (200, 201)
    time.sleep(0.5)
    code, loaded = call("GET", f"{b}/api/v1/workflows/templates/{marker}", token=token)
    seen = marker in json.dumps(loaded, ensure_ascii=False)
    report(write_ok and code == 200 and seen, "write-A-read-B",
           f"write={write_ok} read-HTTP {code} marker-visible={seen}", failures)

    # 5. 登录锁定共享（共享 Redis；实例未启用锁定时明确跳过）
    locked_seen = False
    skipped = True
    for _ in range(8):
        code, _ = call("POST", f"{a}/api/v1/auth/login",
                       {"username": args.username, "password": "wrong-password"})
        if code == 429:
            locked_seen, skipped = True, False
            break
        if code in (401, 403):
            continue
        break
    if locked_seen and args.expect_shared_lock:
        time.sleep(0.3)
        code, _ = call("POST", f"{b}/api/v1/auth/login",
                       {"username": args.username, "password": args.password})
        report(code == 429, "lockout-shared-A-to-B",
               f"B login HTTP {code}（期望 429）", failures)
    elif locked_seen:
        code, _ = call("POST", f"{b}/api/v1/auth/login",
                       {"username": args.username, "password": args.password})
        print(f"[INFO] lockout-shared —— A 已锁定，B HTTP {code}；"
              "未声明 --expect-shared-lock，不作硬判（共享 Redis 部署时应为 429）")
    else:
        print("[SKIP] lockout-shared —— 实例未启用登录锁定或阈值高于 8 次，跳过共享锁定检查")

    return finish(failures)


def finish(failures: list[str]) -> int:
    if failures:
        print(f"\nHA DRILL: FAIL ({len(failures)} 项失败: {', '.join(failures)})")
        return 1
    print("\nHA DRILL: PASS —— 双实例健康 / JWT 互通 / 数据一致 全部验证通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
