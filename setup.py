from setuptools import setup

setup(
    name='cliwrangler',
    version='0.1',
    url='https://github.com/lorenjan/paramiko-expect',
    license='MIT',
    author='Loren Jan Wilson',
    author_email='lorenjanwilson@gmail.com',
    description='A python library for interacting with Cisco switches and other network devices via the CLI.',
    platforms='Posix',
    py_modules=['cliwrangler'],
    install_requires=[
        'paramiko >= 1.10.1',
        'paramiko-expect >= 0.2',
        'yaml >= 3.0'
    ],
)
