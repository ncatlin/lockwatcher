#!/usr/bin/python3
'''
lockwatcher.py
@author: Nia Catlin

Runs a group of threads which monitor for potential forensic-related system events
and trigger the antiforensic module if appropriate

Requires 'motion' and 'ifplugd' to be running and properly configured
to use the motion and network connection triggers
'''
import multiprocessing
import threading, queue, struct, sys
import os,subprocess,time
import dbus, signal, socket
import pyudev, sensors #bastien leonards pysensors 
import imapclient, sendemail
from sendemail import sendEmail,validHMAC
import syslog

from gi.repository import GObject
from pwd import getpwnam
from dbus.mainloop.glib import DBusGMainLoop

import lwconfig, AFroutines
from lwconfig import triggerList

from daemon import daemon

eventQueue = queue.Queue()

def device_changed(action,device):
    details = (device,action)
    eventQueue.put((lwconfig.E_DEVICE,details))
 
def cableSigHandler(sigid, frame):
    eventQueue.put((lwconfig.E_NETCABLE,None))
    

#multiple instances of motion need to be set up as sescribed at 
#http://www.lavrsen.dk/foswiki/bin/view/Motion/FrequentlyAskedQuestions
def chassisMotionSigHandler(sigid, frame):
    eventQueue.put((lwconfig.E_CHASSIS_MOTION,None))

monitoringRoom = False
def roomMotionSigHandler(sigid,frame):
    if monitoringRoom == True:
        eventQueue.put((lwconfig.E_ROOM_MOTION,None))
        
lockQueue = None
def scrnLocked(state):
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(('127.0.0.1',22190))
    if state == 1:s.send(b'True')
    else: s.send(b'False')

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
            if lwconfig.DESKTOP_ENV == 'LXDE':
                print('running lxde lockmon')
                try:
                    currentState = ('locked' in str(subprocess.check_output(["/usr/bin/xscreensaver-command", "-time"])))
                except subprocess.CalledProcessError:
                    syslog.syslog("Screen status not set - lock screen once before running lockwatcher")
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
        
        print('started p',p.pid)
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
            syslog.syslog('Could not bind to 127.0.0.1:22190, please kill any other lockwatchers and try again')
            eventQueue.put(('fatalerror',None))
            return
        
        while True:
            result = s.recv(5)
            if result == b'True': result = True
            elif result == b'False': result = False
            eventQueue.put(('lock',result))

#lack of access to DIMM SPD data means this only checks motherboard
class temperatureMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "TempMonThread"
        for chip in sensors.get_detected_chips():
            if "acpi" in str(chip): break
        else:
            syslog.syslog("Could not read acpi bus: Temperature monitoring disabled")
            self.die = True
            return
        self.chip = chip
            
        for feature in chip.get_features():
            if 'Temperature' in str(feature): break
        for subfeature in chip.get_all_subfeatures(feature):
            if 'input' in str(subfeature.name):break
        self.subfeature = subfeature    
        self.die = False
        
    def run(self):
        lastTemp = self.chip.get_value(self.subfeature.number)
        while self.die == False:
            time.sleep(1)
            newTemp = self.chip.get_value(self.subfeature.number)
            if newTemp < lwconfig.LOW_TEMP: eventQueue.put((lwconfig.E_KILL_SWITCH,"newTemp degrees C"))
            lastTemp = newTemp
            
    def terminate(self):
        self.die = True

def temperatureMonStart():
        tempMon = temperatureMonitor()
        tempMon.daemon = True
        tempMon.start()
        return tempMon

intrusionSwitchPath = '/sys/class/hwmon/hwmon*/device/intrusion0_alarm'
def intrusionSwitchStatus():
    try:
        fd = open(intrusionSwitchPath,'r')
        status = fd.read()
        fd.close()
    except:
        #if it was working when the process started then assume
        #any later problems are due to tampering
        return True 
    return status

#poll the chassis intrusion detection switch for activation

