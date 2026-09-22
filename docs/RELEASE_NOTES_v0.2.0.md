# Nova Orb v0.2.0

发布日期：2026-09-21（公开预览）

这是 Windows x64 便携式预览版，不是稳定版、MSI 安装器、已签名构建或 Lite/Full 构建。产品界面和主要文档为中文优先，macOS、Linux、移动端和高风险自动化不在本版本支持范围内。

## 这次更新

- 锁定暖象牙色「精灵冠」视觉方向：非对称低双峰凝胶轮廓、烟灰胶囊眼腔、柔和散射和克制的状态光。
- 保留 v0.1.0 的 39 个状态名、Qt/QWebChannel 桥接、桌面交互和 Agent 安全边界，并增加 `handoff_enter(source, context)` 的未来交接入口。
- 统一为单一 `VisualPose` 渲染循环：状态优先级、可取消瞬态序列、自然眨眼、低幅呼吸、8 向 gaze 和文档隐藏时暂停均由同一渲染器管理。
- 设置页改为紧凑的“模型与联网”导航，API、联网搜索和 Agent 高级项默认折叠，保留原有配置键和测试入口。
- 更新 Nova Orb SVG/PNG/ICO 品牌资源、README 截图、变更记录和第三方通知。

## 验证

- `python -m unittest discover -s tests -p "test_*.py"`：125 项通过。
- `python -m tests.assistant_ui_smoke`：通过。
- 定向 WebEngine 探针：8 向 gaze、拖拽回弹、透明命中层、状态优先级和 850×650 设置页通过。
- `node --check`：`nova_states.js`、`nova_renderer.js`、`nova_bridge.js` 通过。
- 完整 UI smoke 本轮只运行一次；它在最终 gaze 增益调整前命中过时的对角线阈值，之后以定向探针确认修复，未重复运行。真实 Explorer、DPI、多显示器、音频、GPU 和真人声纹验收仍需目标 Windows 设备。

## 安装包

Release 资产：`NovaOrb-v0.2.0-Windows-x64.zip`（811,961,228 bytes，约 0.76 GiB）。这是 Windows x64 便携式 onedir 包，不是 MSI。解压后运行包根目录的 `启动Nova.cmd`，设置使用 `打开Nova设置.cmd`。

SHA-256：`BC891120BEB5B15423EC205FB1C3A5E9E4F34EAE3B8A4D7E4DCD79BFE83297DB`。下载后建议用 PowerShell `Get-FileHash` 校验，并以 Release 附带的 `.sha256` 资产为准。

冻结包内部仍可能显示 `NovaOrb/Coco.exe` 与 `NovaOrb/CocoSpeech.exe`；这是为兼容既有语音 worker、数据路径和协议保留的内部命名，不是另一款产品。请保留整个 `NovaOrb/` 目录及 `_internal/` 内容，不要只复制 EXE。

源码仓库不提交 API Key、数据库、聊天记录、录音、声纹档案、日志、临时评审目录、私密媒体或本机绝对路径。源码不提交 Whisper/CAM++ 模型大文件；便携 Release 是否携带模型以及模型再分发边界，以资产和 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) 为准。

## 已知边界

- 未签名个人预览包可能触发 Windows SmartScreen、杀毒软件或麦克风权限提示；当前没有代码签名承诺。
- 真实 Explorer 独立启动、不同 DPI、多显示器、桌面背景、音频设备、GPU 驱动和真人声纹准确率仍需目标 Windows 机器确认。
- 工具是受限白名单，不提供任意 shell/PowerShell、权限提升、屏幕截图或高风险操作；当前没有通用的逐动作确认对话框，直接电脑命令应视为该次用户授权并由用户检查结果。
- 当前没有完整英文 UI、MSI、Lite/Full 构建或稳定版支持承诺。

发布前请使用 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) 核对资产、模型许可、隐私边界、校验和和真实设备验证。
