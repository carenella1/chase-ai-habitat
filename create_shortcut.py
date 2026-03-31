# =============================================================
# CHASE AI HABITAT — SHORTCUT INSTALLER
# create_shortcut.py
#
# Run this ONCE:
#   python create_shortcut.py
#
# What it does:
#   1. Generates a custom cyan hexagon .ico icon file
#   2. Creates a proper Windows .lnk shortcut on your Desktop
#   3. The shortcut launches the Habitat with NO terminal window
#   4. You can then pin it to your taskbar like any other app
#
# After running this, just double-click the desktop icon.
# No terminal. No bat file. One click.
# =============================================================

import os
import sys
import struct
import subprocess

PROJECT_ROOT = r"C:\Users\User\Desktop\Github\chase-ai-habitat"
ICON_OUTPUT = os.path.join(PROJECT_ROOT, "static", "habitat.ico")
SHORTCUT_NAME = "Chase AI Habitat"


# =============================================================
# STEP 1: GENERATE THE .ICO ICON FILE
# =============================================================
# We generate a proper Windows .ico file in your cyberpunk style:
# dark background, glowing cyan hexagon, no external dependencies.
# This gets saved to static/habitat.ico


def generate_icon():
    """
    Creates a cyan hexagon icon as a proper Windows .ico file.
    Uses only Pillow — no internet, no external tools.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import math

        print("Generating icon...")

        sizes = [256, 128, 64, 48, 32, 16]
        images = []

        for size in sizes:
            img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            cx, cy = size // 2, size // 2
            r_outer = int(size * 0.44)
            r_inner = int(size * 0.36)
            r_dot = int(size * 0.10)

            # --- Draw outer glow (soft cyan ring) ---
            glow_steps = 6
            for i in range(glow_steps, 0, -1):
                alpha = int(30 * (i / glow_steps))
                glow_r = r_outer + i * max(1, size // 40)
                glow_pts = _hex_points(cx, cy, glow_r, offset_angle=90)
                draw.polygon(glow_pts, fill=(0, 255, 255, alpha))

            # --- Dark background hexagon ---
            bg_pts = _hex_points(cx, cy, r_outer, offset_angle=90)
            draw.polygon(bg_pts, fill=(4, 8, 20, 255))

            # --- Cyan border hexagon ---
            border_thickness = max(1, size // 20)
            for t in range(border_thickness):
                border_pts = _hex_points(cx, cy, r_outer - t, offset_angle=90)
                draw.polygon(border_pts, outline=(0, 255, 255, 255), fill=None)

            # --- Inner hexagon outline ---
            inner_pts = _hex_points(cx, cy, r_inner, offset_angle=90)
            for t in range(max(1, size // 40)):
                inner_p = _hex_points(cx, cy, r_inner - t, offset_angle=90)
                draw.polygon(inner_p, outline=(0, 180, 200, 160), fill=None)

            # --- Center dot ---
            draw.ellipse(
                [cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot],
                fill=(0, 255, 255, 255),
            )

            # --- Small corner dots (cyberpunk detail) ---
            if size >= 32:
                dot_r = max(1, size // 20)
                for angle_deg in [30, 90, 150, 210, 270, 330]:
                    angle = math.radians(angle_deg)
                    dx = int(cx + r_inner * 0.7 * math.cos(angle))
                    dy = int(cy - r_inner * 0.7 * math.sin(angle))
                    draw.ellipse(
                        [dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r],
                        fill=(0, 200, 220, 180),
                    )

            images.append(img)

        # Save as .ico with all sizes embedded
        os.makedirs(os.path.dirname(ICON_OUTPUT), exist_ok=True)
        images[0].save(
            ICON_OUTPUT,
            format="ICO",
            sizes=[(s, s) for s in sizes],
            append_images=images[1:],
        )
        print(f"Icon saved: {ICON_OUTPUT}")
        return True

    except ImportError:
        print("Pillow not installed - using fallback icon method")
        return _generate_minimal_ico()
    except Exception as e:
        print(f"Icon generation error: {e}")
        return _generate_minimal_ico()


def _hex_points(cx, cy, r, offset_angle=0):
    """Calculate the 6 corner points of a hexagon."""
    import math

    points = []
    for i in range(6):
        angle = math.radians(offset_angle + i * 60)
        x = cx + r * math.cos(angle)
        y = cy - r * math.sin(angle)
        points.append((x, y))
    return points


def _generate_minimal_ico():
    """
    Fallback: generate a bare-minimum valid .ico file using raw bytes.
    This creates a simple 32x32 cyan square icon without needing Pillow.
    Plain English: If Pillow isn't available, we still produce a valid
    icon file by writing the raw binary data ourselves.
    """
    try:
        print("Generating minimal fallback icon...")

        # 32x32 RGBA pixels — cyan square with dark center
        width, height = 32, 32
        pixels = []
        for y in range(height):
            for x in range(width):
                # Border = cyan, interior = dark
                if x < 2 or x >= width - 2 or y < 2 or y >= height - 2:
                    pixels.extend([255, 255, 0, 255])  # BGRA: cyan
                elif 10 <= x <= 21 and 10 <= y <= 21:
                    pixels.extend([255, 200, 0, 255])  # center dot
                else:
                    pixels.extend([20, 8, 4, 255])  # dark bg
        pixel_data = bytes(pixels)

        # BMP header for ICO (BITMAPINFOHEADER)
        bmp_header = struct.pack(
            "<IiiHHIIiiII",
            40,  # header size
            width,  # width
            height * 2,  # height (doubled for ICO format)
            1,  # color planes
            32,  # bits per pixel
            0,  # compression (none)
            len(pixel_data),
            0,
            0,
            0,
            0,
        )

        # Flip rows (BMP is bottom-up)
        row_size = width * 4
        rows = [
            pixel_data[i : i + row_size] for i in range(0, len(pixel_data), row_size)
        ]
        flipped = b"".join(reversed(rows))

        image_data = bmp_header + flipped

        # ICO file structure
        ico_header = struct.pack("<HHH", 0, 1, 1)  # reserved, type=1 (ICO), count=1
        ico_entry = struct.pack(
            "<BBBBHHII",
            width,
            height,
            0,
            0,  # width, height, color count, reserved
            1,
            32,  # planes, bit count
            len(image_data),  # size of image data
            6 + 16,  # offset to image data (after header + 1 entry)
        )

        os.makedirs(os.path.dirname(ICON_OUTPUT), exist_ok=True)
        with open(ICON_OUTPUT, "wb") as f:
            f.write(ico_header + ico_entry + image_data)

        print(f"Fallback icon saved: {ICON_OUTPUT}")
        return True

    except Exception as e:
        print(f"Could not generate fallback icon: {e}")
        return False


# =============================================================
# STEP 2: CREATE A SILENT LAUNCHER WRAPPER
# =============================================================
# This creates a tiny .pyw file (Python with no console window)
# that the shortcut points to. .pyw files are identical to .py
# except Windows doesn't show a terminal window when you run them.


def create_silent_launcher():
    """
    Creates launch_habitat_silent.pyw — same as launch_habitat.py
    but with NO console window on double-click.
    Plain English: .pyw = Python Window-less. The app opens
    directly with no black terminal box appearing first.
    """
    pyw_path = os.path.join(PROJECT_ROOT, "launch_habitat_silent.pyw")

    # This just imports and runs your main launcher
    content = """# Silent launcher — no console window
