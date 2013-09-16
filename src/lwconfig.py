'''
Created on 10 Sep 2013

@author: Nia Catlin
'''

import configparser
config = configparser.ConfigParser()
config.read('/etc/lockwatcher/lockwatcher.ini')

E_KILL_SWITCH    = 0
E_TEMPERATURE    = 1
E_ROOM_MOTION    = 2
E_CHASSIS_MOTION = 3
E_INTRUSION      = 4
E_DEVICE         = 5
E_KEYPRESS       = 6
E_NETCABLE       = 7
E_BLUETOOTH      = 8

triggerText = {
    E_KILL_SWITCH    : "Kill switch activation",
    E_TEMPERATURE    : "Low temperature",
    E_ROOM_MOTION    : "Camera detected room motion",
    E_CHASSIS_MOTION : "Camera detected chassis motion",
    E_INTRUSION      : "Chassis intrusion switch activation",
    E_DEVICE         : "Device insertion or removal",
    E_NETCABLE       : "Network cable inserted or removed",
    E_BLUETOOTH      : "Lost Bluetooth connection to device"
}
###BEGIN USER CONFIGURATION SECTION###

#events which are not in either of these lists are ignored
#events which trigger antiforensics when the screen is locked
#E_CHASSIS_MOTION
lockedTrigStrs  =  config['TRIGGERS']['lockedtriggers'].split(',')
lockedTriggers = []
for trig in lockedTrigStrs:
    lockedTriggers.extend([eval(trig)])

#events which trigger antiforensics whenever they occour.
#E_TEMPERATURE and E_INTRUSION will still only trigger when locked
alwaysTrigStrs  =  config['TRIGGERS']['alwaystriggers'].split(',')
alwaysTriggers = []
for trig in alwaysTrigStrs:
    alwaysTriggers.extend([eval(trig)])

triggerList = lockedTriggers+alwaysTriggers

#minimum temperature to trigger the E_TEMPERATURE kill switch in degrees C
LOW_TEMP = int(config['TRIGGERS']['LOW_TEMP'])

#The keyboard scan codes of the keyboard combination to trigger the
#E_KILL_SWITCH event
triggerKeyCombination = config['TRIGGERS']['KBD_KILL_COMBO'].split('+')

import os
kbdDevice = config['TRIGGERS']['KEYBOARD_DEVICE']
for event in os.listdir('/dev/input/by-id'):
    if event == kbdDevice:
        eventID = os.readlink('/dev/input/by-id/%s'%event).split('/')[1]
        kbdEvent = os.path.join('/dev/input', eventID)
        break
else:
    kbdEvent = None



#shutdown if connection lost while locked
BLUETOOTH_DEVICE_ID = config['TRIGGERS']['BLUETOOTH_DEVICE_ID'] 
PID_FILE = config['TRIGGERS']['PID_FILE'] 

#email details for remote control and reporting
EMAIL_IMAP_HOST = config['EMAIL']['EMAIL_IMAP_HOST']
EMAIL_SMTP_HOST = config['EMAIL']['EMAIL_SMTP_HOST']
EMAIL_USERNAME = config['EMAIL']['EMAIL_USERNAME']
EMAIL_PASSWORD = config['EMAIL']['EMAIL_PASSWORD']

#the number of failed network commands to trigger the killswitch
BAD_COMMAND_LIMIT = config['EMAIL']['BAD_COMMAND_LIMIT']

#send an email to alert the user before killing the system
#useful but makes the shutdown process take longer
emailAlert = config['EMAIL']['EMAIL_ALERT']

emailPicture = config['EMAIL']['email_motion_picture']

#the authentication secret - must be used on the mobile device
HMAC_SECRET = config['EMAIL']['EMAIL_SECRET']

#END USER DEFINED VARIABLES#  
DESKTOP_ENV = config['TRIGGERS']['DESKTOP_ENV']
if DESKTOP_ENV == 'LXDE':
    DBUSSUPPORTED = False
else: DBUSSUPPORTED = True
