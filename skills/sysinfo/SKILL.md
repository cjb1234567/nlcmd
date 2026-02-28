---
name: sysinfo
description: 获取系统信息（操作系统、版本、CPU、Python版本）
triggers:
- 电脑信息
- systeminfo
- sysinfo
---

# 系统信息 Skill

## 使用时机
- 当用户希望查看当前机器的基础信息（OS、版本、CPU、Python版本）。

## 执行方法
- 在命令行中运行: `python skills/sysinfo/scripts/sysinfo.py`
- 不需要任何参数。

## 输出
- 每行一个键值对，例如：
  - OS: Windows 10
  - Version: 10.0.19045
  - Machine: AMD64
  - Processor: Intel64 Family 6 Model XX Stepping X, GenuineIntel
  - Python: 3.11.7
