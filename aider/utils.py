import itertools
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import git

from aider.dump import dump  # noqa: F401

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}


class IgnorantTemporaryDirectory:
    def __init__(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def __enter__(self):
        return self.temp_dir.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self):
        try:
            self.temp_dir.cleanup()
        except (OSError, PermissionError):
            pass  # Ignore errors (Windows)

    def __getattr__(self, item):
        return getattr(self.temp_dir, item)


class ChdirTemporaryDirectory(IgnorantTemporaryDirectory):
    def __init__(self):
        try:
            self.cwd = os.getcwd()
        except FileNotFoundError:
            self.cwd = None

        super().__init__()

    def __enter__(self):
        res = super().__enter__()
        os.chdir(self.temp_dir.name)
        return res

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cwd:
            try:
                os.chdir(self.cwd)
            except FileNotFoundError:
                pass
        super().__exit__(exc_type, exc_val, exc_tb)


class GitTemporaryDirectory(ChdirTemporaryDirectory):
    def __enter__(self):
        dname = super().__enter__()
        self.repo = make_repo(dname)
        return dname

    def __exit__(self, exc_type, exc_val, exc_tb):
        del self.repo
        super().__exit__(exc_type, exc_val, exc_tb)


def make_repo(path=None):
    if not path:
        path = "."
    repo = git.Repo.init(path)
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "testuser@example.com").release()

    return repo


def is_image_file(file_name):
    """
    Check if the given file name has an image file extension.

    :param file_name: The name of the file to check.
    :return: True if the file is an image, False otherwise.
    """
    file_name = str(file_name)  # Convert file_name to string
    return any(file_name.endswith(ext) for ext in IMAGE_EXTENSIONS)


def safe_abs_path(res):
    "Gives an abs path, which safely returns a full (not 8.3) windows path"
    res = Path(res).resolve()
    return str(res)


def format_content(role, content):
    formatted_lines = []
    for line in content.splitlines():
        formatted_lines.append(f"{role} {line}")
    return "\n".join(formatted_lines)


def format_messages(messages, title=None):
    output = []
    if title:
        output.append(f"{title.upper()} {'*' * 50}")

    for msg in messages:
        output.append("")
        role = msg["role"].upper()
        content = msg.get("content")
        if isinstance(content, list):  # Handle list content (e.g., image messages)
            for item in content:
                if isinstance(item, dict) and "image_url" in item:
                    output.append(f"{role} Image URL: {item['image_url']['url']}")
        elif isinstance(content, str):  # Handle string content
            output.append(format_content(role, content))
        content = msg.get("function_call")
        if content:
            output.append(f"{role} {content}")

    return "\n".join(output)


def show_messages(messages, title=None, functions=None):
    formatted_output = format_messages(messages, title)
    print(formatted_output)

    if functions:
        dump(functions)


def split_chat_history_markdown(text, include_tool=False):
    messages = []
    user = []
    assistant = []
    tool = []
    lines = text.splitlines(keepends=True)

    def append_msg(role, lines):
        lines = "".join(lines)
        if lines.strip():
            messages.append(dict(role=role, content=lines))

    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("> "):
            append_msg("assistant", assistant)
            assistant = []
            append_msg("user", user)
            user = []
            tool.append(line[2:])
            continue
        # if line.startswith("#### /"):
        #    continue

        if line.startswith("#### "):
            append_msg("assistant", assistant)
            assistant = []
            append_msg("tool", tool)
            tool = []

            content = line[5:]
            user.append(content)
            continue

        append_msg("user", user)
        user = []
        append_msg("tool", tool)
        tool = []

        assistant.append(line)

    append_msg("assistant", assistant)
    append_msg("user", user)

    if not include_tool:
        messages = [m for m in messages if m["role"] != "tool"]

    return messages

def get_pip_install(args):
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
    ]
    cmd += args
    return cmd


def run_install(cmd):
    print()
    print("Installing: ", " ".join(cmd))

    try:
        output = []
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        last_update = time.time()
        update_interval = 0.2  # 5 times per second

        while True:
            char = process.stdout.read(1)
            if not char:
                break

            output.append(char)

            current_time = time.time()
            if current_time - last_update >= update_interval:
                print(f" Installing... {next(spinner)}", end="\r", flush=True)
                last_update = current_time

        return_code = process.wait()
        output = "".join(output)

        if return_code == 0:
            print("\rInstallation complete.")
            print()
            return True, output

    except subprocess.CalledProcessError as e:
        print(f"\nError running pip install: {e}")

    print("\nInstallation failed.\n")

    return False, output


def check_pip_install_extra(io, module, prompt, pip_install_cmd):
    try:
        __import__(module)
        return True
    except (ImportError, ModuleNotFoundError):
        pass

    cmd = get_pip_install(pip_install_cmd)

    text = f"{prompt}:\n\n{' '.join(cmd)}\n"
    io.tool_error(text)

    if not io.confirm_ask("Run pip install?", default="y"):
        return

    success, output = run_install(cmd)
    if success:
        try:
            __import__(module)
            return True
        except (ImportError, ModuleNotFoundError) as err:
            io.tool_error(str(err))
            pass

    io.tool_error(output)

    print()
    print(f"Failed to install {pip_install_cmd[0]}")
    
def get_file_mentions(rel_fname, addable_rel_fnames, content):
    words = set(word for word in content.split())

    # drop sentence punctuation from the end
    words = set(word.rstrip(",.!;:") for word in words)

    # strip away all kinds of quotes
    quotes = "".join(['"', "'", "`"])
    words = set(word.strip(quotes) for word in words)

    addable_rel_fnames = self.get_addable_relative_files()

    mentioned_rel_fnames = set()
    fname_to_rel_fnames = {}
    for rel_fname in addable_rel_fnames:
        normalized_rel_fname = rel_fname.replace("\\", "/")
        normalized_words = set(word.replace("\\", "/") for word in words)
        if normalized_rel_fname in normalized_words:
            mentioned_rel_fnames.add(rel_fname)

        fname = os.path.basename(rel_fname)

        # Don't add basenames that could be plain words like "run" or "make"
        if "/" in fname or "\\" in fname or "." in fname or "_" in fname or "-" in fname:
            if fname not in fname_to_rel_fnames:
                fname_to_rel_fnames[fname] = []
            fname_to_rel_fnames[fname].append(rel_fname)

    for fname, rel_fnames in fname_to_rel_fnames.items():
        if len(rel_fnames) == 1 and fname in words:
            mentioned_rel_fnames.add(rel_fnames[0])

    return mentioned_rel_fnames
        
def check_for_urls(self, inp):
    url_pattern = re.compile(r"(https?://[^\s/$.?#].[^\s]*[^\s,.])")
    urls = list(set(url_pattern.findall(inp)))  # Use set to remove duplicates
#        added_urls = []
#        for url in urls:
#            if url not in self.rejected_urls:
#                if self.io.confirm_ask(f"Add {url} to the chat?"):
#                    inp += "\n\n"
#                    inp += self.commands.cmd_web(url)
#                    added_urls.append(url)
#                else:
#                    self.rejected_urls.add(url)
#
#        return added_urls
    return inp