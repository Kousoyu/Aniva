"""Aniva 入口 — 启动与运行生命核."""

import sys
from aniva.config import AnivaConfig
from aniva.life_core import LifeCore
from aniva.observer import Observer


def main():
    """Aniva 主入口。"""
    print("Aniva v0.0.0.1 — 最小神经生命核")
    config = AnivaConfig()
    core = LifeCore(config)
    observer = Observer(core)
    print(f"  Units:      {core.unit_count}")
    print(f"  Connections:{core.connection_count}")
    print(f"  Seed:       {config.seed}")
    print("骨架已搭好，动力学待实现。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