noSwitchNotified = False    
class intrusionMon(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self) 
        self.name = "IntrusionMonThread"

        self.die = False #prevents thread running if there are problems
        global noSwitchNotified 
        if noSwitchNotified == True:
            self.die = True
            return
        
        if not os.path.exists(intrusionSwitchPath) and noSwitchNotified == False:
            syslog.syslog("Error: No chassis intrusion detection switch found") 
            noSwitchNotified = True
            self.die = True
            return
        
        #switch already triggered, try to reset it
        if intrusionSwitchStatus() != 0: 
            subprocess.Popen("echo 0 > %s"%intrusionSwitchPath,Shell=True)
            time.sleep(0.5)
            if intrusionSwitchStatus() != 0: 
                syslog.syslog("Error: Cannot reset an already triggered intrusion switch. Monitoring disabled.")
                self.die = True
                return
    def run(self):
        
        while self.die == False:
            time.sleep(1)
            if intrusionSwitchStatus != 0:
                eventQueue.put((lwconfig.E_INTRUSION,None))
                
    def terminate(self):
        self.die = True
        

def intrusionMonStart():
        intrusionMon = temperatureMonitor()
        intrusionMon.daemon = True
        intrusionMon.start()
        return intrusionMon                       

class bluetoothMon(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self) 
        
        self.name = "BluetoothMonThread"
        try:
            self.s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self.s.settimeout(50)
            self.s.connect((lwconfig.BLUETOOTH_DEVICE_ID,2))
        except:
            self.s = None
            syslog.syslog("Error: Bluetooth connection to %s unavailable or unauthorised"%lwconfig.BLUETOOTH_DEVICE_ID)
            return
        
    def run(self):
        s = self.s
        if s == None: return
    
        while True:
            try:
                s.recv(1024)
            except socket.timeout:
                pass
            except:
                syslog.syslog("Bad connection to bluetooth device")
                eventQueue.put((lwconfig.E_BLUETOOTH,None))
                time.sleep(60)
            
            s.close()
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            s.settimeout(600)
            s.connect((lwconfig.BLUETOOTH_DEVICE_ID,2))

def setupIMAP():
    try:
        server = imapclient.IMAPClient(lwconfig.EMAIL_IMAP_HOST, use_uid=False, ssl=True)
        server.login(lwconfig.EMAIL_USERNAME, lwconfig.EMAIL_PASSWORD)
        server.select_folder('INBOX')
        syslog.syslog("Established IMAP connection")
        return server
    except:
        syslog.syslog("Error: Could not connect to mail IMAP server, will not listen for remote commands")
        return
              
class emailMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "mailMonThread"
    def run(self):
        server = setupIMAP()
        server.idle()
        syslog.syslog('starting email monitor loop')
        while True:
            #refresh the connection every 14 mins so it doesnt timeout
            seqid = server.idle_check(840)
            if seqid == []: #no mail
                try:
                    server.idle_done()
                    server.idle()
                except ConnectionResetError:
                    syslog.syslog("Connection reset error on imap: reconnecting")
                    server = setupIMAP()
                    server.idle()
                continue
            
            #fetch header data using the sequence id of the new mail  
            seqid = seqid[0][0]
            server.idle_done()
            keys = server.fetch(seqid, ['ENVELOPE'])
            server.idle()
            keys = keys[seqid]['ENVELOPE']
            if keys[2][0][2] == 'niasphone':
                eventQueue.put(("mail",keys[1]))
            else:
                syslog.syslog("Got an email, unknown addressee: %s"%keys[2][0][2])

#find better way to choose event - /proc/bus/input/devics is good       
class keyboardMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "KeyboardMonThread"
    def run(self):
        if lwconfig.kbdEvent == None:
            syslog.syslog("Keyboard not found or not configured - run lockwatcher-gui")
            return
        
        try:
            dev = open(lwconfig.kbdEvent,'rb')
        except IOError as e:
            syslog.syslog("Cannot monitor keyboard: %s\n->Need to run as root"%e)
            return
        
        if len(lwconfig.triggerKeyCombination) == 0: 
            syslog.syslog("No trigger key combination provided: keyboard killswitch inactive")
            return
        
        trigKeys = {}
        for scanCode in lwconfig.triggerKeyCombination:
            trigKeys[scanCode] = False
            
        keyEventFormat = 'llHHI'
        keyEventSize = struct.calcsize(keyEventFormat)
        trigThreshold = len(trigKeys.keys())
        keysPressed = 0
        
        while True:
            event = dev.read(keyEventSize)
            (time1, time2, eType, kCode, pressed) = struct.unpack(keyEventFormat, event)
            kCode = str(kCode)
            if eType != 1: continue
            if kCode in trigKeys.keys():
                if pressed == 1 and trigKeys[kCode] == False:
                    trigKeys[kCode] = True
                    keysPressed += 1
                    if keysPressed >= trigThreshold:
                        eventQueue.put((lwconfig.E_KILL_SWITCH,None))
                elif pressed == 0 and trigKeys[kCode] == True:
                    trigKeys[kCode] = False
                    keysPressed -= 1

