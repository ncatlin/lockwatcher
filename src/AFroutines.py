'''
Created on 1 Sep 2013

@author: nia
'''

import os, time,subprocess, multiprocessing
import sendemail, lwconfig

from lwconfig import config

dbusobj = None
shuttingDown = False
emailAlert = False

screenOwner = None


#also need a gnome version
def lockProcess():
    os.setuid(screenOwner)
    if lwconfig.DESKTOP_ENV == 'LXDE':
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
    if TCUSED == True:
        tc = subprocess.Popen("/usr/bin/truecrypt --dismount --force", shell=True, timeout=2)
        tc.wait()
    
    if DMUSED == True:
        devlist = os.listdir('/dev/mapper')
        for dev in devlist:
            if 'crypt' in dev: #can parallelise this a bit
                #not sure how best to do this - area is in use so cryptsetup fails, does dmsetup clear key?
                subprocess.Popen("/sbin/cryptsetup remove crypt", shell=True, timeout=1)
                dmr = subprocess.Popen("/sbin/dmsetup remove -f crypt", shell=True, timeout=2)
                dmr.wait()
        

#encrypted drives can be specified because they are dismounted after writing
#set to none to disable log writing
LOGFILE = None


#destroy data, deny access, poweroff
#takes as arguments a message for the logfile and the status of the screen lock
def antiforensicShutdown(triggerText,lockStatus, device=None):
    #device change events fire quite rapidly 
    #pnly need to call this once
    print("doing shutdown. triggerText =%s"%triggerText)
    global shuttingDown
    if shuttingDown == True: return
    else: shuttingDown = True
    
    #encase everything in a try->except>pass block
    #so if anything fails we just poweroff
    
    #try: 
    
    #disable the device before it can touch memory
    if device != None:
        deviceEnableSwitch = "/%s/%s/%s/%s/enable"%(device[1],device[2],device[3],device[4])
        fd = open(deviceEnableSwitch,'w')
        fd.write('0')
        fd.close()
        
    if lockStatus == False: lockScreen()
    print("unmounting cryptos - disabled!")
    #unmountEncrypted()
    
    if LOGFILE != None:
        logMsg = "%s: Emergency shutdown: %s %s"%(time.strftime("%x %X"),triggerText,lockStatus)
        try:
            fd = open(LOGFILE,'a')
            fd.write(logMsg)
            fd.close()
        except:
            pass
        
    print('before picturesend')
    motion_picture_sent = False
    if config['EMAIL']['EMAIL_MOTION_PICTURE'] == 'True' and 'room' in triggerText:
        print('in picturesend')
        max_mtime = 0
        newest_file = None
        picPath = '/tmp/motion'
        print('Filenames around : ',os.listdir(picPath))
        for filename in os.listdir(picPath):
            path = os.path.join(picPath, filename)
            mtime = os.lstat(path).st_mtime
            if mtime > max_mtime:
                max_mtime = mtime
                newest_file = filename
        print('newest file = ',newest_file)
        if newest_file != None:
            sendemail.sendEmail("Emergency shutdown",triggerText,attachment=os.path.join(picPath, newest_file))
            motion_picture_sent = True   
            
    if config['EMAIL']['EMAIL_ALERT'] == 'True' and motion_picture_sent == False:
        sendemail.sendEmail("Emergency shutdown",triggerText)             
            
    #except:
    #    pass
    
    print("initiating poweroff!")
    #os.system('/sbin/poweroff -f')
    
