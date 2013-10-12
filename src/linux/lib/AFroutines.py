'''
Created on 1 Sep 2013

@author: Nia Catlin
'''

import os, time,subprocess, multiprocessing
import sendemail, fileconfig,hardwareconfig

from fileconfig import config

dbusobj = None
shuttingDown = False
emailAlert = False

screenOwner = None


#also need a gnome version
def lockProcess():
    os.setuid(screenOwner)
    if fileconfig['TRIGGERS']['DESKTOP_ENV'] == 'LXDE':
        os.system('xscreensaver-command -lock')
    else:
        os.system('qdbus org.kde.screensaver /ScreenSaver Lock')
        

#x does not let root lock the screen
#have to spawn a nonroot process to do it
def lockScreen():
    try:
        P = multiprocessing.Process(target=lockProcess)
        P.start()
    except:
        return False
    return True

def standardShutdown():
    global shuttingDown
    if shuttingDown == True: return
    shuttingDown = True
    
    unmountEncrypted()
    os.system('/sbin/shutdown -P') #poweroff at the end   

TCUSED = False
DMUSED = True
#dismount encrypted containers    
def unmountEncrypted():
    #doesnt seem to have purge or wipecache options on linux
    if os.path.exists(config['TRIGGERS']['tc_path']):
        tc = subprocess.Popen("/usr/bin/truecrypt --dismount --force", shell=True, timeout=2)
        tc.wait()
    
    if config['TRIGGERS']['dismount_dm'] == 'True':
        devlist = os.listdir('/dev/mapper')
        for dev in devlist:
            if 'crypt' in dev: #can parallelise this a bit
                #not sure how best to do this - area is in use so cryptsetup fails, does dmsetup clear key?
                try:
                    subprocess.Popen("/sbin/cryptsetup remove crypt", shell=True, timeout=1)
                    dmr = subprocess.Popen("/sbin/dmsetup remove -f crypt", shell=True, timeout=2)
                    dmr.wait()
                except: continue
        

#encrypted drives can be specified because they are dismounted after writing
#set to none to disable log writing
LOGFILE = None


#destroy data, deny access, poweroff
#takes as arguments a message for the logfile and the status of the screen lock
def emergency(device=None):
    #device change events fire quite rapidly 
    #pnly need to call this once
    global shuttingDown
    if shuttingDown == True: return
    else: shuttingDown = True
    
    #encase everything in a try->except>pass block
    #so if anything fails we skip straight to poweroff
    
    try: 
    
        #disable the device before it can touch memory
        if device != None and os.path.exists(device):
            device = device.split('/')
            deviceEnableSwitch = "/%s/%s/%s/%s/enable"%(device[1],device[2],device[3],device[4])
            print('writing 0 to ',deviceEnableSwitch)
            fd = open(deviceEnableSwitch,'w')
            fd.write('0')
            fd.close()
            
        
        lockStatus = hardwareconfig.checkLock()
        if lockStatus == False: lockScreen()
        
        unmountEncrypted() 
        
        if config['TRIGGERS']['exec_shellscript'] == 'True':
            scriptProcess = subprocess.Popen(".\sd.sh", shell=True, timeout=config['TRIGGERS']['script_timeout'])
            scriptProcess.wait()
    except:
        pass
    
    os.system('/sbin/poweroff -f')
    
