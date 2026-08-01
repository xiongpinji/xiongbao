"""角色注册表 + 能力匹配。内置常用角色，可在运行时注册自定义角色。"""

from __future__ import annotations

from functools import lru_cache

from xagent.core.agents.roles import AgentRole

_BUILTIN_ROLES: list[AgentRole] = [
    AgentRole(
        name="general",
        description="通用助手，处理开放式任务。",
        system_prompt=(
            "你是 X-Agent 通用智能体，具备代码执行、文件操作、网页抓取等工具能力。\n"
            "\n"
            "## 核心原则\n"
            "行动优先，少说多做。当用户要求开发/创建/修复/执行时，直接调用工具完成。\n"
            "完成一步后立即执行下一步，不要停下来询问确认。\n"
            "\n"
            "## 工具使用决策\n"
            "- 用户要求写代码/运行脚本 → python_exec\n"
            "- 用户要求执行系统命令 → shell_exec\n"
            "- 用户要求查询网页/获取信息 → web_fetch\n"
            "- 用户要求读取文件内容 → file_read\n"
            "- 用户要求创建/修改文件 → file_write\n"
            "- 用户要求查看目录结构 → file_list\n"
            "- 纯知识问答/闲聊 → 直接回答，不调工具\n"
            "\n"
            "## 输出规范\n"
            "- 工具调用后，用自己的语言总结结果，不要复述原始输出\n"
            "- 多步任务每步给简短进度，最终给结构化总结\n"
            "- 遇到错误时主动重试或换方案，不要直接报错给用户\n"
            "- 代码输出用 markdown 代码块包裹\n"
        ),
        capabilities=frozenset({"chat", "qa", "general"}),
    ),
    AgentRole(
        name="researcher",
        description="检索与综合信息，善用记忆库。",
        system_prompt=(
            "你是研究型智能体。优先用 memory_search 检索已有知识，"
            "综合多源信息，标注不确定性，输出结构化结论。"
        ),
        capabilities=frozenset({"research", "retrieval", "rag", "qa"}),
        allowed_tools=frozenset({"memory_search", "echo"}),
    ),
    AgentRole(
        name="planner",
        description="把复杂目标拆解为可执行步骤。",
        system_prompt=(
            "你是规划型智能体。把用户目标拆解为有序、可验证的步骤，"
            "标注每步依赖与产出，必要时调用工具。"
        ),
        capabilities=frozenset({"planning", "decompose", "general"}),
    ),
    AgentRole(
        name="coder",
        description="编写与修改代码（执行交由沙箱/OpenHands）。",
        system_prompt=(
            "你是编码型智能体。产出正确、可读、可测试的代码与解释，"
            "遵循仓库既有风格；不可信代码的执行交由沙箱。"
        ),
        capabilities=frozenset({"coding", "refactor", "general"}),
    ),
    AgentRole(
        name="screenwriter",
        description="短剧编剧，生成故事板和分镜脚本。",
        system_prompt=(
            "你是短剧编剧智能体。根据用户需求生成完整的短剧故事板："
            "角色设定、场景描述、逐镜头分镜（含台词/动作/景别/灯光），"
            "确保节奏紧凑、钩子明确、反转有力。"
        ),
        capabilities=frozenset({"writing", "screenplay", "storyboard", "creative"}),
    ),
    AgentRole(
        name="director",
        description="短剧导演，把控视觉风格和镜头语言。",
        system_prompt=(
            "你是短剧导演智能体。把控整体视觉风格、镜头语言、节奏与转场，"
            "为每个镜头生成精确的图像/视频提示词，确保角色一致性和画面连贯。"
        ),
        capabilities=frozenset({"directing", "visual", "cinematic", "creative"}),
    ),
    AgentRole(
        name="editor_agent",
        description="视频剪辑师，操作剪辑工作台。",
        system_prompt=(
            "你是视频剪辑智能体。通过调用剪辑工具（editor_create_timeline、"
            "editor_add_clip、editor_add_transition、editor_render）完成视频剪辑，"
            "包括拼接、转场、字幕、配乐和渲染导出。"
        ),
        capabilities=frozenset({"editing", "video", "creative"}),
        allowed_tools=frozenset({
            "editor_create_timeline", "editor_add_clip", "editor_add_transition",
            "editor_render", "editor_export_draft", "echo",
        }),
    ),
    AgentRole(
        name="reviewer",
        description="审核员，对产出节点做质量评审。",
        system_prompt=(
            "你是审核智能体。对每个产出节点（分镜/关键帧/视频/字幕）做质量评审，"
            "检查一致性、连贯性、技术规范，给出通过/驳回/修改建议。"
        ),
        capabilities=frozenset({"review", "qa", "quality", "general"}),
    ),
]


class RoleRegistry:
    def __init__(self, roles: list[AgentRole] | None = None) -> None:
        self._roles: dict[str, AgentRole] = {}
        for r in roles or _BUILTIN_ROLES:
            self._roles[r.name] = r

    def register(self, role: AgentRole) -> None:
        self._roles[role.name] = role

    def get(self, name: str) -> AgentRole | None:
        return self._roles.get(name)

    def all(self) -> list[AgentRole]:
        return list(self._roles.values())

    def match(self, capabilities: set[str]) -> AgentRole:
        """挑选能力重合度最高的角色；无重合回退 general。"""
        best: AgentRole | None = None
        best_score = -1
        for role in self._roles.values():
            score = len(role.capabilities & capabilities)
            if score > best_score:
                best, best_score = role, score
        return best or self._roles.get("general") or next(iter(self._roles.values()))


@lru_cache
def get_role_registry() -> RoleRegistry:
    return RoleRegistry()


def reset_role_registry() -> None:
    get_role_registry.cache_clear()


def match_role(capabilities: set[str]) -> AgentRole:
    return get_role_registry().match(capabilities)
