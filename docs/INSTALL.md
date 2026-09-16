# 安装与配置

## Windows Release

从 Releases 下载 NovaOrb-2026.09.15-windows-x64.zip，解压后运行：

- 04_桌面桌宠程序/05_可运行版本/启动Nova.cmd：启动桌宠；
- 04_桌面桌宠程序/05_可运行版本/打开Nova设置.cmd：打开设置；
- 04_桌面桌宠程序/05_可运行版本/NovaOrb/Coco.exe：底层兼容入口，不建议直接替代启动脚本。

这是便携式 onedir 包。不要只复制 Coco.exe，需要保留整个 NovaOrb/ 目录及其 _internal/ 内容。当前包把 Whisper 和可选声纹模型一起放入 Release，因此体积较大。

## 源码运行

```powershell
cd 04_桌面桌宠程序/01_程序源码
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m coco
```

不准备模型也可以运行大部分 UI、桌面视觉和测试；使用本地语音前执行：

```powershell
python -m coco.prepare_voice
```

该命令会把 faster-whisper small 模型下载到被 .gitignore 排除的 04_桌面桌宠程序/06_语音模型/faster-whisper-small/。CAM++ 声纹模型需要按照 coco/speaker_model_notice.txt 中的来源和许可证单独准备。

## API 设置

打开设置后填写：

1. API Base URL：OpenAI-compatible 服务的最终接口地址；
2. 模型名：服务端可用模型；
3. API Key：只在需要时填写。

远程 API 应使用 HTTPS；本机服务才使用 HTTP。不要把 Key 放进 profile、Issue、截图、日志或命令行参数。选择“记住”后，程序使用 Windows DPAPI 保存加密密文，密文本身仍在本机用户数据目录中。

## 用户数据位置

冻结包默认使用：

```text
%LOCALAPPDATA%\CocoDesktop\
```

新版本的实例锁和本地 IPC 使用 NovaOrbDesktop 命名空间。可以通过 COCO_DATA_DIR 和 COCO_INSTANCE_DIR 指定隔离测试目录。

## 常见问题

### 双击后没有角色

确认 ZIP 已完整解压，而不是在压缩包预览器中直接运行；保留 NovaOrb/ 下所有文件，并查看 %LOCALAPPDATA%\CocoDesktop\04_运行日志\ 中的日志。

### 语音不可用

确认 Windows 已允许桌面应用访问麦克风，音量条会随声音变化，并且 models/faster-whisper-small/model.bin 存在于包内。源码运行则检查 06_语音模型/faster-whisper-small/。

### 只想使用键盘聊天

语音模型和麦克风不是聊天功能的前置条件。打开设置填写兼容 API 后，可以只使用聊天和桌面 Agent。
