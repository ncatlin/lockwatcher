'''
@author: Nia Catlin

Various config file handling routines
'''
import ConfigParser,re,pickle,os,time
import sys,subprocess
from lockwatcher import hardwareconfig

TRIG_LOCKED = 0
TRIG_NEVER = 1
TRIG_ALWAYS = 2

CONFIG_FILE = '/etc/lockwatcher/lockwatcher.conf'
config = None

writing = False
def writeConfig():
    global writing
    writing = True
    try:
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
            configfile.close()
    except: print('Failed to write config file: %s'%sys.exc_info()[0])
    '''the gui seems to hit a race condition when changing tabs occasionally
    but I haven't found a way to repeat it reliably. Putting a little sleep in here
    to give it time to write.
    '''
    time.sleep(0.1)
    writing = False
    hardwareconfig.sendToLockwatcher('reloadConfig',config.get('TRIGGERS','daemonport'))
    
def checkBtnChanged(btn):

    btnName = btn.get_name()
    if btnName == 'enable_remote':
        config['EMAIL']['enable_remote'] = str(btn.get_active())
    elif btnName == 'enable_alerts':
        config['EMAIL']['email_alert'] = str(btn.get_active())
    elif btnName == 'dismount_crypt':
        config['TRIGGERS']['dismount_crypt'] = str(btn.get_active())
    elif btnName == 'dismount_tc':
        config['TRIGGERS']['dismount_tc'] = str(btn.get_active())
    else: 
        print('unknown toggle box: ',btnName)
        return
    
    writeConfig()
    
def entryChanged(thing):
    entryName = thing.get_name()
    
    if entryName in config.options('EMAIL'):
        section = 'EMAIL'
    elif entryName in config.options('TRIGGERS'):
        section = 'TRIGGERS'
    else:
        print('Unknown section for',entryName)
        return
    
    config[section][entryName] = thing.get_text()
    writeConfig()

def tktrigStateChange(combo):
    LOCKED = config.get('TRIGGERS','lockedtriggers').split(',')
    ALWAYS = config.get('TRIGGERS','alwaystriggers').split(',')
    
    new_trigger = combo.widget.current()
    trigger_type = combo.widget._name.upper()
    
    if trigger_type in LOCKED:
        LOCKED.remove(trigger_type)
    if trigger_type in ALWAYS:
        ALWAYS.remove(trigger_type)
                
    if new_trigger == TRIG_LOCKED:
        LOCKED.append(trigger_type)
    elif new_trigger == TRIG_ALWAYS:
        ALWAYS.append(trigger_type)
    
    config.set('TRIGGERS','lockedtriggers', str(LOCKED).strip("[]").replace("'","").replace(" ",""))
    config.set('TRIGGERS','alwaystriggers', str(ALWAYS).strip("[]").replace("'","").replace(" ",""))
    writeConfig()

def isActive(trigger):
    if trigger in config.get('TRIGGERS','alwaystriggers').split(','):
        return (True,'Always')
    elif trigger in config.get('TRIGGERS','lockedtriggers').split(','):
        return (True,'Locked')
    else:
        return (False,False)
    
def getActiveTriggers():
    lockedTriggers = config.get('TRIGGERS','lockedtriggers').split(',')
    alwaysTriggers = config.get('TRIGGERS','alwaystriggers').split(',')
    return lockedTriggers+alwaysTriggers   
    
#generate a keycode->keyname mapping
def generateKCodeTable():
    for path in ['/bin/dumpkeys','/usr/bin/dumpkeys','/usr/local/bin/dumpkeys']:
        if os.access(path, os.X_OK):
            dkPath = path
            break
    else:
        dkPath = None
        
    try:
        #needs root, sadly
        outp = subprocess.check_output([dkPath, "--keys-only"]).decode('UTF-8')
    except:
        e = sys.exc_info()
        print('kcodegen exception %s'%str(e))
        return False
       
    numNames = {'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9'}      
    
    kCodeTable = {}
    #generate symbols table
    for line in outp.split('\n'):
        reg = re.search('^keycode\s*(\S*)\s*=\s*(\S*)[\S\s]*',line)
        if reg != None:
            hexCode = int(hex(int(reg.group(1))),16)
            symbol = reg.group(2).strip('+')
            if symbol in numNames.keys():
                symbol = numNames[symbol]
            
            kCodeTable[hexCode] = symbol
          
    return kCodeTable

