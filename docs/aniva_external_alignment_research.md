# Aniva 外部对齐研究（三路调研综合）

**日期：** 2026-05-13
**范围：** 经典 ALife 项目、神经动力学 / 学习规则、现代 agent / open-ended 系统
**目的：** 把前人的理念和踩过的坑，落回到 Aniva 当前的 10D.3 证据和 10D.4 方向上

---

## 一、三路最重要的收敛

三路独立调研在**同一个点上汇合**，这是这次研究最硬的信号：

> **10D.3 观察到的 `h_tag_ratio < 1.0`（被 tag 的连接处在历史低 h 区域）不是异常，
> 是多个独立学科早已预言的机制。**

| 路径 | 对 h_tag_ratio < 1.0 的解释 |
|------|-----------------------------|
| 神经生理 | **BCM sliding threshold**：高历史活动 → θ_M 上移 → 同样输入更难诱发 LTP |
| 分子生物 | **STC heterosynaptic inhibition**（Sajikumar 2017）：前 10-40 分钟高活动会**阻断** tag 形成 |
| 生物回路 | **VTA-海马 novelty loop**（Lisman-Grace）：novelty 本身就定义为"与熟悉基线的偏差"，DA 对熟悉区域的 LTP 通门低 |
| ALife | **Surprise Novelty**（Hung 2023）：tag 时刻 h 偏低 = 背景已学会、tag 在标新东西 |
| 现代理论 | **Schmidhuber 压缩进度**：不奖励"已压缩区域"，只奖励"正在学会"的区域 |

这五个独立领域都在同一件事上达成一致：**capture 的正向先验不是"熟悉"，而是"事件打进历史低活动区域"。**

10D.3 不是失败实验，是一次**跨学科三角验证**。

---

## 二、对 10D.4 方向的修正（五条具体）

10D.4 当前设计的三个候选信号 — **background / novelty / surprise** — 方向对，但**细节不够生物化**。根据调研需要修正：

### 修正 1：surprise_conn 应该是**有符号**的

```python
# 当前设计（错）：
surprise_conn = tag_abs * abs(phi_conn - h_norm_conn)

# 修正（对齐 Schultz dopamine RPE）：
surprise_conn = tag * (phi_conn - h_norm_conn)   # 保留符号
```

**理由：** 生物上 RPE 是双向的——正 surprise 增强，负 surprise 抑制 / 擦除。
绝对值丢掉了最关键的语义区分。BCM 的 `φ(y, θ_M)` 也在过零点改变符号。

### 修正 2：h[u] 必须**多时间尺度**，不能只有 τ=10000

生物至少三级：
- **秒级 BTSP**（τ≈0.7-1.3s）— Bittner/Magee 2017
- **分钟级 BCM / cAMP**（τ≈10 min）
- **小时级 STC 蛋白**（τ≈1h）

Aniva 当前从 ms tick 直接跳到 τ=10000 的 h[u]，**中间缺秒级 eligibility 桥梁**。
这可能就是 h_capture_corr ≈ 0 的根因——capture 发生在秒-分钟，h 在分钟-小时，**时间尺度错配**。

**建议：** 10D.4 或 10D.5 引入
```python
h_fast  (τ ≈ 100-500 steps)   # BTSP / 秒级 eligibility
h_slow  (τ ≈ 10000 steps)     # BCM / 分钟级阈值
```

surprise 用 `h_fast` 算（捕捉事件窗口偏差），novelty 用 `h_slow` 算（捕捉背景基线）。

### 修正 3：加入"近期活动抑制"作为 tag 置位门

Sajikumar 2017 的 heterosynaptic inhibition 是**直接匹配 h_tag_ratio < 1.0 的生物机制**。

```python
tag_gate = 1.0 / (1.0 + α * h_recent)   # h_recent: τ≈500-1000
```

这不是重新定义 novelty 信号，而是在 tag 置位阶段就**主动利用** h_tag_ratio < 1.0 的发现。

### 修正 4：novelty/surprise 应有**全局广播**维度，不只是 per-connection

生物上 DA / NE 是**广播第三因子**，同时给所有突触一个全局 M(t)。
Aniva 当前的 novelty/surprise 完全 per-connection，**缺广播维度**。

Gerstner 三因子标准形式：`Δw_ij = e_ij · M(t)`（局部 eligibility × 全局调制）。

10D.4 应同时测三种：
1. 纯局部：per-connection novelty
2. 纯全局：mean(surprise) 作为广播因子
3. 乘积：local_eligibility × global_gate（最接近生物）

### 修正 5：加第四个候选信号 —— **surprise novelty**（误差的稀有性）

两路调研独立建议：
- 经典 ALife → Hung 2023 Surprise Novelty：用重建误差的**稀有性**，不是误差本身
- 现代 open-ended → Schmidhuber 压缩进度：奖励 error 的**减少速率**

当前 10D.4 候选信号都是 "instantaneous magnitude"，**缺"这个 surprise 本身有多罕见"这一维**。

**可操作化候选：**
```
surprise_novelty_conn = tag * |phi - h_slow| / (recent_surprise_std + ε)
```

这避免 noisy-TV 陷阱——持续噪声的 surprise 高但不稀有，不该触发 capture。

---

## 三、对 Aniva 长期路线的启示

### 1. complexity plateau 是所有 ALife 项目的墓地，Max 已本能避开主坑

| 前人死因 | Aniva 的避开方式 |
|---------|-----------------|
| 外部 fitness 塞进核（Sims、Avida、NCA） | "先活，再聪明" 拒绝 reward 目标 |
| 规则固定无 plasticity（Lenia、Boids、GoL） | 持续 plasticity + 四因素耦合 |
| 单向基因→神经决定（Polyworld） | 结构会被历史改变 |
| 纯代码无形态（Tierra/Avida） | 位置/能量/泄漏等物理约束 |
| 监督目标伪装成涌现（NCA） | 没有外部 loss |

