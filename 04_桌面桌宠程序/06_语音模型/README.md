# 本地语音模型

模型文件很大，且有独立的上游许可，因此不会提交到 Git。

## faster-whisper small

在 04_桌面桌宠程序/01_程序源码 目录运行：

```powershell
python -m coco.prepare_voice
```

模型会写入：

04_桌面桌宠程序/06_语音模型/faster-whisper-small/

## CAM++ speaker model

可选声纹模型的名称、下载地址、SHA-256 和许可说明见：

04_桌面桌宠程序/01_程序源码/coco/speaker_model_notice.txt

声纹功能默认关闭。模型只用于本机唤醒后的可选二次校验，不是身份认证或高风险操作授权。
