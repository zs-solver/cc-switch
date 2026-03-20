# CC Switch

Windows 托盘工具，用于快速切换 Claude Code 的 API 配置。

## 原理

读取 `settings-*.json` 中的 `env` 和 `model` 字段，覆盖写入 `~/.claude/settings.json`，其他字段（如 `enabledPlugins`）保持不变。下次启动 Claude Code 时生效。

## 配置文件查找

支持从两个位置加载配置文件，**优先项目目录**：

1. `./settings/` — 项目本地目录（含密钥，已 gitignore）
2. `~/.claude/` — 家目录（回退）

## 自动发现

启动时自动扫描上述两个目录中的 `settings-*.json` 文件，未在 `config.json` 中登记的会自动补充并持久化，无需手动编辑 `config.json`。自动推导规则：

- **name**：从文件名推导，如 `settings-foo-bar.json` → `foo-bar`
- **website**：从文件内 `ANTHROPIC_BASE_URL` 提取域名
- **base_url**：从文件内 `ANTHROPIC_BASE_URL` 读取

只需将配置文件放入 `settings/` 目录，重启程序即可自动出现在菜单中。

## 新增配置

托盘菜单提供「新增配置」入口，点击后弹出对话框：

| 字段 | 必填 | 说明 |
|------|------|------|
| Base URL | 是 | API 地址 |
| API Key | 是 | 认证密钥 |
| 名称 | 否 | 留空则从 Base URL 域名自动推导 |
| Model | 否 | 留空则不指定 |

确认后自动生成 `settings-*.json` 文件并写入 `config.json`，菜单即时刷新。

## 测试所有配置

托盘菜单提供「测试所有配置」入口，对所有已注册的 API 配置进行批量可用性测试。

每个配置同时执行两种测试：
- **HTTP 测试** — 直接请求流式接口，测量首字耗时（TTFT）、回复字数、总耗时、速度
- **CLI 测试** — 通过 `claude --settings <path> -p "Hi"` 验证端到端可用性

测试结果以双行表格展示，每个配置占两行（HTTP + CLI），支持 hover 查看完整响应。也可以 `python test_configs.py` 在命令行运行。

详细开发记录见 [devlog/配置可用性测试功能.md](devlog/配置可用性测试功能.md)。

## 使用

双击 `start.bat` 后台启动，或：

```
python main.py
```

- 右键/左键托盘图标：弹出配置菜单，当前配置带 ✓
- 鼠标悬停托盘图标：显示当前配置名称
- 子菜单功能：切换配置、复制启动参数、打开配置文件、访问官网
- 悬浮「打开配置文件」：预览文件路径和内容
- 切换成功后弹出系统通知

## 依赖

```
pip install PyQt5
```
