'''
@author: Nia Catlin

Various config file handling routines
'''
import ConfigParser, os, time
import _winreg 

CONFIG_FILE = None
config = None

def writeConfig():
    with open(CONFIG_FILE, 'w') as configfile:
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

def isActive(trigger):
    if trigger in config.get('TRIGGERS','alwaystriggers').split(','):
        return (True,'Always')
    elif trigger in config.get('TRIGGERS','lockedtriggers').split(','):
        return (True,'Locked')
    else:
        return (False,False)

def loadConfig():
    global CONFIG_FILE
    try:
        key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\Lockwatcher")
        CONFIG_FILE = str(_winreg.QueryValueEx(key,'ConfigPath')[0])
    except:
        key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,"SOFTWARE\Wow6432Node\Lockwatcher")
        CONFIG_FILE = str(_winreg.QueryValueEx(key,'ConfigPath')[0])
    time.sleep(0.1)
    if not os.path.exists(CONFIG_FILE) or os.path.getsize(CONFIG_FILE)<20:
        global config
        print('writing new config')
        config = ConfigParser.ConfigParser()
        config.add_section('TRIGGERS')
        config.set('TRIGGERS','bluetooth_device_id','')
        config.set('TRIGGERS','bluetooth_device_id','')
        config.set('TRIGGERS','kbd_kill_combo_1','')
        config.set('TRIGGERS','kbd_kill_combo_2','')
        config.set('TRIGGERS','low_temp','21')
        config.set('TRIGGERS','lockedtriggers','E_DEVICE,E_CHASSIS_MOTION,E_ROOM_MOTION,E_NET_CABLE_IN,E_NET_CABLE_OUT,E_KILL_SWITCH_2')
        config.set('TRIGGERS','alwaystriggers','E_KILL_SWITCH_1')
        config.set('TRIGGERS','dismount_tc','False')
        config.set('TRIGGERS','exec_shellscript','False')
        config.set('TRIGGERS','script_timeout','0')
        config.set('TRIGGERS','adapterconguids','')
        config.set('TRIGGERS','adapterdisconguids','')
        config.set('TRIGGERS','ballistix_log_file','')
        config.set('TRIGGERS','tc_path','')
        config.set('TRIGGERS','ispy_path','')
        config.set('TRIGGERS','room_cam_id','')
        config.set('TRIGGERS','logfile','')
        config.set('TRIGGERS','debuglog','False')
        config.set('TRIGGERS','test_mode','False')
        
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
        writeConfig()
    else:    
        config = ConfigParser.ConfigParser()
        config.read(CONFIG_FILE)
        
    return config


config = loadConfig()
def reloadConfig():
    global config
    config = loadConfig()