### 2. 前人还没解决的 #1 问题：**共享资源的竞争**

Tierra 涌现 parasite 是因为 CPU 时间被争夺。Creatures 涌现"脑衰退综合症"是因为神经化学空间被挤压。
**Aniva 目前没有"被争夺的稀缺资源"** — 能量是 per-unit 的、连接是独立的。
长期看这可能是 plateau 的来源。10D 之后值得考虑引入某种 **shared budget**（总 capture 容量？总 slow_weight 预算？空间竞争？）。

不是现在做，但记录在案。

### 3. "真活 vs 假活" 的操作性分界线

现代 agent 调研给了一个很准的定义：

> **真活 = 关掉外部输入它仍在变；假活 = 关掉 prompt 它就静止。**
>
> Aniva 的神经动力学核已在真活这一侧。

这和 Max 的 Alicization Fluctlight 直觉一致。Generative Agents（Smallville）看似社交丰富，本质是 prompt → LLM → response 循环，**没有持续的内部状态演化**——这是 Aniva 从第一天起就拒绝的路线。

**10D.4 的进一步动作不能破坏这条红线：**
- novelty/surprise 的 evaluator **不能外包给外部模型**（像 ASAL 用 CLIP 那样会把"新"锁死在人类视觉先验里）
- novelty 信号必须是**内部动力学自己产生**的

### 4. Creatures (Norns) 的死法是**最准的警告**

Steve Grand 的系统真的涌现了开发者没预设过的"脑衰退综合症"——这是 Max 定义的"真活"——但因为**不可观测、不可调试**就死了，没有第二代。

**Aniva 的 Observer / 重放 / 指标系统必须优先于新机制**。
当前 Phase 10D 的四臂协议（closed_loop / exact_replay / divergent_warmup / matched_control）+ P1-P7 检查体系已经比 Creatures 健全得多，应坚持这个水准。

### 5. Aniva 有一个**独立贡献点**浮出来了

前人所有 novelty search / QD / intrinsic motivation 都在 **agent-环境框架**里算 novelty。
Aniva 可以在**纯内部动力学**里算 novelty —— `slow_weight 轨迹自己的 novelty` / `h[u] 历史场自己的 surprise`。

这和 Max 的 "不把方向感外包给 evaluator" 的红线一致，也是非 LLM 路线才能走的独立方向。
**未来论文的卖点可能就在这里。**

---

## 四、对 10D.4 design 的具体落地建议

基于以上，建议 10D.4 设计文档在当前版本上**新增 / 修正**：

### 候选信号从 3 个扩到 5 个

| # | 名称 | 公式 | 生物依据 |
|---|------|------|---------|
| 1 | background alignment | cosine(h_conn, tag) | 10D.3 baseline |
| 2 | **novelty (unchanged)** | tag * (1 − h_norm) | BCM / STC heterosynaptic inhibition |
| 3 | **surprise (加符号)** | tag * (phi − h_norm) | Schultz RPE |
| 4 | **surprise novelty** (新) | (3) / recent_std | Hung 2023 / Schmidhuber compression |
| 5 | **global-gated** (新) | local × mean(surprise) | Gerstner three-factor |

### 额外诊断（τ 分层）

10D.4 可以同时用 τ = 500 / 2000 / 10000 三个时间尺度的 h[u] 做诊断，但**严守边界**：
- 这是"时间尺度错配假设"的 falsification test，不是 τ 调参
- 如果短 τ 让 D2 alignment 从 0 变正，确认错配假设
- 不允许挑一个好看的 τ 进机制

### 待决策：是否在 10D.4 就引入 h_fast

**保守派：** 10D.4 只做诊断，保持 h[u] 单一 τ，只在候选信号公式里加多种修正。
**激进派：** 10D.4 引入 h_fast (τ≈500) 作为 read-only trace，与 h_slow 平行。

我倾向**保守派**：10D.4 先把候选信号扩到 5 个测完，如果哪个 surprise 候选跑出来但时间尺度错配得明显，再走 10D.4B 引入 h_fast。

---

## 五、值得进一步精读的工作（优先级排序）

**10D.4 前必读：**
1. Gerstner 2018 Frontiers — three-factor rule 综述
2. Sajikumar 2017 — STC heterosynaptic inhibition
3. Lisman-Grace 2005 — VTA-HC novelty loop
4. Hung 2023 (arXiv 2308.04836) — Surprise Novelty

**10D.5+ 参考：**
5. Schmidhuber 2008 (arXiv 0812.4360) — Driven by Compression Progress
6. Bittner-Magee 2017 — BTSP 秒级 eligibility
7. BCM 1982 / Abraham metaplasticity review — sliding threshold
8. Lehman/Stanley 2008 — Novelty Search 原著
9. Mouret/Clune 2015 — MAP-Elites（如果未来做行为多样性）

**警示性阅读（看它们怎么死的）：**
10. Creatures / Steve Grand 经验 — 不可调试的悲剧
11. Generative Agents (Park 2023) — 假活的典型范式
12. Lenia QD extension (arXiv 2406.04235) — 美丽但无继承的吸引子集合

---

## 六、一句话结论

> 10D.3 不是孤立的实验结果。`h_tag_ratio < 1.0` 是 BCM / STC / VTA novelty loop / Surprise Novelty / Schmidhuber
> 五条独立线索共同预言的现象。10D.4 方向正确，但当前候选信号需要三点修正：
> surprise 加符号、引入 surprise novelty（误差稀有性）、加全局广播维度。
> Aniva 的独立贡献点是"在纯内部动力学里算 novelty"，这是非 LLM 路线才能走的方向。
