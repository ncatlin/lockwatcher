'''
@author: Nia Catlin

Various hardware and system state interrogation routines
'''
import subprocess,threading,socket,os,time
import smtplib, re, sys
import imapclient
import bluetooth

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

#ttk combobox doesn't like non-ascii
def removeNonAscii(s):
        return "".join(filter(lambda x: ord(x)<128, s))
    
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
                cameranames[dev]['ID_MODEL'] = removeNonAscii(detail.split('=')[1])
                continue
            if 'ID_VENDOR=' in detail:
                cameranames[dev]['ID_VENDOR'] = removeNonAscii(detail.split('=')[1])
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
        
        sensors.init()
        for chip in sensors.iter_detected_chips():
            if "acpi" in str(chip): break
        else:
            self.die = True
            self.error = "Could not read acpi bus: Temperature monitoring disabled"
            return
        self.chip = chip
            
        for feature in chip:
            if 'MB Temperature' in feature.label: break
        else: 
            self.die = True
            return
        
        self.feature = feature    
        self.die = False
        
    def run(self):
        while self.die == False:
            time.sleep(1)
            newTemp = self.feature.get_value()
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
        if not bluetooth.is_valid_address(self.deviceID): return False
        
        try:
            self.socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            #self.socket.settimeout(45)
            self.socket.connect((self.deviceID,2))
               
        except bluetooth.btcommon.BluetoothError as e:
            if self.die == True: return #test cancelled
            errorno = e.message.strip('()').split(',')[0]
            if errorno == '113': 
                self.callback("Bluetooth Unavailable")
            elif errorno == '115':
                self.callback("Status: Cannot Connect")
            else:
                self.callback(e.message)
            return False
        except:
            print(sys.exc_info())
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
        results = bluetooth.discover_devices(10,True,True)
        
        if results != []: 
            self.callback(results,False)
            return
        else:
            #no results? try hciscantool because it often works when discover_devices doesn't
            try:
                scanprocess = subprocess.Popen(['hcitool','scan'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                self.callback("Could not execute hcitool: %s"+str(e),True)
                return None
            
            if scanprocess == []:
                self.callback("Bluetooth does not appear to be enabled: skipping",True)
                return None
            try:
                out, err = scanprocess.communicate()
                err = False
            except:
                scanprocess.kill()
                out = str(sys.exc_info())
                err = True
            
            devList = []
            for line in out.split('\n'):
                if line in ['Scanning ...','']: continue
                dev = line.lstrip('\t').split('\t')
                if len(dev) == 2:
                    devList.append((dev[0],dev[1]))
                else:
                    devList.append((dev[0]))
            
            self.callback(devList,err)

            
#tries to connect to the email servers listed with the given credentials    
class emailTestThread(threading.Thread):
    def __init__(self,callback,config):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.config = config
        self.name='mailTestThread'
    def run(self):
        host = self.config.get('EMAIL','EMAIL_SMTP_HOST')
        if host != '':
            try:
                s = smtplib.SMTP(host, timeout=10)
                s.ehlo()
                s.starttls()
                s.login(self.config.get('EMAIL','EMAIL_USERNAME'), self.config.get('EMAIL','EMAIL_PASSWORD'))
                s.quit()
            except smtplib.SMTPAuthenticationError:
                resultS = 'Authentication Error'
            except socket.timeout:
                resultS = 'Connection Timeout'
            except socket.gaierror:
                resultS = 'Connection Failed'
            except:
                resultS = 'Connection failed: %s'%sys.exc_info()[0]
            else:
                resultS = 'OK'
        
        host = self.config.get('EMAIL','EMAIL_IMAP_HOST')
        if host != '':    
            try:
                server = imapclient.IMAPClient(host, use_uid=False, ssl=True)
                server.login(self.config.get('EMAIL','EMAIL_USERNAME'), self.config.get('EMAIL','EMAIL_PASSWORD'))
                server.select_folder('INBOX')
                server.logout()
                resultI = "OK"
            except socket.gaierror:
                resultI = 'Connection Failed'
            except socket.timeout:
                resultI = 'Connection Timeout'
            except imapclient.IMAPClient.Error as e:
                resultI = e.args[0].decode('utf-8')
            except:
                resultI = str(sys.exc_info())
            
        self.callback('IMAP: '+resultI,'SMTP: '+resultS)
        return None
    



