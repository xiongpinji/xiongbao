"""Locust 负载测试：模拟并发用户打 X-Agent API。

用法：
  pip install locust
  locust -f tests/load/locustfile.py --host http://localhost:8000

然后在 http://localhost:8089 设置并发数与速率。
或无头模式：
  locust -f tests/load/locustfile.py --host http://localhost:8000 \
    --headless -u 50 -r 5 -t 60s
"""

from __future__ import annotations

import json
import random

from locust import HttpUser, between, task


class XAgentUser(HttpUser):
    """模拟 X-Agent 用户：浏览角色 → 运行 agent → 写记忆 → 搜索。"""

    wait_time = between(1, 3)
    token: str = ""

    def on_start(self) -> None:
        # lite 模式可匿名；full 模式登录
        try:
            resp = self.client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "admin"},
                name="登录",
            )
            if resp.status_code == 200:
                self.token = resp.json().get("access_token", "")
                self.client.headers.update(
                    {"Authorization": f"Bearer {self.token}"}
                )
        except Exception:
            pass  # lite 匿名继续

    @task(3)
    def list_roles(self) -> None:
        self.client.get("/api/v1/agents/roles", name="角色列表")

    @task(2)
    def run_agent(self) -> None:
        goals = ["你好", "介绍一下自己", "今天天气怎样", "帮我规划一个任务"]
        self.client.post(
            "/api/v1/agents/run",
            json={"goal": random.choice(goals)},
            name="运行 Agent",
        )

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="健康检查")

    @task(1)
    def memory_search(self) -> None:
        self.client.post(
            "/api/v1/memory/search",
            json={"query": "测试", "top_k": 3},
            name="记忆检索",
        )

    @task(1)
    def discover(self) -> None:
        self.client.post(
            "/api/v1/open-source/discover",
            json={"query": "web framework", "limit": 3},
            name="开源发现",
        )

    @task(1)
    def create_draft(self) -> None:
        self.client.post(
            "/api/v1/creative-studio/workflow-draft",
            json={"brief": "负载测试短剧", "genre": "逆袭"},
            name="短剧草稿",
        )
