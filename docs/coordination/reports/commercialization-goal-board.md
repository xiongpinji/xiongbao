# X-Agent Commercialization Goal Board

## G0 xagent 商用完整交付
- status: active
- close condition: G1 + G2 + G3 全部 done

## G1 内部试点可稳定使用
- status: done
- completed packages: G1-A1, G1-A2, G1-A3, G1-A4
- gate result: 功能门=done；稳定性门=done；权限/可追溯门=done；试点交付门=done

## G2 正式商用 GA
- status: done
- completed packages: G2-B1, G2-B2, G2-B3, G2-B4
- gate result: 候选冻结门=done；目标环境演练门=done；发布/回滚门=done；签字/证据门=done

## G3 企业级长期运营
- status: active
- active package: G3-C1 HA / K8s 包（验证中，已有首轮通过证据）
- ready packages: G3-C2 可观测 / 告警包（验证中，已有首轮通过证据）；G3-C3 审计 / 保留策略包（验证中，已有首轮通过证据）；G3-C4 容量 / 扩展边界包

## blocked
- reason: none
- owner: Claude Code
- recovery condition: 任何当前 active 包恢复到 in_progress 或 done
- next checkpoint: 当前阶段 Gate 完成后推进下一包