# This file is called by the desktop shortcut
# It simply runs launch_habitat.py without showing a terminal

import sys
import os

# Make sure we run from the project directory
os.chdir(r"C:\\Users\\User\\Desktop\\Github\\chase-ai-habitat")
sys.path.insert(0, r"C:\\Users\\User\\Desktop\\Github\\chase-ai-habitat")

# Run the main launcher
exec(open(r"C:\\Users\\User\\Desktop\\Github\\chase-ai-habitat\\launch_habitat.py").read())
"""

    with open(pyw_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Silent launcher created: {pyw_path}")
    return pyw_path


# =============================================================
# STEP 3: CREATE THE WINDOWS DESKTOP SHORTCUT (.lnk)
# =============================================================


def create_desktop_shortcut(icon_path, pyw_path):
    """
    Creates a proper Windows .lnk shortcut on the Desktop.
    Uses PowerShell's WScript.Shell — built into every Windows machine,
    no extra installs needed.
    Plain English: This is the exact same method Windows uses
    internally when you 'Create Shortcut' from right-click menu.
    """
    # Find the desktop path (works even if Desktop is in OneDrive)
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.exists(desktop):
        # Try OneDrive Desktop
        onedrive_desktop = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
        if os.path.exists(onedrive_desktop):
            desktop = onedrive_desktop

    shortcut_path = os.path.join(desktop, f"{SHORTCUT_NAME}.lnk")

    # Find pythonw.exe (the windowless Python interpreter)
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    if not os.path.exists(pythonw):
        # Try habitat-env
        pythonw = os.path.join(PROJECT_ROOT, "habitat-env", "Scripts", "pythonw.exe")
    if not os.path.exists(pythonw):
        # Fallback to regular python
        pythonw = sys.executable
        print(
            "Note: pythonw.exe not found, using python.exe (terminal may flash briefly)"
        )

    print(f"Creating shortcut at: {shortcut_path}")
    print(f"  Target: {pythonw}")
    print(f"  Script: {pyw_path}")
    print(f"  Icon:   {icon_path}")

    # PowerShell script to create the .lnk file
    ps_script = f"""
