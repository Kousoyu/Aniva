# Phase 10A.0 — Design Freeze

> **定位：** 10A.1 scheduler plumbing smoke 的施工图。
> 填死所有可调参数、公式、schema、pass/fail 标准。
> 10A.1 跑完之后回头看这个文档，判断是否通过，不边跑边改。

---

## 1. 10A.1 目标

**不是证明闭环塑造结构。**
是证明：**"世界事件发生器"没有作弊、没有退化、可回放、可审计。**

具体：
1. 参数化随机 scheduler 能产生 non-degenerate event history
2. event log 字段完整，可验证
3. matched replay 精确（hash exact）
4. scheduler 输入白名单未被违反
5. 不同 seed 产生不同的 event history（分叉存在）

---

## 2. 运行参数

| 参数 | 值 | 说明 |
|------|-----|------|
| seeds | 42, 77 | 2 seeds pilot |
| unit_count | 300 | 匹配 9D 规模 |
| total_steps | 7500 | 匹配 9D.3 |
| warmup | 2000 | 前 2000 步无决策，让动力学稳定 |
| decision_interval | 500 | 每 500 步 scheduler 做一次决策 |
| decision_points | 11 | (7500 − 2000) / 500 |
| pulse_duration | 80 | 匹配 9D PULSE_DURATION |
| plasticity | **OFF** | 10A.1 不开 9C，不开 9D |
| consolidation | **OFF** | — |

## 3. 事件集

```
E = {none, L, R, simultaneous}
```

| 事件 | 含义 | phi 生成 |
|------|------|---------|
| none | 不发射事件 | — |
| L | L-hemi stimulus | phi_L only |
| R | R-hemi stimulus | phi_R only |
| simultaneous | 双侧同时 | phi_L + phi_R combined |

---

## 4. 参数化随机调度器

### 4.1 输入（Allowlist）

调度器在每个 decision point 读取：

```
obs = {
    "activity_L": float,  # mean unit activation in x < -0.1 region
    "activity_R": float,  # mean unit activation in x > 0.1 region
}
```

- `activity_L`, `activity_R` 从当前 step 的 unit activations 计算
- 区域分类使用与 9D 相同的 `_unit_region(pos)`: x < -0.1 → L, x > 0.1 → R
- 不读取 M 区域 (|x| ≤ 0.1) 的 activity

### 4.2 禁止输入（Denylist）

调度器 **不得** 读取以下任何信息：

- `arm_label` / experiment group
- `event_count` / event history / 已经发过几个 event
- `slow_weight_cache`, `tag_cache`, `connections`, `_weight_cache`
- future observations / post-hoc summaries / validation metrics
- 任何在 decision time 之后才生成的数据

### 4.3 调度公式

```
logit_none = b_none                          # 基线 none 倾向
logit_L    = w * activity_R + b_L            # R 侧活跃 → 发 L stimulus
logit_R    = w * activity_L + b_R            # L 侧活跃 → 发 R stimulus
logit_sim  = b_sim                           # 恒定低概率 simultaneous

probs = softmax([logit_none, logit_L, logit_R, logit_sim] / τ)
```

| 参数 | 冻结值 | 说明 |
|------|--------|------|
| w | +5.0 | 反馈强度：对侧 activity 每单位增加 logit |
| b_none | +1.0 | none 基线偏高，防止 event flooding |
| b_L | -1.5 | L event 基线偏低（需要 R activity 推动） |
| b_R | -1.5 | R event 基线偏低（需要 L activity 推动） |
| b_sim | -3.0 | simultaneous 非常罕见 |
| τ | 1.0 | softmax temperature |

**设计意图：** 这是一个 homeostatic 反馈——哪一侧更活跃，就向对侧发 stimulus。
L 侧活跃 → R event 概率升高（刺激右侧）；R 侧活跃 → L event 概率升高（刺激左侧）。
none 有正基线偏置，确保不会每步都发 event。

**参数 θ = {w, b_none, b_L, b_R, b_sim, τ} 全部冻结。**
10A.1 期间不调整，10A.2–10A.4 期间不调整。
如果要改参数，必须作为新的 config variant 注册，不能覆盖原值。

### 4.4 随机采样

```python
u = sched_rng.random()  # uniform [0, 1)
event = categorical_sample(probs, u)
```

- `sched_rng` 独立于 `env_rng`，seed 可独立设置
- `u` 和 `probs` 都写入 event log
- replay 时不重新采样，直接使用 logged event

---

## 5. Event Log Schema

每条决策记录一行：

| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | str | `phase10A1_seed{seed}_{timestamp}` |
| arm | str | `closed_loop` |
| seed_env | int | seed for environment / LifeCore init |
| seed_sched | int | seed for scheduler RNG |
| code_sha | str | git rev-parse HEAD (short) |
| config_sha | str | SHA256 of resolved config dict |
| t_decision | int | step number of decision point |
| obs_activity_L | float | region_activity_L at time t |
| obs_activity_R | float | region_activity_R at time t |
| obs_hash | str | SHA256("{activity_L:.6f},{activity_R:.6f}") |
| logit_none | float | — |
| logit_L | float | — |
| logit_R | float | — |
| logit_sim | float | — |
| prob_none | float | after softmax |
| prob_L | float | — |
| prob_R | float | — |
| prob_sim | float | — |
| u_draw | float | sched_rng uniform draw |
| chosen_event | str | `none` / `L` / `R` / `simultaneous` |
| payload_hash | str | SHA256 of phi vector (for non-none events) |
| applied_ok | bool | whether event was successfully applied |

---

## 6. Replay Exactness 规则

### 6.1 Event Trace

```
trace = [(t_decision, chosen_event, payload_hash), ...]
trace_hash = SHA256("|".join(f"{t}:{e}:{h}" for t,e,h in trace))
```

### 6.2 Matched Replay 硬门槛

| 检查 | 阈值 | 失败后果 |
|------|------|---------|
| trace_hash 一致 | exact match | formal 无效 |
| event count 一致 | 0 diff | formal 无效 |
| timestamp 序列一致 | 0 diff | formal 无效 |

### 6.3 Replay 执行规则

- replay player 读取 logged trace
- 在 `t_decision` 时刻，直接注入 `chosen_event`（如果非 none）
- **不调用 scheduler.propose()**
- **不读取 obs**
- **不重新采样**
- payload 必须与 `payload_hash` 一致
- unit dynamics 照常运行（只是 event source 不同）

---

## 7. 10A.1 Pass/Fail Criteria

### 协议层 — HARD（任一 FAIL = 10A.1 无效）

| # | Criterion | 检测方式 |
|---|-----------|---------|
| P1 | 无 crash / NaN | 自动化检查 |
| P2 | event_log 所有必填字段非空 | schema validation |
| P3 | scheduler 输入仅含 activity_L, activity_R | 单元测试 + 运行时 assert |
| P4 | scheduler 未读 event_count / arm_label / weights / tags | 单元测试 |
| P5 | matched replay trace_hash 完全一致 | 自动化比对 |

### 行为层 — SOFT（FAIL 需解释，不自动作废）

| # | Criterion | 合格阈值 |
|---|-----------|---------|
| B1 | 至少触发 1 个非 none event | event_count > 0 |
| B2 | 不是每步都触发 | none_rate > 30% |
| B3 | 也不是从不触发 | none_rate < 90% |
| B4 | 非 none event 中至少出现 2 种类型 | n_unique_types ≥ 2 |
| B5 | seed 42 和 seed 77 的 event history 不同 | trace_hash(42) ≠ trace_hash(77) |

---

## 8. Anti-Cheat Checklist（10A.1 实施前全部勾选）

- [ ] scheduler 函数签名不含 `arm_label` 参数
- [ ] scheduler 不 import `plasticity_consolidation`, `plasticity_event_pair`
- [ ] scheduler 不访问 `core._slow_weight_cache`, `core._tag_cache`, `core._weight_cache`
- [ ] scheduler 不访问 `core.connections`（除了 region assignment 通过独立 util 获取）
- [ ] scheduler 无内部计数器（不数 event_count）
- [ ] event generation 只用 `obs` + `sched_rng`，不用任何额外状态
- [ ] `env_rng` 和 `sched_rng` 独立初始化
- [ ] `sched_rng` 的 seed 记录在 event_log 中
- [ ] replay player 不 import scheduler 模块
- [ ] summary/metrics 计算全在 offline 脚本，不在 step loop 内
- [ ] 所有 config 参数以 dict 形式冻结，SHA256 记录
- [ ] 不存在 `if arm == "closed_loop"` 分支在 scheduler 内部

---

## 9. 输出产物

| 产物 | 路径 |
|------|------|
| event log | `results/phase10A1_seed{seed}_event_log.csv` |
| run summary | `results/phase10A1_seed{seed}_summary.json` |
| replay log | `results/phase10A1_seed{seed}_replay_event_log.csv` |
| replay summary | `results/phase10A1_seed{seed}_replay_summary.json` |
| trace hash file | `results/phase10A1_seed{seed}_trace_hash.txt` |

---

## 10. 不在 10A.1 范围内

- 不开 event-pair plasticity（9C）
- 不开 consolidation（9D）
- 不比较结构差异
- 不跑 formal validation
- 不调参数 θ
- 不跑 ECS（纯本地）
