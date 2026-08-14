#!/usr/bin/env python3
"""发布标签不可变性哨兵（detect-tamper）。

免费版私有仓库无法启用服务端 tag 保护，本脚本提供等效的检测兜底：
校验三个发布标签在远端仍指向发布时锚定的提交（annotated tag object + 目标提交
双重校验）。任何移动、删除或重打标签都会导致非零退出，CI 随即转红告警。

锚定值来自 2026-08-14 发布当日 ls-remote 实录：
  v1.0.0 -> tag 43b5bac / commit fa8c923
  v1.1.0 -> tag 6aabe34 / commit 8022e3d
  v1.1.1 -> tag d3a656d / commit 792751e

用法：python scripts/verify_release_tags.py
"""

from __future__ import annotations

import subprocess
import sys

EXPECTED = {
    "v1.0.0": ("43b5bac7d699b8492a356f64b8b3bf39f8d44ead",
               "fa8c923c21534c53782d832aa5727735f1aafabd"),
    "v1.1.0": ("6aabe3431f7f4bd273b5ac63e15263a9adf42d0d",
               "8022e3dd28b317e10683d529f64aad246f2c61b8"),
    "v1.1.1": ("d3a656dc2b4d24ab4c77847bb9808ea2415bce88",
               "792751e26139ed9c4b81a2f15667a1c3608c5142"),
}


def remote_refs() -> dict[str, str]:
    result = subprocess.run(
        ["git", "ls-remote", "origin", "refs/tags/v*"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"[FAIL] 无法读取远端标签: {result.stderr.strip()}")
        sys.exit(1)
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, ref = line.split("\t")
        refs[ref] = sha
    return refs


def main() -> int:
    refs = remote_refs()
    failures = []
    for tag, (tag_sha, commit_sha) in EXPECTED.items():
        tag_failures = []
        actual_tag = refs.get(f"refs/tags/{tag}")
        actual_commit = refs.get(f"refs/tags/{tag}^{{}}")
        if actual_tag != tag_sha:
            tag_failures.append(f"{tag}: tag object 漂移 {actual_tag} != {tag_sha[:7]}")
        if actual_commit != commit_sha:
            tag_failures.append(f"{tag}: 目标提交漂移 {actual_commit} != {commit_sha[:7]}")
        if tag_failures:
            failures.extend(tag_failures)
        else:
            print(f"[PASS] {tag} 锚定完整（tag {tag_sha[:7]} -> {commit_sha[:7]}）")
    for failure in failures:
        print(f"[FAIL] {failure} —— 发布标签被移动或重打，立即排查！")
    if failures:
        print(f"\nTAG INTEGRITY: FAIL ({len(failures)} 项漂移)")
        return 1
    print("\nTAG INTEGRITY: PASS —— 全部发布标签锚定未动")
    return 0


if __name__ == "__main__":
    sys.exit(main())
