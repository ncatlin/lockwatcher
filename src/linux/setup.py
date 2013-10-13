from distutils.core import setup

setup(name='Lockwatcher',
      version='0.1',
      description='Anti-forensic monitor',
      author='Nia Catlin',
      url='https://github.com/ncatlin/lockwatcher/',
      packages=['lockwatcher'],
      scripts=['lockwatcherd', 'lockwatcher-gui'],
      data_files=[('/etc/lockwatcher',['lockwatcher.conf','sd.sh'])]
     )