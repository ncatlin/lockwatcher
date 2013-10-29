lockwatcher
===========

Anti live-forensics monitor program: watches for signs of tampering or forensic acquisition, purges encryption keys and shuts 
everything down.

It was thought up when writing a proof of concept for defeating live forensic analysis as part of a masters thesis
 that evaluated anti-forensic techniques.

Download
=========
Linux 32-bit https://github.com/ncatlin/lockwatcher/raw/master/Lockwatcher-0.1-32.tar.gz

Linux 64-bit https://github.com/ncatlin/lockwatcher/raw/master/Lockwatcher-0.1.tar.gz

Windows 64-bit https://github.com/ncatlin/lockwatcher/raw/master/lockwatcher-setup.exe

Linux Installation
================

Install the dependencies

*On Debian/-buntu/mint/etc:*
```
sudo apt-get install python3 python3-setuptools python3-tk python3-pillow ifplugd python3-dbus

sudo easy_install3 IMAPClient pyudev
```

*On fedora*
```
sudo yum install python3 python3-setuptools python3-tkinter python3-pillow ifplugd python3-dbus python3-gobject

sudo easy_install-3.3 IMAPClient pyudev
```

Extract the software, install, run, configure
```
tar -xvzf Lockwatcher*

cd Lockwatcher*

sudo python3 setup.py install

sudo lockwatcherd start

lockwatcher-gui
```

If python3-imaging or python3-pillow isn't available then just skip it.

If your camera monitors give an error about needing libjpeg.so.8, you may want to install libjpeg8. 

http://rpm.pbone.net/index.php3?stat=3&search=libjpeg8&srodzaj=3

Windows Installation (Windows 7, 64 bit)
================
*The free, open-source iSpy software is required for room and chassis motion detection

Get it here: http://www.ispyconnect.com/download.aspx
Install it, configure your cameras (covered later).

* Run the installer
* Configure it

You will need to restart the computer before mouse/keyboard triggers work.

If you have Crucial Ballistix modules you may want to install and run their MOD utility and start temperature logging

Why?
=====
Operating systems have improved physical security over recent years (eg: by not allowing auto-run when 
the screen is locked) but even if they ignore a CD being inserted into the drive while the computer is locked, they
 are still sitting there happily allowing someone to keep trying to get your data. 
 
 This is bad. 
 
 lockwatcher is built around the assumption that if someone tries to use your computer while it is locked
 then they are trying to get your live data, so that data needs to be destroyed and the machine rendered inaccessible.
 
*How lockwatcher works*

* You lock your computer whenever not physically present at it.

* Interaction* with the computer while locked triggers an emergency shutdown.

* Encryption keys are purged from memory and the computer shuts down.


Caveats
==========
The software was designed for running on live-CD/live-USB Linux, where dismounting encrypted storage and 
powering down is accomplished in 3-5 seconds or less, with little warning given to the attacker. 
 
