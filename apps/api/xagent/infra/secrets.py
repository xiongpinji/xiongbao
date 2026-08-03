"""secretRef 解析：在环境变量值中支持引用语法，避免明文 secret 入库 / 入 .env。

语法（大小写敏感，前缀必须为 ``SECRETREF:``）：

- ``SECRETREF:file:/path/to/secret``  —— 从文件读取（自动 strip 首尾空白/换行，
  兼容 k8s secret volume mount 落盘文件）
- ``SECRETREF:env:OTHER_VAR``        —— 从另一环境变量读取
- ``SECRETREF:vault:<path>#<key>``   —— 预留扩展位（未实现，fail-fast 提示）

行为约定：

- 不带 ``SECRETREF:`` 前缀的值原样透传（现有行为完全不变）。
- full / enterprise（生产）模式：解析失败 fail-fast，抛 ``SecretRefError``，
  错误信息只包含字段名 / scheme / 目标，绝不包含 secret 值本身。
- lite 模式：解析失败降级为 warning 日志并返回空字符串，保证本地开发不中断。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

SECRETREF_PREFIX = "SECRETREF:"

_SUPPORTED_SCHEMES = ("file", "env")


class SecretRefError(RuntimeError):
    """secretRef 解析失败（生产模式 fail-fast）。"""


def is_secret_ref(value: object) -> bool:
    """判断值是否为 secretRef 引用。"""
    return isinstance(value, str) and value.startswith(SECRETREF_PREFIX)


def _parse_ref(value: str) -> tuple[str, str]:
    """解析 ``SECRETREF:<scheme>:<target>``，返回 (scheme, target)。"""
    body = value[len(SECRETREF_PREFIX):]
    scheme, sep, target = body.partition(":")
    if not sep or not scheme or not target:
        raise SecretRefError(
            f"非法 secretRef 语法: {SECRETREF_PREFIX}{scheme}"
            f"（期望 {SECRETREF_PREFIX}<file|env>:<target>）"
        )
    return scheme.lower(), target


def _resolve_ref(scheme: str, target: str) -> str:
    """按 scheme 取回 secret 值。失败抛 SecretRefError（消息不含 secret 值）。"""
    if scheme == "file":
        path = Path(target)
        if not path.is_file():
            raise SecretRefError(f"secretRef 文件不存在或不可读: {target}")
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise SecretRefError(
                f"secretRef 文件读取失败: {target}（{exc.__class__.__name__}）"
            ) from exc
    if scheme == "env":
        if target not in os.environ:
            raise SecretRefError(f"secretRef 引用的环境变量未设置: {target}")
        return os.environ[target]
    if scheme == "vault":
        raise SecretRefError(
            "secretRef vault:// 为预留扩展位，当前版本未实现；"
            "请改用 file:/env: 引用或通过 k8s secretKeyRef 注入环境变量"
        )
    raise SecretRefError(
        f"不支持的 secretRef scheme: {scheme}（支持: {', '.join(_SUPPORTED_SCHEMES)}）"
    )


def resolve_secret(value: object, *, field: str = "", lite: bool = False) -> object:
    """解析单个配置值。

    - 非 secretRef 值原样返回。
    - secretRef 解析失败：lite 模式 warning 并返回 ""；否则抛 SecretRefError。
    """
    if not is_secret_ref(value):
        return value
    assert isinstance(value, str)  # is_secret_ref 已保证
    try:
        scheme, target = _parse_ref(value)
        return _resolve_ref(scheme, target)
    except SecretRefError as exc:
        location = f"（字段 {field}）" if field else ""
        if lite:
            logger.warning("secretRef 解析失败%s，lite 模式降级为空值: %s", location, exc)
            return ""
        raise SecretRefError(f"secretRef 解析失败{location}: {exc}") from exc


#: 标记为 secret 的配置字段（嵌套模型路径）。这些字段的值在 Settings 加载后
#: 统一走一遍 secretRef 解析。仅列出持密字段，非密字段不受影响。
SECRET_FIELD_PATHS: tuple[tuple[str, str], ...] = (
    ("security", "jwt_secret"),
    ("security", "oidc_client_secret"),
    ("db", "url"),                       # DSN 内嵌密码
    ("cache", "redis_url"),              # redis://:password@host
    ("llm", "proxy_api_key"),
    ("llm", "openai_api_key"),
    ("llm", "anthropic_api_key"),
    ("llm", "deepseek_api_key"),
    ("memory", "qdrant_api_key"),
    ("media", "openai_image_api_key"),
    ("media", "volcano_ark_api_key"),
    ("media", "kling_api_key"),
    ("media", "jimeng_api_key"),
    ("media", "generic_video_api_key"),
    ("observability", "langfuse_secret_key"),
    ("sandbox", "e2b_api_key"),
)


def resolve_settings_secrets(settings: object) -> object:
    """对 Settings 实例的 secret 字段执行 secretRef 原地解析。

    lite 判定读取 ``settings.mode``（避免循环导入，用属性鸭子类型）。
    """
    mode = getattr(settings, "mode", None)
    lite = getattr(mode, "value", mode) == "lite"
    for section, attr in SECRET_FIELD_PATHS:
        group = getattr(settings, section, None)
        if group is None:
            continue
        current = getattr(group, attr, None)
        if not is_secret_ref(current):
            continue
        resolved = resolve_secret(current, field=f"{section}.{attr}", lite=lite)
        setattr(group, attr, resolved)
    return settings
