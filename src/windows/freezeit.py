import sys
from cx_Freeze import setup, Executable

setup(
    name = "Lockwatcher",
    version = "0.1",
    description = "An anti-tampering monitor",
    executables = [Executable("lockwatcher-gui.py", base = "Win32GUI")])