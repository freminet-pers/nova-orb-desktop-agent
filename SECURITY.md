# Security policy

## Scope and status

Nova Orb is a Chinese-first Windows desktop preview. It can access a configured AI endpoint, a microphone when enabled, local user data, and a deliberately small allowlist of desktop tools. v0.2.0 is not a security-certified product and has not been evaluated as an identity, financial, enterprise or safety-critical control.

The supported public baseline is the current default branch and the latest tagged Release. If a report concerns an older build, please include the exact tag, commit or asset name.

## Report privately

如果问题可能导致密钥泄露、私人数据外流、任意程序执行、权限提升或数据损坏，请不要在公开 Issue、Pull Request 或截图中提交复现材料。当前仓库没有承诺的安全响应 SLA；请先通过维护者可用的私下渠道联系仓库所有者，并只提供最小化、已脱敏的信息。若没有可用的私下渠道，请在公开 Issue 中只留下“需要私下联系”的非敏感提示，不要发布漏洞细节。

报告中可包含：

- 受影响的 Release/tag/commit 和 Windows 版本；
- 不含秘密的最小复现步骤、预期/实际结果和影响；
- 是否需要 API、麦克风、唤醒、声纹或 Agent 开关；
- 可安全公开的修复建议或测试结果。

请不要发送：

- API Key、访问令牌、密码或 DPAPI 文件；
- SQLite 数据库、聊天记录、备注、日志或声纹档案；
- 原始照片、视频、录音、个人画像或带本机绝对路径的打包诊断；
- 未脱敏的完整崩溃日志、模型权重、便携包或私人素材。

## Security boundaries

- API Key 默认不持久化，勾选记住后由 Windows DPAPI 保护；聊天和搜索请求是否离开设备取决于你配置的服务商；
- Agent 没有任意 shell/PowerShell、权限提升、屏幕截图或隐藏程序工具；
- 工具只能使用登记应用、可见窗口、受限文本编辑器、允许目录和公开 HTTP(S) URL；不会覆盖已有文本文件；
- 工具执行需要用户明确的电脑/文件/网页意图；当前版本没有通用的逐动作确认对话框，请把直接命令视为该次授权并检查界面结果；
- 文本输入只允许经过窗口、进程和控件检查的 Notepad/WordPad 类编辑器；
- 语音和声纹数据默认留在本机；声纹校验不等于身份认证、反重放或高风险操作授权；
- 外部模型返回和搜索结果是不可信观察，不能改变本地工具白名单或安全规则。

## Public-repository hygiene

公开仓库只接受代码、测试、文档、经过许可核对的原创资产和脱敏演示素材。不要把个人素材、模型大文件、构建包、release_staging、日志、数据库或阶段报告复制到新的路径来绕过 `.gitignore`。发现疑似秘密已经提交时，请尽快私下报告并暂停继续传播；仅删除工作树文件不能清除 Git 历史。
