from setuptools import setup

setup(name='LVFS',
      version='1.0',
      description='Linux Vendor Firmware Service',
      author='Richard Hughes',
      author_email='richard@hughsie.com',
      url='http://www.python.org/sigs/distutils-sig/',
      install_requires=['Flask>=0.10.1', 'Flask-Login', 'boto3'],
     )
