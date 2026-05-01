# Aniva — 实验日志

> 记录 v0.0.0.1 各阶段的关键机制变更和实验结果。
> 不写"它活了"，只记客观现象。

---

## Phase 3.5 ~ 3.9：核心动力学搭建

**做了什么：**
- 突触传递：source 通过 weighted connection 影响 target
- 噪声扰动：每步微小随机波动
- 能量系统：消耗 + 恢复
- 历史痕迹（trace）：累积 + 衰减
- Leak：activation 向 baseline 自然漂移
- Threshold：每个 unit 有独立阈值
- AnivaConfig 集中管理所有参数

**机制：**
- `unit.activation += synaptic_input * strength * dt * energy_factor`
- 能量 gate：`energy_factor = min_energy_factor + (1 - min_energy_factor) * energy`

---

## Phase 3.10 ~ 3.11：能量平衡修正

**问题：** 默认参数下能量恢复速率低于消耗，长时间运行能量会归零。

**修正：**
- `energy_recovery_rate`: 0.005 → 0.008
- 改为 energy gate（调制 input 响应），而非直接压制 activation
- `min_energy_activation_factor = 0.25`

**结果：** 能量不再慢性归零，基线（baseline_activity=0.05）附近能量稳定。

---

## Phase 3.14：soft threshold

**问题：** 硬阈值（activation > threshold 才输出）导致几乎 0% 单元触发传导。

**修正：**
- 引入 sigmoid 软阈值：`effective_output = activation * sigmoid((activation - threshold) / softness)`
- `threshold_softness = 0.02`

**结果：** ~80% 单元有极弱输出（soft_output），~0-1.7% 有强输出（strong_output）。
系统进入"稳定微传导态"：不静默，但也不活跃。

---

## Phase 3.16：网络边界诊断

**做了什么：** 扩展参数扫描工具，支持 `connection_density` 和 `exc_inh_ratio` 扫描。

**关键发现：**
- 当前网络只有两个状态：微传导（strong ~0%）或爆燃（strong 65-100%）
- 没有"稳定小比例强输出"的中间态
- 爆燃边界在 `synaptic_strength * density ≈ 0.005` 附近
- `exc_inh_ratio = 0.8`（80% 兴奋）让网络过度偏兴奋

---

## Phase 3.17：synaptic response saturation

**问题：** 突触输入线性叠加，activation 已高时仍全量接受兴奋输入 → 无上限正反馈。

**修正（符号分离饱和）：**
```python
if raw_delta >= 0:
    delta = raw_delta * (1.0 - unit.activation)   # 兴奋受天花板限制
else:
    delta = raw_delta * unit.activation            # 抑制在低 activation 时受地板限制
```

**结果：**
- 首次出现中间态：`cd=0.02, eir=0.6, ss=0.20` 下 `mean_act=0.333, energy=0.393, hard=51.7%`
- 3 组原爆燃组合被缓和
- 但 `eir=0.8` 组合依然大面积爆燃

**结论：** 饱和机制必要但不充分，需要配合 E/I 平衡调整。

---

## Phase 3.18：E/I 平衡细扫 + 多 seed 验证

**目标：** 找到跨 seed 稳定的中间态走廊。

**Phase 3.18 单 seed 细扫 (seed=42)：**
- 扫描范围：cd={0.02, 0.05}, eir={0.5-0.8}, ss={0.1-0.2}
- 发现 5 个中间态候选，全部在 eir=0.5-0.55

**Phase 3.18b 多 seed 验证 (seeds 1,2,3,42,77)：**
- 冠军组合：`cd=0.05, eir=0.50, ss=0.20` — 4/5 种子中间态，0 爆炸
- seed=77 在所有组合下偏静默，但不爆炸

**Phase 3.18c seed=77 定向扫描：**
- 提高 ss 到 0.30，eir=0.45-0.55 时 seed=77 全部进入中间态
- 其他 seed 在相同参数下也不爆炸
- eir=0.60 对任何 seed 都是危险边界

**关键发现：**
- `cd=0.05, eir=0.50, ss=0.30` 是唯一 5/5 种子全部进入中间态的组合
- 中间态走廊在 `eir ∈ [0.45, 0.55]`
- `eir ≥ 0.60` 进入危险区

---

## Phase 3.19：默认参数校准

**修改：**

| 参数 | 旧默认 | 新默认 |
|------|--------|--------|
| exc_inh_ratio | 0.80 (80% 兴奋) | 0.50 (50% 兴奋) |
| synaptic_strength | 0.05 | 0.30 |
| connection_density | 0.05 | 0.05 (不变) |

**默认 free-run (seed=42, 300 单元, 1000 步)：**

```
step=100:  mean_act=0.050  energy=0.584  hard=0%     ← 预热
step=200:  mean_act=0.061  energy=0.606  hard=0%     ← 积蓄
step=400:  mean_act=0.339  energy=0.483  hard=45.3%  ← 点火
step=500:  mean_act=0.402  energy=0.279  hard=52%    ← 能量暂降
step=700:  mean_act=0.372  energy=0.327  hard=49%    ← 恢复
step=1000: mean_act=0.363  energy=0.365  hard=48%    ← 稳定平衡
```

