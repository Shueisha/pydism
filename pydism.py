"""
pydism - Windows DISM Repair Tool
https://github.com/YOUR_USERNAME/pydism

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
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{sys.argv[0]}"', None, 1
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


def run_dism_command(command_args, logger, is_restore=False, capture_output=False):
    """
    Execute DISM command with live output and smart progress indicator.
    
    The 62.3% progress indicator explains DISM's normal pause behavior
    during component store analysis - this prevents confusion during
    what looks like a "stuck" operation but is actually normal.
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
            print("  62.3%:   Component store check (may pause 10-20 min)")
            print("  65-100%: Repair and cleanup operations")
            print("")
            print("  The pause at 62.3% is NORMAL - please be patient!")
            print("=" * 55)
            logger.info("DISM RestoreHealth started - 62.3% pause is normal")
        
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
        
        if process.stdout:
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    line = line.strip()
                    print(line)
                    output_lines.append(line)
                    
                    # Monitor progress for RestoreHealth
                    if is_restore and "%" in line:
                        match = re.search(r'(\d+\.?\d*)%', line)
                        if match:
                            progress = float(match.group(1))
                            
                            # Explain the 62.3% pause
                            if 62.0 <= progress <= 63.0 and not pause_notified:
                                print("\n" + "=" * 55)
                                print("  [NORMAL] Component Store Analysis Phase")
                                print("  DISM is checking thousands of system files.")
                                print("  This typically takes 10-20 minutes.")
                                print("  DO NOT interrupt - progress will resume.")
                                print("=" * 55 + "\n")
                                logger.info("DISM 62.3% component store analysis phase")
                                pause_notified = True
                            
                            # Progress milestones
                            elif progress >= 65.0 and last_progress and last_progress < 65.0:
                                print("[PROGRESS] Component check complete - continuing...")
                                logger.info("DISM passed 65%")
                            elif progress >= 90.0 and last_progress and last_progress < 90.0:
                                print("[PROGRESS] Nearly complete...")
                                logger.info("DISM at 90%")
                            
                            last_progress = progress
        
        process.wait(timeout=3600)
        return_code = process.returncode
        
        print("-" * 50)
        print(f"Completed with return code: {return_code}")
        logger.info(f"DISM completed with return code: {return_code}")
        
        # Log key results
        output_text = '\n'.join(output_lines)
        if "No component store corruption detected" in output_text:
            logger.info("Result: System is healthy - no corruption detected")
        elif "repairable" in output_text.lower():
            logger.info("Result: Component store has repairable corruption")
        elif "successfully repaired" in output_text.lower() or "completed successfully" in output_text.lower():
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


def restore_health(logger):
    """Repair Windows system health"""
    print("\n[REPAIR] Repairing Windows System Health...")
    print("This will scan AND repair any corruption found.")
    return run_dism_command(["/Online", "/Cleanup-Image", "/RestoreHealth"], logger, is_restore=True)


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
            if "No component store corruption detected" in output:
                print("\n[SUCCESS] Scan complete - system is healthy!")
                logger.info("User action: Scan Health - system is healthy")
            elif "repairable" in output.lower():
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
