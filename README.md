# cliwrangler

## description

This is a python library which aspires to do all the dirty work necessary for
sending commands and receiving output from an SSH session to a network device.

After much experimentation, I decided to use paramiko and paramiko-expect as the
method to achieve the SSH connection magic and the expect-like functionality.
They are fantastic libraries and I am really grateful to their authors.

I'm hoping to get it working with the following types of devices:

- Cisco IOS
- Cisco Nexus
- Fortinet Fortigate
- Brocade

Cisco IOS is being dealt with first, and it's currently the only thing that
I've tested. Other types of devices will follow shortly.

The CLIWrangler class attempts to deal with the following nasty things on your behalf:

- disabling pagination ("terminal length 0", "skip-page-display", etc.)
- prompt changes due to mode changes (such as entering "conf t" mode)
- enabling
- device identification (figuring out what kind of device we're talking to, so you can make decisions as a result in your Python scripts)
- catching things that look like errors and raising tracebacks when they happen
- communicating with switches over higher-latency or bogged-down links without having to tweak timeout values
- providing cleaned or raw output, as requested
- a bunch of other stuff as it comes up

## FAQ

### Why aren't you using NETCONF?

Have you played with NETCONF at all? Try it and get back to me. If you have a
large campus network, it's just not an option yet, because most devices don't
support it very well at the old software versions that you see out in the wild.
Even if you're lucky enough to have NETCONF support everywhere on your network,
it's far from intuitive and doesn't make things any easier.

CLI scraping is still absolutely necessary unless you have a small network full
of only one particular device family (or unless you're living in a Zen Whitebox
Garden and you're using newer networking technologies to make everything
happen). I'd love to have a REST API to every network device, but that's not
the world we live in yet.

If you work at Cisco and you're reading this, please help!

## installation

To install cliwrangler, run the following command:

```bash
sudo pip install git+https://github.com/lorenjanwilson/cliwrangler.git
```

## usage

Here's a very simple script which uses cliwrangler to log into a switch and run a command, enabling if necessary:

```python
#!/usr/bin/python

import cliwrangler

# Set credentials.
device = 'test-cisco-switch.mynetworkrules.biz'
username = 'cisco'
password = 'sekrit'
enablepass = 'supersekrit'

# Start me up. The "echo=True" will output everything to the screen.

session = cliwrangler.CLIWrangler(echo=True)
session.connect(device=device, username=username, password=password)

# Try a command, but if it doesn't work, enable and try it again.
try:
    session.send('show run | incl aaa')
except:
    session.enable(enablepass)
    session.send('show run | incl aaa')

# Not necessary to close by hand, but it's there if you want it.
session.close()

# The output from the last command is in 'session.output'.
print "\n\n\n******\n%s\n\n" % (session.output)

# We can see what kind of device we logged into by printing the identification
# of this device that we collected.
print session.identification

```

## class variables and methods

coming soon...
