'''
@author: Nia Catlin

Various hardware and system state interrogation routines
'''
import subprocess,threading,socket,os,time
import smtplib, re, sys
import imapclient
try:
    import sensors
    GOTSENSORS = True
except:
    GOTSENSORS = False

def sendToLockwatcher(msg,port):
        s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            s.connect(('127.0.0.1', int(port)))
        except:
            #should probably have some kind of error reporting here
            return
        s.send(msg.encode())
        s.close()
        
#may need to change this to the mousedevices format if sysrq is not cutting it for the real keyboard
def getKBDDevice():
    fd = open('/proc/bus/input/devices')
    text = fd.read()
    #very important: test this on other hardware
    matchObj = re.search(r'sysrq kbd (event\d+)', text, flags=0)
    if matchObj:
        newInput = '/dev/input/'+matchObj.group(1)
        return newInput

def getMouseDevices():
    fd = open('/proc/bus/input/devices')
    text = fd.read()
    #very important: test this on other hardware
    devices = []
    matchObjs = re.findall(r'mouse\d+ (event\d+)', text, flags=0)
    for event in matchObjs:
        devices.append('/dev/input/'+event)
    return devices

#gets the /dev/videoX strings and device/manufacturer names for all the cameras
#returns them in a dict
#had to change from popen->communicate to check_output because debian is still on py 3.2
def getCamNames():
    cameranames = {}
    videodevs = ['/dev/%s'%dev for dev in os.listdir('/dev') if 'video' in dev]
    for dev in videodevs:
        cameranames[dev] = {}
        try:
            output = subprocess.check_output(['/sbin/udevadm','info', '--query=property','-n','%s'%dev])
        except:
            continue
        
        for detail in output.decode('UTF-8').split('\n'):
            if 'ID_MODEL=' in detail:
                cameranames[dev]['ID_MODEL'] = detail.split('=')[1]
                continue
            if 'ID_VENDOR=' in detail:
                cameranames[dev]['ID_VENDOR'] = detail.split('=')[1]
                continue
            
    return cameranames

lockState = False
def setLock(state):
    global lockState
    if state in [True,False]:
        lockState = state
        
def checkLock():
    return lockState
      
    
lockQueue = None

def scrnLocked(state):
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(('127.0.0.1',22190))
    if state == 1:s.send(b'LockTrue')
    else: s.send(b'LockFalse')


#import sensors
#lack of access to DIMM SPD data means this only checks motherboard
#
#cant test this on a vm. todo: test on hardware
class temperatureMonitor(threading.Thread):
    def __init__(self,callback):
        threading.Thread.__init__(self)
        self.name = "TempMonThread"
        self.callback = callback
        self.error = None
        
        for chip in sensors.get_detected_chips():
            if "acpi" in str(chip): break
        else:
            self.die = True
            self.error = "Could not read acpi bus: Temperature monitoring disabled"
            return
        self.chip = chip
            
        for feature in chip.get_features():
            if 'Temperature' in str(feature): break
        for subfeature in chip.get_all_subfeatures(feature):
            if 'input' in str(subfeature.name):break
        self.subfeature = subfeature    
        self.die = False
        
    def run(self):
        while self.die == False:
            time.sleep(1)
            newTemp = self.chip.get_value(self.subfeature.number)
            self.callback("%s degrees C"%newTemp)
            
    def terminate(self):
        self.die = True



class BTTestThread(threading.Thread):
    def __init__(self,callback,deviceID):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.deviceID = deviceID
        self.name='btTestThreads'
        self.socket = None
        self.die = False
    def run(self):
        try:
            self.socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self.socket.settimeout(45)
            #sometimes this 'connects' to and returns a socket for devices that are not turned on
            #might just be a problem with testing it on a vm?
            self.socket.connect((self.deviceID,2))
            
        except ConnectionRefusedError:
            if self.die == True: return #test cancelled
            self.callback("Status: Connection refused")
            return False
        except OSError:
            if self.die == True: return #test cancelled
            self.callback("Status: Not Found")
            return False
        except:
            if self.die == True: return #test cancelled
            self.callback("Status: Unavailable/Unauthorised")
            return False
        
        if self.die == True: return #test cancelled
        try:
            self.socket.close()
        except:
            print('couldnt close socket')
        self.callback("Status: OK")
        
    def terminate(self):
        self.die = True
        self.socket.close()
    

#takes a '12:23:34:45:56:67' string, returns hex equivalent (0x122334455667)
def BTStrToHex(BTStr):
    devIDParts = BTStr.split(':')
        
    if BTStr == 'None' or len(devIDParts) != 6: 
        #self.devStatusLabel.config(text="Status: Invalid ID")
        return 0
    
    hexDevID = 0
    for i in range(5,-1,-1):
        hexDevID += (int(devIDParts[i],base=16)<<0x8*(5-i))
    
    return hexDevID      

#sends the output of 'hcitool scan' to the callback function
#ie: a list of nearby discoverable bluetooth devices
class BTScanThread(threading.Thread):
    def __init__(self,callback):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.name='BTScanThread'
    def run(self):
        
        try:
            scanprocess = subprocess.Popen(['hcitool','scan'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            self.callback("Could not execute hcitool: %s"+str(e))
            return None
        
        if scanprocess == []:
            self.callback("Bluetooth does not appear to be enabled: skipping")
            return None
        try:
            out, err = scanprocess.communicate()
        except:
            scanprocess.kill()
            out, err = str(sys.exc_info())
            
        self.callback(out,err)
        return None


            
#tries to connect to the email servers listed with the given credentials    
class emailTestThread(threading.Thread):
    def __init__(self,callback,config):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.config = config
        self.name='mailTestThread'
    def run(self):
        if self.config['EMAIL']['EMAIL_SMTP_HOST']!= None:
            try:
                s = smtplib.SMTP(self.config['EMAIL']['EMAIL_SMTP_HOST'], timeout=10)
                s.ehlo()
                s.starttls()
                s.login(self.config['EMAIL']['EMAIL_USERNAME'], self.config['EMAIL']['EMAIL_PASSWORD'])
                s.quit()
            except smtplib.SMTPAuthenticationError:
                resultS = 'Authentication Error'
            except socket.timeout:
                resultS = 'Connection Timeout'
            except:
                resultS = 'Connection to %s failed'%self.config['EMAIL']['EMAIL_SMTP_HOST']
            else:
                resultS = 'OK'
            
        if self.config['EMAIL']['EMAIL_IMAP_HOST']!= None:    
            try:
                server = imapclient.IMAPClient(self.config['EMAIL']['EMAIL_IMAP_HOST'], use_uid=False, ssl=True)
                server.login(self.config['EMAIL']['EMAIL_USERNAME'], self.config['EMAIL']['EMAIL_PASSWORD'])
                server.select_folder('INBOX')
                server.logout()
                resultI = "OK"
            except FileNotFoundError:
                resultI = 'Connection to %s failed'%self.config['EMAIL']['EMAIL_IMAP_HOST']
            except socket.gaierror:
                resultI = 'Connection Failed: gaierror'
            except socket.timeout:
                resultI = 'Connection Timeout'
            except imapclient.IMAPClient.Error as e:
                resultI = e.args[0].decode('utf-8')
            
        self.callback('IMAP: '+resultI,'SMTP: '+resultS)
        return None
    



