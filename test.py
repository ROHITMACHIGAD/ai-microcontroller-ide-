"""
Arduino Gemini IDE

A robust, professional-grade Python Tkinter-based desktop IDE designed for generating,
editing, uploading, and monitoring Arduino projects with Google Gemini code generation
and auto-fix, supporting auto library installation and real-time serial communication.
"""

import os
import sys
import re
import subprocess
import threading
import requests
import tempfile
from urllib.parse import urlparse
from tinydb import TinyDB
import serial
import serial.tools.list_ports
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, scrolledtext
import google.generativeai as genai

# ===============================
#        CONFIGURATION
# ===============================

API_KEY = "YOUR_ACTUAL_KEY"  # Replace with your real key!
ARDUINO_CLI_PATH = r"PATH_TO_YOUR_CLI"   # Adjust to your Arduino CLI path
LIB_INSTALL_MAX_ATTEMPTS = 5
GEMINI_MODEL_NAME = "YOUR_MODEL_NAME_HERE"
LIBRARY_ZIP_DOWNLOAD_DIR = "D:\micro_gemini\downloads"
DEFAULT_SKETCH_NAME = "micro_gemini.ino"

BOARD_OPTIONS = {
    "Arduino Uno": "arduino:avr:uno",
    "Arduino Mega": "arduino:avr:mega",
    "Arduino Nano": "arduino:avr:nano",
    "Arduino Leonardo": "arduino:avr:leonardo",
    "Arduino Nano Every": "arduino:megaavr:nanoevery",
    "Arduino Due": "arduino:sam:due",
    "Arduino MKR Zero": "arduino:samd:mkrzero",
    "ESP32 Dev": "esp32:esp32:esp32",
    "NodeMCU 1.0 (ESP-12E Module)": "esp8266:esp8266:nodemcuv2"
    # (add more boards as necessary)
}

# ===============================
# Local tinydb database for project state management
# ===============================

DB = TinyDB('project_db.json')

# ===============================
#     THEMING & GLOBAL STATE
# ===============================

DARK_BG = "#101216"
MID_BG = "#24252a"
BUTTON_BG = "#f1f1f5"
BUTTON_FG = "#222"
ACCENT = "#39ff14"
FONT = "Segoe UI"
MONO = "Consolas"

# ===============================
# Initialize Google Gemini AI
# ===============================

genai.configure(api_key=API_KEY)

# ===============================
#  Standard Output Redirection
# ===============================

class TkinterOutputLogger:
    def __init__(self, text_widget, real_stream):
        self.text_widget = text_widget
        self.real_stream = real_stream

    def write(self, message):
        self.real_stream.write(message)
        self.real_stream.flush()
        if self.text_widget:
            def append():
                self.text_widget.config(state=tk.NORMAL)
                self.text_widget.insert(tk.END, message)
                self.text_widget.see(tk.END)
                self.text_widget.config(state=tk.DISABLED)
            self.text_widget.after(0, append)

    def flush(self):
        self.real_stream.flush()



current_project_dir = os.getcwd()
current_sketch_path = os.path.join(current_project_dir, DEFAULT_SKETCH_NAME)
current_board = None  # will be initialized later as tk.StringVar
sketch_content_cache = ""
last_generated_path = current_sketch_path

# ===============================
#     GLOBALS AND UTILITIES
# ===============================

def log(msg):
    print(msg, flush=True)

def run_subprocess(cmd, capture_output=True):
    try:
        result = subprocess.run(cmd, capture_output=capture_output, text=True, check=False)
        return (result.returncode == 0, result.stdout if capture_output else "")
    except Exception as e:
        return (False, str(e))

def clean_code(code):
    cleaned_lines = []
    for line in code.splitlines():
        stripped = line.strip()
        if (stripped.startswith("```")
            or stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.startswith("*/")):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def extract_first_url(text):
    url_pattern = r"https?://[^\s$$>$$\}]+"
    match = re.search(url_pattern, text)
    if match:
        url = match.group(0)
        return url.rstrip('.*_~`<>[](){}')
    return None

