'''
Created on 26 Aug 2013

@author: Aia Catlin
'''
import os, ctypes, subprocess, _winreg, threading, sys
import fileconfig, hardwareconfig, socket

#doesnt work from service
#def lockScreen():
#    return ctypes.windll.user32.LockWorkStation()

#tell the user-started thread to do the locking
def lockScreen():
        s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            s.connect(('127.0.0.1', 22189))
            s.send('1')
            s.close()
        except:
            return

def standardShutdown():
    shutdownPath = 'shutdown.exe' #probably better to find+use full path
    subprocess.call([shutdownPath,"-s"])

class execScript(object):
    def __init__(self, script):
        self.cmd = script
        self.process = None

    def run(self, timeout):
        def target():
            self.process = subprocess.Popen(self.cmd, shell=True)
            self.process.communicate()

        thread = threading.Thread(target=target)
        thread.start()
        
        if timeout <= 0: timeout=None
        thread.join(timeout)
        
        #try to terminate it but we don't really care, shutdown is going to happen anyway
        if thread.is_alive():
            self.process.terminate()
            thread.join()

def emergency():
    try:

        if hardwareconfig.checkLock()==False: lockScreen()
        
        #truecrypt forces volume dismount and discards any key data
        if fileconfig.config.get('TRIGGERS','dismount_tc') == 'True':
            tcPath  = fileconfig.config.get('TRIGGERS','tc_path')
            try:
                subprocess.call([tcPath,"/dismount","/force","/wipecache","/quit","/silent"])
            except: pass 
        
        if fileconfig.config.get('TRIGGERS','exec_shellscript') == 'True':
                try:
                    key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\Lockwatcher")
                    scriptPath = str(_winreg.QueryValueEx(key,'SDScript')[0])
                except:
                    key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\Wow6432Node\Lockwatcher")
                    scriptPath = str(_winreg.QueryValueEx(key,'SDScript')[0])
        
                if os.path.exists(scriptPath): 
                    try:
                        timeLimit = float(fileconfig.config.get('TRIGGERS','script_timeout'))
                    except: timelimit = 5.0
                    thread = execScript(scriptPath)
                    thread.run(timeout=timeLimit)
    except:
        pass

    #shutdown: force application close, no timeout
    shutdownPath = 'shutdown.exe' #maybe better to find+use full path
    subprocess.call([shutdownPath,"-s","-t","00","-f"])