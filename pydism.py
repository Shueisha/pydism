"""
pydism - Windows DISM Repair Tool
https://github.com/Shueisha/pydism

A simple tool to scan and repair Windows system files using DISM and SFC.
Includes smart progress indicators that explain DISM's normal 62.3% pause.

Usage: 
  - Run pydism.exe as Administrator
  - Or: python pydism.py (requires admin)

License: MIT
"""

import sys
import ctypes
import subprocess
import logging
import os
import re
from datetime import datetime


def is_admin():
    """Check if running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """Re-run with admin privileges"""
    try:
        if not is_admin():
            # Frozen exe relaunches itself directly; a script needs its path
            # passed to the Python interpreter.
            params = None if getattr(sys, 'frozen', False) else f'"{sys.argv[0]}"'
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, params, None, 1
            )
            if result > 32:
                sys.exit(0)
            else:
                print("Failed to get admin privileges.")
                print("Please right-click and 'Run as Administrator'")
                input("Press Enter to exit...")
                sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def get_script_path():
    """Get the directory where the script is located"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def setup_logging():
    """Initialize logging"""
    script_dir = get_script_path()
    log_file = os.path.join(script_dir, f'pydism_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(log_file)]
    )
    return logging.getLogger(__name__), log_file


def classify_dism_output(output_text):
    """Categorize DISM output: 'healthy', 'repairable', 'repaired', or None"""
    if "No component store corruption detected" in output_text:
        return "healthy"
    lowered = output_text.lower()
    if "repairable" in lowered:
        return "repairable"
    if "successfully repaired" in lowered or "completed successfully" in lowered:
        return "repaired"
    return None


