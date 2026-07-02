import os
import subprocess
import sys


def should_launch_streamlit(argv):
    return len(argv) >= 3 and argv[1] == "-m" and argv[2] == "streamlit"


def launch_streamlit(file_path, argv):
    script_args = []
    if len(argv) > 3:
        script_args = argv[3:]

    cmd = [sys.executable, "-m", "streamlit", "run", file_path] + script_args
    os.execv(sys.executable, cmd)
