from distutils.core import setup

setup(name='Lockwatcher',
      version='0.1',
      description='Anti-forensic tampering monitor',
      author='Nia Catlin',
      author_email='nia.catlin.2012@live.rhul.ac.uk',
      url='https://github.com/ncatlin/lockwatcher/',
      packages=['lockwatcher'],
      scripts=['lockwatcherd', 'lockwatcher-gui'],
      data_files=[('/etc/lockwatcher',['lockwatcher.conf','sd.sh']),
                  ('bin/',['motion/motion-lw']),
                  ('/etc/lockwatcher/licences/motion',['motion/COPYING']),
                  ]
     )
