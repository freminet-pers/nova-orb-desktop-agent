# Contributing

感谢关注 Nova Orb。项目当前以中文为主，Issue 和 Pull Request 可以使用中文或英文，但请尽量给出可复现信息。

## Before opening an issue

- 确认问题发生在当前 Release 或当前主分支；
- 写明 Windows 版本、Python/PySide6 版本和运行方式；
- 给出最小复现步骤和实际/预期结果；
- 删除 API Key、用户数据、录音、数据库、日志中的私人内容；
- 不上传模型文件、便携包、截图原图或本机绝对路径。

## Development

```powershell
cd 04_桌面桌宠程序/01_程序源码
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py"
python -m tests.assistant_ui_smoke
python -m tests.ui_smoke
```

视觉改动需要同时检查：

- tests/visual_contract.json 是否仍与桥接接口一致；
- node --check coco/web/nova_states.js；
- node --check coco/web/nova_renderer.js；
- 不要把旧角色 checkout、原始素材或受限上游资产复制到仓库。

## Pull requests

小而聚焦的 PR 更容易审查。请在描述中说明行为变化、测试命令、未验证的真实设备条件和第三方资源来源。不要为了让测试通过删除安全断言或吞掉异常。
