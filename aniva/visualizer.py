"""可视化 — 活性场与连接图的实时显示.

TODO（后续实现）:
- 用 matplotlib 动画或类似库实时展示活性场。
- 支持连接关系可视化、信号流动显示、环境刺激标注。
- 当前仅定义类接口。
"""


class Visualizer:
    """实时可视化生命核状态。

    TODO: 第二步或以后实现。
    """

    def __init__(self):
        raise NotImplementedError("Visualizer not yet implemented")

    def update(self, snapshot: dict) -> None:
        """用新的状态快照更新显示。"""
        raise NotImplementedError("Visualizer not yet implemented")