def run_dism_command(command_args, logger, is_restore=False, capture_output=False):
    """
    Execute DISM command with live output and smart progress indicator.
    
    Explains DISM's normal pause during component store analysis
    (typically around 62.3%, but it varies by install) - this prevents
    confusion during what looks like a "stuck" operation but is normal.
    """
    try:
        dism_path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'dism.exe')
        full_command = [dism_path] + command_args
        
        print(f"\nExecuting: {' '.join(full_command)}")
        logger.info(f"DISM Command: {' '.join(full_command)}")
        
        # Progress guidance for RestoreHealth
        if is_restore:
            print("\n" + "=" * 55)
            print("  DISM RestoreHealth Progress Guide")
            print("=" * 55)
            print("  0-60%:   Initial scan and analysis")
            print("  60-65%:  Component store check (may pause 10-20 min)")
            print("  65-100%: Repair and cleanup operations")
            print("")
            print("  A pause in the low 60s (often 62.3%) is NORMAL!")
            print("=" * 55)
            logger.info("DISM RestoreHealth started - pause in low 60s is normal")
        
        process = subprocess.Popen(
            full_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        print("\nDISM Output:")
        print("-" * 50)
        
        last_progress = None
        pause_notified = False
        output_lines = []
        bar_active = False
        
        def draw_progress_bar(progress):
            bar_width = 50
            filled = int(bar_width * progress / 100)
            bar = '=' * filled + ' ' * (bar_width - filled)
            print(f"\r[{bar}] {progress:5.1f}%", end='', flush=True)
        
        if process.stdout:
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if not line:
                    continue
                line = line.strip()
                if not line:
                    continue
                
                match = re.search(r'(\d+\.?\d*)%', line) if "%" in line else None
                if match:
                    progress = float(match.group(1))
                    
                    # DISM redraws its bar constantly through the pipe;
                    # only update ours when the percentage changes
                    if progress != last_progress:
                        draw_progress_bar(progress)
                        bar_active = True
                    
                    if is_restore:
                        # Explain the analysis pause (often 62.3%, varies by install)
                        if 60.0 <= progress < 65.0 and not pause_notified:
                            print("\n" + "=" * 55)
                            print("  [NORMAL] Component Store Analysis Phase")
                            print("  DISM is checking thousands of system files.")
                            print("  This typically takes 10-20 minutes.")
                            print("  DO NOT interrupt - progress will resume.")
                            print("=" * 55 + "\n")
                            logger.info(f"DISM component store analysis phase at {progress}%")
                            pause_notified = True
                            bar_active = False
                        
                        # Progress milestones
                        elif progress >= 65.0 and last_progress is not None and last_progress < 65.0:
                            print("\n[PROGRESS] Component check complete - continuing...")
                            logger.info("DISM passed 65%")
                            bar_active = False
                        elif progress >= 90.0 and last_progress is not None and last_progress < 90.0:
                            print("\n[PROGRESS] Nearly complete...")
                            logger.info("DISM at 90%")
                            bar_active = False
                    
                    last_progress = progress
                else:
                    # Move past the in-place bar before printing normal output
                    if bar_active:
                        print()
                        bar_active = False
                    print(line)
                    output_lines.append(line)
        
        if bar_active:
            print()
        
        process.wait(timeout=3600)
        return_code = process.returncode
        
        print("-" * 50)
        print(f"Completed with return code: {return_code}")
        logger.info(f"DISM completed with return code: {return_code}")
        
        # Log key results
        output_text = '\n'.join(output_lines)
        result = classify_dism_output(output_text)
        if result == "healthy":
            logger.info("Result: System is healthy - no corruption detected")
        elif result == "repairable":
            logger.info("Result: Component store has repairable corruption")
        elif result == "repaired":
            logger.info("Result: Operation completed successfully")
        
        if capture_output:
            return return_code == 0, output_text
        return return_code == 0
        
    except subprocess.TimeoutExpired:
        print("[ERROR] Operation timed out after 1 hour")
        logger.error("DISM timed out")
        if capture_output:
            return False, "Timeout"
        return False
    except Exception as e:
        print(f"[ERROR] {e}")
        logger.error(f"DISM failed: {e}")
        if capture_output:
            return False, str(e)
        return False


def scan_health(logger):
    """Scan Windows system health"""
    print("\n[SCAN] Scanning Windows System Health...")
    print("This checks for corruption but does not repair.")
    return run_dism_command(["/Online", "/Cleanup-Image", "/ScanHealth"], logger, is_restore=False, capture_output=True)


def read_cbs_tail(max_bytes):
    """
    Read the last max_bytes of CBS.log as text, or None if unavailable.
    
    DISM never prints what it repaired to the console - the detail only
    lands in CBS.log, which can be hundreds of MB. We only ever need the
    portion written by the session that just finished.
    """
    cbs_log = os.path.join(
        os.environ.get('SystemRoot', 'C:\\Windows'), 'Logs', 'CBS', 'CBS.log'
    )
    try:
        with open(cbs_log, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - max_bytes))
            return f.read().decode('utf-8', errors='ignore')
    except OSError:
        return None


def get_cbs_repair_count(started_at=None):
    """
    Read the most recent 'Total Repaired Corruption' counter from CBS.log.
    If started_at is set, only consider lines from that session onward.
    """
    tail = read_cbs_tail(2 * 1024 * 1024)
    if not tail:
        return None
    text = tail
    if started_at is not None:
        session_start = started_at.strftime('%Y-%m-%d %H:%M:%S')
        text = '\n'.join(
            line for line in tail.splitlines()
            if len(line) >= 19 and line[:19] >= session_start
        )
    matches = re.findall(r'Total Repaired Corruption:\s*(\d+)', text)
    if matches:
        return int(matches[-1])
    return None


def _cbs_int(pattern, text, default=None):
    match = re.search(pattern, text)
    if match:
        return int(match.group(1))
    return default


