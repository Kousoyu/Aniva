# Phase 8B: Closed-Loop World — 20k Pilot 笔记

> **日期**: 2026-05-04
> **状态**: 低线成功，进入 120k full run
> **依赖**: Phase 8B smoke (5k)

---

## 1. 目的

在 5k smoke 确认 closed-loop event scheduler 接线正确后，20k pilot 测试：
1. 偏置效应是否持续（非单次偶然）
2. 不同 seed 是否产生不同方向的 event stream bias
3. 结构差异是否开始显现

---

## 2. 参数

| 参数 | 值 |
|------|-----|
| Steps | 20,000 |
| Seeds | 42, 999 |
| Arms | open_loop / closed_loop / shuffled_feedback |
| feedback_gain | 2.5 |
| max_bias | 0.2 |
| base_p_L | 0.5 |
| event_interval | 200 (99 events per arm) |

---

## 3. 结果

### 3.1 Event distribution

| Seed | Arm | Events | Overrides | L_frac | Δ vs open |
|------|-----|--------|-----------|--------|-----------|
| 42 | open_loop | 99 | 0 | 0.384 | — |
| 42 | closed_loop | 99 | 9 | **0.414** | +3.0% |
| 42 | shuffled | 99 | 5 | 0.414 | +3.0% |
| 999 | open_loop | 99 | 0 | 0.384 | — |
| 999 | closed_loop | 99 | 5 | **0.374** | −1.0% |
| 999 | shuffled | 99 | 2 | 0.384 | 0% |

### 3.2 结构差异

| Seed | Arm | final_wL1 |
|------|-----|-----------|
| 42 | open_loop | 0.195208 |
| 42 | closed_loop | 0.195202 |
| 42 | shuffled | 0.195209 |
| 999 | open_loop | 0.196733 |
| 999 | closed_loop | 0.196729 |
| 999 | shuffled | 0.196733 |

结构差异尚未显现（final_wL1 差异 < 1e-4）。

### 3.3 护栏

全部 6 臂正常完成，无崩溃。

---

## 4. 解读

### 4.1 低线成功：闭环机制稳定工作

- **seed=42**: 9/99 事件被覆盖，L_frac 从 0.384 → 0.414（+3 pp）
- **seed=999**: 5/99 事件被覆盖，L_frac 从 0.384 → 0.374（−1 pp）

偏置效应在 20k 尺度上持续存在，不是 5k smoke 的偶然。

### 4.2 Seed-specific direction

同一个反馈规则下，seed=42 向更多 L 事件偏，seed=999 向更少 L 事件偏。方向相反。

这符合 Aniva 当前主线：**同一个世界规则，落在不同 topology 上，生成不同历史轨迹。**

### 4.3 shuffled_feedback 部分复现

seed=42 的 shuffled 也达到 L_frac=0.414。说明当前还不能证明 state-timed feedback 优于 scrambled feedback。120k full 需要把 closed_loop vs shuffled_feedback 分离作为重要判据。

### 4.4 结构差异未显现

final_wL1 在 open/closed/shuffled 之间几乎无差异。20k 步的结构积累不足以被 ~3% 的事件分布差异显著改变。需要 120k full run 测试。

---

## 5. 成功标准判定

| 级别 | 标准 | 状态 |
|------|------|:--:|
| 低线 | event distribution 持续偏离 | ✓ |
| 中线 | 结构差异出现 | ✗ (需 120k) |
| 强线 | closed_loop 与 shuffled 分离 | ✗ (需 120k) |

---

## 6. 下一步

**Phase 8B 120k full run** — 云机，4 seed (42/77/123/999)，每 seed 3 arm，并行执行。

关键判据：
1. 结构差异是否在 120k 尺度上出现
2. closed_loop 是否与 shuffled_feedback 分离
3. 不同 seed 是否产生不同方向的 event stream bias
4. 不同 seed 是否产生不同方向的结构轨迹
