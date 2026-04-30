# Aniva

> 不是 AI 模型，不是聊天机器人，不是 agent。
> 是一个可生长、可分叉、不可完全预写结局的数字生命系统。

---

## 一句话

**先活，再聪明。**

---

## Aniva 不是什么

- 不是聊天机器人
- 不是大模型（LLM）外壳
- 不是行为树 agent
- 不是"看起来像活着"的演示程序

---

## v0.0.0.1 — 最小神经生命核

当前版本只做一件事：证明 Aniva 的生命核不是写死的。

目标：
- 200~500 个活性单元组成的自发活动系统
- 单元之间有稀疏连接，兴奋/抑制共存
- 持续扰动、能量节律、历史痕迹
- 封闭运行下出现涌现行为

### 当前状态

**第一阶段已基本完成**：代码骨架已搭建，核心数据结构（Unit、Connection、AnivaConfig）和 LifeCore 初始化逻辑就位，Observer 快照接口可用。

**尚未完成**：
- Dynamics（活性流动）
- Energy（能量消耗与恢复）
- Noise（持续扰动）
- Plasticity（连接权重变化与历史痕迹）
- Visualizer（可视化）

4 个验证实验（零输入活动、刺激响应、轨迹分叉、涌现）仅留空壳。

---

## 项目结构

```
aniva/
├── core/
│   ├── unit.py          # 活性单元
│   ├── connection.py    # 连接
│   ├── dynamics.py      # 活性流动（TODO）
│   ├── plasticity.py    # 历史痕迹与连接变化（TODO）
│   ├── energy.py        # 能量系统（TODO）
│   └── noise.py         # 扰动（TODO）
├── environment/
│   └── environment.py   # 极简环境 + Stimulus
├── life_core.py         # 生命核
├── observer.py          # 状态观测
├── visualizer.py        # 可视化（TODO）
├── experiments/         # 4 个实验（TODO）
├── config.py            # 全局配置
└── main.py              # 入口
tests/
├── test_unit.py
├── test_connection.py
└── test_life_core.py
```

---

## 安装与运行

**要求：Python 3.10+（当前开发环境），未来推荐 Python 3.11+。**

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

---

## 技术决策

| 项 | 决定 |
|---|---|
| 语言 | Python |
| 核心 | 最小神经生命核（200~500 活性单元） |
| 时间模型 | 连续时间，小步长模拟 |
| 影响方式 | 突触传递 + 局部场效应 + 弥散调节 |
| 可视化 | 活性场 + 连接图（待实现） |

---

## 许可证

MIT（待定）