**多 seed 验证 (seeds 1,2,3,42,77)：**

| seed | mean_act | mean_energy | hard_active | strong_output |
|------|----------|-------------|-------------|---------------|
| 1    | 0.338    | 0.430       | 45.0%       | 46.7%         |
| 2    | 0.361    | 0.385       | 48.0%       | 50.3%         |
| 3    | 0.381    | 0.415       | 50.3%       | 51.0%         |
| 42   | 0.371    | 0.377       | 49.7%       | 52.3%         |
| 77   | 0.379    | 0.331       | 50.3%       | 52.3%         |

**5/5 种子全部进入中间态。0 爆炸，0 静默。**

---

## Phase 4.0：点刺激环境接口

**做了什么：**
- `Stimulus` 增加 `start_step`/`duration_steps`/`is_active()`/`influence_at()`
- `Environment` 增加 `compute_influences()`，按空间距离衰减计算各单元影响
- `LifeCore.step()` 新增可选参数 `env_influences`，在突触传递之前应用
- 新增 `tests/test_environment.py`（25 个环境测试）

**设计原则：**
- 环境输入在突触传递之前："外界先轻推，网络自己传播"
- 只实现点刺激，架构预留全局刺激
- 不影响无刺激时的 free-run 行为

---

## Phase 4.1：环境刺激响应实验

**做了什么：**
- 实现 `exp2_stimulus.py`：对比同 seed 下 baseline（无刺激）和 stimulus（点刺激）的轨迹
- 记录三阶段（pre / during / post）的对比指标和 trajectory_distance
- 支持 CLI 参数

**关键发现（seed=42, intensity=0.03, 300 单元, 1000 步）：**
```
step=300:  traj_dist=0.000000  ← 刺激前完全一致
step=400:  traj_dist=0.189058  ← 刺激期间明显分叉
step=1000: traj_dist=0.125733  ← 600 步后仍未归零
```

- 刺激只直接影响 4.67% 的单元（14/300），是"轻触"而非"接管"
- 刺激结束后 trajectory_distance 不归零，系统走上不同轨迹
- 验证了 VISION.md 实验 2 的核心假设

---

## Phase 4.2：刺激参数扫描

**做了什么：**
- 实现 `exp2_stimulus_sweep.py`：批量运行 `exp2_stimulus.run()`，支持多维度扫描
- 内置响应分类：`none`（dur_max < 0.01）、`touch`（有分叉无崩溃）、`takeover`（hard > 80% 或 energy < 0.15）

**第一轮扫描（intensity 0.01/0.03/0.05 × seed 1/2/3/42/77）：**

| | seed=1 | seed=2 | seed=3 | seed=42 | seed=77 |
|---|---|---|---|---|---|
| 0.01 | touch | touch | **none** | touch | touch |
| 0.03 | touch | touch | touch | touch | touch |
| 0.05 | touch | touch | touch | touch | touch |

**结果：1 none / 14 touch / 0 takeover**

**关键发现：**
- `intensity=0.01` 处于边界：seed=3 近乎无视（dur_max=0.00386），不同先天结构对弱刺激敏感性不同
- `intensity=0.03` 是稳定轻触强度：全 seed 响应，无接管
- `intensity=0.05` 更强但安全：无接管，无能量崩溃
- **seed=77 独特行为**：baseline 下偏冷（B_act=0.07），刺激能将其"唤醒"到正常中间态（S_act=0.36-0.39）
  - 同一环境事件对不同先天结构产生不同命运——不是写死的

---

## 当前系统状态

### 已实现的机制

| 机制 | 状态 |
|------|------|
| 活性单元 (Unit) | ✅ |
| 连接 (Connection) | ✅ |
| 突触传递 (soft threshold) | ✅ |
| 噪声扰动 | ✅ |
| 能量消耗与恢复 | ✅ |
| Leak (向 baseline 漂移) | ✅ |
| 历史痕迹 (trace) | ✅ |
| 能量 gate (调制输入响应) | ✅ |
| Synaptic response saturation | ✅ |
| Observer / 指标系统 | ✅ |
| 参数扫描工具 | ✅ |
| Environment (点刺激接口) | ✅ |
| 环境刺激响应实验 (exp2) | ✅ |
| 刺激参数扫描 (exp2 sweep) | ✅ |

### 尚未实现

| 机制 | 状态 |
|------|------|
| Plasticity (连接变化) | 待定 |
| 局部场效应 | 待定 |
| 弥散调节 | 待定 |
| Visualizer (可视化) | 待定 |

### 默认参数 (v0.0.0.1 校准后)

```python
unit_count = 300
connection_density = 0.05
exc_inh_ratio = 0.50
synaptic_strength = 0.30
threshold_softness = 0.02
noise_strength = 0.01
baseline_activity = 0.05
leak_rate = 0.02
threshold_min = 0.2
threshold_max = 0.4
min_energy_activation_factor = 0.25
```

### 测试数

**161 个**（最后更新：Phase 4.2）

---

*日志起始：2026-05-01*
*最后更新：Phase 4.2*
