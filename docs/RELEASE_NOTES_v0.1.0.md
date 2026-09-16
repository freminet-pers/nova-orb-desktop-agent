# Nova Orb v0.1.0

首个公开预览版本，构建于 2026-09-15。

## Windows 下载

Release 资产：

- 文件名：NovaOrb-2026.09.15-windows-x64.zip
- 类型：Windows x64 便携式 onedir 包
- 大小：约 804 MB
- SHA-256：2D6ADC5C43DF2F63A08C1B84092BF8ED827A8D34E470D0A1A3D83448AA6569A8

下载后解压整个 ZIP，运行 04_桌面桌宠程序/05_可运行版本/启动Nova.cmd。不要只复制 Coco.exe；NovaOrb/ 目录中的 _internal/ 文件是运行所必需的。

## 本版本包含

- Qt/PySide6 桌面宿主和设置面板；
- OpenAI-compatible 聊天接口；
- 本地 faster-whisper 中文语音识别；
- 可选英文唤醒词和本机声纹二次校验；
- 受限桌面 Agent 工具；
- 本地 SQLite 状态、聊天、备注和个人记忆；
- 离线 Nova Orb SVG/CSS/JavaScript 视觉层；
- 125 项 unittest、助理 UI smoke 和完整 UI smoke 验证。

## 已知限制

- 当前界面与主要文档是中文优先，没有完整英文本地化；
- 当前角色形象是功能验证阶段的过渡稿，视觉完成度不高，确实比较丑；
- 下一版的主要迭代方向是重新设计角色形象和整套视觉语言；
- 这是便携式 ZIP，不是 MSI 安装器；
- 未签名个人预览包可能触发 Windows SmartScreen 或杀毒软件提示；
- 用户仍需在自己的 Windows 设备上确认 Explorer 启动、麦克风权限、显卡、DPI 和多显示器行为。

## 隐私提示

源码和 Release 均不包含用户的照片、视频、录音、数据库、聊天记录、备注、API Key 或声纹档案。API Key 只有在用户主动选择记住时才会以 Windows DPAPI 密文保存在本机用户数据目录。
