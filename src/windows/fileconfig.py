'''
@author: Nia Catlin

Various config file handling routines
'''
import ConfigParser, os 

TRIG_LOCKED = 0
TRIG_ALWAYS = 1
TRIG_NEVER = 2

CONFIG_FILE = os.path.join(os.getcwd(),'lockwatcher.ini')
config = None

def writeConfig():
    with open(CONFIG_FILE, 'wb') as configfile:
            config.write(configfile)#,space_around_delimiters=False)
            
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
    LOCKED = config['TRIGGERS']['lockedtriggers'].split(',')
    ALWAYS = config['TRIGGERS']['alwaystriggers'].split(',')
    
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
    
    config['TRIGGERS']['lockedtriggers'] = str(LOCKED).strip("[]").replace("'","").replace(" ","")
    config['TRIGGERS']['alwaystriggers'] = str(ALWAYS).strip("[]").replace("'","").replace(" ","")
    writeConfig()

def isActive(trigger):
    if trigger in config['TRIGGERS']['alwaystriggers'].split(','):
        return (True,'Always')
    elif trigger in config['TRIGGERS']['lockedtriggers'].split(','):
        return (True,'Locked')
    else:
        return (False,False)

def trigStateChange(combo):
    new_trigger = combo.get_active()
    trigger_type = combo.get_title().strip()
    LOCKED = config['TRIGGERS']['lockedtriggers'].split(',')
    ALWAYS = config['TRIGGERS']['alwaystriggers'].split(',')
    
    if trigger_type in LOCKED:
        LOCKED.remove(trigger_type) 
    if trigger_type in ALWAYS:
        ALWAYS.remove(trigger_type)
          
    if new_trigger == TRIG_LOCKED:
        LOCKED.append(trigger_type)
    elif new_trigger == TRIG_ALWAYS:
        ALWAYS.append(trigger_type)
        
    config['TRIGGERS']['lockedtriggers'] = str(LOCKED).strip("[]").replace("'","").replace(" ","")
    config['TRIGGERS']['alwaystriggers'] = str(ALWAYS).strip("[]").replace("'","").replace(" ","")
    writeConfig()

def loadConfig():
    if not os.path.exists(CONFIG_FILE) or os.path.getsize(CONFIG_FILE)<20:
        global config
        config = ConfigParser.ConfigParser()
        config.add_section('TRIGGERS')
        config.set('TRIGGERS','bluetooth_device_id','')
        config.set('TRIGGERS','bluetooth_device_id','')
        config.set('TRIGGERS','kbd_kill_combo_1','')
        config.set('TRIGGERS','kbd_kill_combo_2','')
        config.set('TRIGGERS','low_temp','21')
        config.set('TRIGGERS','lockedtriggers','E_DEVICE,E_NETCABLE,E_CHASSIS_MOTION,E_ROOM_MOTION,E_NET_CABLE_IN,E_NET_CABLE_OUT,E_KILL_SWITCH_2')
        config.set('TRIGGERS','alwaystriggers','E_KILL_SWITCH_1')
        config.set('TRIGGERS','dismount_tc','False')
        config.set('TRIGGERS','exec_shellscript','False')
        config.set('TRIGGERS','adapterconguids','')
        config.set('TRIGGERS','adapterdisconguids','')
        config.set('TRIGGERS','ballistix_log_file','')
        config.set('TRIGGERS','tc_path','')
        config.set('TRIGGERS','ispy_path','')
        config.set('TRIGGERS','room_cam_id','')
        config.set('TRIGGERS','logfile','')
        config.set('TRIGGERS','immediatestart','False')
        
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
        config.set('EMAIL','alert_email_address','changeme@mail.domain')
        config.set('EMAIL','command_email_address','yourpc@mail.domain')
        writeConfig()
    else:    
        config = ConfigParser.ConfigParser()
        config.read(CONFIG_FILE)
        
    return config


config = loadConfig()
def reloadConfig():
    global config
    config = loadConfig()
