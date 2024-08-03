import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.shortcuts import CompleteStyle, PromptSession, prompt
from prompt_toolkit.styles import Style
from pygments.lexers import MarkdownLexer, guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound
from rich.console import Console
from rich.text import Text

from aider.coders import Command, CommandResults, Coder
from aider import utils

from aider.versioncheck import check_version

class AutoCompleter(Completer):
    def __init__(self, root, rel_fnames, addable_rel_fnames, commands, encoding):
        self.addable_rel_fnames = addable_rel_fnames
        self.rel_fnames = rel_fnames
        self.encoding = encoding

        fname_to_rel_fnames = defaultdict(list)
        for rel_fname in addable_rel_fnames:
            fname = os.path.basename(rel_fname)
            if fname != rel_fname:
                fname_to_rel_fnames[fname].append(rel_fname)
        self.fname_to_rel_fnames = fname_to_rel_fnames

        self.words = set()

        self.commands = commands
        self.command_completions = dict()
        if commands:
            self.command_names = self.commands.get_commands(False)

        for rel_fname in addable_rel_fnames:
            self.words.add(rel_fname)

        for rel_fname in rel_fnames:
            self.words.add(rel_fname)

            fname = Path(root) / rel_fname
            try:
                with open(fname, "r", encoding=self.encoding) as f:
                    content = f.read()
            except (FileNotFoundError, UnicodeDecodeError, IsADirectoryError):
                continue
            try:
                lexer = guess_lexer_for_filename(fname, content)
            except ClassNotFound:
                continue
            tokens = list(lexer.get_tokens(content))
            self.words.update(token[1] for token in tokens if token[0] in Token.Name)

    def get_command_completions(self, text, words):
        candidates = []
        if len(words) == 1 and not text[-1].isspace():
            partial = words[0].lower()[1:]
            candidates = [cmd for cmd in self.command_names if cmd.startswith(partial)]
            return candidates

        if len(words) <= 1:
            return []
        if text[-1].isspace():
            return []

        cmd = words[0]
        partial = words[-1].lower()

        if cmd not in self.command_names:
            return

        if cmd not in self.command_completions:
            candidates = self.commands.get_completions(cmd)
            self.command_completions[cmd] = candidates
        else:
            candidates = self.command_completions[cmd]

        if candidates is None:
            return

        candidates = [word for word in candidates if partial in word.lower()]
        return candidates

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        words = text.split()
        if not words:
            return

        if text[0] == "/":
            candidates = self.get_command_completions(text, words)
            if candidates is not None:
                for candidate in candidates:
                    yield Completion(candidate, start_position=-len(words[-1]))
                return

        candidates = self.words
        candidates.update(set(self.fname_to_rel_fnames))
        candidates = [(word, f"`{word}`") for word in candidates]

        last_word = words[-1]
        for word_match, word_insert in candidates:
            if word_match.lower().startswith(last_word.lower()):
                rel_fnames = self.fname_to_rel_fnames.get(word_match, [])
                if rel_fnames:
                    for rel_fname in rel_fnames:
                        yield Completion(
                            f"`{rel_fname}`", start_position=-len(last_word), display=rel_fname
                        )
                else:
                    yield Completion(
                        word_insert, start_position=-len(last_word), display=word_match
                    )


class Terminal:
    num_error_outputs = 0
    num_user_asks = 0

    def __init__(
        self,
        pretty=True,
        yes=False,
        input=None,
        output=None,
        user_input_color="blue",
        tool_output_color=None,
        tool_error_color="red",
        encoding="utf-8",
        dry_run=False,
        editingmode=EditingMode.EMACS,
    ):
        self.editingmode = editingmode
        self.rel_fnames = []
        self.addable_rel_fnames = []
        no_color = os.environ.get("NO_COLOR")
        if no_color is not None and no_color != "":
            pretty = False

        self.user_input_color = user_input_color if pretty else None
        self.tool_output_color = tool_output_color if pretty else None
        self.tool_error_color = tool_error_color if pretty else None

        self.input = input
        self.output = output

        self.pretty = pretty
        if self.output:
            self.pretty = False

        self.yes = yes
        self.encoding = encoding
        self.dry_run = dry_run
        
        self.root = None
        self.command_list = None

        if pretty:
            self.console = Console()
        else:
            self.console = Console(force_terminal=False, no_color=True)

    def update_files(self, coder):
        self.rel_fnames = coder.get_inchat_relative_files()
        self.addable_rel_fnames = coder.get_addable_relative_files()
            
    def update_coder(self, coder):
        self.root = coder.root
        self.command_list=coder.commands.get_commands(False)
        
