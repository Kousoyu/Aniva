"""连接 — 单元之间的影响通道."""

from dataclasses import dataclass


@dataclass
class Connection:
    """两个 Unit 之间的有向连接。

    连接承载突触传递：source 的活性通过连接影响 target。
    权重可正可负：正=兴奋性，负=抑制性。
    权重会随历史变化（plasticity 模块负责）。

    Attributes:
        cid: 连接唯一标识。
        source_id: 信号发出单元的 uid。
        target_id: 信号接收单元的 uid。
        weight: 连接权重，范围 [-1, 1]。正=兴奋，负=抑制。
        is_inhibitory: 是否为抑制性连接（由 weight 符号衍生，显式冗余标记）。
    """

    cid: int
    source_id: int
    target_id: int
    weight: float = 0.1
    is_inhibitory: bool = False

    def __post_init__(self):
        if not -1.0 <= self.weight <= 1.0:
            raise ValueError(f"weight must be in [-1, 1], got {self.weight}")
        # 保持 is_inhibitory 与 weight 符号一致
        if self.is_inhibitory and self.weight > 0:
            raise ValueError(
                f"is_inhibitory=True but weight={self.weight} is positive"
            )
        if not self.is_inhibitory and self.weight < 0:
            raise ValueError(
                f"is_inhibitory=False but weight={self.weight} is negative"
            )
