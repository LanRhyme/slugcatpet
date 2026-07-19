# slugcatpet-wayland

Linux Wayland 桌面宠物，让 Rain World 的蛞蝓猫住在你的屏幕上

本项目是基于 PySide6 和 GTK3 Layer Shell 的 Wayland 原生移植版本
专为 Niri 等现代 Wayland 混成器优化了渲染和交互逻辑，原生支持鼠标透明穿透和物理交互

## 运行要求

- Linux 操作系统 (Wayland 混成器环境，例如 Niri, Sway, Hyprland)
- Python 3.10 或更高版本
- 初始化时需要在本机已安装 Rain World，且必须包含 Downpour (More Slugcats) DLC
- 依赖系统级包 `gtk-layer-shell` 协议实现

## 环境准备与安装

推荐使用 Python 虚拟环境来隔离安装依赖包

```bash
# Arch Linux 依赖安装
sudo pacman -S gtk-layer-shell

# Python 依赖安装
pip install PySide6 UnityPy numpy Pillow PyGObject pycairo
```

## 启动与交互

项目提供了快速启动脚本和桌面快捷方式模板

```bash
chmod +x start.sh
./start.sh
```

你也可以将生成的 `slugcatpet-wayland.desktop` 移动到 `~/.local/share/applications/` 目录下，随后即可通过系统的应用程序启动器直接运行

**初始化说明**
首次启动时，程序会弹窗引导你选择本机的 Rain World 安装目录
程序将自动从中提取精灵图集并保存到 `~/.slugcatpet/assets` 目录
提取的素材仅存放在你的本机，完全离线使用，绝不会包含在本代码仓库中

**交互说明**
启动后，桌面右下角会出现系统托盘图标
右键点击托盘图标可展开菜单，控制侧边栏面板、设置项以及桌宠本身的显示与隐藏

## 核心技术特性

- 基于 Wayland Layer Shell 协议的全局悬浮层实现，彻底告别 XWayland 兼容性问题
- 精准的动态坐标计算，完美自适应状态栏偏移和混成器平铺布局规则
- 创新的分离式渲染架构，使用 PySide6 进行后台物理逻辑运算，通过 cairo 桥接至 GTK3 绘制透明穿透窗口
- 浮动控制面板适配，支持托盘图标快速控制显隐
- 修复并重构了圣徒 (Saint) 攀爬等特化动作在 Wayland 环境下的物理碰撞与画面出界裁切问题

## 素材与版权说明

- 本项目代码仓库不包含任何 Rain World 游戏内部的图像、音频等私有素材
- 所有的游戏素材资源均需要用户自行购买原版游戏，并在本机从自己拥有的合法正版安装目录中动态提取
- 此项目为纯粹的粉丝热爱衍生项目，Rain World 游戏本身及其相关的专有名称、美术资产及世界观设定均完全归属于其原始的合法权利所有人 (Videocult, Akupara Games 等)
- 本仓库所提供的开源代码遵循 MIT 许可证发布 (详情请参阅 [LICENSE](LICENSE) 文件)
- **特别声明**：MIT 许可证仅覆盖本仓库所编写的代码部分，绝对不授予任何人关于提取后游戏素材的任何版权、分发权或其他知识产权

---

A Linux Wayland desktop pet that puts Rain World's slugcats on your screen

This project is a native Wayland port based on PySide6 and GTK3 Layer Shell
It optimizes rendering and interaction logic for modern Wayland compositors like Niri, natively supporting mouse passthrough and physics interaction

## Requirements

- Linux OS (Wayland compositor environment, e.g., Niri, Sway, Hyprland)
- Python 3.10+
- Rain World installed locally, including the Downpour (More Slugcats) DLC
- System dependency `gtk-layer-shell`

## Install and run

```bash
# Arch Linux
sudo pacman -S gtk-layer-shell

# Python dependencies
pip install PySide6 UnityPy numpy Pillow PyGObject pycairo
```

Run the optimized startup script:

```bash
./start.sh
```

On first launch, you will be prompted to pick your Rain World install folder
Sprite atlases are extracted once to `~/.slugcatpet/assets`, kept entirely on your local machine, and used only by this program

## Assets and copyright

- This repository contains no Rain World assets. All game images are extracted locally on your machine from your own legal copy
- This is a fan project. Rain World and all related names and artwork belong to their respective owners
- The code in this repository is released under the MIT license (see [LICENSE](LICENSE))
- **Disclaimer**: The MIT license covers this repository's code only and grants no rights, distribution permissions, or intellectual property claims to any game assets
