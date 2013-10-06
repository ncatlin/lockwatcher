'''
Created on 26 Aug 2013

@author: Aia Catlin
'''
import os, ctypes, subprocess
import fileconfig, hardwareconfig

def lockScreen():
    ctypes.windll.user32.LockWorkStation()

def standardShutdown():
    shutdownPath = 'shutdown.exe' #probably better to find+use full path
    subprocess.call([shutdownPath,"-s"])
    
def emergency():
    print("running AF routines")
    #if not locked
    if hardwareconfig.checkLock()==False:
        lockScreen()
    
    #truecrypt forces volume dismount and discards any key data
    if fileconfig.config['TRIGGERS']['dismount_tc'] == 'True':
        tcPath  = fileconfig.config['TRIGGERS']['tc_path']
        try:
            subprocess.call([tcPath,"/dismount","/force","/wipecache","/quit","/silent"])
        except: pass 
    
    if fileconfig.config['TRIGGERS']['exec_shellscript'] == 'True':
        try:
            scriptPath = os.getcwd()+'\sd.bat'
            if os.path.exists(scriptPath): subprocess.call([scriptPath])
        except: pass
    
    #shutdown: force application close, no timeout
    shutdownPath = 'shutdown.exe' #maybe better to find+use full path
    subprocess.call([shutdownPath,"-s","-t","00","-f"])
    print('calling shutdown...')