REMOTE_LOCK = 1
REMOTE_STARTMONITOR = 2
REMOTE_STOPMONITOR = 3
REMOTE_SHUTDOWN = 4
REMOTE_KILLSWITCH = 5
commandList = range(REMOTE_LOCK,REMOTE_KILLSWITCH+1)
    
class lockWatcher(daemon):   
    def run(self):
#if __name__ == "__main__":
        syslog.syslog('Staring lockwatcher daemon')
        lockState = False 
        
        
        #the dbus interface we use to catch and send lock signals
        #requires we be that users UID, so we save it here
        if (os.getenv("SUDO_USER")) != None:
            suUser = getpwnam(os.getenv("SUDO_USER")).pw_uid
            AFroutines.screenOwner = suUser
        else: 
            suUser = None
            AFroutines.screenOwner = os.getuid()
        #AFroutines.lockObject = dbus.Interface(proxy,interface)
        
        #monitor when when the screen becomes locked or unlocked
        lockmon = lockMonitor(suUser)
        lockmon.daemon = True
        lockmon.start()
        
        
        
        #monitor for the keyboard killswitch command
        if lwconfig.E_KILL_SWITCH in triggerList:
            keyMon = keyboardMonitor()
            keyMon.daemon = True
            keyMon.start()
        
        
        #wait for a signal from 'netplugd' indicating a cable change
        #subprocess.Popen(['/etc/init.d/ifplugd','restart'])
        if lwconfig.E_NETCABLE in triggerList:
            signal.signal(signal.SIGUSR1, cableSigHandler)
        
        
        #wait for a signal from the room motion process
        monitoringRoom = False
        if lwconfig.E_ROOM_MOTION in triggerList:
            signal.signal(signal.SIGHUP, roomMotionSigHandler)
            #assume these are not running on startup
            if lockState == True:
                print("starting motion")
                subprocess.Popen(['/etc/init.d/motion','restart'])
                monitoringRoom = True
            else:
                subprocess.Popen(['/etc/init.d/motion','stop'])
                
        #wait for a signal from the chassis motion process
        #handle it always incase the daemon is running
        signal.signal(signal.SIGUSR2, chassisMotionSigHandler)
        if lwconfig.E_CHASSIS_MOTION in triggerList:
            subprocess.Popen(['/etc/init.d/motion2','restart'])
        
        if lwconfig.E_BLUETOOTH in triggerList:
            BTThread = bluetoothMon()
            BTThread.daemon = True
            BTThread.start()
        
        badCommands = 0
        #if remote control
        EMThread = emailMonitor()
        EMThread.daemon = True
        EMThread.start()
        
        #monitor for device change events from the kernel
        #hopefully intervene before the device can do anything
        if lwconfig.E_DEVICE in triggerList: 
            context = pyudev.Context()
            monitor = pyudev.Monitor.from_netlink(context,source='kernel')
            monitor.start()
            deviceMonitor = pyudev.MonitorObserver(monitor, event_handler=device_changed)
            deviceMonitor.start()
        
        tempMonThread = None
        intrusionMonThread = None
            
        syslog.syslog("AF detection started at %s"%time.strftime('%x %X'))
        while True:
            (event,details) = eventQueue.get(block=True, timeout=None)
            if event in lwconfig.triggerText.keys():
                syslog.syslog("Trigger event '%s' (Details:%s, Lock status:%s)"%(lwconfig.triggerText[event],details,lockState))
            else: syslog.syslog("Non trigger event: %s"%event)
            
            if event in lwconfig.alwaysTriggers or (lockState == True and event in lwconfig.lockedTriggers): 
                triggerInfo = "%s. Extra details: %s"%(lwconfig.triggerText[event],details)
                if event == lwconfig.E_DEVICE:
                    AFroutines.antiforensicShutdown(triggerInfo,lockState,device=details[0].sys_path.split('/'))
                AFroutines.antiforensicShutdown(triggerInfo,lockState)
            elif event == 'lock':
                lockState = details
                if lockState == True:
                    syslog.syslog('setting lock to true')
                    #polling threads die when the screen is unlocked - have to ressurect
                    if lwconfig.E_TEMPERATURE in triggerList and tempMonThread == None: 
                        tempMonThread = temperatureMonStart()
                    if lwconfig.E_INTRUSION in triggerList and intrusionMonThread == None:  
                        intrusionMonThread = intrusionMonStart()
                else:
                    syslog.syslog('setting lock to false')
                    if tempMonThread != None: 
                        tempMonThread.terminate()
                        tempMonThread = None
                    if intrusionMonThread!= None:
                        intrusionMonThread.terminate()
                        intrusionMonThread = None
            elif event == 'mail': 
                command, code = details.split(' ')
                syslog.syslog('processing mail %s %s'%(command,code))
                command = int(command)
                if command not in commandList or validHMAC(code,command) == False:
                    badCommands += 1
                    sendEmail("Command failed","Bad command or authentication code received: %s"%command)
                    if badCommands >= lwconfig.BAD_COMMAND_LIMIT:
                        reason = "Too many bad remote commands received"
                        AFroutines.antiforensicShutdown(reason,lockState)
                else:
                    syslog.syslog('mail accepted')
                
                #a successful command resets the counter
                badCommands = 0       
                
                if command == REMOTE_LOCK:
                    if lockState == False:
                        AFroutines.lockScreen()
                        sendEmail("Command successful","Screen locked")
                        syslog.syslog('Locking screen from remote command')
                    else:
                        sendEmail("Command failed","Screen was already locked")
                        syslog.syslog('Lock screen command received while locked')
                    
                elif command == REMOTE_STARTMONITOR and monitoringRoom == False:
                    monitoringRoom = True
                    subprocess.Popen(['/etc/init.d/motion','restart'],stderr= subprocess.DEVNULL)
                    sendEmail("Command successful","Movement monitoring initiated. Have a nice day.")
                elif command == REMOTE_STOPMONITOR and monitoringRoom == True:
                    monitoringRoom = False
                    subprocess.Popen(['/etc/init.d/motion','stop'],stderr= subprocess.DEVNULL)
                    sendEmail("Command successful","Movement monitoring disabled. Welcome home!")
                elif command == REMOTE_SHUTDOWN:
                    AFroutines.standardShutdown()
                    sendEmail("Command successful","Shutting down...")
                elif command == REMOTE_KILLSWITCH:
                    reason = "Remote shutdown command received"
                    AFroutines.antiforensicShutdown(reason,lockState)   
                    
            elif event == 'fatalerror':
                syslog.syslog('dying after fatal error')
                exit()
                
