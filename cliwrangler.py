# cliwrangler
# by Loren Jan Wilson
# 
# A python library for interacting with Cisco switches and other network
# devices via the CLI.
#
# Uses paramiko and paramiko-expect.
#
# Intended to be run at a Unix shell prompt.
#

import paramiko
import paramikoe
import re
import yaml
import time

class CLIWrangler:
    """This class provides a clean interface to a Cisco IOS CLI ssh session. 
    To deal with the SSH and expect-type functionality, we use Paramiko and
    Paramiko-expect."""

    def __init__(self, timeout=20, newline='\r', backspace='\b', buffer_size=1024, wait=0.2, echo=False, debug=False):    
        """The constructor for the CLIWrangler class.

        Arguments:
        timeout - Connection timeout in seconds.
        newline - The newline character if '\r' doesn't work.
        backspace - The backspace character if '\b' doesn't work.
        buffer_size - The buffer size.
        wait - The number of seconds to wait after every command sent, thanks to IOS-XE.
        echo - Should we echo the session to the screen? (For verbosity purposes.)
        debug - Should we provide ssh debug information on the screen as well?
        """

        # Arguments
        self.timeout = timeout
        self.newline = newline
        self.backspace = backspace
        self.buffer_size = buffer_size
        self.wait = wait
        self.echo = echo
        self.debug = debug

        # The device they asked to connect to.
        self.device = None
        # Our output after running a command.
        self.output = None
        self.output_raw = None
        # The last thing that matched during an expect.
        self.last_match = None
        # The last prompt we found, and a boolean for whether or not the prompt changed after the last command send.
        self.prompt = None
        self.prompt_changed = False
        # The prefix of the prompt that we try to consistently match. Let's see if this works.
        self.prompt_prefix = None
        # A list of keywords used to identify this device. Discovered via things like "show ver".
        # This might be something like ['Cisco', 'IOS', 'C3750'] or ['Cisco', 'NX-OS', 'Nexus', '5000']
        self.identifiers = []
        # If an enable succeeds, we set this to True.
        self.enabled = False
        # If we decide this device is safe to change, we set this to True.
        # If we decide this device is NOT safe to change, we set this to False.
        self.changeable = None

        # Initialize Paramiko and Paramiko-expect objects.
        self.client = paramiko.SSHClient()
        # paramikoe.SSHClientInteraction() can't be initialized until after we
        # connect, so this variable gets set during connect.
        self.interact = None

    def __del__(self):
        """The destructor for our CLIWrangler class."""
        self.close()

    def close(self):
        """Attempts to close the paramiko-expect session for clean completion."""
        try:
            # Close the paramiko-expect session.
            self.channel.close()
        except:
            pass

    def connect(self, device, username, password):
        """Connect to the given device using our Paramiko client.

        Arguments:
        device - The device to connect.
        username - The username to use.
        password - The password to use.
        """

        self.device = device

        # Set SSH key parameters to auto accept unknown hosts.
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect to the host.
        # "allow_agent=False" and "look_for_keys=False" are necessary to log into some IOS devices.
        self.client.connect(hostname=device, username=username, password=password, allow_agent=False, look_for_keys=False)
        # Now we can initialize our interaction object.
        self.interact = paramikoe.SSHClientInteraction(self.client, timeout=self.timeout, display=self.echo)

        # Hit a carriage return to make sure we can sense the prompt.
        # This isn't necessary on Cisco IOS, but it's necessary on FortiOS.
        self.interact.send(self.newline)

        # Expect before continuing, to clear the buffer and set the prompt.
        self._expect_output()

        # Prep the session (term len 0, etc).
        self._prepare()
        
        # Identify the device we're on.
        self._identify()

        # If we auto-enabled, we can set that bit now.
        if re.match('^.*#\s*$', self.prompt):
            self.enabled = True

        return True

    def _expect_output(self):
        """Expect our entire output. This is meant to be used during a "send"
        method call, or after any manual send. There are some dirty tricks in here."""

        # The first thing we do is type a string that we don't expect to get
        # from any command output. This puts us in a known state. Otherwise, if
        # we try to just match on the prompt, we won't know whether we're
        # matching the last prompt available, or something before we ran the
        # last command.
        unique_string = 'RRRR'
        length_of_unique_string = len(unique_string)
        backspace_string = self.backspace * length_of_unique_string

        # Send our unique string.
        self.interact.channel.send(unique_string)

        # Expect the unique string we just sent, with the prompt prefix at the
        # beginning of the line if we have one.
        if self.prompt_prefix:
            self.interact.expect("%s.*%s" % (self.prompt_prefix, unique_string))
        else:
            # If we don't have a prompt prefix, at least expect something sane.
            # Unfortunately, this is a bit more complex, because we have to
            # define sanity. It should be "something kind of prompty" followed
            # by an allowed end-of-prompt character followed by the unique
            # string we typed.
            end_of_prompt_chars = ['>', '#', '$', '%']
            # A prompt, simply, is 3 or more [a-z0-9/-] characters, plus maybe
            # an extension of other things, with an end_of_prompt_char at the end,
            # and maybe some whitespace after that. You can thank the FWSM for
            # using the forward slash in a prompt.
            general_prompt_regex_template = '[a-zA-Z0-9/-]{3,}\s*%s\s*%s'
            # Create a regex for each char in the list above.
            general_prompt_regexes = [ general_prompt_regex_template % (char, unique_string) for char in end_of_prompt_chars ]
            # See if any of the "sane-looking possible prompts" matched.
            self.interact.expect(general_prompt_regexes)

        # Set the output variables.
        self.output = self.interact.current_output_clean
        self.output_raw = self.interact.current_output

        # Backspace over the dirty trick.
        self.interact.channel.send(backspace_string)

        # We now need to set the "prompt" variable in case the prompt changed.
        # See what's now at the end.
        output = self.output_raw
        # Strip the extra stuff we created off the end.
        output = output[:-length_of_unique_string]
        # Take the last line. That's our prompt.
        self.prompt = output.splitlines()[-1];

        # Try to get the prompt prefix if we haven't already. We keep track of
        # this in case the prompt gets suffixes tacked onto it by mode changes.
        # If we don't do this, we'll trip up when a prompt-ending character is
        # found at the end of a line of command output. 
        if self.prompt_prefix is None:
            m = re.match('^([a-zA-Z0-9-]{3,})', self.prompt)
            if m is not None:
                self.prompt_prefix = m.group(1)

        # Let's return True. I have no idea what would be useful here yet.
        return True

    def _prepare(self):
        """Prepare the session by doing "terminal length 0" and any other
        such things that might be necessary."""

        # The very first thing we need to do is turn off paging.
        result = self.send('terminal length 0', graceful=True)
        # If that worked, send IOS commands to disable monitor and editing.
        if result is not None:
            self.send('terminal no monitor', graceful=True)
            self.send('terminal no editing', graceful=True)
            return True

        # Cisco ASAs don't let you run "terminal pager 0" unless you've
        # enabled. This is severely cramping my style. Not sure how to deal
        # with this case yet.

        # The usual IOS commands didn't work, so let's try the FortiOS ones.
        # This is horribly dirty because FortiOS CLI is terrible.
        # I don't feel comfortable trying these things unless we're relatively
        # sure we're on FortiOS, so let's look for the Fortinet error format in
        # the output of our last command.
        if "Command fail. Return code" in self.output:
            # There are two ways to do this. Here's the one you need if you have vdoms:
            result = self.send('config global', graceful=True)
            if result is not None:
                self.send('config system console')
                self.send('set output standard')
                self.send('end')
                self.send('end')
            # And here's the one you need if you don't have vdom support (fortiOS 4.x?)
            else:
                self.send('config system console')
                self.send('set output standard')
                self.send('end')

        # None of our prep worked. This may not be catastrophic, so let's return False.
        return False
        
    def _identify(self):
        """Run various commands to identify the device we're on."""

        # Here's a big collection of strings to look for. If we find any of
        # these strings in command output, we add their value to the
        # identification list. I should probably load this in from a separate
        # file because it's going to get huge.
        identification_strings = yaml.load("""
            'Cisco ': 'Cisco'
            'cisco ': 'Cisco'
            'CISCO ': 'Cisco'
            ' IOS ': 'IOS'
            'IOS ': 'IOS'
            ' C3750 ': 'C3750'
            ' WS-C6509-E ': 'C6509-E'
            'Adaptive Security Appliance': 'ASA'
            'ASA5520': 'ASA5520'
            'FWSM Firewall': 'FWSM'
            'FWSM Firewall Version': 'Cisco'
            'FortiOS': 'Fortinet'
            'FortiGate': 'FortiGate'
            'FortiGate-1000C': '1000C'
            'Nexus Operating': 'Nexus'
            'NX-OS': 'NX-OS'
            'Nexus5548': 'Nexus5548'
        """)

        identification_commands = yaml.load("""
            - 'show version' # Cisco IOS
            - 'get system status' # Fortinet FortiOS
        """)

        # Run a slew of commands and search through the output of the one (or
        # ones) that worked. Right now, we break after one successful command
        # run.
        output = None

        for command in identification_commands:
            # "graceful" just means "Don't raise an exception because this
            # command might fail and I don't care if it does."
            result = self.send(command, graceful=True)
            if result is not None:
                output = self.output
                break

        # If any of the identification strings are found in the output, stick
        # them into the identifiers list.
        for string in identification_strings.keys():
            if string in output:
                identity = identification_strings[string]
                # Don't add it if it's already there. More than one might match.
                if identity not in self.identifiers:
                    self.identifiers.append(identity)

        return True

    def send(self, command, graceful=False):
        """Run a command.

        Here's what a "send" does:

        1. Send the line.
        2. Expect some type of prompt-looking thing.
        3. Switch the prompt if necessary.
        4. Clean the output if necessary.
        5. Check the output for obvious errors, and maybe raise an exception if we got one. 
        6. Send back the output and set it to self.output.

        If you set "graceful" to True, this function will not raise an exception.
        This allows us not to have to take sides in the
        exceptions-vs.-return-codes holy war. 
        """

        # Send the command.
        self.interact.send(command)

        # Unfortunately, on IOS-XE, there's a short period of time after a
        # command is sent where if you send characters, they get thrown out.
        # This should be considered a bug, but I doubt Cisco's going to fix it.
        # Because of this IOS-XE bug, we need to wait after sending a command.
        time.sleep(self.wait)

        # On the off chance that we couldn't disable paging, hit space bar a
        # few times. This is pretty sad, but necessary for things like the
        # ASAs, which don't let you disable paging until you've enabled.
        self.interact.channel.send('     ')

        # Expect the end of the output of the send command.
        self._expect_output()

        # If something looked like an error, print it and maybe raise an exception.
        error_patterns = ['^% Invalid', '^% Incomplete', '^ERROR: ', '^Cannot make changes', 'Command fail. Return code']
        for error in error_patterns:
            if re.search(error, self.output, flags=re.MULTILINE):
                # If they don't want exceptions, don't raise an exception.
                # The reason why I offer the choice is because some Python
                # programmers do everything by exception handling, and others
                # hate it.
                if graceful:
                    # We return None if there was an error and the user didn't
                    # want exceptions to be raised. If the user wants to check
                    # for a specific error, it will be in self.output.
                    return None
                else:
                    raise Exception("Found error string! \n%s" % (self.output))

        # Return the output.
        return self.output

    def send_char(self, char):
        """Send just a single character.
        Useful for those times you need to hit 'y' at a prompt.
        """

        interact.channel.send(char)
        return True

    def enable(self, enable_password):
        """For people who need to manually enable, this is a helper method to
perform that action.
        """

        self.interact.send('enable')
        self.interact.expect([self.prompt, '.*ssword:\s*$'])

        # Type the password at the password prompt.
        if re.search('ssword:', self.interact.last_match, flags=re.IGNORECASE):
            self.send(enable_password)
            #self.interact.send(enable_password)
            #self._expect_prompt()
        else:
            raise Exception("Didn't get something that looked like a password prompt when trying to enable!")

        # Make sure we enabled.
        if (re.search('#', self.prompt)):
            self.enabled = True

        # If we're on an ASA, we need to disable paging here, because we
        # couldn't do it during the _prepare.
        if ("Cisco" in self.identifiers and "ASA" in self.identifiers):
            self.send('terminal pager 0')

        return self.enabled

    def interactive(self):
        """Hand the session to the user.
        This is useful if you do a really stupid thing in config mode and can
        no longer log in, for example."""

        self.interact.send(self.newline * 2)
        self.interact.take_control()
        return True

    def check_ha_status(self):
        """Run a series of tests to figure out whether we should make config
        changes on this device. This is an HA test.

        Active or standalone devices should return True, and the secondary
        (inactive) device in a redundant pair should return False. If we can't
        figure it out, return None."""

        # We should use the identifiers to figure out how to proceed.
        # Cisco ASAs and FWSMs need to be checked to make sure they're
        # standalone or currently active.
        if "Cisco" in self.identifiers:
            if "ASA" in self.identifiers:
                # Run "show failover" on the ASA and look for various strings.
                # Has to be graceful because this command requires the failover license.
                self.send('show failover', graceful=True)
                if re.search('Command requires failover license', self.output):
                    self.changeable = True
                elif 'Failover Off' in self.output:
                    self.changeable = True
                elif re.search('This host:.*- Active', self.output):
                    self.changeable = True
                elif re.search('This host:.*- Standby', self.output):
                    self.changeable = False
                else:
                    # We don't know for sure, so return None.
                    pass
            elif "FWSM" in self.identifiers:
                # We run "show failover" on the FWSM and look for various strings.
                self.send('show failover', graceful=True)
                if 'Failover Off' in self.output:
                    self.changeable = True
                elif 'This context: Active' in self.output:
                    self.changeable = True
                elif re.search('This Host:.*- Active', self.output):
                    self.changeable = True
                elif 'This context: Standby' in self.output:
                    self.changeable = False
                elif re.search('This Host:.*- Standby', self.output):
                    self.changeable = False
                else:
                    # We don't know for sure, so return None.
                    pass
            else:
                # We'll always give a green light for Cisco devices.
                self.changeable = True
        # On Fortinet devices, this probably won't always work, but it works
        # for FortiOS 5.x so far.
        elif "Fortinet" in self.identifiers:
            if "FortiGate" in self.identifiers:
                self.send('get system status', graceful=True)
                if 'Current HA mode: a-p, master' in self.output:
                    self.changeable = True
                elif 'Current HA mode: standalone' in self.output:
                    self.changeable = True
                elif 'Current HA mode: a-p, backup' in self.output:
                    self.changeable = False
                else:
                    # We don't know for sure, so return None.
                    pass
        
        # For anything else, we aren't qualified to say with certainty.
        # The default value is None.
        return self.changeable

    def apply_config(self, config):
        """Apply some config lines to the config.
        You can pass in a string or a list.
        This should even be made to work on things like Juniper devices."""

        # Make sure we're enabled.
        if not self.enabled:
            raise Exception("Called apply_config() without being enabled")

        # If it seems like we were passed a string, split it into a list.
        # If this is a list, the split will raise an exception, which is fine.
        try:
            # This will transform a string into a list, even if it's just one
            # item. Very classy.
            config = config.split('\n')
        except:
            pass

        if "Cisco" in self.identifiers:
            if "IOS" in self.identifiers:
                # Apply the config by entering config mode, writing lines, then
                # leaving config mode.
                self.send('configure terminal')
                # Send each line one at a time.
                for line in config:
                    self.send(line)
                self.send('exit')
            else:
                raise Exception("Don't know how to apply config on this type of Cisco device!")
        else:
            raise Exception("Don't know how to apply config on this vendor yet!")

    def write_config(self):
        """Write mem or copy run start or whatever.
        Depending on the device type, this could be quite different."""

        # Make sure we're enabled.
        if not self.enabled:
            raise Exception("Called write_config() without being enabled")
            
        if "Cisco" in self.identifiers:
            if "IOS" in self.identifiers:
                self.send('write memory')
            elif "Nexus" in self.identifiers:
                self.send('copy running-config startup-config')
            elif "ASA" in self.identifiers:
                self.send('write memory')
            elif "FWSM" in self.identifiers:
                self.send('write memory')
            else:
                raise Exception("Don't know how to write config on this type of Cisco device!")
        elif "Fortinet" in self.identifiers:
            if "FortiGate" in self.identifiers:
                # FortiGate devices automatically write their config when you
                # leave edit mode.
                pass
            else:
                raise Exception("Don't know how to write config on this type of Fortinet device!")
        else:
            raise Exception("Don't know how to write config on this vendor yet!")

        return True


