# CC Switch

Windows 托盘工具，用于快速切换 Claude Code 的 API 配置。

## 原理

读取 `~/.claude/settings-*.json` 中的 `env` 和 `model` 字段，覆盖写入 `~/.claude/settings.json`，其他字段（如 `enabledPlugins`）保持不变。下次启动 Claude Code 时生效。

## 支持的配置

| 菜单名称 | 设置文件 | Base URL |
|----------|---------|----------|
| One API (AI In One) | `settings-one-api.json` | https://ai-in.one |
| Fucheers (New API) | `settings-fucheers.json` | https://www.fucheers.top |
| GLM5 (阿里云) | `settings-glm5.json` | https://dashscope.aliyuncs.com |
| TimeSniper (一元) | `settings-timesniper.json` | https://timesniper.club |
| AI派 (AIPaiBox) | `settings-aipaibox.json` | https://api.aipaibox.com |

## 使用

双击 `start.bat` 后台启动，或：

```
python main.py
```

- 右键托盘图标：弹出配置菜单，当前配置带 ✓
- 左键托盘图标：同上
- 鼠标悬停：显示当前配置名称
- 切换成功后弹出系统通知

## 依赖

```
pip install PyQt5
```
