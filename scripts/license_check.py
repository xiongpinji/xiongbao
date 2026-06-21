#!/usr/bin/env python
"""许可证门禁：扫描已安装依赖的许可证，拦截禁用项。

红线（对外商业平台一票否决）：
  - AGPL（任何版本）
  - GPL（直接链接；GPL-3.0/2.0）。LGPL 允许（动态链接）。
  - ELv2（Elastic License v2）
  - SSPL / BUSL / "Sustainable Use" / "Source Available" 等非 OSI

用法：
  python scripts/license_check.py            # 扫描当前环境
退出码非 0 表示发现违规，CI 失败。
"""

from __future__ import annotations

import re
import sys
from importlib import metadata

# 允许的（白名单关键词，命中即放行）
ALLOW = re.compile(
    r"\b(MIT|BSD|Apache|ISC|Python Software Foundation|PSF|MPL|"
    r"Mozilla|LGPL|Unlicense|Public Domain|Zlib|CC0)\b",
    re.IGNORECASE,
)

# 禁止的（命中即违规）
DENY = re.compile(
    r"\b(AGPL|Affero|"
    r"GNU General Public License|GPLv3|GPLv2|GPL-3|GPL-2|"
    r"Elastic License|ELv2|"
    r"Server Side Public License|SSPL|"
    r"Business Source|BUSL|"
    r"Sustainable Use|Source.Available)\b",
    re.IGNORECASE,
)

# LGPL 是允许的，但上面 DENY 的 "GPL" 可能误伤，单独豁免
LGPL_OK = re.compile(r"\bLGPL\b", re.IGNORECASE)

# 已知误报豁免（包名 -> 原因）。例如某些包 classifier 写法不规范。
EXEMPT: dict[str, str] = {}


def _license_text(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    parts: list[str] = []
    if lic := meta.get("License"):
        parts.append(lic)
    for clf in meta.get_all("Classifier") or []:
        if clf.startswith("License ::"):
            parts.append(clf)
    return " ; ".join(parts)


def main() -> int:
    violations: list[tuple[str, str]] = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name", "?")
        if name in EXEMPT:
            continue
        text = _license_text(dist)
        if not text:
            continue
        if DENY.search(text) and not LGPL_OK.search(text):
            violations.append((name, text))

    if violations:
        print("❌ 许可证门禁失败：发现禁用许可的依赖\n")
        for name, text in sorted(violations):
            print(f"  - {name}: {text}")
        print(
            "\n红线：AGPL / GPL(直接链接) / ELv2 / SSPL / BUSL / Source-Available。"
            "\n请替换为 MIT/Apache/BSD 等价物，或（GPL 服务）改为独立进程 + HTTP 调用。"
        )
        return 1

    print("✅ 许可证门禁通过：未发现禁用许可的依赖。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