$WScriptShell = New-Object -ComObject WScript.Shell
$Shortcut = $WScriptShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{pythonw}"
$Shortcut.Arguments = '"{pyw_path}"'
$Shortcut.WorkingDirectory = "{PROJECT_ROOT}"
$Shortcut.IconLocation = "{icon_path}"
$Shortcut.Description = "Chase AI Habitat - Cognitive Desktop AI"
$Shortcut.WindowStyle = 7
$Shortcut.Save()
Write-Host "Shortcut created successfully"
"""

    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            print(f"Desktop shortcut created successfully!")
            print(f"Location: {shortcut_path}")
            return shortcut_path
        else:
            print(f"PowerShell error: {result.stderr}")
            return None

    except Exception as e:
        print(f"Shortcut creation error: {e}")
        return None


# =============================================================
# STEP 4: PIN TO TASKBAR INSTRUCTIONS
# =============================================================


def show_completion_dialog(shortcut_path):
    """
    Shows a success dialog with instructions for pinning to taskbar.
    """
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()

    if shortcut_path:
        messagebox.showinfo(
            "Chase AI Habitat — Setup Complete!",
            f"Desktop shortcut created successfully!\n\n"
            f"Location: {shortcut_path}\n\n"
            f"TO LAUNCH:\n"
            f"  Double-click the 'Chase AI Habitat' icon on your Desktop\n\n"
            f"TO PIN TO TASKBAR:\n"
            f"  1. Double-click the shortcut to launch the app\n"
            f"  2. While it's open, right-click the taskbar icon\n"
            f"  3. Select 'Pin to taskbar'\n"
            f"  4. Done — one-click launch forever\n\n"
            f"Ollama starts automatically. No terminal needed.",
        )
    else:
        messagebox.showerror(
            "Shortcut Creation Failed",
            "Could not create the desktop shortcut automatically.\n\n"
            "Manual steps:\n"
            f"1. Right-click your Desktop\n"
            f"2. New > Shortcut\n"
            f"3. Target: pythonw.exe\n"
            f"4. Arguments: \"{os.path.join(PROJECT_ROOT, 'launch_habitat_silent.pyw')}\"\n"
            f"5. Change icon: {ICON_OUTPUT}",
        )

    root.destroy()


# =============================================================
# MAIN
# =============================================================
def main():
    print("=" * 55)
    print("  CHASE AI HABITAT — SHORTCUT INSTALLER")
    print("=" * 55)
    print()

    # Step 1: Generate icon
    print("[1/3] Generating icon...")
    icon_ok = generate_icon()
    icon_path = ICON_OUTPUT if icon_ok and os.path.exists(ICON_OUTPUT) else ""

    # Step 2: Create silent launcher
    print("\n[2/3] Creating silent launcher...")
    pyw_path = create_silent_launcher()

    # Step 3: Create desktop shortcut
    print("\n[3/3] Creating desktop shortcut...")
    shortcut_path = create_desktop_shortcut(icon_path, pyw_path)

    print()
    print("=" * 55)

    # Show result dialog
    show_completion_dialog(shortcut_path)

    if shortcut_path:
        print("  SETUP COMPLETE")
        print(f"  Shortcut: {shortcut_path}")
        print()
        print("  To pin to taskbar:")
        print("  1. Launch the app from the desktop icon")
        print("  2. Right-click the taskbar icon")
        print("  3. Pin to taskbar")
    else:
        print("  Shortcut creation failed - see errors above")

    print("=" * 55)


if __name__ == "__main__":
    main()
