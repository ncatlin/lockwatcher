'''
Created on 5 Sep 2013

@author: Nia Catlin
'''
import smtplib, time, sys
import hashlib, hmac, os
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders

#use a HMAC to prevent impersonation/replay

def validHMAC(code,command, secretStr):
            secret = bytes(secretStr,'UTF-8')
            timenow = time.strftime('%d%m%Y%H%M') #day,month,year,hour,minute
            validTimes = (str(int(timenow)-1),timenow,str(int(timenow)+1)) #1 minute leeway
            
            validHashes = []
            for validTime in validTimes:
                validHashes = validHashes + [hmac.new(secret+bytes(str(command),'UTF-8'),bytes(validTime,'UTF-8'),hashlib.sha1)]
            
            validCodes = []
            for h in validHashes:
                smallDigest = h.hexdigest()
                validCodes = validCodes + [''.join([smallDigest[x].lower() for x in range(1,20,2)])]
            
            if code in validCodes:
                return True
            else:
                return False

def doSend(msg,config):
    try:
        s = smtplib.SMTP(config['EMAIL']['EMAIL_SMTP_HOST'])
        s.ehlo()
        s.starttls()
        s.login(config['EMAIL']['EMAIL_USERNAME'], config['EMAIL']['EMAIL_PASSWORD'])
        s.sendmail(msg['From'], msg['To'],msg.as_string())  
        s.quit()
    
    #this threw an 'InterruptedError not defined' on one test system, what the hell?
    #except InterruptedError as e:
    #    return 'SMTP connect error %s'%e
    except smtplib.SMTPRecipientsRefused as e:
        return 'Bad email recipient: %s'%msg['To']
    except smtplib.SMTPServerDisconnected as e:
        return 'Server closed connection. It may think that sender address "%s" looks like a spam email address'%msg['From']
    except smtplib.SMTPSenderRefused as e:
        return 'Sender %s refused'%e
    except:
        return "Unexpected error: %s"%sys.exc_info()[0]
    return True
        
def sendEmail(subject,message,config,attachment=None):

    if attachment == None:
        msg = MIMEText(message)
    else:
        msg = MIMEMultipart()
        msg.attach( MIMEText(message) )
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(attachment,"rb").read() )
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(attachment))
        msg.attach(part)
        
    msg['Subject'] = subject
    msg['From'] = config['EMAIL']['SENDER_EMAIL_ADDRESS']
    msg['To'] = config['EMAIL']['ALERT_EMAIL_ADDRESS']
    
    result = doSend(msg,config)
    print('email send result: %s'%result)
    return result
    
        
    
        