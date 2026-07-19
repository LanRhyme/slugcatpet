# slugcatpet-wayland

Linux Wayland 桌面宠物，让 Rain World 的蛞蝓猫住在你的屏幕上

本项目是基于 PySide6 和 GTK3 Layer Shell 的 Wayland 移植版本
专为 Niri 等现代 Wayland 混成器优化了渲染和交互逻辑，支持透明穿透和物理交互

## 运行要求

- Linux (Wayland 混成器环境，例如 Niri, Sway, Hyprland)
- Python 3.10+
- 依赖系统包 `gtk-layer-shell`
- 初始化时需要已下载 Rain World，包含 Downpour (More Slugcats) DLC

## 环境准备与安装

推荐使用虚拟环境安装依赖

```bash
# Arch Linux 依赖安装
sudo pacman -S gtk-layer-shell

# Python 依赖安装
pip install PySide6 UnityPy numpy Pillow PyGObject pycairo
```

## 启动方式

直接运行优化后的启动脚本

```bash
./start.sh
```

或将生成的 `slugcatpet-wayland.desktop` 移动到 `~/.local/share/applications/` 后，通过桌面启动器运行

首次启动会引导你选择本机的 Rain World 安装目录，从中提取精灵图集到 `~/.slugcatpet/assets`
提取的素材仅存放在本机，不会包含在仓库中

## 核心特性

- 基于 Wayland Layer Shell 协议的全局悬浮层
- 动态坐标计算，自适应状态栏偏移和混成器布局
- 分离式渲染架构 (PySide6 逻辑运算，GTK3 绘制透明窗口)
- 浮动控制面板适配，支持托盘图标快速控制显隐
- 修复了圣徒攀爬等逻辑在 Wayland 下的出界裁切问题

## 素材与版权说明

- 本仓库不包含任何 Rain World 游戏素材，全部游戏图像需从用户本机的合法安装中提取
- 此项目为粉丝衍生项目，Rain World 及相关名称、美术资产均归其原始权利人所有
- 本仓库代码以 MIT 许可发布，该许可仅覆盖代码部分，不授予任何游戏素材的相关权利
