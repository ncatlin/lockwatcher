#!/usr/bin/python3
'''
Created on Sep 12, 2013

@author: Nia Catlin

I am bad at Gtk so this is a nightmare to read with all the boxes

todo: need to catch destroy and kill any threads
'''
from gi.repository import Gtk
from gi.repository import GObject
import sensors, socket, subprocess
import re, os 
import string, random

import fileconfig, hardwareconfig
from fileconfig import config

MINFRAMES_TT = 'Consecutive frames of motion to trigger activation.\nLower to increase sensitivity and reaction speed.\nRaise to reduce false positives and improve chance of capturing image of intruder.'
FPS_TT = 'Frames capture per second.\nRaise to improve accuracy.\nLower to improve performance.'

IFPD_CONFIG= '/etc/default/ifplugd'
ROOM_MOTION_CONF = '/etc/motion/motion.conf'
CHASSIS_MOTION_CONF = '/etc/motion2/motion2.conf'
OTHERCMDS_FILE = '/etc/lockwatcher/othercmds.sh'

statelist = Gtk.ListStore(int, str)
statelist.append([1, "Locked"])
statelist.append([2, "Always"])
statelist.append([3, "Never"])
    




class ConfigTab (GObject.GObject):
    name = GObject.property(type=str)
    def __init__(self):
        GObject.GObject.__init__(self)
    def __repr__(self):
        return "%s" % (self.get_property("name"))


def getMotionVariable(file,var):
    motconf = open(file,'r')
    for line in motconf.readlines():
        x = re.search('(^%s.*$)'%var,line)
        if x != None:
            return line.split(' ')[1].strip()
    else:
        return ''
    
settingList = ["Status",
               "Bluetooth Triggers",
               "Motion Triggers",
               "Keyboard Triggers",
               "Network Triggers",
               "Chassis Triggers", 
               "Email Settings",
               "Shutdown Actions",
               "Other Settings"]
