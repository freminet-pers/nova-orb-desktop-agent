"""Make PySide6 and shiboken DLL directories win over Python's CRT copy."""
import os
import sys


if sys.platform.startswith("win"):
    root = sys._MEIPASS
    qt_dir = os.path.join(root, "PySide6")
    shiboken_dir = os.path.join(root, "shiboken6")
    os.environ["PATH"] = os.pathsep.join((qt_dir, shiboken_dir, root, os.environ.get("PATH", "")))
    # Load the exact Qt CRT/ICU ABI before QtCore resolves its imports.  A
    # Python installation or another bundled dependency may expose older
    # copies under the same DLL names.
    import ctypes
    for dependency in (
        "VCRUNTIME140.dll",
        "VCRUNTIME140_1.dll",
        "MSVCP140.dll",
        "MSVCP140_1.dll",
        "MSVCP140_2.dll",
    ):
        path = os.path.join(qt_dir, dependency)
        if os.path.isfile(path):
            ctypes.WinDLL(path)
    for path in (
        os.path.join(root, "icuuc.dll"),
        os.path.join(qt_dir, "Qt6Core.dll"),
        os.path.join(shiboken_dir, "shiboken6.abi3.dll"),
    ):
        if os.path.isfile(path):
            ctypes.WinDLL(path)
