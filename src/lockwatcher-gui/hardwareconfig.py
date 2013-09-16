'''
Created on Sep 15, 2013

@author: liveuser
'''
import subprocess,threading,socket,smtplib,imapclient,os

def reloadCameras(ignore):
    subprocess.call(['/etc/init.d/motion','reload'])
    subprocess.call(['/etc/init.d/motion2','reload'])

#gets the /dev/videoX strings and device/manufacturer names for all the cameras
#returns them in a dict
def getCamNames():
    cameranames = {}
    videodevs = ['/dev/%s'%dev for dev in os.listdir('/dev') if 'video' in dev]
    for dev in videodevs:
        cameranames[dev] = {}
        scanprocess = subprocess.Popen(['/sbin/udevadm','info', '--query=property','-n','%s'%dev], stdout=subprocess.PIPE)
        if scanprocess == []:
            print("bad process?")
            return None
        try:
            out, err = scanprocess.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            scanprocess.kill()
            out, err = scanprocess.communicate()
        
        for detail in out.decode('UTF-8').split('\n'):
            if 'ID_MODEL=' in detail:
                cameranames[dev]['ID_MODEL'] = detail.split('=')[1]
                continue
            if 'ID_VENDOR=' in detail:
                cameranames[dev]['ID_VENDOR'] = detail.split('=')[1]
                continue
            
    return cameranames
   

   

import struct
#passes keystrokes from (eventFile device) to the callback function 
class kbdListenThread(threading.Thread):
    def __init__(self,callback,eventFile):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.event = eventFile
    def run(self):
        self.listening = True
        try:
            dev = open(self.event,'rb')
        except IOError as e:
            print("Cannot monitor keyboard: %s\n->Need to run as root"%e)
            return
            
        keyEventFormat = 'llHHI'
        keyEventSize = struct.calcsize(keyEventFormat)
        
        while self.listening == True:
            event = dev.read(keyEventSize)
            (time1, time2, eType, kCode, pressed) = struct.unpack(keyEventFormat, event)
            if eType != 1: continue
            if pressed == 1:
                self.callback(kCode)
        return None
    def terminate(self):
        self.listening = False

#sends the output of 'hcitool scan' to the callback function
#ie: a list of nearby discoverable bluetooth devices
class BTScanThread(threading.Thread):
    def __init__(self,callback):
        threading.Thread.__init__(self) 
        self.callback = callback
    def run(self):
        scanprocess = subprocess.Popen(['hcitool', 'scan'], stdout=subprocess.PIPE)
        print("scanprocess = ",scanprocess)
        if scanprocess == []:
            print("Bluetooth does not appear to be enabled: skipping")
            return None
        try:
            out, err = scanprocess.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            scanprocess.kill()
            out, err = scanprocess.communicate()
        self.callback(out)
        return None

#tries to connect to the email hosts listed with the given credentials    
class emailTestThread(threading.Thread):
    def __init__(self,callback,config):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.config = config
    def run(self):
        print("in email test thread")
        if self.config['EMAIL']['EMAIL_SMTP_HOST']!= None:
            try:
                s = smtplib.SMTP(self.config['EMAIL']['EMAIL_SMTP_HOST'], timeout=10)
                s.login(self.config['EMAIL']['EMAIL_USERNAME'], self.config['EMAIL']['EMAIL_PASSWORD'])
                s.quit()
            except smtplib.SMTPAuthenticationError:
                resultS = 'Authentication Error'
            except socket.timeout:
                resultS = 'Connection Timeout'
            except socket.gaierror:
                resultS = 'Connection Failed'
            except:
                resultS = 'Failed'
            else:
                resultS = 'OK'
            
        if self.config['EMAIL']['EMAIL_IMAP_HOST']!= None:    
            try:
                server = imapclient.IMAPClient(self.config['EMAIL']['EMAIL_IMAP_HOST'], use_uid=False, ssl=True)
                server.login(self.config['EMAIL']['EMAIL_USERNAME'], self.config['EMAIL']['EMAIL_PASSWORD'])
                server.select_folder('INBOX')
                server.logout()
                resultI = "OK"
            except socket.gaierror:
                resultI = 'Connection Error'
            except socket.timeout:
                resultI = 'Connection Timeout'
            except imapclient.IMAPClient.Error as e:
                resultI = e.args[0].decode('utf-8')
            
        self.callback('IMAP: '+resultI,'SMTP: '+resultS)
        return None