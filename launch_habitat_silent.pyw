# Silent launcher — no console window
# This file is called by the desktop shortcut
# It simply runs launch_habitat.py without showing a terminal

import sys
import os

# Make sure we run from the project directory
os.chdir(r"C:\Users\User\Desktop\Github\chase-ai-habitat")
sys.path.insert(0, r"C:\Users\User\Desktop\Github\chase-ai-habitat")

# Run the main launcher
exec(open(r"C:\Users\User\Desktop\Github\chase-ai-habitat\launch_habitat.py").read())