def build_cbs_plain_summary(session_text, repaired_count):
    """
    Turn CBS session lines into a short plain-English briefing for the shop floor.
    Returns a list of text lines (no trailing newline on the list itself).
    """
    detected = _cbs_int(r'Total Detected Corruption:\s*(\d+)', session_text)
    repaired = repaired_count
    if repaired is None:
        repaired = _cbs_int(r'Total Repaired Corruption:\s*(\d+)', session_text)

    cbs_manifest = _cbs_int(r'CBS Manifest Corruption:\s*(\d+)', session_text, 0) or 0
    cbs_meta = _cbs_int(r'CBS Metadata Corruption:\s*(\d+)', session_text, 0) or 0
    csi_manifest = _cbs_int(r'CSI Manifest Corruption:\s*(\d+)', session_text, 0) or 0
    csi_meta = _cbs_int(r'CSI Metadata Corruption:\s*(\d+)', session_text, 0) or 0
    csi_payload = _cbs_int(r'CSI Payload Corruption:\s*(\d+)', session_text, 0) or 0
    csi_flags = _cbs_int(r'CSI FileFlags Corrupt:\s*(\d+)', session_text, 0) or 0

    ok = 'S_OK' in session_text or 'HRESULT = 0x00000000' in session_text
    failed = bool(re.search(r'HRESULT = 0x(?!00000000)\w+', session_text))
    meta_note = 'CSI meta data corruption found' in session_text
    fileflags_note = 'file flag corruption' in session_text.lower()

    lines = []
    lines.append("PLAIN ENGLISH SUMMARY (for the repair team)")
    lines.append("=" * 70)

    if ok and not failed:
        lines.append("Result:        Completed successfully (Windows reported S_OK).")
    elif failed:
        lines.append("Result:        Finished with errors - check the raw section / DISM return code.")
    else:
        lines.append("Result:        Completed (exact HRESULT not found in this extract).")

    if detected is not None:
        lines.append(f"Problems found:  {detected}")
    if repaired is not None:
        lines.append(f"Problems fixed:  {repaired}")

    lines.append("")
    lines.append("What this means:")
    if detected == 0 and (repaired == 0 or repaired is None):
        lines.append("  - The component store looks healthy.")
        lines.append("  - DISM did not need to replace corrupted system files.")
        if meta_note or fileflags_note:
            lines.append("  - Windows still ran a repair transaction for metadata/file-flag")
            lines.append("    housekeeping. That can be normal even when the count is 0.")
    elif repaired and repaired > 0:
        lines.append(f"  - Windows repaired {repaired} component-store problem(s).")
        lines.append("  - A reboot is recommended before handing the PC back.")
        lines.append("  - Run SFC (/scannow) as a follow-up if you have not already.")
    elif detected and detected > 0 and (repaired == 0 or repaired is None):
        lines.append("  - Corruption was detected but the repaired count is 0.")
        lines.append("  - Try Restore Health again using a clean install USB as source.")
        lines.append("  - If that still fails, the image may need in-place upgrade / reinstall.")
    else:
        lines.append("  - Could not fully interpret the CBS counters from this session.")
        lines.append("  - Use the raw log section below, or open CBS.log if needed.")

    total_breakdown = cbs_manifest + cbs_meta + csi_manifest + csi_meta + csi_payload + csi_flags
    if detected or total_breakdown:
        lines.append("")
        lines.append("Corruption breakdown (Windows categories):")
        lines.append(f"  - Package manifests (CBS):     {cbs_manifest}")
        lines.append(f"  - Package metadata (CBS):      {cbs_meta}")
        lines.append(f"  - Component manifests (CSI):   {csi_manifest}")
        lines.append(f"  - Component metadata (CSI):    {csi_meta}")
        lines.append(f"  - Component files (CSI):       {csi_payload}")
        lines.append(f"  - File flags (CSI):            {csi_flags}")

    lines.append("")
    lines.append("Suggested next steps:")
    if repaired and repaired > 0:
        lines.append("  1. Restart Windows")
        lines.append("  2. Run SFC (System File Checker)")
        lines.append("  3. Re-test the original customer issue")
    elif detected == 0:
        lines.append("  1. If the PC still misbehaves, the problem is likely not component-store")
        lines.append("     corruption (check drivers, disk health, user profile, malware, etc.)")
        lines.append("  2. Optional: run SFC anyway for a second opinion")
    else:
        lines.append("  1. Retry Restore Health with install USB / LimitAccess")
        lines.append("  2. Confirm the WIM index matches the installed edition (Home/Pro/etc.)")
        lines.append("  3. Check disk health before spending more time on DISM")

    lines.append("")
    lines.append("Tip: You usually do NOT need to read the raw CBS lines below.")
    lines.append("=" * 70)
    return lines


