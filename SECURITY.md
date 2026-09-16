# Security policy

## Scope

Nova Orb is a personal Windows desktop assistant. It can access a configured AI endpoint, a microphone when enabled, and a deliberately small allowlist of desktop tools.

## Do not disclose

请不要在公开 Issue、Pull Request 或截图中提交：

- API Key、访问令牌、密码或 DPAPI 文件；
- SQLite 数据库、聊天记录、备注、日志或声纹档案；
- 原始照片、视频、录音、个人画像或带本机绝对路径的打包诊断；
- 未脱敏的完整崩溃日志。

## Reporting

如果问题可能导致密钥、私人数据、任意程序执行或数据损坏，请不要公开描述复现材料。请通过维护者可用的私下渠道联系仓库所有者，并只提供最小化、已脱敏的复现信息。

## Security boundaries

- API Key 默认不持久化，勾选记住后由 Windows DPAPI 保护；
- Agent 没有任意 shell/PowerShell 工具；
- 文本输入只允许经过窗口、进程和控件检查的 Notepad/WordPad 类编辑器；
- 语音和声纹数据默认留在本机，不进入公开仓库；
- 声纹校验不等于身份认证，不应保护高风险操作。
