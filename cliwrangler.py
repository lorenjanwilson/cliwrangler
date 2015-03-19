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

class CLIWrangler:
    """This class provides a clean interface to a Cisco IOS CLI ssh session. 
    To deal with the SSH and expect-type functionality, we use Paramiko and
    Paramiko-expect."""

    def __init__(self, timeout=60, newline='\r', backspace='\b', buffer_size=1024, echo=False, debug=False):    
        """The constructor for the CLIWrangler class.

        Arguments:
        timeout - Connection timeout in seconds.
        newline - The newline character if '\r' doesn't work.
        newline - The backspace character if '\b' doesn't work.
        buffer_size - The buffer size.
        echo - Should we echo the session to the screen? (For verbosity purposes.)
        debug - Should we provide ssh debug information on the screen as well?
        """

        # Arguments
        self.timeout = timeout
        self.newline = newline
        self.backspace = backspace
        self.buffer_size = buffer_size
        self.echo = echo
        self.debug = debug

        # Our output after running a command.
        self.output = None
        self.output_raw = None
        # The thing we just tried to send.
        self.current_send_string = None
        # The last thing that matched during an expect.
        self.last_match = None
        # The last prompt we found, and a boolean for whether or not the prompt changed after the last command send.
        self.prompt = None
        self.prompt_changed = False
        # A list of keywords used to identify this device. Discovered via things like "show ver".
        # This might be something like ['Cisco', 'IOS', 'C3750'] or ['Cisco', 'NX-OS', 'Nexus', '5000']
        self.identification = []

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

        # Set SSH key parameters to auto accept unknown hosts.
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Connect to the host.
        # "allow_agent=False" and "look_for_keys=False" are necessary to log into some IOS devices.
        self.client.connect(hostname=device, username=username, password=password, allow_agent=False, look_for_keys=False)
        # Now we can initialize our interaction object.
        self.interact = paramikoe.SSHClientInteraction(self.client, timeout=self.timeout, display=self.echo)

        # Get the prompt.
        self._get_prompt()

        # Prep the session (term len 0, etc).
        self._prepare()
        
        # Identify the device we're on.
        self._identify()

        return True

    def _get_prompt(self):
        """Figure out the device prompt. We will probably need to do this
        after running each command, just to make sure the prompt hasn't
        changed due to a mode change."""

        unique_string = 'RRRR'
        length_of_unique_string = len(unique_string)
        backspace_string = self.backspace * length_of_unique_string

        # First, send a newline.
        self.interact.send(self.newline)
        # Send a string that will signify the absolute end of the buffer.
        # Sad, but necessary. If we don't do this, we won't know whether
        # we're matching the very last thing we got.
        self.interact.channel.send(unique_string)
        self.interact.expect(".*%s$" % (unique_string))
        # See what's now at the end.
        output = self.interact.current_output
        # Strip the extra stuff we created off the end.
        output = output[:-length_of_unique_string]
        # Take the last line. That's our prompt.
        prompt = output.splitlines()[-1];
        # Backspace over the dirty trick.
        self.interact.channel.send(backspace_string)

        # Check to see if the prompt has changed.
        if (self.prompt == prompt):
            self.prompt_changed = False
        else:
            self.prompt_changed = True
            self.prompt = prompt

        return self.prompt

    def _prepare(self):
        """Prepare the session by doing "terminal length 0" and any other
        such things that might be necessary."""

        # This is going to have to do much more in the future, but right now it just sends a "term len 0".
        self.interact.send('terminal length 0')
        self.interact.expect(self.prompt)
        return True
        
    def _identify(self):
        """Run various commands to identify the device we're on."""

        # Here's a big collection of strings to look for.
        # If we find any of these strings in command output, we add their value
        # to the identification list.
        identification_strings = yaml.load("""
            'Cisco ': 'Cisco'
            'cisco ': 'Cisco'
            'CISCO ': 'Cisco'
            ' IOS ': 'IOS'
            ' C3750 ': 'C3750'
        """)

        # Run a show ver and hope for the best.
        # In the future, we might run a slew of commands and search through the
        # output of any of the ones that worked.
        self.send('show version')

        # If any of the identification strings are found in the output, stick
        # them into the identification array.
        for string in identification_strings.keys():
            if string in self.output:
                identity = identification_strings[string]
                # Don't add it if it's already there. More than one might match.
                if identity not in self.identification:
                    self.identification.append(identity)

        return True

    def _expect_prompt(self):
        """Expect something that looks like our prompt. It may have changed by
        now because of a mode switch, so if it did, update the prompt
        definition."""

        # We currently allow a certain set of common prompt chars.
        prompt_chars = ['>', '#', ']', ':']
        general_prompt_regex = '.*%s\s*$'
        # Create a regex for each char in the list above.
        prompt_regexes = [ general_prompt_regex % (char) for char in prompt_chars ]
        # Expect one of the regexes or the prompt.
        self.interact.expect([self.prompt] + prompt_regexes)
        # If we didn't match the prompt itself, get a new prompt.
        if (self.interact.last_match != self.prompt):
            self._get_prompt()

        return self.prompt

    def send(self, command):
        """Run a command.

        Here's what a "send" does:

        1. Send the line.
        2. Expect some type of prompt-looking thing.
        3. Switch the prompt if necessary.
        4. Clean the output if necessary.
        5. Check the output for obvious errors, and maybe raise an exception if we got one. 
        6. Send back the output and set it to self.output.
        """

        # Send the command.
        self.interact.send(command)

        # Expect something that looks like our prompt, although it might have changed by now.
        self._expect_prompt()

        # Set the output.
        self.output = self.interact.current_output_clean
        self.output_raw = self.interact.current_output

        # If something looked like an error, print it and raise an exception.
        error_patterns = ['^% Invalid', '^ERROR: ', '^Cannot make changes']
        for error in error_patterns:
            if re.search(error, self.output, flags=re.MULTILINE):
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
            self.interact.send(enable_password)
            self._expect_prompt()
        else:
            raise Exception("Didn't get something that looked like a password prompt when trying to enable!")

        # Make sure we enabled.
        if (re.search('#', self.prompt)):
            return True
        else:
            return False

