#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import json
import urllib.request
import platform

# Color Codes for Pretty Terminal Output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_banner():
    banner = f"""
{BLUE}{BOLD}======================================================================
     ____                  ____        __ 
    / __ )____ _____ ___  / __ )____  / /_
   / __  / __ `/ __ `__ \\/ __  / __ \\/ __/
  / /_/ / /_/ / / / / / / /_/ / /_/ / /_  
 /_____/\\__,_/_/ /_/ /_/_____/\\____/\\__/  
                                          
         💿 BamBot OrcaSlicer Auto-Installer & Configurator 💿
======================================================================{RESET}
"""
    print(banner)

def get_latest_github_release_assets():
    print(f"[{CYAN}*{RESET}] Fetching latest OrcaSlicer release from GitHub...")
    api_url = "https://api.github.com/repos/SoftFever/OrcaSlicer/releases/latest"
    try:
        req = urllib.request.Request(
            api_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get("tag_name"), data.get("assets", [])
    except Exception as e:
        print(f"{YELLOW}Warning: Could not fetch latest release info from GitHub ({e}).{RESET}")
        return None, []

def detect_system():
    os_type = platform.system().lower()
    arch = platform.machine().lower()
    return os_type, arch

def install_macos():
    print(f"\n{BOLD}🍏 Installing OrcaSlicer on macOS...{RESET}")
    # 1. Check if brew is installed
    if shutil.which("brew"):
        print(f"[{CYAN}*{RESET}] Homebrew detected. Installing OrcaSlicer via homebrew cask...")
        try:
            subprocess.run(["brew", "install", "--cask", "orca-slicer"], check=True)
            print(f"{GREEN}✔ OrcaSlicer installed successfully via Homebrew Cask!{RESET}")
            return "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"
        except subprocess.CalledProcessError as e:
            print(f"{YELLOW}Warning: Homebrew installation failed: {e}. Trying manual download...{RESET}")
    
    # 2. Manual download fallback
    tag, assets = get_latest_github_release_assets()
    dmg_url = None
    if assets:
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith(".dmg") and ("arm64" in name or "AppleSilicon" in name):
                dmg_url = asset.get("browser_download_url")
                break
        if not dmg_url:
            # Fallback to any DMG
            for asset in assets:
                if asset.get("name", "").endswith(".dmg"):
                    dmg_url = asset.get("browser_download_url")
                    break

    if not dmg_url:
        dmg_url = f"https://github.com/SoftFever/OrcaSlicer/releases/download/v2.1.1/OrcaSlicer_Mac_Arm64_v2.1.1.dmg"
        print(f"[{CYAN}*{RESET}] Using fallback download URL: {dmg_url}")

    local_dmg = "/tmp/OrcaSlicer.dmg"
    print(f"[{CYAN}*{RESET}] Downloading OrcaSlicer DMG from: {dmg_url}...")
    try:
        urllib.request.urlretrieve(dmg_url, local_dmg)
        print(f"[{CYAN}*{RESET}] Mounting DMG image...")
        subprocess.run(f"hdiutil attach {local_dmg} -mountpoint /Volumes/OrcaSlicerMount", shell=True, check=True)
        print(f"[{CYAN}*{RESET}] Copying OrcaSlicer.app to Applications...")
        subprocess.run("cp -R /Volumes/OrcaSlicerMount/OrcaSlicer.app /Applications/", shell=True, check=True)
        print(f"[{CYAN}*{RESET}] Detaching DMG image...")
        subprocess.run("hdiutil detach /Volumes/OrcaSlicerMount", shell=True, check=True)
        print(f"{GREEN}✔ OrcaSlicer successfully installed to /Applications/OrcaSlicer.app!{RESET}")
        return "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"
    except Exception as e:
        print(f"{RED}Error: Failed to install OrcaSlicer automatically: {e}{RESET}")
        print(f"Please install it manually from: {BLUE}https://github.com/SoftFever/OrcaSlicer/releases{RESET}")
        return None

def install_linux(arch):
    print(f"\n{BOLD}🐧 Installing OrcaSlicer on Linux ({arch})...{RESET}")
    # 1. Flatpak option
    if shutil.which("flatpak"):
        confirm = input(f"[{CYAN}?{RESET}] Flatpak detected. Would you like to install OrcaSlicer from Flathub? (Y/n): ").strip().lower()
        if confirm != 'n':
            try:
                print(f"[{CYAN}*{RESET}] Installing from Flathub...")
                subprocess.run(["flatpak", "install", "flathub", "com.orca_slicer.OrcaSlicer", "-y"], check=True)
                print(f"{GREEN}✔ OrcaSlicer Flatpak installed successfully!{RESET}")
                # Flatpak runs via command
                return "flatpak run com.orca_slicer.OrcaSlicer"
            except subprocess.CalledProcessError as e:
                print(f"{YELLOW}Warning: Flatpak installation failed: {e}. Trying AppImage...{RESET}")

    # 2. AppImage option
    tag, assets = get_latest_github_release_assets()
    appimage_url = None
    is_arm = "arm" in arch or "aarch64" in arch
    
    if assets:
        for asset in assets:
            name = asset.get("name", "").lower()
            if name.endswith(".appimage"):
                if is_arm and ("arm64" in name or "aarch64" in name):
                    appimage_url = asset.get("browser_download_url")
                    break
                elif not is_arm and "x86_64" in name:
                    appimage_url = asset.get("browser_download_url")
                    break
        if not appimage_url:
            for asset in assets:
                if asset.get("name", "").lower().endswith(".appimage"):
                    appimage_url = asset.get("browser_download_url")
                    break

    if not appimage_url:
        if is_arm:
            # Fallback to community ARM64 AppImage release
            appimage_url = "https://github.com/SoftFever/OrcaSlicer/releases/download/v2.1.1/OrcaSlicer_Linux_V2.1.1.AppImage" # fallback (will run on standard systems if x86, else community build needed)
        else:
            appimage_url = "https://github.com/SoftFever/OrcaSlicer/releases/download/v2.1.1/OrcaSlicer_Linux_V2.1.1.AppImage"
            
    print(f"[{CYAN}*{RESET}] Downloading OrcaSlicer AppImage: {appimage_url}...")
    local_appimage = os.path.expanduser("~/OrcaSlicer.AppImage")
    try:
        # Check libfuse dependency
        if shutil.which("apt-get"):
            print(f"[{CYAN}*{RESET}] Checking for 'libfuse2' library required by AppImage...")
            subprocess.run("sudo apt-get update && sudo apt-get install -y libfuse2", shell=True, check=False)
            
        urllib.request.urlretrieve(appimage_url, local_appimage)
        os.chmod(local_appimage, 0o755)
        print(f"{GREEN}✔ OrcaSlicer AppImage downloaded and made executable at {local_appimage}!{RESET}")
        return local_appimage
    except Exception as e:
        print(f"{RED}Error: Failed to download AppImage: {e}{RESET}")
        print(f"Please install it manually from: {BLUE}https://github.com/SoftFever/OrcaSlicer/releases{RESET}")
        return None

def configure_presets(orca_path, presets_dir):
    print(f"\n[{CYAN}*{RESET}] Configuring default system presets inside: {presets_dir}")
    os.makedirs(os.path.join(presets_dir, "process"), exist_ok=True)
    os.makedirs(os.path.join(presets_dir, "filament"), exist_ok=True)
    os.makedirs(os.path.join(presets_dir, "machine"), exist_ok=True)

    copied = False
    
    # 1. Attempt to copy from macOS App Bundle
    if "OrcaSlicer.app" in orca_path:
        app_path = orca_path.split(".app")[0] + ".app"
        mac_profiles_src = os.path.join(app_path, "Contents", "Resources", "profiles", "BBL")
        if os.path.exists(mac_profiles_src):
            try:
                shutil.copytree(mac_profiles_src, presets_dir, dirs_exist_ok=True)
                print(f"{GREEN}✔ Successfully copied system profiles from macOS App bundle.{RESET}")
                copied = True
            except Exception as e:
                print(f"{YELLOW}Warning: Failed to copy macOS bundle profiles: {e}{RESET}")
                
    # 2. Attempt to extract from Linux AppImage
    elif orca_path.endswith(".AppImage"):
        print(f"[{CYAN}*{RESET}] Extracting system profiles from Linux AppImage...")
        try:
            # Run extraction in /tmp
            subprocess.run([orca_path, "--appimage-extract"], cwd="/tmp", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            extracted_src = "/tmp/squashfs-root/resources/profiles/BBL"
            if os.path.exists(extracted_src):
                shutil.copytree(extracted_src, presets_dir, dirs_exist_ok=True)
                print(f"{GREEN}✔ Successfully extracted and copied system profiles from Linux AppImage.{RESET}")
                copied = True
            # Cleanup
            shutil.rmtree("/tmp/squashfs-root", ignore_errors=True)
        except Exception as e:
            print(f"{YELLOW}Warning: Failed to extract AppImage profiles: {e}{RESET}")
            
    # 3. Fallback placeholder JSONs (with correct 'from': 'system' attribute)
    if not copied:
        print(f"[{CYAN}*{RESET}] Writing default preset profiles manually...")
        process_file = os.path.join(presets_dir, "process", "0.20mm Standard @BBL X1C.json")
        filament_file = os.path.join(presets_dir, "filament", "Bambu PLA Basic @BBL X1C.json")
        machine_file = os.path.join(presets_dir, "machine", "Bambu Lab X1 Carbon 0.4 nozzle.json")
        
        process_data = {
            "type": "process",
            "setting_id": "GP004",
            "name": "0.20mm Standard @BBL X1C",
            "from": "system",
            "inherits": "0.20mm Standard @BBL X1C",
            "instantiation": "true",
            "layer_height": "0.2",
            "first_layer_height": "0.2"
        }
        filament_data = {
            "type": "filament",
            "setting_id": "GF001",
            "name": "Bambu PLA Basic @BBL X1C",
            "from": "system",
            "inherits": "Bambu PLA Basic @BBL X1C",
            "instantiation": "true",
            "filament_type": "PLA",
            "filament_density": "1.24"
        }
        machine_data = {
            "type": "machine",
            "setting_id": "GM001",
            "name": "Bambu Lab X1 Carbon 0.4 nozzle",
            "from": "system",
            "inherits": "Bambu Lab X1 Carbon 0.4 nozzle",
            "instantiation": "true",
            "nozzle_diameter": ["0.4"]
        }
        with open(process_file, "w") as f:
            json.dump(process_data, f, indent=4)
        with open(filament_file, "w") as f:
            json.dump(filament_data, f, indent=4)
        with open(machine_file, "w") as f:
            json.dump(machine_data, f, indent=4)
        print(f"{GREEN}✔ Created fallback JSON presets for standard slicing profiles.{RESET}")

def load_existing_env(filepath):
    env_vars = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        env_vars[parts[0].strip()] = parts[1].strip()
    return env_vars

def update_env_files(orca_path, orca_res_dir):
    print(f"\n[{CYAN}*{RESET}] Saving OrcaSlicer configuration to .env and app/.env...")
    for filepath in [".env", "app/.env"]:
        existing = load_existing_env(filepath)
        existing["ORCA_SLICER_PATH"] = orca_path
        existing["ORCA_RESOURCES_DIR"] = orca_res_dir
        
        # Write back retaining all values
        lines = []
        # Keep comments and insert/modify keys
        written_keys = set()
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("#") or not stripped:
                        lines.append(line)
                    else:
                        parts = stripped.split("=", 1)
                        if len(parts) == 2:
                            key = parts[0].strip()
                            if key in existing:
                                lines.append(f"{key}={existing[key]}\n")
                                written_keys.add(key)
                            else:
                                lines.append(line)
        
        # Write any new keys not yet written
        for key, val in existing.items():
            if key not in written_keys:
                lines.append(f"{key}={val}\n")
                
        with open(filepath, "w") as f:
            f.writelines(lines)
            
    print(f"{GREEN}✔ Environment files successfully updated.{RESET}")

def main():
    print_banner()
    os_type, arch = detect_system()
    print(f"[{CYAN}*{RESET}] Detected System: {BOLD}{os_type.upper()} ({arch}){RESET}")
    
    orca_path = None
    
    # Check if already installed
    which_orca = shutil.which("orcaslicer") or shutil.which("OrcaSlicer") or shutil.which("orca-slicer")
    if which_orca:
        print(f"{GREEN}✔ Existing OrcaSlicer installation found in PATH: {which_orca}{RESET}")
        orca_path = which_orca
    elif os_type == "darwin" and os.path.exists("/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"):
        print(f"{GREEN}✔ Existing OrcaSlicer installation found: /Applications/OrcaSlicer.app{RESET}")
        orca_path = "/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"
    else:
        confirm = input(f"[{CYAN}?{RESET}] OrcaSlicer not found. Would you like to install it now? (Y/n): ").strip().lower()
        if confirm != 'n':
            if os_type == "darwin":
                orca_path = install_macos()
            elif os_type == "linux":
                orca_path = install_linux(arch)
            else:
                print(f"{RED}Unsupported OS for auto-installation: {os_type}{RESET}")
                print(f"Please install it manually from: {BLUE}https://github.com/SoftFever/OrcaSlicer/releases{RESET}")
                
    if not orca_path:
        print(f"\n{YELLOW}Please configure OrcaSlicer paths manually.{RESET}")
        orca_path = input("Enter OrcaSlicer executable path: ").strip()
        if not orca_path:
            print(f"{RED}No OrcaSlicer executable path provided. Exiting.{RESET}")
            sys.exit(1)

    # Detect default resource dir
    home = os.path.expanduser("~")
    if os_type == "darwin":
        default_res_dir = os.path.join(home, "Library", "Application Support", "OrcaSlicer", "system", "BBL")
    else:
        default_res_dir = os.path.join(home, ".config", "OrcaSlicer", "system", "BBL")

    print(f"\n{BOLD}📂 Configuring Preset Presets:{RESET}")
    orca_res_dir = input(f"Enter OrcaSlicer Presets Directory [{default_res_dir}]: ").strip()
    if not orca_res_dir:
        orca_res_dir = default_res_dir

    configure_presets(orca_path, orca_res_dir)
    update_env_files(orca_path, orca_res_dir)

    print(f"\n{GREEN}{BOLD}🎉 OrcaSlicer configuration complete and ready for BamBot! 🎉{RESET}")

if __name__ == "__main__":
    main()
