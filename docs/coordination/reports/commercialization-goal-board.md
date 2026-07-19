# X-Agent Commercialization Goal Board

## G0 xagent 商用完整交付
- status: active
- close condition: G1 + G2 + G3 全部 done

## G1 内部试点可稳定使用
- status: done
- completed packages: G1-A1, G1-A2, G1-A3, G1-A4
- gate result: 功能门=done；稳定性门=done；权限/可追溯门=done；试点交付门=done

## G2 正式商用 GA
- status: active
- active package: G2-B1 候选冻结包
- ready packages: G2-B2 目标环境演练包
- candidate: `commercialization-ladder @ 3a1eb28`
- candidate PR: `#11`
- candidate checks: backend=pass；frontend=pass；license-gate=pass；promptfoo-eval=pass

## G3 企业级长期运营
- status: pending

## blocked
- reason: none
- owner: Claude Code
- recovery condition: 任何当前 active 包恢复到 in_progress 或 done
- next checkpoint: 当前阶段 Gate 完成后推进下一包
