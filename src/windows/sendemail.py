'''
@author: Nia Catlin
'''
import smtplib, time, sys
import hashlib, hmac, os
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email import encoders
from socket import gaierror 

from fileconfig import config

def validHMAC(code,command):
            #use a HMAC to prevent impersonation/replay
            secret = config.get('EMAIL','EMAIL_SECRET')
            
            timenow = time.strftime('%d%m%Y%H%M') #day,month,year,hour,minute
            validTimes = (str(int(timenow)-1),timenow,str(int(timenow)+1)) #1 minute leeway
            
            validHashes = []
            for validTime in validTimes:
                validHashes = validHashes + [hmac.new(secret+str(command),validTime,hashlib.sha1)]
            
            validCodes = []
            for h in validHashes:
                smallDigest = h.hexdigest()
                validCodes = validCodes + [''.join([smallDigest[x].lower() for x in range(1,20,2)])]
            
            if code in validCodes:
                return True
            else:
                return False

def doSend(msg):
    try:
        s = smtplib.SMTP(config.get('EMAIL','email_smtp_host'),timeout=4)
        s.ehlo()
        s.starttls()
        s.login(config.get('EMAIL','email_username'), config.get('EMAIL','email_password'))
        s.sendmail(msg['From'],msg['To'], msg.as_string())
        s.quit()
        return True  
    except gaierror:
        return 'SMTP connect error'
    except smtplib.SMTPAuthenticationError:
        return 'SMTP authentication error'
    except smtplib.SMTPException as e:
        return 'SMTP error :%s'%e
    except:
        return 'SMTP exception: %s'%str(sys.exc_info())

#takes subject/message strings, optional attachment filepath
#returns True if ok or string describing error
def sendEmail(subject,message,attachment=None):

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
    msg['From'] = config.get('EMAIL','SENDER_EMAIL_ADDRESS')
    msg['To'] = config.get('EMAIL','ALERT_EMAIL_ADDRESS')
    
    return doSend(msg)