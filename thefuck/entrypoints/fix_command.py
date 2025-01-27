from pprint import pformat
import os
import sys
import re
import openai
from difflib import SequenceMatcher
from .. import logs, types, const
from ..conf import settings
from ..corrector import get_corrected_commands
from ..exceptions import EmptyCommand
from ..ui import select_command
from ..utils import get_alias, get_all_executables
from ..types import CorrectedCommand
import socket

openai.api_key = "xxx"


def _get_raw_command(known_args):
    if known_args.force_command:
        return [known_args.force_command]
    elif not os.environ.get('TF_HISTORY'):
        return known_args.command
    else:
        history = os.environ['TF_HISTORY'].split('\n')[::-1]
        alias = get_alias()
        executables = get_all_executables()
        for command in history:
            diff = SequenceMatcher(a=alias, b=command).ratio()
            if diff < const.DIFF_WITH_ALIAS or command in executables:
                return [command]
    return []


def qeury_wizard(command):
    '''This function asks wizardcoder to fix the python script.'''

    # any .py file in this command?
    file_pattern = "\S+\.py"
    file_matches = re.findall(file_pattern, command.script)
    if len(file_matches) == 0 or not os.path.exists(file_matches[0]):
        pass
    else:
        # Code Generation Task
        py_files = file_matches[0]
        with open(py_files, 'r') as file:
            code = file.read()

        usr_prompt = f"My code is {code}, and my command is {command.script}, but the terminal outputs {command.output}. Please correct my code."
        
        s = socket.socket() 
        host = "127.0.0.1"
        port = 11451
        
        s.connect((host, port))
        s.send(usr_prompt.encode('utf-8'))
        ans = s.recv(1024)
        s.close()

        # Send Query
        print(ans, file=sys.stderr)
        sys.exit(0)



def qeury_gpt(command):
    '''This function asks gpt to fix the input command.'''

    # any .py file in this command?
    file_pattern = "\S+\.py"
    file_matches = re.findall(file_pattern, command.script)
    if len(file_matches) == 0 or not os.path.exists(file_matches[0]):
        # Command Fix Task
        sys_prompt = (
            "You are an assistant that help fix an error terminal script. "
            "Please give the correct command in the first row with quotation mark in your response."
        )
        usr_prompt = f"My input is {command.script}, but the terminal outputs {command.output}. "

        # Send Query
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": usr_prompt}
            ],
            temperature=0.7,
            max_tokens=256
        )

        # Print Answer
        ans = response['choices'][0]['message']['content']
        print(ans, file=sys.stderr)

        # Get Script
        pattern = "\"(.*?)\""
        matches = re.findall(pattern, ans)
        script = matches[0]

        return script
    else:
        # Code Generation Task
        py_files = file_matches[0]
        with open(py_files, 'r') as file:
            code = file.read()

        sys_prompt = (
            "You are an assistant that help generates python code."
            "Please give the correct code according to the output. "
        )
        usr_prompt = f"My code is {code}, and my script is {command.script}, but the terminal outputs {command.output}."
        
        # Send Query
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": usr_prompt}
            ],
            temperature=0.7,
            max_tokens=2048
        )

        # Print Answer
        ans = response['choices'][0]['message']['content']
        print(ans, file=sys.stderr)
        sys.exit(0)


def fix_command(known_args, gpt=False, wizard=False):
    """Fixes previous command. Used when `thefuck` called without arguments. If gpt = True, we use gpt4 to fix comamnd."""
    settings.init(known_args)
    with logs.debug_time('Total'):
        logs.debug(u'Run with settings: {}'.format(pformat(settings)))
        raw_command = _get_raw_command(known_args)

        try:
            command = types.Command.from_raw_script(raw_command)
        except EmptyCommand:
            logs.debug('Empty command, nothing to do')
            return

        # Use gpt or not?
        if gpt:
            script = qeury_gpt(command)
            corrected_commands = iter([CorrectedCommand(script, side_effect=None, priority=1e6)])
        elif wizard:
            script = qeury_wizard(command)
            corrected_commands = iter([CorrectedCommand(script, side_effect=None, priority=1e6)])
        else:
            corrected_commands = get_corrected_commands(command)

        selected_command = select_command(corrected_commands)

        if selected_command:
            selected_command.run(command)
        else:
            sys.exit(1)
