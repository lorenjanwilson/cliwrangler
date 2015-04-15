# cliwrangler

## description

CLIWrangler is a python library which aspires to do all the dirty work necessary for
sending commands and receiving output from an SSH session to a network device.

I'm hoping to get it working with at least the following types of devices, for
starters:

- Cisco IOS
- Cisco ASA &amp; FWSM
- Cisco IOS XE
- Cisco IOS XR (ASR 9k, etc.)
- Cisco Nexus NXOS
- Fortinet FortiOS (FortiGate)
- Brocade/Foundry OS (pre-VSS)

Cisco IOS is being dealt with first, and it's currently the only thing that
I've tested in the testlab. Other types of devices will follow shortly after
I've used this to make changes on more device types.

## disclaimer

This is not production-ready code. Use it at your own risk and proceed
carefully. Do lots of testing in a testlab before you unleash your scripts on a
production network. 

Don't mess up your network. I can't be held responsible for what you do with
this code.

## features

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

If you have a large, heterogenous campus network, NETCONF is usually not an
option yet, because most devices don't support it very well at the software
versions that you see out in the wild. And even if you're lucky enough to have
NETCONF support everywhere on your network, using it can be far from intuitive.

I'm excited about using NETCONF when I can, but a good part of my job still
needs me to interact with the CLI. I'd rather not do that by hand.

### Yeah, but CLI scraping? That's so dirty, there's got to be a better way.

Sometimes yes, sometimes no. Even in 2015, CLI scraping is often the most
straightforward way to go about making a change on a large network. You can do
things via SNMP writes or NETCONF or vendor-specific APIs or centralized
management technologies, but even then, you'll find that some things can still
only be done via the CLI.

Of course, if you're using generic whitebox network devices and doing
everything with an SDN controller, you have more options.

I'd love to have a REST API to every network device, but that's not the world
we live in yet. If you work at Cisco and you're reading this, please help!

### How do you make this happen in so few lines of code?

After much experimentation, I decided to use
[paramiko](http://www.paramiko.org) and
[paramiko-expect](https://github.com/fgimian/paramiko-expect) 
as the method to achieve the SSH connection magic and the expect-like
functionality. They are fantastic libraries and I am really grateful to their
authors.

It's great stuff. Without those two libraries, I would have had a much harder
time doing this.

## installation

To install CLIWrangler, run the following commands:

```bash
sudo pip install git+https://github.com/fgimian/paramiko-expect.git 
sudo pip install git+https://github.com/lorenjanwilson/cliwrangler.git
```

## usage

Here's a very simple script which uses CLIWrangler to log into a switch and run a command, enabling if necessary:

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

# We can see what kind of device we logged into by printing the identifiers for
# this device that we collected.

print "identifiers: %s" % (session.identifiers)

```

## class variables and methods

Thus far, a CLIWrangler object supports the following methods and variables.
(Methods are executable functions that you can use to accomplish tasks.)

### object instantiation

* cliwrangler.CLIWrangler(timeout, newline, backspace, buffer_size, wait, echo, debug) - Instantiate a cliwrangler object.
    * timeout - Connection timeout in seconds.
    * newline - The newline character if '\r' doesn't work on this device.
    * backspace - The backspace character if '\b' doesn't work on this device.
    * buffer_size - The buffer size.
    * wait - The time to wait after each command before continuing (sadly necessary for IOS-XE support).
    * echo - Should we echo the session to the screen? (For verbosity purposes.)
    * debug - Should we provide ssh debug information on the screen as well?

### overall session control methods

* connect(device, username, password) - Connect to a device.
* close() - Close a session cleanly.
* send(command, graceful=False) - Sends a given command and hits carriage return afterwards. It returns a cleaned version of the output that is returned from that command. If you set "graceful" to True, this function will never raise an exception, which makes for cleaner code if you know there's a good chance that your command will return an error.
* send_char(char) - This sends one character and does not hit carriage return afterwards, nor does it expect any output afterwards. This is good for sending extra carriage returns, hitting 'y' at a confirm prompt, backspacing, and that sort of thing.
* interactive() - This hands the session over to the user who's running the script, so they can type things if they need to. Helpful for emergencies, or when you see unexpected behavior and you don't know what to do next. Once you bring a session into interactive mode, there's no way to come back from it, so it's usually good to "sys.exit" after you do that.

### convenience functions that perform tasks

* check_ha_status() - This attempts to figure out whether you're on a device that you could make changes on. If you're on a standalone or primary device, it returns True. If you're on a secondary or backup device in an HA pair, it returns False. If it can't figure it out, it returns None.
* enable(enablepass) - This enables for you and deals with the password prompt that comes up. If it succeeds, it sets the variable "enabled" to True. If the CLIWrangler senses from the prompt style that you're already enabled, it won't try to re-enable.
* apply_config(lines_of_config) - This applies a block of configuration to the running config. You can pass the config in as either a multi-line string, or a list of lines.
* write_config() - This writes the config for you. Some devices use "write mem", some use "copy run start", and so forth.. this one tries to abstract that detail away from you so you don't need to worry about it.

### object variables

After running

```python
session = cliwrangler.CLIwrangler()
```

you then have access to the following variables.

#### session start variables

* session.timeout - The timeout for this connection in seconds. Default = 60
* session.newline - The newline character chosen for this session. Default = '\r'
* session.backspace - The backspace character chosen for this session. Default = '\b'
* session.buffer_size - The buffer size for this session. Default = '1024'
* session.echo - Whether or not to echo all the connection to the screen. Default = False
* session.debug - Whether or not to provide ssh debug information on the screen. Default = False

#### connect variables

* session.device - The device we were asked to connect to.
* session.output - A cleaned output string from the last command sent using session.send().
* session.output_raw - A non-cleaned output string from the last command sent.
* self.prompt - The last prompt we found.
* self.prompt_changed - A boolean for whether or not the prompt changed after the last command sent.
* self.prompt_prefix - The prefix of the first prompt that we got, which is used for expect purposes. We expect that this will always be at the beginning of a prompt line, although this may be wishful thinking.

#### session state variables 

* self.identifiers - A list of strings, each of which is an identifier for the current device. We get these strings by looking for them in the output of commands like 'show ver', which we run using the internal method _identify() when we establish the session. For example, on a Nexus 5k, this might look like ['Cisco', 'NX-OS', 'Nexus', 'Nexus5548'].
* self.enabled - True if we're currently enabled, False if we aren't.
* self.changeable - True if this device is safe to change (aka True was returned from a check_ha_status() run), False if it isn't.