There is a Windows version but even forced shutdown is SLOW and obvious, and the difficulty in running it 
from ramdisk (live-USB,etc) means you are likely to have lots of interesting things on disk even if they can't 
get your RAM out in time. The driver used to monitor keyboard and mouse events (https://github.com/oblitum/Interception)
isn't compatible with Windows 8 so those triggers won't work.
 
It is specifically designed for defeating live memory acquisition. It does not protect against disk analysis. 
That is what encryption is for, but lockwatcher will help keep your keys safe.

It does not stop malicious software from stealing your data. Good information security practice will help, running 
a live distribution from read-only media will help and doing your sensitive stuff on a computer that does not 
talk to the internet will help but this is a big problem.

It offers very little protection from surveillance. Although it can be configured to save (or email) a photo of
an intruder in the room, this isn't an insurmountable obstacle to someone who wants to use cameras, microphones, 
RF monitoring equipment and so on.

It does not protect you from having someone beat you with a wrench (or threaten prison time) to get your 
encryption keys. Deniable encryption might help, but using it effectively requires a lot of diligence.

There can be false positives. A device failing or a cat walking around the room can scare the system into 
shutting down. By default a shutdown isn't very destructive, so this should only be a nuisance if it happens.

*What kind of 'Interaction' are we talking about?
=============
There are lots of triggers for an emergency shutdown which can be tailored for the environment 
the computer is running in.

* Device monitoring

Any devices or disks being plugged into the system or removed. USB, Firewire, CDs, etc.

* Keyboard kill-switch

One or more keyboard keys can be set to trigger an emergency shutdown if you are at the computer when it is required.

You can also designate a key to shutdown the computer if it is pressed while locked. This can be given to attackers 
as part of a false password if you are forced to give up your screen-unlocking password. What happens after that might 
not be pretty though.

* Mouse kill-switch

If you think your attacker might move your mouse around or click buttons to see if the screen is locked, this trigger
 can help. Obviously you will have to unlock the system without using the mouse functions, but it is an easy trap to set.

* Network interface monitoring

If the standard procedure of isolating the computer from the network is followed, or an attacker connects/disconnects
a network interface to access traffic then lockwatcher will notice this and trigger a shutdown.

* Bluetooth monitoring

lockwatcher can connect to a Bluetooth device and trigger a shutdown if this connection is severed. This is useful 
if your devices are confiscated, turned off or placed in a shielded container by an attacker. If you have a device which
 can be quickly turned off or parted from its batteries then this becomes a handy portable kill-switch when you are 
 not in arms-reach of the computer.
 
* RAM temperature detection

The first defence against RAM acquisition by freezing/removing memory modules 
(see: https://citp.princeton.edu/research/memory/), Lockwatcher can monitor the temperature of certain memory 
modules and trigger if their temperature falls below a certain point.

The availability of memory modules with temperature sensors is horrendous at the moment so lockwatcher only
supports monitoring Crucial Ballistix modules, and only on Windows (requires installing the Ballistix MOD utility).
Anyone who would like to contribute code to read temperature directly and from other types of RAM (like 
HWMonitor does) would be appreciated. The test system motherboard wouldn't even support decode-dimms, so I added a
 motherboard temperature monitoring trigger for the sake of it and gave up. Use chassis movement monitoring if you
  are worried about this kind of attack.

* Chassis movement detection

A much better defence against RAM acquisition, but fiddly to set up and requires some hardware.

You need a webcam. A £5 no-brand horror will be fine but one without a microphone (or a microphone you have 
disabled) would be a good idea for obvious reasons. The camera or inside of your case should have an LED or two 
to give a bit of light inside.

Now the tricky bit: Suspend it in the computer case so it can swing freely. Use tape, string, whatever: just make sure
 the camera is free to swing a little when the case itself is moved. It also needs to be plugged in to USB, 
 preferably to an internal USB port.
 
 ![It is easier if your case is not cable-managment hell](casepicture1.jpg)
 
If the case is securely shut (preferably with a lock) then any movement of the case or attempts to open it up will
 either move the camera or change the lighting conditions in the chassis, triggering a shutdown long before the
 RAM or BIOS can be tampered with. This also helps prevent hot-plug attacks against self-encrypting hard drives.

On Windows this trigger (and the one below) requires the free open-source 'iSpy' software. 

* Room movement detection

A camera can be pointed at the room to allow a shutdown when any motion is detected. Not too useful if pets/family/coworkers
 are expected to be in the same room as the computer while you are away.
 
This trigger can be activated and deactivated remotely so the system doesn't shutdown 
whenever you return to the computer. 

This also allows a photo to be saved or emailed to alert you to the identity of the attacker.

* Not yet implemented - Intrusion switch monitoring

Trigger a shutdown if the case is opened and the motherboard intrusion detection switch is activated. 

* Not yet implemented - Power supply monitoring

The room motion trigger could in theory be circumvented by cutting power to the room and then taking the memory
 modules. If the case is reasonably secure then there is minimal chance of this being successful, but a transition 
 from mains power to uninterruptable power supply could be used as a trigger. And cause false positives in a 
 power outage.

Bonus points
===============
Anything that increases the time between trigger activation and having your memory ripped out is helpful. Keep your 
system chassis secure, and tucked away so that doing anything with it requires moving it around and 
setting off the chassis motion monitor.

Password protect your BIOS to stop someone rebooting straight into a memory analysis CD. 

If your BIOS can be configured to perform a complete memory check on start up, (or even better to wipe memory) 
then activate those options. Yes it will require a password every time your system boots up and slow the 
process down, but some level of inconvenience has to be accepted.

Not important, but If your cables allow it you can swap the reset and power switch pins on the motherboard. 
An attempt to use the reset button to do a hard reset will trigger a standard shutdown instead, which causes 
Truecrypt to dismount its volumes. 

Using remote control
====================
(I know this is a pain in the neck, hopefully a native app will be up and running for iOS and Android at some point)
You need an email account with smtp and imap access, preferably a throwaway account that you don't use for anything else.

* Install QPython on your Android device

* Go to http://qpython.com/create.php, paste in the mobilecontrol.py code

* Edit emails,password to your liking and add the authentication secret from the Lockwatcher email settings tab

* Generate the QRCode on the web page, scan it with QPython on your phone

* Save it as a script
 
* Whenever you want to use it, open QPython and execute the script

![The mobile control interface](mcpicture.png)

Q&A
============
Q.Can lockwatcher wipe files instead of just shutting down? 

A.You can add relevant commands to the custom batch script which will be executed on emergency shutdown, 
but it takes a long time and makes false positive triggers a much bigger problem.

Q.Curse you authoritarian pigdog fascist, I want to use your stuff but it is riddled with government backdoors!

A. You can go through the source code if you want, most of it is written in Python so it isn't even 
compiled on Linux. The lack of Windows access to Bluetooth sockets (with Python 3, try it if you don't believe me) 
and user defined Signals means a bit of C code is in the Win32 distribution as little executables, 
which is what Avast flags as suspicious occasionally. They are easy to compile with cygwin.

Q.When is the Mac version coming out?

A.Either when someone else writes one or when someone buys me a Mac to develop/test it on.

To-do list
===========
* Write iOS/Android apps instead of doing the qpython thing

* RAM temperature monitoring on Linux. My motherboard won't play nice with decode-dimms and 
I haven't had much luck doing what the ballistix MOD utility does. 
Also: other types of RAM on both operating systems.

* Testing and better install configurations for other Linux distros. Start-on-Startup in particular I'm not sure
 how to do in a distribution-independent way.

* If anyone could write something like this for Android/iOS/etc then please do: pair-locking is nice but possibly
 vendor-surmountable. The exposure of mobile devices to seizure and acquisition at borders or on arrest, plus 
their critical reliance on a tiny stable of acquisition tools makes them the most deserving hosts of this kind 
of tool. Storage wiping would even be handy because of easier false-positive avoidance, but I don't know if 
it can be done without jailbreaking at the very least.

* Python was probably a bad choice for this. Consider a C version. 

Windows Version:

* I'm not happy with the Windows shutdown speed at all, it might be worth implementing RAM erasing instead.
I can't get firewire attacks to work on Windows 7 so whether the shutdown process interrupts 
RAM acquisition in time or not is a mystery. Being able to disconnect hardware devices would be a big help, 
like how VMWare or VirtualBox can steal your USB devices, but I haven't looked into how to do that yet.

* Get keyboard/mouse interception working on Windows 8. If it isn't run as a service then GetAsyncKeystate 
can get keypresses when the screen isn't locked but that isn't much. Come to think of it the Interception driver in
 general is far from ideal even without the Win 8 problem: there is no source code for the installer and no licence.

* Ditch the iSpy requirement. Slicing and dicing Motion for use with lockwatcher was easy because it 
isn't a GUI program but I took one look at the iSpy code and went "nope". 
