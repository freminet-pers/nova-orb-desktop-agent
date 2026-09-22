# 安装与配置

Nova Orb 当前是 Windows x64 中文优先预览版。它以完整的便携目录运行；不要把发布包当作 MSI 安装器，也不要只复制其中一个 EXE。

## Windows Release（v0.2.0）

1. 从 [v0.2.0 Release](https://github.com/freminet-pers/nova-orb-desktop-agent/releases/tag/v0.2.0) 下载 `NovaOrb-v0.2.0-Windows-x64.zip`。
2. 可选但建议在 PowerShell 校验 SHA-256：

   ```powershell
   Get-FileHash .\NovaOrb-v0.2.0-Windows-x64.zip -Algorithm SHA256
   ```

   当前发布说明记录的值是 `BC891120BEB5B15423EC205FB1C3A5E9E4F34EAE3B8A4D7E4DCD79BFE83297DB`。以 Release 附带的 `.sha256` 资产为准。
3. 将 ZIP 完整解压到你有读写权限的目录。保留 `NovaOrb/` 及其 `_internal/` 内容。
4. 运行包根目录的 `启动Nova.cmd`；运行 `打开Nova设置.cmd` 配置 API、语音、唤醒词和本地声纹。

发布包是约 0.76 GiB 的 Windows x64 便携式 onedir ZIP，不会自动写入注册表。v0.2.0 是未签名的个人预览包，Windows SmartScreen、杀毒软件和麦克风权限提示可能出现；请先核对来源和校验和，再按自己的安全策略决定是否运行。仓库当前没有 MSI、签名或 Lite/Full 构建。

冻结包内部仍可能显示 `NovaOrb/Coco.exe` 与 `NovaOrb/CocoSpeech.exe`。这是为兼容既有语音 worker、数据路径和协议保留的内部命名；面向用户的产品名和启动脚本是 Nova Orb。请使用启动脚本，不要单独移动或替换 EXE。

Release 是否携带 Whisper/CAM++ 模型及其再分发条款，必须以该 Release 的资产和 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 为准。源代码仓库不提交模型大文件。

## 从源码运行

系统要求：

- Windows 10/11 x64；
- Python 3.10 或更高版本；
- 使用语音时需要可用的 Windows 音频输入设备；
- 自由聊天或模型规划需要 OpenAI-compatible endpoint 和 API Key；
- 本地语音需要额外下载模型。

在 PowerShell 中：

```powershell
cd 04_桌面桌宠程序/01_程序源码
python -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m coco
```

不准备模型也可以运行大部分 UI、桌面视觉、本地命令和测试。准备中文语音模型：

```powershell
python -m coco.prepare_voice
```

模型会写入被 `.gitignore` 排除的 `04_桌面桌宠程序/06_语音模型/faster-whisper-small/`。可选 CAM++ 声纹模型的来源、SHA-256 和许可说明见 `coco/speaker_model_notice.txt`。不要把模型、密钥、数据库、录音、声纹档案或日志提交到 Git。

## API 与联网

在“模型与联网”中填写：

1. API Base URL：OpenAI-compatible 服务的最终接口地址；
2. 模型名：服务端可用模型；
3. API Key：只在需要时填写。

远程服务建议使用 HTTPS；本机服务才使用 HTTP。API Key 默认只在内存中使用；选择“记住”后，程序使用 Windows DPAPI 保存按 endpoint 作用域隔离的密文。不要把 Key 放进 profile、Issue、截图、日志、命令行参数或公开诊断。

联网搜索只有在用户使用并配置对应 provider 时才发出。搜索结果是外部观察，不是可信指令，不会自动写入长期记忆；服务商仍可能按自己的条款记录请求。

## 用户数据位置

- 冻结包默认：`%LOCALAPPDATA%\\CocoDesktop\\`；
- 源码运行默认：仓库外的本地状态目录；
- 测试隔离：可用 `COCO_DATA_DIR` 和 `COCO_INSTANCE_DIR` 指定目录；
- 结束试用时，关闭 Nova 后可以删除便携目录；这不会自动删除用户数据目录。

用户数据目录可能包含 SQLite、聊天/备注、日志和 DPAPI 密文。需要迁移或清理时请先备份并按自己的隐私要求处理，不要上传公开 Issue。

## 常见问题

### 双击后没有角色

确认 ZIP 已完整解压，而不是在压缩包预览器中直接运行；保留 `NovaOrb/` 下所有文件，先运行 `启动Nova.cmd`。如仍失败，请在脱敏后查看 `%LOCALAPPDATA%\\CocoDesktop\\04_运行日志\\`，不要上传完整日志或绝对路径。

### 语音不可用

确认 Windows 已允许桌面应用访问麦克风，音量条会随声音变化，并且冻结包的 `models/faster-whisper-small/model.bin` 存在；源码运行则检查 `04_桌面桌宠程序/06_语音模型/faster-whisper-small/model.bin`。模型目录缺失时，先重新运行 `python -m coco.prepare_voice`。

### 只想使用键盘聊天

语音模型和麦克风不是聊天功能的前置条件。打开设置填写兼容 API 后，可以只使用聊天和受限桌面工具。

### 我不想让 Agent 操作电脑

在“模型与联网”关闭“允许 Nova 使用受限电脑工具”。Nova 仍可以显示视觉状态和提供本地无副作用的回答；需要电脑操作时，只有你明确发出请求且开关重新打开才会进入受限工具路径。

更多边界见 [README](../README.md)、[架构说明](ARCHITECTURE.md)、[安全策略](../SECURITY.md) 和 [第三方通知](../THIRD_PARTY_NOTICES.md)。
