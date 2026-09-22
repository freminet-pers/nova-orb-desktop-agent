# Contributing

感谢关注 Nova Orb。项目当前以中文为主，Issue 和 Pull Request 可以使用中文或英文，但请尽量给出可复现信息。仓库治理的目标是让公开快照可审查、可运行、不会意外带出私人素材；本次贡献边界不包含业务功能重写。

## 先确认公开边界

可以提交：

- 可复现的 bug、文档修正、测试改进和小范围安全/治理修复；
- 经过许可核对的代码、原创视觉资产和脱敏截图；
- 能说明 Windows 版本、运行方式和验证命令的变更。

不要提交：

- API Key、访问令牌、密码、DPAPI 文件、数据库、聊天记录、备注、录音、声纹档案或完整日志；
- 模型权重、便携包、构建产物、release_staging、临时评审目录或个人照片/视频；
- 带本机绝对路径、窗口内容、桌面通知或私人账号信息的截图；
- 来自受限上游、私人素材目录或未确认许可的角色/声音/图标资源。

`.gitignore` 只是一道辅助防线，不是隐私保证。提交前请检查 `git status` 和待提交文件内容；不能因为文件被忽略就把它复制到别的公开路径。

## Before opening an issue

- 确认问题发生在当前 Release 或当前主分支，并注明版本/commit；
- 写明 Windows 版本、Python/PySide6 版本、是否冻结包、是否启用语音/API/Agent；
- 给出最小复现步骤、实际结果、预期结果，以及是否可稳定复现；
- 删除 API Key、用户数据、录音、数据库、日志中的私人内容；
- 不上传模型文件、便携包、原始截图或本机绝对路径；
- 安全问题不要公开复现细节，先阅读 [SECURITY.md](SECURITY.md)。

## Development

在 Windows PowerShell 中：

```powershell
cd 04_桌面桌宠程序/01_程序源码
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py"
python -m tests.assistant_ui_smoke
python -m tests.ui_smoke
node --check coco/web/nova_states.js
node --check coco/web/nova_renderer.js
node --check coco/web/nova_bridge.js
```

如果当前机器无法运行 Qt/WebEngine 或音频设备测试，请明确写出“未验证”，不要把静态检查写成完整 UI 通过。测试会话应使用隔离的 `COCO_DATA_DIR` / `COCO_INSTANCE_DIR`，避免把个人状态混入仓库。

## 视觉与演示素材规范

视觉改动需要同时检查：

- `tests/visual_contract.json` 是否仍与桥接接口一致；
- 三份 `node --check` 是否通过；
- 状态名、截图和 README 是否只描述仓库中真实存在的行为；
- 低打扰、可取消、可观察的状态反馈是否仍然成立。

新增 PNG/GIF/视频或截图前，请确认：

- 素材来自公开仓库、明确授权的原创内容或可公开发布的录制；
- 已裁掉用户名、通知、桌面文件名、绝对路径、API Key、私人窗口和设备标识；
- 不伪造尚未实现的 Lite/Full 构建、英文 UI、签名、性能数字或自动化成功结果；
- 在 PR 中写明素材来源、处理方式、文件大小和是否需要单独的上游通知。

## Pull requests

请使用仓库的 PR 模板。每个 PR 应：

- 只做一个清晰主题；业务功能、文档治理和素材大改动尽量拆分；
- 说明改变了什么、明确没有改变什么，以及任何需要维护者决定的事项；
- 列出实际运行过的验证命令，并区分本机验证、CI 验证和未验证的真实设备条件；
- 对第三方代码、模型、字体、图片、音频和字体说明来源、版本、许可证与校验信息；
- 不为了让测试通过删除安全断言、扩大路径白名单或吞掉异常；
- 不直接推送 `main`；从公开默认分支创建短期分支并通过 Pull Request 合并。