#kill lock watching process
def killLockmon():
    try: 
        lockmonFD = open('/var/run/lockpid','r')
        lockmonPID = lockmonFD.read()
        lockmonFD.close()
        subprocess.Popen(['/bin/kill',lockmonPID],stderr= subprocess.DEVNULL)  
    except:
        pass
     
    if os.path.exists('/var/run/lockpid'): 
        os.remove('/var/run/lockpid')

def kill_self(signal, frame):
        '''
        #this doesnt work, os.path.exists() thinks it exists then
        #we get filenotfound for trying to kill it
        if os.path.exists(lwconfig.PID_FILE): 
            print(lwconfig.PID_FILE, 'exists!')
            os.remove(lwconfig.PID_FILE)
        '''
        killLockmon()
        exit()    

if __name__ == "__main__":
        
        if len(sys.argv) == 2:
                if sys.argv[1] == 'console':
                    try:
                        fd = open(lwconfig.PID_FILE,'w')
                        fd.write(str(os.getpid()))
                        fd.close()
                    except PermissionError:
                        print("Do not have permission to write PID to %s"%lwconfig.PID_FILE)
                        exit()
                    
                    signal.signal(signal.SIGINT, kill_self)   
                    lockWatcher.run(lockWatcher)

                        
                daemon = lockWatcher(lwconfig.PID_FILE)
                if 'start' == sys.argv[1]:
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        killLockmon()
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        daemon.restart()
                else:
                        print( "Unknown command")
                        sys.exit(2)
                sys.exit(0)
        else:
                print( "usage: %s start|stop|restart|console" % sys.argv[0])
                sys.exit(2)                