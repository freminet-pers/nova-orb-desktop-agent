# Nova Orb v0.2.0

发布日期：2026-09-21

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
- 完整 UI smoke 本轮只运行一次；它在最终 gaze 增益调整前命中过时的对角线阈值，之后以定向探针确认修复，未重复运行。

## 安装包

Release 资产：`NovaOrb-v0.2.0-Windows-x64.zip`（811,961,228 bytes，约 0.76 GiB）。这是 Windows x64 便携式 onedir 包，不是 MSI 安装器。解压后运行包根目录的 `启动Nova.cmd`，设置使用 `打开Nova设置.cmd`。

SHA-256：`BC891120BEB5B15423EC205FB1C3A5E9E4F34EAE3B8A4D7E4DCD79BFE83297DB`。源码仓库不提交 API Key、数据库、聊天记录、录音、声纹档案、日志、临时评审目录、私密媒体或本机绝对路径。

## 已知边界

- 真实 Explorer 独立启动、不同 DPI、多显示器、桌面背景、音频设备、GPU 驱动和真人声纹准确率仍需目标 Windows 机器确认。
- 源码仓库不包含 Whisper/CAM++ 模型大文件；便携 Release 的模型与上游许可记录见 `THIRD_PARTY_NOTICES.md`。