def export_cbs_repair_report(started_at, repaired_count):
    """
    Write a shop-friendly repair summary plus the raw CBS extract.
    Returns the report path, or None if CBS.log couldn't be read.
    """
    tail = read_cbs_tail(16 * 1024 * 1024)
    if tail is None:
        return None
    
    # CBS.log lines start with 'YYYY-MM-DD HH:MM:SS'; this format compares
    # correctly as plain strings, so no timestamp parsing is needed
    session_start = started_at.strftime('%Y-%m-%d %H:%M:%S')
    session_lines = [
        line for line in tail.splitlines()
        if len(line) >= 19 and line[:19] >= session_start
    ]
    session_text = '\n'.join(session_lines)

    # Prefer the session-scoped repaired count when the caller passed a stale value
    session_repaired = get_cbs_repair_count(started_at)
    if session_repaired is not None:
        repaired_count = session_repaired

    keywords = ('Repr:', 'Repaired', 'orrupt', 'HRESULT', 'Total Detected', 'Total Repaired')
    detail_lines = [
        line for line in session_lines
        if any(k in line for k in keywords)
    ]
    
    report_file = os.path.join(
        get_script_path(),
        f'pydism_repair_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
    )
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("pydism - DISM Repair Report\n")
            f.write(f"Session started: {session_start}\n")
            if repaired_count is not None:
                f.write(f"Files/items repaired (CBS counter): {repaired_count}\n")
            f.write("Extracted from:  C:\\Windows\\Logs\\CBS\\CBS.log\n")
            f.write("\n")
            for line in build_cbs_plain_summary(session_text, repaired_count):
                f.write(line + "\n")
            f.write("\n")
            f.write("RAW CBS EXTRACT (advanced)\n")
            f.write("-" * 70 + "\n")
            if detail_lines:
                f.write('\n'.join(detail_lines) + '\n')
            else:
                f.write("No corruption or repair entries found for this session.\n")
    except OSError:
        return None
    return report_file


def find_install_image(path):
    """
    Locate install.wim, install.esd, or install.swm under a media path.
    Prefers .wim, then .esd, then .swm (split USB media). Returns absolute path or None.
    """
    if not path:
        return None
    path = os.path.abspath(path.strip().strip('"'))
    if os.path.isfile(path):
        lower = path.lower()
        if lower.endswith(('.wim', '.esd', '.swm')):
            return path
        return None

    search_dirs = []
    if os.path.isdir(path):
        search_dirs.append(path)
        sources = os.path.join(path, 'sources')
        if os.path.isdir(sources):
            search_dirs.append(sources)

    for directory in search_dirs:
        for name in ('install.wim', 'install.esd', 'install.swm'):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate
    return None


def resolve_media_root(user_input):
    """
    Turn a drive letter or path into a folder/file to search for install media.
    Examples: E, E:, E:\\, E:\\sources, E:\\sources\\install.esd
    """
    raw = (user_input or '').strip().strip('"')
    if not raw:
        return None

    # Bare drive letter -> E:\sources
    if len(raw) == 1 and raw.isalpha():
        return os.path.join(f"{raw.upper()}:\\", 'sources')
    if len(raw) == 2 and raw[0].isalpha() and raw[1] == ':':
        return os.path.join(f"{raw[0].upper()}:\\", 'sources')
    if len(raw) == 3 and raw[0].isalpha() and raw[1] == ':' and raw[2] in '\\/':
        return os.path.join(f"{raw[0].upper()}:\\", 'sources')

    return os.path.abspath(raw)


def build_wim_source(image_path, image_index=1):
    """
    Build DISM /Source value for install media.
    Uses ESD: for .esd files, WIM: for .wim/.swm.
    """
    prefix = 'ESD' if image_path.lower().endswith('.esd') else 'WIM'
    return f"{prefix}:{image_path}:{int(image_index)}"


def _is_ready_source(value):
    """True if value is already a DISM WIM:/ESD: source string."""
    upper = (value or '').upper()
    return upper.startswith('WIM:') or upper.startswith('ESD:')


