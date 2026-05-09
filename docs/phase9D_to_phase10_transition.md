# Phase 9D → Phase 10: Transition Note

> **定位：** 封存 9D，规划 Phase 10 方向。不是设计文档，是路线选择。

---

## 9D 留下了什么

```
phase-9D-structural-consolidation (tag, 9e4b9b4)

9D.1: tag / capture / slow_weight plumbing passed
9D.2: behavior smoke caveated positive
9D.2A/B/C: simultaneous caveat traced to geometry_projection_asymmetry
9D.3: geometry-aware 4-seed validation positive
```

一句话结论：**短时 event-pair dW 可以通过 tag/capture/slow_weight 管线
沉积为可验证的长期方向性结构。** 即使在地形有固有几何不对称的情况下，
repeated ordered history 仍能在 baseline 之上产生额外方向性沉积。

这是机制层的证明——"事件顺序能沉进骨头里"。

---

## 为什么不做 9D.4

9D.4 的设计方向是 multi-scale / longer-history / cross-condition validation。
它在以下情况才需要：

- 想验证不同 event 强度/间隔/数量下的 consolidation 稳定性
- 想验证不同 unit distribution / topology 下的泛化
- 想测试 multi-event-type 下的积累和干扰

这些都是鲁棒性补强，不是核心路线推进。9D 的核心命题已经在 9D.3 上给出了
干净答案。继续在 9D 里加 seed、加条件，边际收益递减。

**建议：9D.4 只在 9D 受到质疑或需要鲁棒性报告时才回头做，不作为主线。**

---

## Phase 10 的方向

### 核心问题变了

```
Phase 9: 事件顺序能否沉积为方向性结构？
  → 答案：能。证据链完整。

Phase 10: 世界历史能否持续塑造这副骨头？
  → 开放问题。需要把 consolidation 放回更真实的
     closed-loop world / environment history 里。
```

### 可能的 Phase 10 方向

#### 10A — Closed-Loop Event History

不再用固定的 event schedule（L then R, 3 pairs），而是让 environment
根据 unit 状态反馈动态生成下一个 event。关键：environment 不再是
"实验者预设的刺激序列"，而是"和 unit 互动出来的历史"。

- 需要：environment → unit 响应 → 响应塑造下一个 event
- 验证：是否涌现出预设 schedule 没有的 event 模式
- 风险：闭环可能不稳定，需要 careful gating

#### 10B — Multi-Day Accumulation

拉长时间尺度。不再是 7500 steps 内 3 对 event，而是多天累积：
每天多次 event，跨越多天，观察 slow weight 是否持续累积还是饱和。

- 需要：更长的模拟时间、合理的时间压缩
- 验证：slow weight 是否在 days 尺度上仍有方向性信号
- 风险：饱和后无新信号（9D.3 已看到 slow weight 量级稳定）

#### 10C — Multi-Modal Experience

不止一种 event type（不只是 L/R stimulus）。引入多种 modality：
不同位置的 stimulus、不同强度的 stimulus、甚至不同的 environment 类型。

- 需要：event type 分类、多 phi 场
- 验证：不同 event type 是否产生可区分的 slow structural signature
- 风险：复杂度高，需先厘清 type encoding 机制

#### 10D — Birth-to-Death Lifecycle

不给"成年体"，而是从婴儿（少连接、弱连接）开始，让世界历史
同时塑造连接生长和 slow weight 沉积。

- 需要：connection growth/death 机制、发育阶段定义
- 验证：同样的 world history 在不同发育阶段是否产生不同结构
- 风险：需要 9A-9D 之外的很多基础设施

---

## 倾向

**从路线推进看，优先 10A（Closed-Loop Event History）。**

理由：
1. 这是 9D 的自然延伸——9D 证明了"被动 event 序列能沉积"，10A 问"主动闭环历史能不能塑造"
2. 不需要新机制（consolidation 管线已验证），只需要改 environment 侧
3. 这直接触及 Aniva 的核心命题："世界经历塑造结构"
4. 复杂度可控——从固定 schedule 到状态反馈 schedule 是增量改动

10B/10C/10D 更适合作为并行探索或后续阶段。

---

## 边界

- 9D 不改、不回退、不重新解读
- 9D.4 不是主线，仅在需要鲁棒性补强时回头做
- Phase 10 仍然在底层生命基底，不引入 reward/goal/agent/emotion/LLM
- 不宣布生命
