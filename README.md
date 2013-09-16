lockwatcher
===========

Anti-forensic monitor program: watches for signs of forensic aquisition and purges keys/shuts everything down.
Pretty much everything is written in Python 3


This program is the result of my masters thesis on anti-forensics and was written as part of a case-study on
building a forensic aquisition/analysis resistant sytem.

TL;DR

You lock computer whenever not physically present at it.

Someone attempts to do something to computer (or walks in room - there are lots of trigger options).

Encryption keys are purged, computer shuts down, your data is safe. Probably.

Install
=============
sudo apt-get install motion ifplugd lm-sensors

Install Imapclient (https://pypi.python.org/pypi/IMAPClient/0.10.2) by whatever method is convenient 

[download/unzip lockwatcher]

sudo setupfiles/setup.sh


Configuration
================
sudo src/lockwatcher-gui/lockwatcher-gui.py

Run
============
sudo src/lockwatcher.py start

Notes
===========
I just uploaded this and it has only been tested on lubuntu, so good luck installing it.
 