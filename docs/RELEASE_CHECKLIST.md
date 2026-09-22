# Release checklist

这份清单用于 Windows 预览版发布。它不替代真实目标设备验收，也不授予项目代码或视觉资产许可证。

## 版本与范围

- [ ] 版本号、tag、`CHANGELOG.md`、README、`docs/INSTALL.md` 和本发布说明使用同一版本语义；
- [ ] 明确写出这是预览版还是稳定版、支持的 Windows 范围、中文优先状态和未支持平台；
- [ ] 未把 Lite/Full、MSI、签名、英文 UI、视频或性能数字写成已存在的交付物；
- [ ] Release 资产名称、架构、便携式/安装器类型与实际构建一致。

## 公开边界与许可

- [ ] `git diff --stat` 和待发布 tree 只包含代码、测试、文档、许可已核对的原创资产和脱敏演示素材；
- [ ] 没有 API Key、凭据、数据库、聊天记录、录音、声纹档案、日志、模型权重、构建包、临时目录、私人素材或本机绝对路径；
- [ ] `.gitignore` 规则和发布资产内容都经过人工检查；忽略规则不视为隐私证明；
- [ ] 第三方运行库、模型、字体、图片、音频的版本、来源、许可证、NOTICE 和再分发边界记录在 `THIRD_PARTY_NOTICES.md`；
- [ ] 项目本身没有许可证时，发布说明明确标为维护者待决策，不暗示 MIT/Apache-2.0 等授权。

## 构建与完整性

- [ ] 在干净的 Windows x64 环境完成构建，记录 Python、PySide6、PyInstaller、模型和 Windows 版本；
- [ ] 便携目录可从包根目录启动，保留所有 `_internal/` 和模型依赖；不要只测试单个 EXE；
- [ ] 运行 `Get-FileHash <asset> -Algorithm SHA256`，把校验值写入 Release 说明并上传 `.sha256` 资产；
- [ ] 明确 SmartScreen/杀毒软件/麦克风权限提示，以及当前是否签名；
- [ ] 检查用户数据仍写入用户目录，不写回 Release 目录。

## 验证

- [ ] `python -m unittest discover -s tests -p "test_*.py"`；
- [ ] `python -m tests.assistant_ui_smoke`；
- [ ] `python -m tests.ui_smoke`；若未运行或使用定向探针，必须如实说明；
- [ ] `node --check coco/web/nova_states.js`、`nova_renderer.js`、`nova_bridge.js`；
- [ ] 手工检查模型缺失、麦克风不可用、API 错误、取消、超时和工具失败时的可见反馈；
- [ ] 手工检查 Explorer 独立启动、不同 DPI、多显示器、桌面背景、GPU 驱动和至少一种真实音频设备；未验证项目列入已知限制。

## 发布后

- [ ] Release 正文包含下载、校验和、安装入口、已知限制、隐私/联网边界和安全报告入口；
- [ ] PR 正文列出改变、未改变、验证、未解决风险和需要维护者决定的事项；
- [ ] 发布后重新打开 README、安装说明和 Release 资产链接，确认路径、文件名和版本没有漂移；
- [ ] 如发生秘密泄露，立即私下报告并按 GitHub 的凭据撤销/历史清理流程处理，而不是只删除工作树文件。
