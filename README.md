# OpenBot Custom

基于 [OpenBot](https://github.com/nightly-labs/openbot) 的个人定制：完整 macOS App 打包、Grok 协调助手的上下文精简，以及 main / plan / execute 三位助手的协作指令。

这个仓库维护定制部分的源码。OpenBot 本体由官方发行版提供，打包时原样内置，不修改原始程序或签名。仓库不包含安装包、聊天数据库、模型登录信息、SSH 密钥或个人项目数据。

## 当前功能

- main 使用 Grok 负责协调，plan 使用 Claude 负责规划和审查，execute 使用 Codex 负责执行；模型型号由 OpenBot 设置决定。
- plan 与 execute 可以直接交接。plan 只补充新增的审查判断，不复制 execute 已报告的结果；失败、阻碍和用户决策照常汇报。
- Grok 使用精简工具配置，通过 OpenBot 的通信工具联系同事。
- ACP 转接程序压缩已知的 OpenBot 指令块，并对严格匹配且有真实发送回执的简单问候回信省去额外模型调用。其他消息正常转发；不把通用任务结果一律静默处理。
- macOS 完整版内置官方应用。首次准备独立运行组件后，无需再保留原来的 OpenBot App；原有聊天数据仍由 OpenBot 保存。

指令精简和问候去重依赖具体的上游提示词、工具回执和协议形状。上游变化时，未知形状应正常转发；升级后应重新验证。这里的规则不保证所有模型在所有对话中都不重复。

## 平台状态

| 部分 | 状态 |
|---|---|
| macOS 完整 App | 已实现；原个人构建使用 OpenBot 0.65.0 |
| 助手指令模板 | 可按不同平台的实际路径填写 |
| Grok ACP 转接程序 | 使用 POSIX 管道；macOS 已验证，Windows 尚未适配 |
| Windows 定制安装包 | 尚未实现或实测；官方 Windows 版见上游 Releases |

两台设备独立运行时，不会自动共用聊天、登录和文件。使用 OpenBot 的远程主机功能是另一种部署方式。

## 构建 macOS 安装包

需要 macOS、Python 3 和 Xcode Command Line Tools。先取得官方 OpenBot App，再执行：

```bash
python3 macos/build.py --source-app /Applications/OpenBot.app --output-dir dist --dmg
```

输出 `dist/OpenBot Custom.app` 和 `dist/OpenBot-Custom-2.0.0.dmg`。构建器会核验官方应用签名，并对本地生成的外壳作临时签名；这不等同于 Apple 公证。

从其他位置构建时，用 `--source-app` 指向那份官方 App。重复构建请指定新的输出目录。构建不会下载模型、复制登录凭据或上传用户文件。

打开 App 时，官方程序会放在：

```text
~/Library/Application Support/OpenBot Custom/Application/OpenBot.app
```

运行配置在同一父目录下，独立于只读 App 资源。退出正在运行的其他 OpenBot 后，再打开本 App；现有数据库和助手工作目录由官方程序沿用。删除旧应用时，只移除 App，不要连同聊天数据或项目目录一起清理。

## 本机设置

Grok Build 需要先安装并登录。默认入口是 `~/.grok/bin/grok`；其他安装位置可以配置 `grokPath`。Codex、Claude 使用 OpenBot 自己的运行时与登录设置，只有填写 `codexPath` 时才显式覆盖 Codex 路径。

如果需要代理或自定义 CLI 路径，把 `config/settings.example.json` 复制为：

```text
~/Library/Application Support/OpenBot Custom/settings.json
```

示例：

```json
{
  "httpProxy": "http://127.0.0.1:7897",
  "httpsProxy": "http://127.0.0.1:7897",
  "codexPath": "",
  "grokPath": ""
}
```

代理端口以自己的软件为准；无需代理时留空。不要把真实本机配置、带密码的代理地址或凭据提交到仓库。修改后重启 App。`config/main-grok.toml` 是可选的项目级配置参考，不会自动覆盖已有助手配置。

## 助手指令模板

将 `templates/main.md`、`templates/plan.md`、`templates/execute.md` 分别填入对应助手的指令设置。先替换所有占位符：

| 占位符 | 含义 |
|---|---|
| `{{LOCAL_PROJECT_DIR}}` | 本地代码、开发记录和重要结果的主目录 |
| `{{SSH_HOST}}` | 已配置的 SSH 连接别名 |
| `{{REMOTE_PROJECT_DIR}}` | 远端数据和运行产物总目录 |
| `{{REMOTE_CODE_DIR}}` | 从本地上传的代码副本目录 |
| `{{REMOTE_ENV_DIR}}` | 远端现有 Python / Conda 环境目录 |

模板约定：先在本地修改和验证代码，再按清单上传到远端；数据集、模型参数和大型运行产物留在远端，重要评测摘要和开发记录回传本地。配置这些规则本身不会启动训练或同步文件。

## 检查

```bash
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_policy.py
PYTHONDONTWRITEBYTECODE=1 python3 tests/test_relay.py
zsh -n src/grok-main
```

第二个脚本通过真实子进程和模拟 CLI 检查 JSON-RPC 转发、通信回执、问候去重、登录扩展透传及阻塞消息保留，不调用模型或访问服务器。

构建后可检查独立程序是否准备完成，而不启动 OpenBot：

```bash
"dist/OpenBot Custom.app/Contents/MacOS/OpenBotStandalone" --check
```

此检查会准备运行组件，只输出运行路径和已配置的环境变量名称，不输出代理或认证值。测试时可以将 `OPENBOT_CUSTOM_SUPPORT_DIR` 设置为一个绝对路径，隔离运行组件缓存；这不会创建新的 OpenBot 聊天配置。

## 目录

```text
src/        Grok CLI 包装与 ACP 转接逻辑
config/     协调助手 profile 和本机设置示例
templates/  三位助手的通用指令
macos/      完整 App 与 DMG 构建源码
tests/      协议策略与子进程检查
```

许可和上游归属见 [LICENSE](LICENSE) 与 [NOTICE.md](NOTICE.md)。