#    def start(self, coder):
#        self.update_coder(coder)
#        self.update_files(coder)
#        
#        while True:
#            try:
#                commands = self.get_input(coder)
#                
#                for command in commands:
#                    
#                    if command.type == "exit":
#                        coder.stop()
#                        return
#                
#                    coder.run_command(command.type, command.input)
#                
#
#            except SwitchModel as switch:
#                coder = Coder.create(main_model=switch.model, from_coder=coder)
#                self.update_coder(coder)
#                coder.show_announcements()
                
    def get_input(self, coder):
        if self.pretty:
            style = dict(style=self.user_input_color) if self.user_input_color else dict()
            self.console.rule(**style)
        else:
            print()

        show = " ".join(self.rel_fnames)
        if len(show) > 10:
            show += "\n"
        show += "> "

        inp = ""
        multiline_input = False

        if self.user_input_color:
            style = Style.from_dict(
                {
                    "": self.user_input_color,
                    "pygments.literal.string": f"bold italic {self.user_input_color}",
                }
            )
        else:
            style = None

        completer_instance = AutoCompleter(
            self.root, self.rel_fnames, self.addable_rel_fnames, coder.commands, self.encoding
        )

        while True:
            if multiline_input:
                show = ". "

            session_kwargs = {
                "message": show,
                "completer": completer_instance,
                "reserve_space_for_menu": 4,
                "complete_style": CompleteStyle.MULTI_COLUMN,
                "input": self.input,
                "output": self.output,
                "lexer": PygmentsLexer(MarkdownLexer),
            }
            if style:
                session_kwargs["style"] = style

            kb = KeyBindings()

            @kb.add("escape", "c-m", eager=True)
            def _(event):
                event.current_buffer.insert_text("\n")

            session = PromptSession(
                key_bindings=kb, editing_mode=self.editingmode, **session_kwargs
            )
            line = session.prompt()

            print(f"line {line}")
            if line and line[0] == "{" and not multiline_input:
                multiline_input = True
                inp += line[1:] + "\n"
                continue
            elif line and line[-1] == "}" and multiline_input:
                inp += line[:-1] + "\n"
                break
            elif multiline_input:
                inp += line + "\n"
            else:
                inp = line
                break

        print()
        self.user_input(inp)
        return inp

    def init_before_message(self):
        self.reflected_message = None
        self.num_reflections = 0
        self.lint_outcome = None
        self.test_outcome = None
        self.edit_outcome = None
        
    def run(self, coder, with_message=None):
        self.update_coder(coder)
        self.update_files(coder)
        
        while True:
            self.init_before_message()

            try:
                if with_message:
                    new_user_message = with_message
                    self.user_input(with_message)
                else:
                    new_user_message = self.run_loop(coder)

                while new_user_message:
                    self.reflected_message = None
                    list(coder.send_new_user_message(new_user_message))

                    new_user_message = None
                    if self.reflected_message:
                        if self.num_reflections < self.max_reflections:
                            self.num_reflections += 1
                            new_user_message = self.reflected_message
                        else:
                            self.print_error(
                                f"Only {self.max_reflections} reflections allowed, stopping."
                            )

                if with_message:
                    return self.partial_response_content

            except KeyboardInterrupt:
                self.keyboard_interrupt()
            except EOFError:
                return
    
    def run_loop(self, coder):
        inp = self.get_input(coder)

        if not inp:
            return
        
        if(inp[0] in "/!"):
            type, input = self.parse_command(inp[1:])
            
            response = coder.run_command(type, input)
            
            if type == 'add`:
                if len(missing_fnames) > 0:
                    
                
            if type == "add" or type == "remove":
                self.update_files(coder)
                
            if response:
                self.print(response)
                
            return 

        self.check_for_file_mentions(inp)
        self.check_for_urls(inp)

        return inp
    
    def parse_command(self, inp):
        parts = inp.split(" ", 1)
        type = parts[0]
        input = parts[1] if len(parts) > 1 else ""
        return type, input

    def user_input(self, inp, log_only=True):
        if not log_only:
            style = dict(style=self.user_input_color) if self.user_input_color else dict()
            self.console.print(inp, **style)

    def check_for_file_mentions(self, content):
        mentioned_rel_fnames = utils.get_file_mentions(self.rel_fnames, self.addable_rel_fnames, content)

        if not mentioned_rel_fnames:
            return

        for rel_fname in mentioned_rel_fnames:
            self.print(rel_fname)

        if not self.confirm_ask("Add these files to the chat?"):
            return

        for rel_fname in mentioned_rel_fnames:
            self.coder.run_command("add", rel_fname)

        return prompts.added_files.format(fnames=", ".join(mentioned_rel_fnames))
    
    def check_for_urls(self, inp):
        urls = utils.check_for_urls(inp)
        
        for url in urls:
            if self.confirm_ask(f"Add {url} to the chat?"):
                self.coder.run_command("web", url)
                
    def check_version(self):
        update_available, info = check_version()
        
        if not update_available:
            return
        
        cmd = utils.get_pip_install(["--upgrade", "aider-chat"])

        text = f"""
    Newer aider version v{info} is available. To upgrade, run:

        {' '.join(cmd)}
    """

        if self.confirm_ask("Run pip install?"):
            success, _output = utils.run_install(cmd)
            if success:
                self.print("Re-run aider to use new version.")
                sys.exit()


    # OUTPUT
    def confirm_ask(self, question, default="y"):
        if self.yes is True:
            res = "yes"
        elif self.yes is False:
            res = "no"
        else:
            res = prompt(question + " ", default=default)

        return res.strip().lower().startswith("y")

    def prompt_ask(self, question, default=None):
        self.num_user_asks += 1

        if self.yes is True:
            res = "yes"
        elif self.yes is False:
            res = "no"
        else:
            res = prompt(question + " ", default=default)

        hist = f"{question.strip()} {res.strip()}"

        if self.yes in (True, False):
            self.print(hist)

        return res

    def print(self, *messages, log_only=False):
        if not log_only:
            messages = list(map(Text, messages))
            style = dict(style=self.tool_output_color) if self.tool_output_color else dict()
            self.console.print(*messages, **style)
            
    def print_error(self, message="", strip=True):
        message = Text(message)
        style = dict(style=self.tool_error_color) if self.tool_error_color else dict()
        self.console.print(message, **style)
