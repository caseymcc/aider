import sys
import json
import select
import re

from aider.io import InputOutput

class CommandIO(InputOutput):
    def __init__(
        self,
        yes=False,
        input_history_file=None,
        chat_history_file=None,
        encoding="utf-8",
        dry_run=False,
        llm_history_file=None,
    ):
        super().__init__(
            input_history_file=input_history_file,
            chat_history_file=chat_history_file,
            encoding=encoding,
            dry_run=dry_run,
            llm_history_file=llm_history_file,
        )

        self.edit_format:str = "whole"
        self.yes = yes
        self.input_buffer = ""
        self.input_decoder = json.JSONDecoder()

    def set_edit_format(self, edit_format):
        self.edit_format = edit_format
        
    def get_input(
        self,
        root,
        rel_fnames,
        addable_rel_fnames,
        commands,
        abs_read_only_fnames=None,
        edit_format=None
    ):
        obj = self.get_command()
        
        if obj:
            send, inp = self.run_command(obj, commands)

            if send:
                return inp
        
        return ""
    
    def get_command(self, wait = True):
        need_input = False
        
        while True:
            try:
                input_chunk = sys.stdin.readline()
                
#                print(f"read: {input_chunk}", flush=True)
                if not input_chunk and need_input:
                    if wait:
                        select.select([sys.stdin], [], [], 1)
                    else:
                        return None
                    
                if input_chunk:
                    self.input_buffer += input_chunk

                while self.input_buffer:
                    try:
                        obj, idx = self.input_decoder.raw_decode(self.input_buffer)
                        self.input_buffer = self.input_buffer[idx:].lstrip()
                        return obj
                        
                    except json.JSONDecodeError as e:
                        # If JSON is not complete, break
                        print(f"json not complete: {e.msg}", flush=True)
                        need_input = True
                        self.input_buffer.clear()
                        break

            except KeyboardInterrupt:
                break
        
        return ""
    
    #return Send, Input
    def run_command(self, obj, commands):
        cmd_list=commands.get_commands()
        
        cmd = obj.get('cmd')
        
        if cmd in cmd_list:
            return True, f"/{cmd} {' '.join(obj.get('value'))}"
        elif cmd == 'user':
            return True, obj.get('value')
        
        return False, ""
        
    def user_input(self, inp, log_only=True):
        msg = {
            "cmd": "user",
            "value": inp
        }
        print(json.dumps(msg), flush=True)
        return

    # OUTPUT
        
    def ai_output(self, content):
        hist = "\n" + content.strip() + "\n\n"
        self.append_chat_history(hist)
#        msg = {
#            "cmd": "ai",
#            "value": content,
#        }
#        print(json.dumps(msg), flush=True)
        
    def confirm_ask(
        self, 
        question, 
        default="y", 
        subject=None, 
        explicit_yes_required=False, 
        group=None,
        allow_never=False):
        msg = {
            "cmd": "prompt",
            "value": question,
            "default": default,
            "subject": subject,
            "explicit_yes_required": explicit_yes_required,
            "group": group,
            "allow_never": allow_never
        }
        print(json.dumps(msg), flush=True)
        
        obj = self.get_command()
        
        cmd = obj.get('cmd')
        res = "no"
        
        if cmd == "prompt_response":
            res = obj.get('value')

        hist = f"{question.strip()} {res.strip()}"
        self.append_chat_history(hist, linebreak=True, blockquote=True)
                
        return res.strip().lower().startswith("y")

    def prompt_ask(self, question, default="", subject=None):
        res = self.confirm_ask(question, default)
    
    def _tool_message(self, type, message="", strip=True):
        if message.strip():
            if "\n" in message:
                for line in message.splitlines():
                    self.append_chat_history(line, linebreak=True, blockquote=True, strip=strip)
            else:
                hist = message.strip() if strip else message
                self.append_chat_history(hist, linebreak=True, blockquote=True)

        if not message:
            return
                       
        msg = {
            "cmd": type,
            "value": json.dumps(message)
        }
        print(json.dumps(msg), flush=True)
        
    def tool_error(self, message="", strip=True):
        self.num_error_outputs += 1
        self._tool_message("error", message, strip)

    def tool_warning(self, message="", strip=True):
        self._tool_message("warning", message, strip)
        
    def tool_output(self, *messages, log_only=False, bold=False):
        message=" ".join(messages)
        
        if not message:
            return
        
        if messages:
            hist = message
            hist = f"{hist.strip()}"
            self.append_chat_history(hist, linebreak=True, blockquote=True)
            
        msg = {
            "cmd": "output",
            "value": json.dumps(message)
        }
        print(json.dumps(msg), flush=True)
        
    def assistant_output(self, message, pretty=None):
        if not message:
            return
        
        type = ""
        text = ""
        filename = ""
        code = ""
        
        if self.edit_format == "whole":
            pattern = re.compile(r"^(.*?)(?:\n){4}([\w\.]+)\n+```\n(.*?)```$", re.DOTALL)
            match = pattern.match(message)
            
            type = "whole"           
            text = match.group(1).strip()
            filename = match.group(2).strip()
            code = match.group(3).strip()
        elif self.edit_format == "diff":
            pattern = re.compile(r"^(.*?)(?:\n){4}([\w\.]+)\n+```\n(.*?)```$", re.DOTALL)
            
            match = pattern.match(message)
            
            type = "diff"
            text = match.group(1).strip()
            filename = match.group(2).strip()
            code = match.group(3).strip()
        
        msg = {
            "cmd": "assistant",
            "type": type,
            "value": json.dumps(text),
            "filename": filename,
            "code": code
        }
        print(json.dumps(msg), flush=True)
        
    def print(self, message=""):
        if not message:
            return
        
        msg = {
            "cmd": "print",
            "value": json.dumps(message)
        }
        print(json.dumps(msg), flush=True)
