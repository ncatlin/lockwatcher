'''
@author: Nia Catlin

Various hardware and system state interrogation routines
'''
import subprocess,threading,socket,os,time,multiprocessing
import smtplib, sensors
import fileconfig

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

lockState = False
def setLock(state):
    print('Setting lock state to ',state)
    global lockState
    if state in [True,False]:
        lockState = state
        
def checkLock():
    return lockState
      
    
lockQueue = None

def scrnLocked(state):
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(('127.0.0.1',22190))
    if state == 1:s.send(b'True')
    else: s.send(b'False')

'''
#cannot interact with user screen as root,
#make new process to do it
def lockMonitorProcess(uid,q):
        if os.getuid()==0:
            os.setuid(uid)

        #this isnt great, there are a few different lock implementations floating around
        #lubuntu switching from xscreensaver-command to lightdm from locking next release
        if lwconfig.DBUSSUPPORTED == True:
            session_bus = dbus.SessionBus(mainloop=DBusGMainLoop())
            #subscribe to kde and gnome lock notification signals
            session_bus.add_signal_receiver(scrnLocked,'ActiveChanged','org.freedesktop.ScreenSaver')
            session_bus.add_signal_receiver(scrnLocked,'ActiveChanged','org.gnome.ScreenSaver')
            GObject.MainLoop().run()
        else:
            if fileconfig.config['TRIGGERS']['desktop_env'] == 'LXDE':
                try:
                    currentState = ('locked' in str(subprocess.check_output(["/usr/bin/xscreensaver-command", "-time"])))
                except subprocess.CalledProcessError:
                    print("Screen status not set - lock screen once before running lockwatcher")
                    currentState = False
                while True:
                    time.sleep(1)
                    
                    try:
                        outp = subprocess.check_output(["/usr/bin/xscreensaver-command", "-time"])
                    except subprocess.CalledProcessError:
                        continue
                    
                    if 'locked' in str(outp):
                        if currentState == False:
                            currentState = True
                            scrnLocked(1)
                    else:
                        if currentState == True:
                            currentState = False
                            scrnLocked(0)
 '''               
            
'''      
#put this in a thread to stop it blocking everything else
#this also stops keyboard interrupts from closing the program
class lockMonitor(threading.Thread):
    def __init__(self,user):
        threading.Thread.__init__(self)
        self.name = "LockMonThread"
        self.user = user
    def run(self):
        lockQueue = multiprocessing.Queue()
        p = multiprocessing.Process(target=lockMonitorProcess,args=(self.user,lockQueue))
        p.daemon = True
        p.start()
        
        pidfd = open('/var/run/lockpid','w')
        pidfd.write(str(p.pid))
        pidfd.close()
        #i dont like using sockets here but queues often lost
        #values in transit and left the system in an inconsistent state
        #bug to be fixed
        try:
            s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            s.bind(('127.0.0.1',22190))
        except:
            printMessage('Could not bind to 127.0.0.1:22190, please kill any other lockwatchers and try again')
            eventQueue.put(('fatalerror',None))
            return
        
        while True:
            result = s.recv(5)
            if result == b'True': result = True
            elif result == b'False': result = False
            eventQueue.put(('lock',result))
'''           
            
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

numNames = {'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9'}      
import struct, re,sys
#passes keystrokes from (eventFile device) to the callback function 
class kbdListenThread(threading.Thread):
    def __init__(self,callback,device):
        threading.Thread.__init__(self,) 
        self.callback = callback
        self.event = device
        self.name = 'kbdListenThread'
    def run(self):
        self.listening = True
        try:
            dev = open(self.event,'rb')
        except IOError as e:
            print("Cannot monitor keyboard: %s"%e)
            return
        
        
        KCodes = {} 
        try:
            outp = subprocess.check_output(["/bin/dumpkeys", "--keys-only"]).decode('UTF-8')
        except:
            e = sys.exc_info()[0]
            print('Could not get keyboard symbols from /bin/dumpkeys:',e)
            outp = ''
            
        #generate symbols table
        for line in outp.split('\n'):
            reg = re.search('^keycode\s*(\S*)\s*=\s*(\S*)[\S\s]*',line)
            if reg != None:
                hexCode = int(hex(int(reg.group(1))),16)
                symbol = reg.group(2).strip('+')
                if symbol in numNames.keys():
                    symbol = numNames[symbol]
                
                KCodes[hexCode] = symbol
        
        keyEventFormat = 'llHHI'
        keyEventSize = struct.calcsize(keyEventFormat)
        
        while self.listening == True:
            event = dev.read(keyEventSize)
            (time1, time2, eType, kCode, pressed) = struct.unpack(keyEventFormat, event)
            if eType != 1: continue #not key down
            if pressed == 1:
                if kCode in KCodes.keys():
                    keyname = KCodes[kCode]
                else: keyname = 0
                print(kCode)
                self.callback(kCode,keyname)
        return None
    def terminate(self):
        self.listening = False


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
            self.socket.connect((self.deviceID,2))
        #todo : put all these in one except as e
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
            print('fuck ',e)
        print("scanprocess = ",scanprocess)
        if scanprocess == []:
            self.callback("Bluetooth does not appear to be enabled: skipping")
            return None
        try:
            out, err = scanprocess.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            scanprocess.kill()
            out, err = scanprocess.communicate()
            
        self.callback(out,err)
        return None


#checks temperature.csv for updates
class RAMMonitor(threading.Thread):
    def __init__(self, callback):
        threading.Thread.__init__(self)
        self.callback = callback
        self.die = False
        self.name='ramMonitorThread'
    def run(self):
        lastTime = None
        startup = True
        while self.die == False:
            if startup == False: time.sleep(1) #the MOD logger only writes once per second
            else: startup = False
            
            try:
                csvfile = open(fileconfig.config['TRIGGERS']['BALLISTIX_LOG_FILE'],mode='rb')
                csvfile.seek(-30, 2)
                line = csvfile.readline()
                csvfile.close()
            except IOError as e:
                if e.errno == 2:
                    self.callback("Unable to open log file")
                    return
                else:
                    continue #probably locked by logger writing
                    time.sleep(0.5)
        
            
            
            logDetail = line.decode("utf-8").split(',')
            if len(logDetail) != 4 and len(logDetail) != 0: continue #empty or invalid
            
            logTime,RAMTemp =  (logDetail[0],logDetail[2])
            if lastTime == None or logTime != lastTime:
            #if RAMTemp <= fileconfig.config['TRIGGERS']['LOW_TEMP']:  
                self.callback('('+logTime+'): '+RAMTemp+'C')
                lastTime = logTime
                
    def terminate(self):
        self.die = True
            
#tries to connect to the email hosts listed with the given credentials    
import imapclient
class emailTestThread(threading.Thread):
    def __init__(self,callback,config):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.config = config
        self.name='mailTestThread'
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
                resultS = 'Connection to %s failed'%self.config['EMAIL']['EMAIL_SMTP_HOST']
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
    



