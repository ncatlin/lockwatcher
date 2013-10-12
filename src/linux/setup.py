'''
Created on 12 Oct 2013

@author: root
'''
'''
create /etc/lockwatcher for ini
put lockwatcher, lockwatcher-gui in /usr/bin
start on boot...?

'''
from distutils.core import setup

setup(name='Lockwatcher',
      version='0.1',
      description='Anti-forensic monitor',
      author='Nia Catlin',
      url='https://github.com/ncatlin/lockwatcher/',
      packages=['lockwatcher']
     )