def loadConfig():
    CF_EXISTS = os.path.exists(CONFIG_FILE)
    if not CF_EXISTS or os.path.getsize(CONFIG_FILE)<30:
        if CF_EXISTS and not os.access(CONFIG_FILE,os.W_OK):
            print('Either lockwatcherd or lockwatcher-gui must first be run as root to perform some initial configuration')
            sys.exit()
        fd = open(CONFIG_FILE, 'w')
        fd.close()
        if os.geteuid() == 0:
            os.chmod(CONFIG_FILE, 438) #rw-rw-rw-
        
        global config
        config = ConfigParser.ConfigParser()
        config.add_section('TRIGGERS')
        config.set('TRIGGERS','bluetooth_device_id','')
        config.set('TRIGGERS','kbd_kill_combo_1','')
        config.set('TRIGGERS','kbd_kill_combo_1_txt','')
        config.set('TRIGGERS','kbd_kill_combo_2','')
        config.set('TRIGGERS','kbd_kill_combo_2_txt','')
        config.set('TRIGGERS','keyboard_device','None')
        config.set('TRIGGERS','mouse_device','None')
        config.set('TRIGGERS','low_temp','21')
        config.set('TRIGGERS','lockedtriggers','E_DEVICE,E_NETCABLE,E_CHASSIS_MOTION,E_ROOM_MOTION,E_NET_CABLE_IN,E_NET_CABLE_OUT,E_KILL_SWITCH_2')
        config.set('TRIGGERS','alwaystriggers','E_KILL_SWITCH_1')
        config.set('TRIGGERS','dismount_tc','False')
        config.set('TRIGGERS','dismount_dm','False')
        config.set('TRIGGERS','exec_shellscript','False')
        config.set('TRIGGERS','script_timeout','5')
        config.set('TRIGGERS','adapterconids','')
        config.set('TRIGGERS','adapterdisconids','')
        
        if os.path.exists('/usr/bin/truecrypt'):
            config.set('TRIGGERS','tc_path','/usr/bin/truecrypt')
        elif os.path.exists('/usr/local/bin/truecrypt'):
            config.set('TRIGGERS','tc_path','/usr/local/bin/truecrypt')
        else:
            config.set('TRIGGERS','tc_path','')
            
        config.set('TRIGGERS','logfile','/var/log/lockwatcher')
        config.set('TRIGGERS','daemonport','22191')
        config.set('TRIGGERS','test_mode','False')
        
        config.add_section('CAMERAS')
        config.set('CAMERAS','cam_chassis','')
        config.set('CAMERAS','chassis_minframes','2')
        config.set('CAMERAS','chassis_fps','2')
        config.set('CAMERAS','chassis_threshold','5000')
        config.set('CAMERAS','cam_room','')
        config.set('CAMERAS','room_minframes','5')
        config.set('CAMERAS','room_fps','10')
        config.set('CAMERAS','room_threshold','10000')
        config.set('CAMERAS','room_savepicture','True')
        config.set('CAMERAS','image_path','/tmp')
        
        config.add_section('EMAIL')
        
        config.set('EMAIL','email_alert','False')
        config.set('EMAIL','email_imap_host','imap.changeme.domain')
        config.set('EMAIL','email_smtp_host','smtp.changeme.domain')
        config.set('EMAIL','email_username','changeme')
        config.set('EMAIL','email_password','changeme')
        config.set('EMAIL','email_secret','changeme')
        config.set('EMAIL','bad_command_limit','3')
        config.set('EMAIL','enable_remote','False')
        config.set('EMAIL','email_motion_picture','False')
        config.set('EMAIL','alert_email_address','yourphone@mail.domain')
        config.set('EMAIL','command_email_address','yourphone@mail.domain')
        config.set('EMAIL','sender_email_address','yourpc@mail.domain')
        
        config.add_section('KEYBOARD')
        config.set('KEYBOARD','MAP','None')
        writeConfig()
    else:    
        config = ConfigParser.ConfigParser()
        config.read(CONFIG_FILE)
    return config

config = loadConfig()

def reloadConfig():
    global config
    config = loadConfig()

#generate a keyboard map if none exists
if not os.path.exists('/etc/lockwatcher/keymap') and os.geteuid() == 0:
    mapfile = '/etc/lockwatcher/keymap'
    
    kCodes = generateKCodeTable()
    if kCodes != False:
        pickle.dump( kCodes, open( mapfile, "wb" ))
        config.set('KEYBOARD','MAP',mapfile)
        writeConfig()

#there must be a better way
def getLockProgram():
    if os.access('/usr/lib/kde4/libexec/kscreenlocker', os.X_OK):
            return '/usr/lib/kde4/libexec/kscreenlocker --force'
    elif os.access('/usr/lib/kde4/libexec/kscreenlocker_greet', os.X_OK):
            return '/usr/lib/kde4/libexec/kscreenlocker_greet'
    elif os.access('/usr/bin/gnome-screensaver-command', os.X_OK):
            return '/usr/bin/gnome-screensaver-command -l'
    elif os.access('/usr/bin/xscreensaver-command', os.X_OK):
            return '/usr/bin/xscreensaver-command -lock'   
    elif os.access('/usr/bin/mate-screensaver-command', os.X_OK):
            return '/usr/bin/mate-screensaver-command -l'   
    else: 
        print('No lock program found - may be unable to force lock activation')
        return None

#find the UID to use with the dbus
DESK_UID = None
sp = subprocess.Popen(['/usr/bin/pgrep','-xl', 'gnome-session|ksmserver|lxsession|mate-session|xfce4-session'],stdout=subprocess.PIPE)
out = sp.communicate()
results = out[0].decode('UTF-8')
if results != '':
    processes = results.split('\\n')
    if len(processes) > 1 and processes[-1] == '':
        del processes[-1]
    
    if len(processes) > 1:
        '''multiple desktop environment running?
        I don't know how to deal with that, I guess by running lock 
        detection/response on all of them at once. 
        todo it if it turns out to be needed'''
        pass
    
    pid,deskenv = processes[0].split(' ')
    for ln in open('/proc/%d/status' % int(pid)):
        if ln.startswith('Uid:'):
            DESK_UID = int(ln.split()[1])
            break 

#find the lock program to activate
if os.geteuid() == 0:
    LOCKCMD = None
    lockCmdFile = '/etc/lockwatcher/lockcmd'
    if os.path.exists(lockCmdFile):
        fd = open(lockCmdFile)
        cmd = fd.read().split(' ')[0]
        fd.close()
        if os.access(lockCmdFile, os.X_OK):
            LOCKCMD = cmd
    
    if LOCKCMD == None:
        LOCKCMD = getLockProgram()
        if LOCKCMD != None:
            fd = open(lockCmdFile,'w')
            fd.write(LOCKCMD)
            fd.close()