def list_wim_indexes(wim_path):
    """
    Run DISM /Get-WimInfo and return [(index, name), ...].
    Returns [] if DISM fails or nothing could be parsed.
    """
    dism_path = os.path.join(
        os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'dism.exe'
    )
    try:
        result = subprocess.run(
            [dism_path, "/Get-WimInfo", f"/WimFile:{wim_path}"],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = (result.stdout or "") + "\n" + (result.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return []

    indexes = []
    current_index = None
    current_name = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        index_match = re.match(r'Index\s*:\s*(\d+)$', line, re.IGNORECASE)
        if index_match:
            if current_index is not None:
                indexes.append((current_index, current_name or f"Image {current_index}"))
            current_index = int(index_match.group(1))
            current_name = None
            continue
        name_match = re.match(r'Name\s*:\s*(.+)$', line, re.IGNORECASE)
        if name_match and current_index is not None:
            current_name = name_match.group(1).strip()
    if current_index is not None:
        indexes.append((current_index, current_name or f"Image {current_index}"))
    return indexes


def prompt_for_media_source():
    """
    Ask for USB/media path, image index, and LimitAccess preference.
    Returns (source_string, image_path, limit_access) or (None, None, None)
    if cancelled / not found.
    """
    print("\n[SOURCE] Restore Health from install USB/media")
    print("Plug in a clean Windows install USB first.")
    print("Examples: E   or   E:\\sources   or   E:\\sources\\install.esd")
    user_path = input("USB drive letter or path: ").strip()
    if not user_path:
        print("[ERROR] No path entered.")
        return None, None, None

    root = resolve_media_root(user_path)
    image_path = find_install_image(root)
    if not image_path:
        print(f"[ERROR] Could not find install.wim, install.esd, or install.swm under: {root}")
        return None, None, None

    print(f"\n[OK] Found image: {image_path}")
    print("Reading edition list (DISM /Get-WimInfo)...")
    wim_indexes = list_wim_indexes(image_path)
    if wim_indexes:
        print("\nAvailable editions on this media:")
        for idx, name in wim_indexes:
            print(f"  {idx}. {name}")
        valid_indexes = {idx for idx, _ in wim_indexes}
        default_index = wim_indexes[0][0]
    else:
        print("[WARNING] Could not list editions - enter the index manually.")
        print("          (Common: 1 = first edition on the USB)")
        valid_indexes = None
        default_index = 1

    index_raw = input(f"Image index (default {default_index}): ").strip() or str(default_index)
    try:
        image_index = int(index_raw)
        if image_index < 1:
            raise ValueError
        if valid_indexes is not None and image_index not in valid_indexes:
            print(f"[ERROR] Index {image_index} is not on this media.")
            return None, None, None
    except ValueError:
        print("[ERROR] Index must be a positive integer.")
        return None, None, None

    # Default Y: only use the USB/media, do not fall back to Windows Update
    limit_raw = input("Disable Windows Update fallback (/LimitAccess)? (Y/n): ").strip().lower()
    limit_access = limit_raw not in ('n', 'no')

    source = build_wim_source(image_path, image_index)
    chosen_name = None
    if wim_indexes:
        chosen_name = next((name for idx, name in wim_indexes if idx == image_index), None)
    print("\nResolved media:")
    print(f"  Image:  {image_path}")
    if chosen_name:
        print(f"  Edition: {chosen_name} (index {image_index})")
    print(f"  Source: {source}")
    if limit_access:
        print("  LimitAccess: yes (Windows Update fallback disabled)")
    else:
        print("  LimitAccess: no (may fall back to Windows Update)")
    confirm = input("\nProceed with Restore Health? (y/n): ").strip().lower()
    if confirm not in ('y', 'yes'):
        print("Cancelled.")
        return None, None, None
    return source, image_path, limit_access


def restore_health(logger, source=None, image_index=1, limit_access=True):
    """Repair Windows system health, optionally from install USB/media"""
    print("\n[REPAIR] Repairing Windows System Health...")
    if source:
        if limit_access:
            print("Using install media as repair source (/LimitAccess).")
        else:
            print("Using install media as repair source (Windows Update fallback allowed).")
    else:
        print("This will scan AND repair any corruption found.")
    started_at = datetime.now()

    command_args = ["/Online", "/Cleanup-Image", "/RestoreHealth"]
    if source:
        source_value = source
        if not _is_ready_source(source_value):
            image_path = find_install_image(resolve_media_root(source_value) or source_value)
            if not image_path:
                print(f"[ERROR] Could not find install.wim, install.esd, or install.swm for: {source}")
                logger.error(f"Source media not found: {source}")
                return False
            source_value = build_wim_source(image_path, image_index)
        command_args.append(f"/Source:{source_value}")
        if limit_access:
            command_args.append("/LimitAccess")
        logger.info(
            f"DISM RestoreHealth using source: {source_value} "
            f"(LimitAccess={'yes' if limit_access else 'no'})"
        )

    success = run_dism_command(command_args, logger, is_restore=True)
    
    if success:
        repaired = get_cbs_repair_count(started_at)
        if repaired is not None:
            if repaired > 0:
                print(f"\n[INFO] Windows reports {repaired} corrupted item(s) were repaired.")
                logger.info(f"CBS repair summary: {repaired} items repaired")
            else:
                print("\n[INFO] Windows reports no component-store items needed repair.")
                logger.info("CBS repair summary: 0 items repaired")
        
        report = export_cbs_repair_report(started_at, repaired)
        if report:
            print(f"Repair report saved: {report}")
            print("(Opens with a plain-English summary first - raw CBS lines are below it.)")
            logger.info(f"CBS repair report: {report}")
        else:
            print("Full details: C:\\Windows\\Logs\\CBS\\CBS.log")
    
    return success


def run_sfc(logger):
    """Run System File Checker"""
    print("\n[SFC] Running System File Checker...")
    print("This verifies and repairs protected system files.")
    logger.info("Starting SFC /scannow")
    
    try:
        process = subprocess.Popen(
            ["sfc", "/scannow"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        print("\nSFC Output:")
        print("-" * 50)
        
        last_percent = -1
        result_buffer = ""
        
        if process.stdout:
            while True:
                # Read raw bytes and decode UTF-16
                chunk = process.stdout.read(1024)
                if not chunk and process.poll() is not None:
                    break
                if chunk:
                    try:
                        # SFC outputs UTF-16LE
                        text = chunk.decode('utf-16-le', errors='ignore')
                    except:
                        text = chunk.decode('utf-8', errors='ignore')
                    
                    # Clean up null bytes
                    text = text.replace('\x00', '')
                    
                    # Check for progress percentage
                    if '%' in text:
                        match = re.search(r'(\d+)\s*%', text)
                        if match:
                            percent = int(match.group(1))
                            if percent != last_percent:
                                # Simple progress bar
                                bar_width = 50
                                filled = int(bar_width * percent / 100)
                                bar = '=' * filled + ' ' * (bar_width - filled)
                                print(f"\r[{bar}] {percent:3d}%", end='', flush=True)
                                last_percent = percent
                    else:
                        # Buffer non-progress text for final results
                        result_buffer += text
        
        print()  # New line after progress bar
        
        # Print final results (cleaned up)
        final_result = ""
        if result_buffer:
            # Clean and print meaningful lines
            for line in result_buffer.split('\n'):
                line = line.strip()
                # Skip empty lines and progress-related text
                if line and 'verification' not in line.lower() and 'complete' not in line.lower():
                    print(line)
                    final_result += line + " "
        
        process.wait(timeout=1800)
        
        print("-" * 50)
        print(f"Completed with return code: {process.returncode}")
        logger.info(f"SFC completed with return code: {process.returncode}")
        
        # Log the result
        if "did not find any integrity violations" in final_result.lower():
            logger.info("SFC Result: No integrity violations found")
        elif "found corrupt files and successfully repaired" in final_result.lower():
            logger.info("SFC Result: Found and repaired corrupt files")
        elif "found corrupt files but was unable to fix" in final_result.lower():
            logger.info("SFC Result: Found corrupt files but could not repair")
        elif final_result.strip():
            logger.info(f"SFC Result: {final_result.strip()[:200]}")
        
        return process.returncode == 0
        
    except Exception as e:
        print(f"[ERROR] {e}")
        logger.error(f"SFC failed: {e}")
        return False


def show_menu():
    """Display main menu"""
    print("\n" + "=" * 55)
    print("    pydism - Windows DISM Repair Tool")
    print("=" * 55)
    print("")
    print("  1. [SCAN]   Scan Health (check for issues)")
    print("  2. [REPAIR] Restore Health (scan and repair)")
    print("  3. [SFC]    System File Checker")
    print("  4. [FULL]   Full Repair (DISM + SFC)")
    print("  5. [SOURCE] Restore Health from USB/media")
    print("")
    print("  0. [EXIT]   Exit")
    print("")
    print("-" * 55)


def main():
    print("pydism - Windows DISM Repair Tool")
    print("Checking privileges...")
    
    if not is_admin():
        print("Requesting admin privileges...")
        run_as_admin()
        return
    
    logger, log_file = setup_logging()
    logger.info("pydism started with admin privileges")
    
    print(f"\n[OK] Running as Administrator")
    print(f"[OK] Log file: {log_file}")
    
    while True:
        show_menu()
        choice = input("Select option: ").strip()
        
        if choice == "0":
            print("\nExiting pydism...")
            logger.info("pydism session ended")
            break
            
        elif choice == "1":
            success, output = scan_health(logger)
            scan_result = classify_dism_output(output)
            if scan_result == "healthy":
                print("\n[SUCCESS] Scan complete - system is healthy!")
                logger.info("User action: Scan Health - system is healthy")
            elif scan_result == "repairable":
                print("\n[NOTICE] Scan complete - minor issues found")
                print("The component store has repairable corruption.")
                print("Run option 2 (Restore Health) to fix it.")
                logger.info("User action: Scan Health - repairable issues found")
            elif success:
                print("\n[SUCCESS] Scan complete")
                logger.info("User action: Scan Health completed")
            else:
                print("\n[WARNING] Scan completed with errors")
                logger.warning("User action: Scan Health completed with errors")
            input("\nPress Enter to continue...")
            
        elif choice == "2":
            success = restore_health(logger)
            if success:
                print("\n[SUCCESS] Repair complete!")
                print("Consider running option 3 (SFC) as a follow-up")
                logger.info("User action: Restore Health completed successfully")
            else:
                print("\n[WARNING] Repair completed with issues")
                print("Check the log file for details")
                logger.warning("User action: Restore Health completed with issues")
            input("\nPress Enter to continue...")
            
        elif choice == "3":
            success = run_sfc(logger)
            if success:
                print("\n[SUCCESS] SFC complete!")
                logger.info("User action: SFC completed successfully")
            else:
                print("\n[WARNING] SFC completed with issues")
                logger.warning("User action: SFC completed with issues")
            input("\nPress Enter to continue...")
            
        elif choice == "4":
            print("\n[FULL] Running Full Repair Sequence...")
            logger.info("User action: Starting Full Repair (DISM + SFC)")
            
            print("Step 1/2: DISM Restore Health")
            dism_success = restore_health(logger)
            
            print("\nStep 2/2: System File Checker")
            sfc_success = run_sfc(logger)
            
            print("\n" + "=" * 55)
            print("  Full Repair Summary")
            print("=" * 55)
            print(f"  DISM Restore Health: {'SUCCESS' if dism_success else 'ISSUES'}")
            print(f"  System File Checker: {'SUCCESS' if sfc_success else 'ISSUES'}")
            print("=" * 55)
            
            if dism_success and sfc_success:
                print("\n[SUCCESS] Full repair completed successfully!")
                print("A restart is recommended.")
                logger.info("User action: Full Repair completed successfully")
            else:
                print("\n[WARNING] Repair completed with some issues")
                print("Check the log file for details")
                logger.warning(f"User action: Full Repair completed - DISM: {dism_success}, SFC: {sfc_success}")
            
            input("\nPress Enter to continue...")

        elif choice == "5":
            source, _image, limit_access = prompt_for_media_source()
            if source:
                success = restore_health(logger, source=source, limit_access=limit_access)
                if success:
                    print("\n[SUCCESS] Repair complete!")
                    print("Consider running option 3 (SFC) as a follow-up")
                    logger.info("User action: Restore Health from media completed successfully")
                else:
                    print("\n[WARNING] Repair completed with issues")
                    print("Check the log file for details")
                    logger.warning("User action: Restore Health from media completed with issues")
            input("\nPress Enter to continue...")
            
        else:
            print("\nInvalid option. Please try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        input("Press Enter to exit...")
