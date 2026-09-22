# Third-party notices for Nova Orb

This file records the dependencies used by the v0.2.0 Windows build prepared
on 2026-09-21. Nova's visual layer is authored locally with SVG, CSS and
JavaScript; it does not vendor or load an avatar, icon, animation or visual
library. The v0.2.0 role and `Nova_Orb` brand icon are original project
assets. Retain the upstream license/notice files required by the selected
binary distribution.

## Runtime and build dependencies

| Component | Version used locally | License / notice | Integrity record |
| --- | --- | --- | --- |
| PySide6 / Qt for Python | 6.11.2 | LGPLv3 / GPLv3 / commercial terms as applicable; Qt modules may carry additional notices | package version pinned in `04_桌面桌宠程序/01_程序源码/requirements.txt`; see [Qt for Python licenses](https://doc.qt.io/qtforpython-6.11/licenses.html) |
| faster-whisper | 1.2.1 | MIT | package version pinned in `requirements.txt`; see [upstream license](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) |
| CTranslate2 | 4.8.2 | MIT | collected transitively by faster-whisper; see [upstream license](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) |
| PyAV | 17.1.0 | BSD-3-Clause | collected transitively by faster-whisper; see [upstream license](https://github.com/PyAV-Org/PyAV/blob/main/LICENSE.txt) |
| NumPy | 2.2.6 | BSD-3-Clause | runtime dependency; see [upstream license](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| pywin32 | 312 | PSF-derived license | package version pinned transitively/locally; see [upstream license](https://github.com/mhammond/pywin32/blob/main/LICENSE.txt) |
| ONNX Runtime | 1.20.1 | MIT | optional speaker verification runtime; see [upstream license](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| sherpa-onnx | 1.13.8 | Apache License 2.0 | optional speaker verification runtime; see [upstream license](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE) |
| Pillow | 12.2.0 | HPND-style Pillow license | local brand build helper only; not required by the frozen app; see [upstream license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |

PyInstaller 6.22.2 is a local build tool, not an application feature. Its
bootloader license and exception apply to the generated executable; retain
the versioned build records if a binary is redistributed.

## Models

- `faster-whisper-small` is a local model directory and is not committed to
  this repository. Its model-card and weight licenses must be retained with
  any binary distribution selected by the maintainer.
- `3dspeaker_speech_campplus_sv_zh-cn_16k-common.onnx` is the optional CAM++
  speaker model. The local file SHA-256 is
  `F682B514C05D947EE3FA91CD6EC6C5C7543479A128373FA29B1FAEDCCD21FD11`.
  The source and Apache 2.0 notice are recorded in
  `04_桌面桌宠程序/01_程序源码/coco/speaker_model_notice.txt`.

## Authored assets

The Nova Orb SVG, preview PNG, ICO, renderer, state table and bridge are
original project assets in this branch. They are not derived from a remote
avatar or icon package. The final release license for project-authored code
and artwork remains a maintainer decision and is intentionally not asserted
here before repository visibility and license are confirmed.