def get_fqbn():
    return BOARD_OPTIONS.get(current_board.get().strip(), "")

# ===============================
#     ARDUINO INTERFACE
# ===============================

def list_ports():
    ports = list(serial.tools.list_ports.comports())
    log("Available serial ports:")
    for port in ports:
        log(f"Device: {port.device}, Description: {port.description}, HWID: {port.hwid}")
    return ports

def find_arduino_port(ports):
    for port in ports:
        if port.manufacturer and "Arduino" in port.manufacturer:
            log(f"\nAuto-detected Arduino on port: {port.device}")
            return port.device
        if "Arduino" in port.description:
            log(f"\nAuto-detected Arduino on port: {port.device}")
            return port.device
    if ports:
        log(f"Could not auto-detect Arduino. Using first available port: {ports[0].device}")
        return ports[0].device
    else:
        log("No serial ports detected. Please check your connection.")
        return None

def upload_code(arduino_cli_path, sketch_path, fqbn, port):
    try:
        log(f"Compiling sketch {sketch_path} for board {fqbn}...")
        compile_command = [
            arduino_cli_path,
            "compile",
            "--fqbn", fqbn,
            sketch_path,
        ]
        compile_result = subprocess.run(compile_command, check=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True)
        log(compile_result.stdout)

        log(f"Uploading sketch to port {port}...")
        upload_command = [
            arduino_cli_path,
            "upload",
            "--fqbn", fqbn,
            "--port", port,
            sketch_path,
        ]
        upload_result = subprocess.run(upload_command, check=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True)
        log(upload_result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        log(f"Upload failed:\n{e.output}")
        return False
    except Exception as e:
        log(f"Unexpected Error: {e}")
        return False

def compile_sketch(sketch_path, fqbn):
    try:
        log(f"Compiling sketch {sketch_path} for board {fqbn} ...")
        cmd = [ARDUINO_CLI_PATH, "compile", "--fqbn", fqbn, sketch_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout + "\n" + result.stderr
        log(output)
        return (result.returncode == 0, output)
    except Exception as e:
        log(f"Compilation error: {e}")
        return (False, str(e))

# ===============================
#    LIBRARY MANAGEMENT
# ===============================

def list_arduino_libraries():
    success, output = run_subprocess([ARDUINO_CLI_PATH, "lib", "list"])
    if not success:
        log("[Error] Cannot list Arduino libraries.")
        return []
    libs = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Assume first word is library name, or entire line if you want
        lib_name = line.split()[0]
        libs.append(lib_name)
    return libs

def library_installed(lib):
    lib_lower = lib.lower()
    installed_libs = list_arduino_libraries()
    for installed_lib_name in installed_libs:
        if lib_lower == installed_lib_name.lower():
            return True
    return False

def install_library(lib):
    log(f"Installing library '{lib}' via Arduino Library Manager...")
    success, output = run_subprocess([ARDUINO_CLI_PATH, "lib", "install", lib])
    log(output)
    return success and library_installed(lib)

def get_required_libraries(code, board_name):
    model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    prompt = (
        f"List all the Arduino library names (as in Arduino Library Manager) required to compile code "
        f"for the {board_name} microcontroller. List only names, one per line, no other text.\n"
        f"CODE:\n{code}"
    )
    response = model.generate_content(prompt)
    libs = []
    for line in response.text.splitlines():
        line = line.strip().strip("-*0123456789. \t")
        if line and line not in libs:
            libs.append(line)
    return libs

def query_library_repo_url(library_name, board_name):
    prompt = (
        f"You are an expert on Arduino libraries and GitHub repositories.\n"
        f"For the microcontroller library '{library_name}' supporting the board '{board_name}':\n"
        f"1. Provide ONLY the official GitHub (or equivalent) repository homepage URL of the library.\n"
        f"2. Do NOT provide ZIP download links.\n"
        f"3. Do NOT include explanations or markdown formatting—only return the plain link.\n"
        f"Return ONLY the URL as plain text."
    )
    model = genai.GenerativeModel(GEMINI_MODEL_NAME)
    response = model.generate_content(prompt)
    return response.text.strip()

def github_get_default_branch(owner, repo):
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    response = requests.get(api_url)
    if response.status_code != 200:
        raise Exception(f"GitHub API error: {response.status_code} - {response.text}")
    result = response.json()
    return result.get("default_branch", "main")

def download_zip_from_github_url(repo_url, save_path=LIBRARY_ZIP_DOWNLOAD_DIR):
    parsed = urlparse(repo_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError("Invalid GitHub URL")
    owner, repo = path_parts, path_parts
    default_branch = github_get_default_branch(owner, repo)
    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{default_branch}.zip"
    os.makedirs(save_path, exist_ok=True)
    zip_filename = f"{repo}-{default_branch}.zip"
    zip_path = os.path.join(save_path, zip_filename)
    log(f"Downloading ZIP from {zip_url} ...")
    r = requests.get(zip_url)
    if r.status_code == 200:
        with open(zip_path, "wb") as f:
            f.write(r.content)
        log(f"Downloaded ZIP to {zip_path}")
        return zip_path
    else:
        raise Exception(f"Failed to download ZIP from {zip_url}, HTTP {r.status_code}")

def install_library_zip_with_arduino_cli(zip_path):
    cmd = [ARDUINO_CLI_PATH, "lib", "install", "--zip-path", zip_path]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return proc.returncode == 0, proc.stdout + proc.stderr

def install_libraries_from_github(libraries, board_name):
    """
    libraries: list of library names (strings)
    Returns dict: {lib_name: (repo_url, zip_path, install_success)}
    """
    results = {}
    for lib in libraries:
        log(f"Querying repository URL for library: {lib}")
        repo_url_text = query_library_repo_url(lib, board_name)
        repo_url = extract_first_url(repo_url_text)
        zip_path = None  # <-- SAFE: always defined
        if not repo_url:
            log(f"Failed to find repository URL for '{lib}': [{repo_url_text}]")
            results[lib] = (repo_url_text, None, False)
            continue
        try:
            zip_path = download_zip_from_github_url(repo_url)
            success, output = install_library_zip_with_arduino_cli(zip_path)
            if success:
                log(f"Installed '{lib}' from GitHub ZIP successfully.")
            else:
                log(f"Failed to install '{lib}' from ZIP: {output}")
            results[lib] = (repo_url, zip_path, success)
        except Exception as e:
            log(f"Error while installing '{lib}' from GitHub ZIP: {e}")
            results[lib] = (repo_url, zip_path, False)
        finally:
            # Delete the downloaded ZIP to save space
            try:
                if zip_path and os.path.isfile(zip_path):
                    os.remove(zip_path)
                    log(f"Deleted ZIP file {zip_path} after installation.")
            except Exception as e:
                log(f"Failed to delete ZIP file {zip_path}: {e}")
    return results

def check_and_install_libraries(code, board_name):
    log("Detecting required Arduino libraries...")
    required_libs = get_required_libraries(code, board_name)
    if not required_libs:
        log("No required libraries detected.")
        return
    log(f"Libraries required: {', '.join(required_libs)}")

    for libname in required_libs:
        if library_installed(libname):
            log(f"Library '{libname}' is already installed.")
            continue
        log(f"Library '{libname}' not found locally. Attempting installation via Arduino Library Manager...")
        if install_library(libname):
            log(f"Installed '{libname}' via Arduino Library Manager successfully.")
            continue
        log(f"Library '{libname}' not found in Arduino Library Manager. Trying GitHub repositories...")
        github_results = install_libraries_from_github([libname], board_name)
        if github_results.get(libname, (None, None, False)):
            log(f"Installed '{libname}' from GitHub successfully.")
        else:
            log(f"Failed to install '{libname}' from GitHub after retries. Please install manually.")

# ===============================
# --- COMPILATION WITH AUTO-FIX LOOP ---
# ===============================

def auto_fix_and_compile(sketch_path, fqbn, orig_prompt):
    max_attempts = LIB_INSTALL_MAX_ATTEMPTS
    try_fix_prompt = (
        "I encountered these Arduino compiler errors for the following sketch. Rewrite ONLY the corrected code (no comments, no code fences)—"
        "fixing the issues. Do not change features, just fix errors."
    )
    with open(sketch_path, "r", encoding="utf-8", errors="replace") as f:
        code = f.read()
    for attempt in range(max_attempts):
        check_and_install_libraries(code, current_board.get())
        success, output = compile_sketch(sketch_path, fqbn)
        show_code_in_preview()
        show_terminal_out(f"=== Compile attempt {attempt+1} ===\n{output}")
        if success:
            return True
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        combined_query = (
            f"{try_fix_prompt}\n"
            f"Compiler errors:\n{output}\n"
            f"Code:\n{code}\n"
        )
        response = model.generate_content(combined_query)
        new_code = clean_code(response.text)
        with open(sketch_path, "w", encoding="utf-8") as f:
            f.write(new_code)
        code = new_code
    return False

# ===============================
# --- GUI HELPER FUNCTIONS ---
# ===============================

def show_code_in_preview():
    global current_sketch_path
    if os.path.isfile(current_sketch_path):
        try:
            with open(current_sketch_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            content = f"[Error reading file: {e}]"
    else:
        content = ""
    code_preview.config(state=tk.NORMAL)
    code_preview.delete("1.0", tk.END)
    code_preview.insert(tk.END, content)
    code_preview.config(state=tk.NORMAL)

def show_terminal_out(text):
    terminal_output.config(state=tk.NORMAL)
    terminal_output.delete("1.0", tk.END)
    terminal_output.insert(tk.END, text)
    terminal_output.config(state=tk.DISABLED)

def save_sketch(sketch_path, code):
    try:
        with open(sketch_path, "w", encoding="utf-8") as f:
            f.write(code)
        log(f"Sketch saved to {sketch_path}")
        return True
    except Exception as e:
        log(f"Failed to save sketch: {e}")
        return False

# ===============================
# --- PROJECT MANAGEMENT ---
# ===============================

def create_new_project():
    name = simpledialog.askstring("New Project", "Enter project name (no spaces):")
    if not name:
        return
    folder = filedialog.askdirectory(title="Select Project Directory")
    if not folder:
        return
    project_dir = os.path.join(folder, name)
    ino_path = os.path.join(project_dir, f"{name}.ino")
    try:
        os.makedirs(project_dir, exist_ok=True)
        with open(ino_path, "w", encoding="utf-8") as f:
            f.write("")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to create project:\n{e}")
        return
    global current_project_dir, current_sketch_path, last_generated_path
    current_project_dir = project_dir
    current_sketch_path = ino_path
    last_generated_path = ino_path
    show_code_in_preview()

def open_project():
    file_path = filedialog.askopenfilename(
        title="Open Arduino Project",
        filetypes=[("Arduino Sketch", "*.ino"), ("All files", "*.*")]
    )
    if file_path:
        global current_sketch_path, last_generated_path
        current_sketch_path = file_path
        last_generated_path = file_path
        show_code_in_preview()

def save_displayed_code():
    code = code_preview.get("1.0", tk.END)
    success = save_sketch(current_sketch_path, code)
    if success:
        messagebox.showinfo("Success", f"Code saved to:\n{current_sketch_path}")
        show_code_in_preview()
    else:
        messagebox.showerror("Error", "Failed to save file.")

# ===============================
# --- WIRING SUGGESTION ---
# ===============================

def get_wiring_suggestion():
    try:
        with open(current_sketch_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        messagebox.showerror("Error", f"Cannot read Sketch: {e}")
        return

    prompt = (
        f"You are an Arduino hardware expert. The following is an Arduino C++ code written for the microcontroller '{current_board.get()}'.\n"
        "Your task: Carefully analyze the code and provide a complete pin-by-pin wiring table.\n"
        "For every hardware component and every microcontroller pin or port that is used or referenced in the code, list exactly how and where each wire should be connected between the component and the board.\n\n"
        "Format your answer as a wiring CONNECTIONS TABLE, with columns: [Board Pin], [Component], [Component Pin/Terminal], [Purpose/Signal].\n"
        "Only list wires essential for this code to function.\n\n"
        "BOARD: " + current_board.get() + "\n"
        "CODE:\n" + code
    )

    def thread_call():
        try:
            model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            response = model.generate_content(prompt)
            suggestion = clean_code(response.text)
            terminal_output.config(state=tk.NORMAL)
            terminal_output.delete("1.0", tk.END)
            terminal_output.insert(tk.END, "Wiring Suggestion:\n\n")
            terminal_output.insert(tk.END, suggestion)
            terminal_output.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to get wiring suggestion:\n{e}")

    threading.Thread(target=thread_call, daemon=True).start()

# ===============================
# --- GENERATE CODE ACTION ---
# ===============================

def generate_code_action():
    prompt = prompt_entry.get().strip()
    if not prompt or prompt == prompt_placeholder:
        messagebox.showwarning("Prompt Required", "Please enter a prompt to generate code.")
        return
    board_name = current_board.get()
    fqbn = get_fqbn()
    if not fqbn:
        messagebox.showerror("Error", f"Unknown board selected: {board_name}")
        return

    full_prompt = (
        f"Write Arduino C++ code for {prompt} for this microcontroller: '{board_name}'. "
        "Include all required libraries and header files. Output code only—no comments or code fences. "
        "Do not assume database persistence. Only include what the prompt asks."
    )
    terminal_output.config(state=tk.NORMAL)
    terminal_output.delete("1.0", tk.END)
    terminal_output.insert(tk.END, f"Generating code for: {board_name}...\n")
    terminal_output.config(state=tk.DISABLED)

    def thread_main():
        try:
            model = genai.GenerativeModel(GEMINI_MODEL_NAME)
            response = model.generate_content(full_prompt)
            code = clean_code(response.text)
            with open(current_sketch_path, "w", encoding="utf-8") as f:
                f.write(code)
            show_code_in_preview()

            success = auto_fix_and_compile(current_sketch_path, fqbn, prompt)
            show_code_in_preview()
            if success:
                messagebox.showinfo("Code Generation Complete", f"Code compiled and saved to:\n{current_sketch_path}")
                show_terminal_out("Compilation successful!\n")
            else:
                messagebox.showerror("Compile Error", "Could not auto-fix all errors automatically. Please review the last code and log.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate or compile code:\n{e}")

    threading.Thread(target=thread_main, daemon=True).start()

# ===============================
# --- UPLOAD ACTION ---
# ===============================

def upload_code_action():
    ports = list_ports()
    if not ports:
        messagebox.showerror("Upload Error", "No serial ports detected.")
        return

    port = find_arduino_port(ports)
    if not port:
        messagebox.showerror("Upload Error", "Could not auto-detect Arduino serial port.")
        return

    fqbn = get_fqbn()
    if not fqbn:
        messagebox.showerror("Upload Error", "Unknown board selected.")
        return
    sketch_path = current_sketch_path

    terminal_output.config(state=tk.NORMAL)
    terminal_output.insert(tk.END, f"\nUploading sketch {sketch_path} to port {port}...\n")
    terminal_output.config(state=tk.DISABLED)

    def thread_func():
        tried_ports = set()
        success = upload_code(ARDUINO_CLI_PATH, sketch_path, fqbn, port)
        tried_ports.add(port)

        def update_terminal(text):
            terminal_output.config(state=tk.NORMAL)
            terminal_output.insert(tk.END, text)
            terminal_output.see(tk.END)
            terminal_output.config(state=tk.DISABLED)

        if success:
            root.after(0, lambda: update_terminal("Upload successful!\n"))
        else:
            root.after(0, lambda: update_terminal("Upload failed. Trying other available ports...\n"))
            found_success = False
            for p in ports:
                if p.device not in tried_ports:
                    if upload_code(ARDUINO_CLI_PATH, sketch_path, fqbn, p.device):
                        found_success = True
                        root.after(0, lambda d=p.device: update_terminal(f"Upload successful on port {d}!\n"))
                        break
            if not found_success:
                root.after(0, lambda: update_terminal("All upload attempts failed.\n"))

    threading.Thread(target=thread_func, daemon=True).start()

# ===============================
# --- SERIAL MONITOR ---
# ===============================

def open_serial_monitor():
    # Prevent multiple Serial Monitors
    if hasattr(open_serial_monitor, "window") and open_serial_monitor.window.winfo_exists():
        open_serial_monitor.window.lift()
        return

    win = tk.Toplevel(root)
    win.title("Serial Monitor")
    win.geometry("700x450")

    # ===============================
    # Top frame for controls
    # ===============================

    frame_top = ttk.Frame(win)
    frame_top.pack(fill="x", padx=6, pady=6)

    ports = [port.device for port in serial.tools.list_ports.comports()]
    port_var = tk.StringVar(value=ports[0] if ports else "")
    baud_var = tk.StringVar(value="115200")

    ttk.Label(frame_top, text="Port:").pack(side="left")
    port_combo = ttk.Combobox(frame_top, values=ports, textvariable=port_var, width=18, state="readonly")
    port_combo.pack(side="left", padx=4)
    ttk.Label(frame_top, text="Baud:").pack(side="left", padx=(10, 0))
    baud_combo = ttk.Combobox(frame_top, values=["9600", "19200", "38400", "57600", "115200"], textvariable=baud_var,
                              width=8, state="readonly")
    baud_combo.pack(side="left", padx=4)
    connect_btn = ttk.Button(frame_top, text="Connect")
    connect_btn.pack(side="left", padx=10)
    disconnect_btn = ttk.Button(frame_top, text="Disconnect", state="disabled")
    disconnect_btn.pack(side="left", padx=4)
    status_var = tk.StringVar(value="Disconnected")
    ttk.Label(frame_top, textvariable=status_var, foreground="red").pack(side="left", padx=10)

    # ===============================
    # Serial output area
    # ===============================

    serial_text = scrolledtext.ScrolledText(win, font=("Consolas", 12), wrap=tk.WORD, state=tk.DISABLED)
    serial_text.pack(expand=True, fill=tk.BOTH, padx=6, pady=6)

    # ===============================
    # Monitor state (holds serial obj and polling job handle)
    # ===============================

    monitor = {"ser": None, "job": None}

    def poll_serial():
        ser = monitor["ser"]
        if ser and ser.is_open:
            try:
                data = ser.read(ser.in_waiting or 1)
                if data:
                    try:
                        text = data.decode(errors='replace')
                    except Exception as e:
                        text = f"[Decode error: {e}]\n"
                    serial_text.config(state=tk.NORMAL)
                    serial_text.insert(tk.END, text)
                    serial_text.see(tk.END)
                    serial_text.config(state=tk.DISABLED)
            except serial.SerialException as e:
                serial_text.config(state=tk.NORMAL)
                serial_text.insert(tk.END, f"\n[Serial error: {e}]\n")
                serial_text.config(state=tk.DISABLED)
                disconnect()
                return
            monitor["job"] = win.after(50, poll_serial)

    def connect():
        port = port_var.get()
        if not port:
            messagebox.showerror("Serial Monitor", "No serial port selected.")
            return
        try:
            baud = int(baud_var.get())
        except ValueError:
            messagebox.showerror("Serial Monitor", "Invalid baud rate.")
            return
        try:
            ser = serial.Serial(port, baud, timeout=0)
            monitor["ser"] = ser
        except serial.SerialException as e:
            messagebox.showerror("Serial Monitor", f"Error opening serial port:\n{e}")
            return
        serial_text.config(state=tk.NORMAL)
        serial_text.insert(tk.END, f"Connected to {port} at {baud} baud.\n")
        serial_text.config(state=tk.DISABLED)
        status_var.set("Connected")
        connect_btn.config(state="disabled")
        disconnect_btn.config(state="normal")
        port_combo.config(state="disabled")
        baud_combo.config(state="disabled")
        poll_serial()

    def disconnect():
        if monitor["job"]:
            win.after_cancel(monitor["job"])
            monitor["job"] = None
        if monitor["ser"]:
            try:
                monitor["ser"].close()
            except Exception:
                pass
            monitor["ser"] = None
        serial_text.config(state=tk.NORMAL)
        serial_text.insert(tk.END, "\n[Serial connection closed]\n")
        serial_text.config(state=tk.DISABLED)
        status_var.set("Disconnected")
        connect_btn.config(state="normal")
        disconnect_btn.config(state="disabled")
        port_combo.config(state="readonly")
        baud_combo.config(state="readonly")

    def on_close():
        disconnect()
        win.destroy()

    connect_btn.config(command=connect)
    disconnect_btn.config(command=disconnect)
    win.protocol("WM_DELETE_WINDOW", on_close)
    open_serial_monitor.window = win

# ===============================
# --- GUI SETUP ---
# ===============================

root = tk.Tk()
root.title("Arduino Gemini Code Generator & Uploader")
root.geometry("1200x860")
root.configure(bg=DARK_BG)

style = ttk.Style()
style.theme_use('clam')
style.configure("Rounded.TButton",
                background=BUTTON_BG, foreground=BUTTON_FG,
                anchor="center", padding=14,
                font=(FONT, 11, "bold"),
                relief="flat", borderwidth=0)
style.map("Rounded.TButton",
          background=[("active", "#e0ffe0")],
          relief=[("pressed", "flat")])
style.configure("Grey.TFrame", background=MID_BG)

# ===============================
# -- Initialize state variables
# ===============================

current_board = tk.StringVar(value=list(BOARD_OPTIONS.keys()))

# ===============================
# -- Top frame for buttons and board combo
# ===============================

top_row = tk.Frame(root, bg=MID_BG)
top_row.pack(fill="x", padx=30, pady=(18, 10))

def make_round_btn(parent, text, cmd):
    return ttk.Button(parent, text=text, command=cmd, style="Rounded.TButton")

btns = []
for btn_text, action in [
        ("New Project", create_new_project),
        ("Open Project", open_project),
        ("Generate", generate_code_action),
        ("Save Code", save_displayed_code),
        ("Wiring", get_wiring_suggestion),
        ("Upload", upload_code_action),
    ]:
    b = make_round_btn(top_row, btn_text, action)
    b.pack(side="left", padx=(0, 18), pady=13)
    btns.append(b)

select_board_cbox = ttk.Combobox(top_row, values=list(BOARD_OPTIONS.keys()),
                                textvariable=current_board, width=23, state="readonly",
                                font=(FONT, 11))
select_board_cbox.pack(side="left", padx=(40, 0), pady=15)
select_board_cbox.bind("<<ComboboxSelected>>", lambda e: show_code_in_preview())
style.configure("TCombobox",
                background=BUTTON_BG, fieldbackground=BUTTON_BG, foreground=BUTTON_FG,
                arrowcolor=BUTTON_FG, selectbackground=BUTTON_BG, font=(FONT, 11), padding=9)
select_board_cbox.configure(style="TCombobox")

# ===============================
# -- Search bar
# ===============================

row_search = tk.Frame(root, bg=DARK_BG)
row_search.pack(fill="x", padx=190, pady=(28, 0))
search_pill = tk.Frame(row_search, bg="#343941", bd=0, highlightbackground="#343941",
                       highlightcolor="#343941", highlightthickness=3)
search_pill.pack(fill="x", expand=True, ipady=15)

prompt_placeholder = "Describe your project requirements here and click 'Go'..."
prompt_entry = tk.Entry(search_pill, font=(FONT, 16), bg="#343941", fg="#aaa",
                        bd=0, relief="flat", highlightthickness=0, insertbackground=ACCENT)
prompt_entry.pack(side="left", fill="x", expand=True, padx=(22, 2), ipady=10)
prompt_entry.insert(0, prompt_placeholder)

def on_search_focus_in(event):
    if prompt_entry.get() == prompt_placeholder:
        prompt_entry.delete(0, tk.END)
        prompt_entry.config(fg="#dedede")

def on_search_focus_out(event):
    if not prompt_entry.get():
        prompt_entry.insert(0, prompt_placeholder)
        prompt_entry.config(fg="#aaa")

prompt_entry.bind("<FocusIn>", on_search_focus_in)
prompt_entry.bind("<FocusOut>", on_search_focus_out)

go_btn = ttk.Button(search_pill, text="Go", style="Rounded.TButton", command=generate_code_action)
go_btn.pack(side="left", padx=18, ipadx=12, ipady=8)

tk.Frame(root, height=38, bg=DARK_BG).pack(fill="x")

splitter = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                         sashwidth=8, showhandle=True, bg=DARK_BG, bd=2)
splitter.pack(expand=True, fill="both", padx=28, pady=(0, 17))

# ===============================
# -- Left code preview frame
# ===============================

left_frame = tk.Frame(splitter, bg="#191c22")
label_cp = tk.Label(left_frame, text="Code Preview (Editable)", font=(FONT, 13, "bold"), bg="#191c22", fg=ACCENT)
label_cp.pack(anchor="nw", padx=13, pady=(8, 5))

code_preview = scrolledtext.ScrolledText(left_frame, font=(MONO, 12), wrap=tk.WORD, height=16,
                                         bg="#191c22", fg="#e2e2e2", insertbackground=ACCENT,
                                         selectbackground="#384042", selectforeground=ACCENT, borderwidth=0)
code_preview.pack(expand=True, fill=tk.BOTH, padx=12, pady=12)
code_preview.config(state=tk.NORMAL)

# ===============================
# -- Right terminal output frame
# ===============================

right_frame = tk.Frame(splitter, bg="#191c1d")
label_term = tk.Label(right_frame, text="Terminal", font=(FONT, 13, "bold"), bg="#191c1d", fg=ACCENT)
label_term.pack(anchor="nw", padx=13, pady=(8, 5))

term_taskbar = tk.Frame(right_frame, bg="#191c1d")
term_taskbar.pack(fill="x", padx=6, pady=(0, 6))

btn_clear = ttk.Button(term_taskbar, text="Clear", command=lambda: terminal_output.config(state=tk.NORMAL) or terminal_output.delete("1.0", tk.END) or terminal_output.config(state=tk.DISABLED),
                       style="Rounded.TButton", width=8)
btn_clear.pack(side="left", padx=(0, 18))

btn_serial = ttk.Button(term_taskbar, text="Serial Monitor", command=open_serial_monitor, style="Rounded.TButton", width=14)
btn_serial.pack(side="left", padx=(0, 8))

terminal_output = scrolledtext.ScrolledText(right_frame, font=(MONO, 12), wrap=tk.WORD, height=16,
                                            bg="#23272e", fg=ACCENT, insertbackground=ACCENT,
                                            selectbackground="#343746", selectforeground=ACCENT, borderwidth=0)
terminal_output.pack(expand=True, fill=tk.BOTH, padx=12, pady=12)
terminal_output.config(state=tk.DISABLED)

sys.stdout = TkinterOutputLogger(terminal_output, sys.__stdout__)
sys.stderr = TkinterOutputLogger(terminal_output, sys.__stderr__)

splitter.add(left_frame, minsize=435)
splitter.add(right_frame, minsize=435)
splitter.paneconfig(left_frame, stretch="always")
splitter.paneconfig(right_frame, stretch="always")

# ===============================
# Show initial code preview
# ===============================

show_code_in_preview()

# ===============================
# Run the main loop
# ===============================

root.mainloop()