'''
todo: add shutdown actions- truecrypt, custom(wait x seconds or inf for completion)
'''
class MainWindow(Gtk.Window):
    def __init__(self, *args, **kwargs):
        Gtk.Window.__init__(self, *args, **kwargs)
        self.set_title("Lockwatcher configuration")
        self.set_size_request(200, 400)
        self.connect("destroy", Gtk.main_quit)
        self.create_widgets()
        self.set_border_width(10)
        
        for name in settingList:
            t = ConfigTab()
            t.name = name
            self.treestore.append(None, (t,))
            
        self.show_all()
        
    def create_widgets(self):
        self.treestore = Gtk.TreeStore(ConfigTab.__gtype__)
        self.treeview = Gtk.TreeView()
        self.treeview.set_model(self.treestore)
        column = Gtk.TreeViewColumn("Settings")

        cell = Gtk.CellRendererText()
        column.pack_start(cell, True)

        column.set_cell_data_func(cell, self.get_name)

        self.treeview.append_column(column)
        windowBox = Gtk.VBox(orientation =Gtk.Orientation.HORIZONTAL)
        self.add(windowBox)
        windowBox.pack_start(self.treeview, True, True, 0)
        select = self.treeview.get_selection()
        select.connect("changed", self.retrieve_element)
        
        self.configBox = None
        self.windowBox = windowBox
        self.DevIDDict = {}
        
    def get_name(self, column, cell, model, iter, data):
        cell.set_property('text', self.treestore.get_value(iter, 0).name)
        
    def retrieve_element(self, widget):
        model, treeiter = self.treeview.get_selection().get_selected()
        if treeiter:
            selection = model[treeiter][0].name
        
        if self.configBox != None:
            self.configBox.destroy()

        configItemsBox = Gtk.VBox(spacing = 8)

        self.configBox = configItemsBox
        self.configBox.set_size_request(400, 400)
        self.windowBox.pack_start(configItemsBox, True, True, 8)
        
        if selection == 'Bluetooth Triggers':
            self.createBTBox()
        elif selection == 'Keyboard Triggers':
            self.createKeyboardBox()
        elif selection == "Motion Triggers":
            self.createMotionBox()
        elif selection == "Chassis Triggers":
            self.createChassisBox()
        elif selection == "Network Triggers":
            self.createNetworkBox()    
        elif selection == "Email Settings":
            self.createEmailBox()
        elif selection == "Shutdown Actions":
            self.createShutdownBox()
        elif selection == "Status":
            self.createStatusBox()
        elif selection == "Other Settings":
            self.createOtherBox()
        self.show_all()
    
    def createOtherBox(self):
        
        settingsBox = Gtk.VBox()
        self.configBox.add(settingsBox)
                
        deskEnv_TT = "The value of the users XDG_CURRENT_DESKTOP enviromental variable, required to handle screen locking.\nRun 'env' without root to find it."
        boxdeskEnv = Gtk.HBox()
        settingsBox.pack_start(boxdeskEnv, False, False, 0)
        boxdeskEnv.set_tooltip_text(deskEnv_TT)
        deskEnvL = Gtk.Label('The desktop environment:')
        boxdeskEnv.pack_start(deskEnvL, False, False, 0)
        deskEnvE = Gtk.Entry()
        deskEnvE.set_name('desktop_env')
        deskEnvE.set_text(config['TRIGGERS']['DESKTOP_ENV'])
        deskEnvE.connect('changed',fileconfig.entryChanged)
        boxdeskEnv.pack_start(deskEnvE, False, False, 0)
        
        boxBaseDir = Gtk.VBox()
        settingsBox.pack_start(boxBaseDir, False, False, 14)
        baseDir_TT = "Base directory of lockwatcher.py"
        boxBaseDir.set_tooltip_text(baseDir_TT)
        baseDirL = Gtk.Label('Lockwatcher.py location')
        boxBaseDir.pack_start(baseDirL, False, False, 0)
        
        fileEntryBox = Gtk.HBox()
        boxBaseDir.pack_start(fileEntryBox, False, False, 0)
        self.baseDirE = Gtk.Entry()
        self.baseDirE.set_name('base_dir')
        self.baseDirE.set_text(config['TRIGGERS']['BASE_DIR'])
        self.baseDirE.connect('changed',fileconfig.entryChanged)
        fileEntryBox.pack_start(self.baseDirE, True, True, 0)
        
        filechooserbutton = Gtk.FileChooserButton('Select a File')
        filechooserbutton.set_action(Gtk.FileChooserAction.SELECT_FOLDER)
        fileEntryBox.pack_start(filechooserbutton, False, False, 0)
        filechooserbutton.connect('file-set',self.chosenDir)
    
    def chosenDir(self,filediag):
        print('setting to',filediag.get_uri())
        self.baseDirE.set_text(filediag.get_uri())
        
        
    def createStatusBox(self):
        warnLab = Gtk.Label('Note: Disable Lockwatcher while altering its configuration')
        self.configBox.add(warnLab)
        
        if os.path.exists('/var/tmp/trigpid'):
           warnLab = Gtk.Label('Running')
           self.configBox.add(warnLab) 
        else:
            warnLab = Gtk.Label('Not running')
            self.configBox.add(warnLab) 
        
    def createShutdownBox(self):
        
        emailBox = Gtk.VBox()
        self.configBox.pack_start(emailBox, False, False, 0)
        SA_TT = 'Configure shutdown alerts in the Email Settings section'
        IC_TT = 'Configure image capture emails in the Motion Triggers section.'
        emailBox.set_tooltip_text(SA_TT+'\n'+IC_TT)
        if config['EMAIL']['email_alert'] == 'True': emStatus = 'enabled'
        else: emStatus = 'disabled'  
        sendAlertL = Gtk.Label()
        sendAlertL.set_text('Email shutdown alerts: %s'%emStatus)
        emailBox.add(sendAlertL)

        sendPictureL = Gtk.Label()
        if config['EMAIL']['email_motion_picture'] == 'True': picStatus = 'enabled'
        else: picStatus = 'disabled'  
        sendPictureL.set_text('Image capture emails: %s'%picStatus)
        emailBox.add(sendPictureL)      
        
        tcCheck = Gtk.CheckButton("Dismount Truecrypt volumes")
        if config['TRIGGERS']['dismount_tc'] == 'True':
            tcCheck.set_active(True)
        else:
            tcCheck.set_active(False)
        tcCheck.set_name('dismount_tc')
        tcCheck.connect('toggled',fileconfig.checkBtnChanged)
        self.configBox.pack_start(tcCheck, False, False, 0)    
        
        CVFrame = Gtk.Frame()
        CVBox = Gtk.VBox()
        CVFrame.add(CVBox)
        CVBox.set_tooltip_text('All volumes with a name containing the specified label will be dismounted')
        self.configBox.pack_start(CVFrame, False, False, 0) 
        cryptVolCheck = Gtk.CheckButton("Dismount dm-crypt/LUKS volumes")
        if config['TRIGGERS']['dismount_crypt'] == 'True':
            cryptVolCheck.set_active(True)
        else:
            cryptVolCheck.set_active(False)
        cryptVolCheck.set_name('dismount_crypt')
        cryptVolCheck.connect('toggled',fileconfig.checkBtnChanged)
        CVBox.pack_start(cryptVolCheck, False, False, 0)  
        
        CVLabelBox = Gtk.HBox()
        CVBox.add(CVLabelBox)
        cryptVolWordL = Gtk.Label('Volume label to dismount:')
        CVLabelBox.pack_start(cryptVolWordL, False, False, 0)  
        cryptVolWordE = Gtk.Entry()
        cryptVolWordE.set_text(config['TRIGGERS']['cryptlabel'])
        CVLabelBox.pack_start(cryptVolWordE, False, False, 0) 
        
        customBox = Gtk.VBox()
        self.configBox.add(customBox)
        shellCheck = Gtk.CheckButton("Execute custom shellscript")
        if config['TRIGGERS']['exec_shellscript'] == 'True':
            shellCheck.set_active(True)
        else:
            shellCheck.set_active(False)
        customBox.pack_start(shellCheck, False, True, 0)
        
        scrolledwindow = Gtk.ScrolledWindow()
        scrolledwindow.set_hexpand(True)
        scrolledwindow.set_vexpand(True)

        textview = Gtk.TextView()
        self.cmdtext = textview.get_buffer()
        fd = open(OTHERCMDS_FILE,'r')
        self.cmdtext.set_text(fd.read())
        fd.close()
        
        scrolledwindow.add(textview)
        customBox.pack_start(scrolledwindow, False, True, 0)
        saveBtn = Gtk.Button('Save')
        customBox.pack_start(saveBtn, False, True, 0)
        saveBtn.connect('clicked',self.saveOtherCmds)
        
    def saveOtherCmds(self,btn):
        start,end = self.cmdtext.get_bounds()
        fd = open(OTHERCMDS_FILE,'w')
        fd.write(self.cmdtext.get_text(start,end,False))
        fd.close()
        
    def createMotionBox(self):
        cameraDetails = hardwareconfig.getCamNames()
        
        devList = sorted(cameraDetails.keys())
        devListStore = Gtk.ListStore(str)
        devListStore.append([''])
        for dev in devList:
            devListStore.append([dev])
        
        camLookup = {}
        for idx,dev in enumerate(devList):
            camLookup[dev] = idx+1
        
        model = Gtk.ListStore(str)
        self.camList = model

        for dev,details in cameraDetails.items():
            devString = "%s - (%s) %s"%(dev,details['ID_VENDOR'],details['ID_MODEL'])
            self.camList.append([devString])

        treeView = Gtk.TreeView(model)
        combo_cell_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Cameras connected", combo_cell_text, text=0)
        treeView.append_column(column_text)
        #treeView.set_size_request(100, 100)
        self.configBox.add(treeView)
        
        roomFrame = Gtk.Frame()
        self.configBox.add(roomFrame)
        
        roomCamDev = getMotionVariable(ROOM_MOTION_CONF,'videodevice')
        
        boxRoomAll = Gtk.VBox()
        roomFrame.add(boxRoomAll)
        boxR = Gtk.HBox()
        boxRoomAll.add(boxR)
        roomCam = Gtk.Label('Room monitoring camera:')
        boxR.pack_start(roomCam, True, True, 0)
        
        room_combo = Gtk.ComboBox.new_with_model_and_entry(devListStore)
        self.roomCombo = room_combo
        room_combo.set_entry_text_column(0)
        room_combo.set_active(camLookup[roomCamDev])
        room_combo.set_name('RoomCam')
        room_combo.connect("changed", self.videoDevChange)
        boxR.pack_start(room_combo, True, True, 0)
        
        boxMinFrames = Gtk.HBox()
        boxRoomAll.add(boxMinFrames)
        boxMinFrames.set_tooltip_text(MINFRAMES_TT)
        motionTimeL = Gtk.Label('Minimum motion frames:')
        boxMinFrames.pack_start(motionTimeL, True, True, 0)
        motionTimeE = Gtk.Entry()
        motionTimeE.set_name('MinFrames-R')
        motionTimeE.set_text(getMotionVariable(ROOM_MOTION_CONF,'minimum_motion_frames'))
        motionTimeE.connect('changed',self.motionEntryChange)
        boxMinFrames.pack_start(motionTimeE, True, True, 0)
        
        boxFPS = Gtk.HBox()
        boxFPS.set_tooltip_text(FPS_TT)
        boxRoomAll.add(boxFPS)
        FPSL = Gtk.Label('Camera Framerate:')
        boxFPS.pack_start(FPSL, True, True, 0)
        FPSE = Gtk.Entry()
        FPSE.set_name('FPS-R')
        FPSE.set_text(getMotionVariable(ROOM_MOTION_CONF,'framerate'))
        FPSE.connect('changed',self.motionEntryChange)
        boxFPS.pack_start(FPSE, True, True, 0)
        
        boxTol_TT='Number of changed pixels to signify motion.\nLower to improve sensitivity. Raise to reduced false positives.'
        boxTolerance = Gtk.HBox()
        boxTolerance.set_tooltip_text(boxTol_TT)
        boxRoomAll.add(boxTolerance)
        tolLabel = Gtk.Label('Pixel Change Threshold:')
        boxTolerance.pack_start(tolLabel, True, True, 0)
        tolEntry = Gtk.Entry()
        tolEntry.set_name('tol-R')
        tolEntry.set_text(getMotionVariable(ROOM_MOTION_CONF,'threshold'))
        tolEntry.connect('changed',self.motionEntryChange)
        boxTolerance.pack_start(tolEntry, True, True, 0)
        
        sendImgBox = Gtk.HBox()
        sendImgBox.set_tooltip_text('Allows remote assessment of intruder but may delay shutdown by several seconds')
        boxRoomAll.add(sendImgBox)
        sendImgCheck = Gtk.CheckButton('Email Image on activation')
        doSave = getMotionVariable(ROOM_MOTION_CONF,'on_picture_save')
        sendImgCheck.set_active(doSave != '')
        sendImgCheck.connect('toggled',self.togglePictureEmail)
        sendImgBox.pack_start(sendImgCheck, True, True, 0)
        
        chassisFrame = Gtk.Frame()
        self.configBox.pack_start(chassisFrame, False, False, 0)
        boxChassisAll = Gtk.VBox()
        chassisFrame.add(boxChassisAll)
        
        boxC = Gtk.HBox()
        boxChassisAll.add(boxC)
        chassisCam = Gtk.Label('Chassis monitoring camera:')
        boxC.pack_start(chassisCam, True, True, 0)
        
        chassis_combo = Gtk.ComboBox.new_with_model_and_entry(devListStore)
        self.chassisCombo = chassis_combo
        chassis_combo.set_entry_text_column(0)
        chassisCamDev = getMotionVariable(CHASSIS_MOTION_CONF,'videodevice')
        chassis_combo.set_active(camLookup[chassisCamDev])
        chassis_combo.set_name('ChassisCam')
        chassis_combo.connect("changed", self.videoDevChange)
        boxC.pack_start(chassis_combo, True, True, 0)
        

        
        boxMinFrames = Gtk.HBox()
        boxChassisAll.add(boxMinFrames)
        boxMinFrames.set_tooltip_text(MINFRAMES_TT)
        
        motionTimeL = Gtk.Label('Minimum motion frames:')
        boxMinFrames.pack_start(motionTimeL, True, True, 0)
        motionTimeE = Gtk.Entry()
        motionTimeE.set_name('MinFrames-C')
        motionTimeE.set_text(getMotionVariable(CHASSIS_MOTION_CONF,'minimum_motion_frames'))
        motionTimeE.connect('changed',self.motionEntryChange)
        boxMinFrames.pack_start(motionTimeE, True, True, 0)
        
        boxFPS = Gtk.HBox()
        boxFPS.set_tooltip_text(FPS_TT)
        boxChassisAll.add(boxFPS)
        FPSL = Gtk.Label('Camera Framerate:')
        boxFPS.pack_start(FPSL, True, True, 0)
        FPSE = Gtk.Entry()
        FPSE.set_name('FPS-C')
        FPSE.set_text(getMotionVariable(CHASSIS_MOTION_CONF,'framerate'))
        FPSE.connect('changed',self.motionEntryChange)
        boxFPS.pack_start(FPSE, True, True, 0)
        
        boxTolerance = Gtk.HBox()
        boxTolerance.set_tooltip_text(boxTol_TT)
        boxChassisAll.add(boxTolerance)
        tolLabel = Gtk.Label('Pixel Change Threshold:')
        boxTolerance.pack_start(tolLabel, True, True, 0)
        tolEntry = Gtk.Entry()
        tolEntry.set_name('tol-C')
        tolEntry.set_text(getMotionVariable(CHASSIS_MOTION_CONF,'threshold'))
        tolEntry.connect('changed',self.motionEntryChange)
        boxTolerance.pack_start(tolEntry, True, True, 0)
        
        
        reloadBtn = Gtk.Button('Apply Camera Settings')
        self.configBox.add(reloadBtn)
        reloadBtn.connect('clicked',hardwareconfig.reloadCameras)
    
    #choose whether to trigger before or after a camera capture has been saved
    def togglePictureEmail(self,toggle):
        if toggle.get_active() == True:
            config['EMAIL']['email_motion_picture'] = 'True'
            fileconfig.writeMotionConfig(ROOM_MOTION_CONF,'on_picture_save','"kill -s HUP `cat /var/tmp/trigpid`"')
            fileconfig.writeMotionConfig(ROOM_MOTION_CONF,'on_motion_detected','none')
        else:
            config['EMAIL']['email_motion_picture'] = 'False'
            fileconfig.writeMotionConfig(ROOM_MOTION_CONF,'on_picture_save','none')
            fileconfig.writeMotionConfig(ROOM_MOTION_CONF,'on_motion_detected','"kill -s HUP `cat /var/tmp/trigpid`"')
            
        fileconfig.writeConfig()   
        
    
    def videoDevChange(self,combo):
        if combo.get_active_iter() != None:
            newDev = combo.get_model()[combo.get_active_iter()][0]

            
        print("changing %s to %s"%(combo.get_name(),newDev))
        
        if combo.get_name() == 'RoomCam':
            fileconfig.writeMotionConfig('/tmp/motion.conf','videodevice',newDev)
            
            chassisDev = self.chassisCombo.get_model()[self.chassisCombo.get_active_iter()][0]
            if newDev == chassisDev:
                self.chassisCombo.set_active(0)
                print("setting chassis to none")
        else:
            fileconfig.writeMotionConfig('/tmp/motion2.conf','videodevice',newDev)
            
            roomDev = self.roomCombo.get_model()[self.roomCombo.get_active_iter()][0]
            if newDev == roomDev:
                self.roomCombo.set_active(0)
                print("setting room to none")
    
    def motionEntryChange(self,entry):
        entryName = entry.get_name()
        var, cam = entryName.split('-')
        
        if cam == 'R':
            file = ROOM_MOTION_CONF
        elif cam == 'C':
            file = CHASSIS_MOTION_CONF
            
        value = entry.get_text()
        if var == 'MinFrames': 
            fileconfig.writeMotionConfig(file,'minimum_motion_frames',value)
        elif var == 'FPS':
            fileconfig.writeMotionConfig(file,'framerate',value)
        elif var == 'tol':
            fileconfig.writeMotionConfig(file,'threshold',value)
        
        
        
        
    def createEmailBox(self):
        box6 = Gtk.VBox()
        self.configBox.pack_start(box6, False, False, 0)
        
        checkEmailCMD = Gtk.CheckButton("Enable Remote Control")
        checkEmailCMD.set_name('enable_remote')
        checkEmailCMD.set_tooltip_text('Lockwatcher will check the specified IMAP inbox for remote commands')
        checkEmailCMD.set_active(config['EMAIL']['enable_remote'])
        checkEmailCMD.connect('toggled',fileconfig.checkBtnChanged)
        box6.pack_start(checkEmailCMD, True, True, 0)
        
        checkEmailSend = Gtk.CheckButton("Send Shutdown Alerts")
        checkEmailSend.set_name('enable_alerts')
        checkEmailSend.set_tooltip_text('When an emergency shutdown is triggered, Lockwatcher will send an alert by email.')
        checkEmailSend.set_active(config['EMAIL']['email_alert'])
        checkEmailSend.connect('toggled',fileconfig.checkBtnChanged)
        box6.pack_start(checkEmailSend, True, True, 0)
        
        box1 = Gtk.HBox()
        self.configBox.pack_start(box1, False, False, 0)
        IMAPServerL = Gtk.Label('IMAP Server:')
        box1.pack_start(IMAPServerL, True, True, 0)
        IMAPServerE = Gtk.Entry()
        IMAPServerE.set_name('email_imap_host')
        IMAPServerE.set_text(config['EMAIL']['EMAIL_IMAP_HOST'])
        IMAPServerE.connect('changed',fileconfig.entryChanged)
        box1.pack_start(IMAPServerE, True, True, 0)
        
        boxCR = Gtk.HBox()
        boxCR.set_tooltip_text('The email address corresponding to the IMAP account. Often the same as the username.')
        self.configBox.pack_start(boxCR, False, False, 0)
        comRecL = Gtk.Label('IMAP Email Address:')
        boxCR.pack_start(comRecL, True, True, 0)
        comRecE = Gtk.Entry()
        comRecE.set_name('command_email_address')
        comRecE.set_text(config['EMAIL']['COMMAND_EMAIL_ADDRESS'])
        comRecE.connect('changed',fileconfig.entryChanged)
        boxCR.pack_start(comRecE, True, True, 0)
        
        box2 = Gtk.HBox()
        self.configBox.pack_start(box2, False, False, 0)
        SMTPServerL = Gtk.Label('SMTP Server:')
        box2.pack_start(SMTPServerL, True, True, 0)
        SMTPServerE = Gtk.Entry()
        SMTPServerE.set_name('email_smtp_host')
        SMTPServerE.set_text(config['EMAIL']['EMAIL_SMTP_HOST'])
        SMTPServerE.connect('changed',fileconfig.entryChanged)
        box2.pack_start(SMTPServerE, True, True, 0)
        
        box3 = Gtk.HBox()
        self.configBox.pack_start(box3, False, False, 0)
        unameL = Gtk.Label('Account Username:')
        box3.pack_start(unameL, True, True, 0)
        unameE = Gtk.Entry()
        unameE.set_name('email_username')
        unameE.set_text(config['EMAIL']['EMAIL_USERNAME'])
        unameE.connect('changed',fileconfig.entryChanged)
        box3.pack_start(unameE, True, True, 0)
        
        box4 = Gtk.HBox()
        self.configBox.pack_start(box4, False, False, 0)
        passwordL = Gtk.Label('Account Password:')
        box4.pack_start(passwordL, True, True, 0)
        passwordE = Gtk.Entry()
        passwordE.set_name('email_password')
        passwordE.set_visibility(False)
        passwordE.set_text(config['EMAIL']['EMAIL_PASSWORD'])
        passwordE.connect('changed',fileconfig.entryChanged)
        box4.pack_start(passwordE, True, True, 0)
        
        box4a = Gtk.VBox()
        self.configBox.pack_start(box4a, False, False, 0)
        testSetB = Gtk.Button('Test Settings')
        testSetB.connect('clicked',self.testEmail)
        self.emailTestBtn = testSetB
        box4a.pack_start(testSetB, True, True, 0)
        testSetL = Gtk.Label('')
        self.emailTestLabel = testSetL
        testSetL.set_name('testSettings')
        #passwordE.connect('changed',fileconfig.entryChanged)
        box4a.pack_start(testSetL, True, True, 0)
        
        boxAR = Gtk.HBox()
        boxAR.set_tooltip_text('Lockmonitor will send alerts, command responses and captured images to this email address.')
        self.configBox.pack_start(boxAR, False, False, 0)
        authSecretL = Gtk.Label('Alert Email Address:')
        boxAR.pack_start(authSecretL, True, True, 0)
        alertRecE = Gtk.Entry()
        alertRecE.set_name('alert_email_address')
        alertRecE.set_text(config['EMAIL']['ALERT_EMAIL_ADDRESS'])
        alertRecE.connect('changed',fileconfig.entryChanged)
        boxAR.pack_start(alertRecE, True, True, 0)
        
        box5 = Gtk.HBox()
        box5.set_tooltip_text('Secret code used by Lockwatcher to authenticate remote commands')
        self.configBox.pack_start(box5, False, False, 0)
        authSecretL = Gtk.Label('Authentication Secret:')
        box5.pack_start(authSecretL, True, True, 0)
        authSecretE = Gtk.Entry()
        authSecretE.set_width_chars(10)
        authSecretE.set_name('email_secret')
        authSecretE.set_text(config['EMAIL']['EMAIL_SECRET'])
        self.secretCode = authSecretE
        authSecretE.connect('changed',fileconfig.entryChanged)
        box5.pack_start(authSecretE, True, True, 0)
        genSecretBtn = Gtk.Button('Generate')
        genSecretBtn.connect('clicked',self.genCode)
        box5.pack_start(genSecretBtn, True, True, 0)
        
        
        box7 = Gtk.HBox()
        box7.set_tooltip_text('Number of bad commands to cause an emergency shutdown. 0 to disable.')
        self.configBox.pack_start(box7, False, False, 0)
        numFailedL = Gtk.Label('Failed Command Limit')
        box7.pack_start(numFailedL, True, True, 0)
        numFailedE = Gtk.Entry()
        numFailedE.set_width_chars(5)
        numFailedE.set_name('bad_command_limit')
        numFailedE.set_text(config['EMAIL']['BAD_COMMAND_LIMIT'])
        numFailedE.connect('changed',fileconfig.entryChanged)
        box7.pack_start(numFailedE, True, True, 0)
    
    
    def genCode(self,btn):
        chars = string.ascii_letters + string.digits
        newCode = ''.join(random.choice(chars) for x in range(9))
        self.secretCode.set_text(newCode)
    
    def testEmail(self,btn):
        self.emailThread = hardwareconfig.emailTestThread(self.emailTestResult,config)
        self.emailThread.start()
        btn.set_label('Testing email settings...')
        self.emailTestLabel.set_text('')
        self.emailResults = 0
        
    def emailTestResult(self,resultI,resultS):
        self.emailTestLabel.set_text(resultI+' , '+resultS) 
        self.emailTestBtn.set_label('Test Settings') 
            
    def createBTBox(self):
        BTBox = Gtk.VBox(spacing = 12)
        f = Gtk.Frame(label="Bluetooth device settings")
        f.set_label_align(0.5,0)
        f.add(BTBox)
        self.configBox.add(f)
        
        model = Gtk.ListStore(str,int)
        self.BTDevList = model
        if len(self.DevIDDict.keys()) > 0:
            for idx,dev in self.DevIDDict.items():
                self.BTDevList.append(["Name: %s    ID: %s"%(dev[1],dev[0]),idx])
        else:
            self.BTDevList.append(['No devices scanned',0])
        
        
        
        treeView = Gtk.TreeView(model)
        
        
        combo_cell_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Nearby devices", combo_cell_text, text=0)
        treeView.append_column(column_text)
        treeView.set_size_request(100, 200)
        
        select = treeView.get_selection()
        select.connect("changed", self.BTDevSelect)
        
        BTViewBox = Gtk.VBox()
        BTBox.add(BTViewBox)
        BTViewBox.add(treeView)
        self.BTTree = treeView
        self.show_all()
        
        scanBtnBox = Gtk.HBox()
        BTViewBox.add(scanBtnBox)
        scanBtn = Gtk.Button("Scan for devices")
        scanBtnBox.add(scanBtn)
        scanBtn.connect('clicked',self.BTDoScan)
        #spinner broken https://bugs.launchpad.net/granite/+bug/1020355
        #self.BTSpinner = Gtk.Label()
        #scanBtnBox.add(self.BTSpinner)
        #self.BTSpinner.set_text('Idle')
        self.BTScanBtn = scanBtn
        
        devInfo = Gtk.HBox()
        BTBox.add(devInfo)
        
        devInfoBox = Gtk.VBox()
        devInfo.add(devInfoBox)
        devInfoLabel = Gtk.Label("Current Device")
        devInfoBox.add(devInfoLabel)
        
        
        devInfoID = Gtk.Entry()
        devInfoID.set_text(config['TRIGGERS']['bluetooth_device_id'])
        devInfoID.set_name('bluetooth_device_id')
        devInfoID.connect('changed',fileconfig.entryChanged)
        devInfoBox.add(devInfoID)
        
        devStatusLabel = Gtk.Label("Status: Unknown")
        devInfoBox.add(devStatusLabel)
        self.BTCurrentDevStatus = devStatusLabel
        
        devStatusBox = Gtk.VBox()
        devInfo.add(devStatusBox)
        devStatusButton = Gtk.Button('Test')
        devStatusBox.add(devStatusButton) 
        devStatusButton.connect('clicked',self.BTDevTest) 
        
        triggerBox = Gtk.VBox()
        BTBox.add(triggerBox)
        
        BTTrigLabel = Gtk.Label("Triggers when:")
        triggerBox.pack_start(BTTrigLabel, True, True, 0)
        name_combo = Gtk.ComboBox.new_with_model_and_entry(statelist)
        name_combo.set_entry_text_column(1)
        if 'E_BLUETOOTH' in config['TRIGGERS']['lockedtriggers'].split(','):
            trigStatus = fileconfig.TRIG_LOCKED
        elif 'E_BLUETOOTH' in config['TRIGGERS']['alwaystriggers'].split(','):
            trigStatus = fileconfig.TRIG_ALWAYS
        else: trigStatus = fileconfig.TRIG_NEVER
        name_combo.set_active(trigStatus)
        name_combo.set_title('E_BLUETOOTH')
        name_combo.connect("changed", fileconfig.trigStateChange)
        triggerBox.pack_start(name_combo, True, True, 0)
        
    def BTDevTest(self,btn):
        print("Testing ",self.BTCurrentDev.get_text())
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            s.settimeout(25)
            s.connect((self.BTCurrentDev.get_text(),2))
        except ConnectionRefusedError:
            self.BTCurrentDevStatus.set_label("Status: Connection refused")
            return False
        except OSError:
            self.BTCurrentDevStatus.set_label("Status: Not Found")
            return False
        except:
            self.BTCurrentDevStatus.set_label("Status: Unavailable/Unauthorised")
            return False
        self.BTCurrentDevStatus.set_label("Status: OK")
        
    def BTDoScan(self,blah):
        print("launching scan thread")
        self.DevIDDict = {}
        self.BTScanBtn.set_label('Scanning...')
        self.BTScan = hardwareconfig.BTScanThread(self.BTGotDevices)
        self.BTScan.start()
        print("Scan thread launched")

             
    def BTGotDevices(self,out):
        self.BTScanBtn.set_label('Scan for devices')
        results = str(out).split('\\n')
        BTList = []
        for line in results:
            line = line.strip('\\t')
            listEntry = line.split('\\t')
            if len(listEntry) != 2: continue
            BTList = BTList + [listEntry]
                
        self.BTDevList.clear()
        if len(BTList) == 0:
            self.BTDevList.append(['No results',0])
            
        i = 0
        for dev in BTList:
            self.BTDevList.append(["Name: %s    ID: %s"%(dev[1],dev[0]),i])
            self.DevIDDict[i] = dev
            i += 1
    
    def BTDevSelect(self,item):
        model, treeiter = self.BTTree.get_selection().get_selected()
        if treeiter:
            devString = model[treeiter][0]
            devIDX = model[treeiter][1]
            print ("You selected", devString)
            self.BTCurrentDev.set_text(self.DevIDDict[devIDX][0]) 

    def createKeyboardBox(self):
        label = Gtk.Label("Keyboard Settings")
        #label.set_justify(Gtk.Justification.TOP)
        self.configBox.pack_start(label, True, True, 0)    
        
        
        
        model = Gtk.ListStore(str,str)
        treeView = Gtk.TreeView(model)
        combo_cell_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Select keyboard device to monitor", combo_cell_text, text=0)
        treeView.append_column(column_text)
        treeView.set_size_request(100, 150)
        self.kbdTree = treeView
        treeView.set_enable_search(False)
        
        currentDevice = config['TRIGGERS']['keyboard_device']
        
        select = treeView.get_selection()
        
        self.kbdThread = None
        eventIdx = 0
        for event in os.listdir('/dev/input/by-id'):
            if 'kbd' in event:
                eventID = os.readlink('/dev/input/by-id/%s'%event).split('/')[1]
                model.append(["%s -> %s"%(event,eventID),eventID])
                if event == currentDevice:
                    select.select_path(Gtk.TreePath([eventIdx]))
                    self.kbdDevSelect(select)
                eventIdx += 1
        
        self.configBox.add(treeView)
        select.connect("changed", self.kbdDevSelect)
        
        showKeysBox = Gtk.Entry()
        self.configBox.add(showKeysBox)
        if os.geteuid() == 0:
            showKeysBox.set_text('Captured keystrokes appear here')
        else:
            showKeysBox.set_text('Captured keystrokes appear here (requires root)')
            
        showKeysBox.set_editable(False)
        self.kbdEntry = showKeysBox
        
        KSCBox = Gtk.HBox() 
        self.configBox.add(KSCBox)
        KSLLabel = Gtk.Label('Current Killswitch Key Combination:')
        KSCBox.pack_start(KSLLabel, True, True, 0)
        KSLabel = Gtk.Label()
        KSLabel.set_text(config['TRIGGERS']['kbd_kill_combo'])
        self.keyComboLabel = KSLabel
        KSCBox.pack_start(KSLabel, True, True, 0)
        
        KSRecordBtn = Gtk.Button('Record Key Combination')
        self.configBox.add(KSRecordBtn)
        KSRecordBtn.connect('clicked',self.recordKbd)
        self.kbdRecordBtn = KSRecordBtn
        self.kbdRecording = False
        
        trigBox = Gtk.VBox()
        self.configBox.add(trigBox)
        trigLabel = Gtk.Label("Triggers when:")
        trigBox.pack_start(trigLabel, True, True, 0)
        name_combo = Gtk.ComboBox.new_with_model_and_entry(statelist)
        name_combo.set_entry_text_column(1)
        if 'E_KILL_SWITCH' in config['TRIGGERS']['lockedtriggers'].split(','):
            trigStatus = fileconfig.TRIG_LOCKED
        elif 'E_KILL_SWITCH' in config['TRIGGERS']['alwaystriggers'].split(','):
            trigStatus = fileconfig.TRIG_ALWAYS
        else: trigStatus = fileconfig.TRIG_NEVER
        name_combo.set_active(trigStatus)
        name_combo.set_title('E_KILL_SWITCH') #todo: change to e_network
        name_combo.connect("changed", fileconfig.trigStateChange)
        trigBox.pack_start(name_combo, True, True, 0)
    
    def kbdDevSelect(self,select):
        if self.kbdThread != None:
            self.kbdThread.terminate()
            
        model, treeiter = self.kbdTree.get_selection().get_selected()
        if treeiter:
            devPath = "/dev/input/%s"%model[treeiter][1]
            device = "/dev/input/%s"%model[treeiter][0]
            print('spawning thread on ',devPath)
            self.startKbdListen(devPath)
        self.set_focus(None)
        
        config['TRIGGERS']['keyboard_device'] = model[treeiter][0].split(' ')[0]
        fileconfig.writeConfig()
            
    def recordKbd(self,button):
        if self.kbdRecording == False:
            self.kbdRecording = True
            self.set_focus(None)
            self.kbdEntry.set_text('')
            self.kbdRecordBtn.set_label('Save this key combination...')
        else:
            self.kbdRecording = False
            newCombo = self.kbdEntry.get_text()
            self.keyComboLabel.set_text(newCombo)
            config['TRIGGERS']['kbd_kill_combo'] = newCombo
            fileconfig.writeConfig()
            self.kbdRecordBtn.set_label('Record New Key Combination')
        
    def startKbdListen(self,event):
        self.kbdThread = hardwareconfig.kbdListenThread(self.gotKbdKey,event)
        self.kbdThread.start()
    
    def gotKbdKey(self,kCode):
        text = self.kbdEntry.get_text()
        if 'appear' in text or len(text)>30 or len(text)==0:
            text = str(kCode)
        else:
            text = text+'+'+str(kCode)    
        self.kbdEntry.set_text(text)

    def createNetworkBox(self):

        
        if os.access(IFPD_CONFIG, os.W_OK):
            label = Gtk.Label("ifplugd network monitoring daemon status")
            self.configBox.pack_start(label, True, True, 0)  
        else:
            labelWarn = Gtk.Label("ifplugd network monitoring daemon status\n(do not have permissions to modify monitored interfaces)")
            self.configBox.pack_start(labelWarn, True, True, 0)  
            
        #label.set_justify(Gtk.Justification.TOP)
         
        
        #get the current ifplugd interfaces from its config file
        fd = open(IFPD_CONFIG,'r')
        text = fd.readlines()
        fd.close()
        currentIfaces = []
        for line in text:
            if 'INTERFACES=' in line:
                #covnerts INTERFACES="eth0,eth1" to ['eth0','eth1']
                interfaces = line.strip().replace('=',' ').replace('"','').split(' ')[1].split(',')
                if interfaces != ['']:
                    currentIfaces.extend(interfaces)
        
        scanprocess = subprocess.Popen(['/usr/sbin/ifplugstatus'], stdout=subprocess.PIPE)
        if scanprocess == []:
            print("Couldn't find ifplugstatus?")
            return None
        else:
            out, err = scanprocess.communicate(timeout=6)
            devString = out.decode("utf-8").strip('\n').split('\n')
            deviceList = []
            for dev in devString:
                deviceList.append(dev.split(': '))
                
        model = Gtk.ListStore(str)
        treeView = Gtk.TreeView(model)
        combo_cell_text = Gtk.CellRendererText()
        column_text = Gtk.TreeViewColumn("Available interfaces (Highlighted = Monitored)", combo_cell_text, text=0)
        treeView.append_column(column_text)
        treeView.set_size_request(100, 150)
        
        select = treeView.get_selection()
        select.set_mode(Gtk.SelectionMode.MULTIPLE)
        self.show_all()
        
        pathIdx = 0
        if len(devString) > 0:
            for dev in deviceList:
                model.append(["%s (%s)"%(dev[0],dev[1])])
                if dev[0] in currentIfaces:
                    select.select_path(Gtk.TreePath([pathIdx]))
                pathIdx += 1
                    
            
        else:
            model.append(['No network interfaces found'])
            
        
        select.connect("changed", self.netIFSelect)
        
        self.configBox.add(treeView)
        
        trigBox = Gtk.VBox()
        self.configBox.add(trigBox)
        
        trigLabel = Gtk.Label("Triggers when:")
        trigBox.pack_start(trigLabel, True, True, 0)
        name_combo = Gtk.ComboBox.new_with_model_and_entry(statelist)
        name_combo.set_entry_text_column(1)
        if 'E_NETCABLE' in config['TRIGGERS']['lockedtriggers'].split(','):
            trigStatus = fileconfig.TRIG_LOCKED
        elif 'E_NETCABLE' in config['TRIGGERS']['alwaystriggers'].split(','):
            trigStatus = fileconfig.TRIG_ALWAYS
        else: trigStatus = fileconfig.TRIG_NEVER
        name_combo.set_active(trigStatus)
        name_combo.set_title('E_NETCABLE') #todo: change to e_network
        name_combo.connect("changed", fileconfig.trigStateChange)
        trigBox.pack_start(name_combo, True, True, 0)

        
    def netIFSelect(self,selection):
        model, paths = selection.get_selected_rows()
        ssIFs = ''
        for path in paths:
            val=model.get_value(model.get_iter(path),0)
            interface = val.split(' ')[0]
            ssIFs = ssIFs + interface+','
            
        selectionstring = 'INTERFACES="%s"'%ssIFs.strip(',')
        print(selectionstring)
        
        
        #place into file
        fd = open(IFPD_CONFIG,'r')
        text = fd.read()
        fd.close()
        x,y = re.search('(^INTERFACES.*$)',text,re.MULTILINE).span(1)
            
        try:
            fd = open(IFPD_CONFIG,'w')
            fd.write(text[:x]+selectionstring+text[y:])
            fd.close()
        except:
            print("cant edit config file ",IFPD_CONFIG)
        
    def createChassisBox(self):  

        #intrusion switch panel
        ISwitchBox = Gtk.VBox(spacing = 12)
        ISwitchBox.set_size_request(50, 50)
        f = Gtk.Frame(label="Chassis Intrusion Switch")
        f.add(ISwitchBox)
        self.configBox.add(f)
        
        intrusionSwitchPath = '/sys/class/hwmon/hwmon*/device/intrusion0_alarm'
        try:
            fd = open(intrusionSwitchPath,'r')
            status = fd.read()
            fd.close()
            label = Gtk.Label("Intrusion Switch Status: %s"%status)
            ISwitchBox.pack_start(label, False, False, 12)
        except:
            label = Gtk.Label("No intrusion switch detected")
            ISwitchBox.pack_start(label, False, False, 4)
            
            ISButtons = Gtk.HBox()
            ISwitchBox.add(ISButtons)
            
            butanBox = Gtk.VBox()
            alabel = Gtk.Label("")
            butanBox.pack_start(alabel, False, False, 0)
            
            butan = Gtk.Button("Reset status")
            butanBox.pack_start(butan, False, False, 0)
            ISButtons.add(butanBox)
            
            switchTrigBox = Gtk.VBox()
                  
            resetSwitchLabel = Gtk.Label("Triggers when:")
            switchTrigBox.pack_start(resetSwitchLabel, False, False, 0)
        
            name_combo = Gtk.ComboBox.new_with_model_and_entry(statelist)
            name_combo.set_entry_text_column(1)
            
            if 'E_INTRUSION' in config['TRIGGERS']['lockedtriggers'].split(','):
                trigStatus = fileconfig.TRIG_LOCKED
            elif 'E_INTRUSION' in config['TRIGGERS']['alwaystriggers'].split(','):
                trigStatus = fileconfig.TRIG_ALWAYS
            else: trigStatus = fileconfig.TRIG_NEVER
            name_combo.set_active(trigStatus)
            name_combo.set_title('E_INTRUSION')
            name_combo.connect("changed", fileconfig.trigStateChange)
            switchTrigBox.pack_start(name_combo, False, False, 0)
            
            ISButtons.add(switchTrigBox)
        #motherboard temperature panel
        TempPanel = Gtk.VBox(spacing = 12)
        TempPanel.set_size_request(50, 50)
        f = Gtk.Frame(label="Motherboard Temperature")
        f.add(TempPanel)
        self.configBox.add(f)
        
        #current temperature label
        for chip in sensors.get_detected_chips():
            if "acpi" in str(chip): break
        else:
            print("Could not read acpi bus: Temperature monitoring disabled")
            return
        self.chip = chip
            
        for feature in chip.get_features():
            if 'Temperature' in str(feature): break
        for subfeature in chip.get_all_subfeatures(feature):
            if 'input' in str(subfeature.name):break
        self.subfeature = subfeature    
        newTemp = self.chip.get_value(self.subfeature.number)
        
        label = Gtk.Label("Current Temperature: %s"%newTemp)
        TempPanel.pack_start(label, False, False, 8) 
        
        TempButtons = Gtk.HBox()
        TempPanel.add(TempButtons)
        TempEntryBox = Gtk.VBox()
        TempButtons.add(TempEntryBox)
        
        tempEntryLabel = Gtk.Label("Trigger Temperature (°C)")
        TempEntryBox.pack_start(tempEntryLabel, False, False, 0)
        
        tempentry = Gtk.Entry()
        tempentry.set_name('low_temp')
        tempentry.set_text(config['TRIGGERS']['LOW_TEMP'])
        tempentry.connect('changed',fileconfig.entryChanged)
        TempEntryBox.pack_start(tempentry, False, False, 0)
        
        TempTrigBox = Gtk.VBox()
        TempButtons.add(TempTrigBox)
        
        tempTrigLabel = Gtk.Label("Triggers when:")
        TempTrigBox.pack_start(tempTrigLabel, False, False, 0)

        name_combo = Gtk.ComboBox.new_with_model_and_entry(statelist)
        name_combo.set_entry_text_column(1)
        
        if 'E_TEMPERATURE' in config['TRIGGERS']['lockedtriggers'].split(','):
            trigStatus = fileconfig.TRIG_LOCKED
        elif 'E_TEMPERATURE' in config['TRIGGERS']['alwaystriggers'].split(','):
            trigStatus = fileconfig.TRIG_ALWAYS
        else: trigStatus = fileconfig.TRIG_NEVER
        name_combo.set_active(trigStatus)
        name_combo.set_title('E_TEMPERATURE')
        name_combo.connect("changed", fileconfig.trigStateChange)
        TempTrigBox.pack_start(name_combo, False, False, 0)
        
        #RAM temperature box
        TempPanel2 = Gtk.VBox(spacing = 12)
        f = Gtk.Frame(label="RAM Temperature")
        f.add(TempPanel2)
        self.configBox.add(f)
        
        label = Gtk.Label("Current Temperature: %s"%"Not implemented")
        TempPanel2.pack_start(label, False, False, 8) 

GObject.threads_init()     
win = MainWindow()
win.connect("delete-event", Gtk.main_quit)
win.show_all()
Gtk.main()


