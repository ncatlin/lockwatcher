#build with: pythonpath setup.py bdist --format=msi

import sys
from cx_Freeze import setup, Executable

setup(
    name = "Lockwatcher",
    version = "0.1",
    description = "Anti-tampering monitor",
    executables = [Executable("lockwatcher-gui.py", base = "Win32GUI",icon='favicon.ico'),
                   Executable('serviceconfig.py', base='Win32Service',targetName='LockWatcherSvc.exe'),
                   Executable("locker.py", base = "Win32GUI")],
    data_files=[('', ['favicon.ico']),
                ('', ['btscanner.exe','chastrigger.exe','roomtrigger.exe','install-interception.exe']),
                ('', ['roomcam.png','chascam.png','camid.png']),
                ('', ['cygwin1.dll','interception.32.dll','interception.64.dll'])
                ],
    options = {'build_exe': {'includes': ['devdetect']}},
    )