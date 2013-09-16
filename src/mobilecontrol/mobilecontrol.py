"""
mobilecontrol.py
@author: Nia Catlin

This is a python script to be run on QPython on Android
A remote control program which communicates with the designated computer using authenticated email
Upload to your Qpython app using http://qpython.com/create.php
"""

import androidhelper
import hashlib,time
import hmac
import binascii
import email
import smtplib
     
secret = 'secret!'
#use time+command+secret to generate HMAC
def genCode(command):
    timenow = time.strftime('%d%m%Y%H%M')
    secretCat = 'secret!'+str(command)
    ourHash = hmac.new(bytes(secretCat),bytes(timenow),hashlib.sha1)
    code= ourHash.hexdigest()
    code = ''.join([code[x].lower() for x in range(1,20,2)])
    return code
 
droid = androidhelper.Android()

message = "\
 \n\
 \t 1 -> Lock computer\n\
 \t 2 -> Start Motion Monitor\n\
 \t 3 -> Stop Motion Monitor\n\
 \t 4 -> Standard Shutdown\n\
 \t 5 -> Antiforensic Shutdown\n\
Enter Numeric Command"

droid.dialogCreateInput("Remote System Control", message, None, "number")
droid.dialogSetPositiveButtonText("Send") 
droid.dialogShow()
command = droid.dialogGetResponse().result['value']

HOST = 'CHANGEME'
USERNAME = 'CHANGEME'
PASSWORD = 'CHANGEME'
 
s = smtplib.SMTP(HOST)
s.login(USERNAME, PASSWORD)
 
msg = email.mime.Text.MIMEText('')
msg['Subject'] = str(command)+' '+genCode(command)
msg['From'] = 'niasphone@hotmail.com'
msg['To'] = 'aftest123@aol.co.uk'
s.sendmail(msg['To'],USERNAME, msg.as_string())
 

droid.makeToast("Command send: check email for reply.")
