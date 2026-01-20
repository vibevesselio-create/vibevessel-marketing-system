#!/usr/bin/env python3
"""
Claude Code Agent Desktop Automation
=====================================

Replicates the Keyboard Maestro macro 91D83B2F-C2C2-44AE-A254-F4EDDC6C4ED4
"Folder Trigger: Claude Code Agent" for submitting prompts.

ACTUAL KM Macro Sequence (verified from plist):
1. 1-Second Pause
2. Bring Claude Window to Front (sub-macro 6CB5D6D2)
3. Paste Trigger Clipboard (sub-macro D8CE117A):
   - 1s pause
   - InsertText by pasting %TriggerClipboard%
   - 1s pause
   - KeyCode 36 (Return)
4. 1-Second Pause
5. Type Return (KeyCode 36)
6. Wait for response...

Usage:
    python scripts/trigger_claude_code_prompt.py "Your prompt here"
    python scripts/trigger_claude_code_prompt.py --file /path/to/prompt.txt
    python scripts/trigger_claude_code_prompt.py --file prompt.md --submit
    python scripts/trigger_claude_code_prompt.py --verbose --submit "test"

Author: Cursor MM1 Agent • 2026-01-20
"""

import os
import sys
import time
import logging
import subprocess
import argparse
from typing import Dict, Any, Tuple
from pathlib import Path
from datetime import datetime

# Configure logging
log_dir = Path('/Users/brianhellemn/Projects/github-production/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'claude_code_desktop_automation.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ClaudeCodeDesktopAutomation:
    """Desktop automation for Claude Code - replicates KM folder trigger."""
    
    KM_MACRO_UUID = "91D83B2F-C2C2-44AE-A254-F4EDDC6C4ED4"
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.step_num = 0
        
    def log_step(self, description: str):
        """Log a step with timestamp."""
        self.step_num += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        msg = f"[Step {self.step_num:02d}] [{timestamp}] {description}"
        logger.info(msg)
        if self.verbose:
            print(f"  >> {msg}")
        
    def run_applescript(self, script: str, timeout: int = 30) -> Tuple[bool, str]:
        """Execute AppleScript."""
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                logger.debug(f"AppleScript stderr: {result.stderr}")
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)
    
    def set_clipboard(self, content: str) -> bool:
        """Set clipboard using pbcopy."""
        try:
            proc = subprocess.run(['pbcopy'], input=content, text=True, capture_output=True)
            if proc.returncode == 0:
                self.log_step(f"Set clipboard ({len(content)} chars)")
                return True
            return False
        except Exception as e:
            logger.error(f"Clipboard error: {e}")
            return False
    
    def pause(self, seconds: float, reason: str = ""):
        """Pause with logging."""
        desc = f" ({reason})" if reason else ""
        self.log_step(f"Pause {seconds}s{desc}")
        time.sleep(seconds)
    
    def bring_claude_to_front(self) -> bool:
        """Bring Claude window to front and position to right half."""
        self.log_step("Bring Claude to front + position right half")
        script = '''
-- Get screen size
tell application "Finder"
    set screenBounds to bounds of window of desktop
    set screenWidth to item 3 of screenBounds
    set screenHeight to item 4 of screenBounds
end tell

-- Activate and position Claude
tell application "Claude"
    activate
end tell

delay 0.5

tell application "System Events"
    tell process "Claude"
        set frontmost to true
        delay 0.3
        
        -- Position to right half of screen
        try
            set position of window 1 to {(screenWidth / 2) as integer, 0}
            set size of window 1 to {(screenWidth / 2) as integer, screenHeight}
        end try
    end tell
end tell
'''
        success, _ = self.run_applescript(script, timeout=10)
        return success
    
    def paste_clipboard(self) -> bool:
        """Paste clipboard content (Cmd+V)."""
        self.log_step("Paste clipboard (Cmd+V)")
        script = '''
tell application "System Events"
    tell process "Claude"
        set frontmost to true
        delay 0.2
        keystroke "v" using command down
    end tell
end tell
'''
        success, _ = self.run_applescript(script)
        return success
    
    def press_return(self) -> bool:
        """Press Return key to submit."""
        self.log_step("Press Return (submit)")
        script = '''
tell application "System Events"
    tell process "Claude"
        set frontmost to true
        key code 36
    end tell
end tell
'''
        success, _ = self.run_applescript(script)
        return success
    
    def trigger_km_macro(self) -> bool:
        """Fallback: trigger the actual KM macro."""
        self.log_step(f"Trigger KM macro {self.KM_MACRO_UUID}")
        script = f'''
tell application "Keyboard Maestro Engine"
    do script "{self.KM_MACRO_UUID}"
end tell
'''
        success, _ = self.run_applescript(script, timeout=10)
        return success
    
    def submit_prompt(
        self,
        prompt: str,
        auto_submit: bool = False,
        use_km_fallback: bool = False
    ) -> Dict[str, Any]:
        """
        Submit prompt to Claude Code.
        
        Sequence (matching KM macro):
        1. Set clipboard
        2. 1s pause
        3. Bring Claude to front + position
        4. 1s pause  
        5. Paste (Cmd+V)
        6. 1s pause
        7. Press Return (if auto_submit)
        """
        self.step_num = 0
        start = time.time()
        
        result = {
            "success": False,
            "method": "unknown",
            "error": None,
            "prompt_length": len(prompt),
            "elapsed_seconds": 0
        }
        
        logger.info("=" * 60)
        logger.info(f"Starting Claude Code automation ({len(prompt)} chars)")
        logger.info("=" * 60)
        
        try:
            # Step 1: Set clipboard
            if not self.set_clipboard(prompt):
                result["error"] = "Failed to set clipboard"
                return result
            
            # Use KM fallback if requested
            if use_km_fallback:
                self.pause(1.0)
                if self.trigger_km_macro():
                    result["success"] = True
                    result["method"] = "keyboard_maestro"
                else:
                    result["error"] = "KM macro failed"
                return result
            
            # Step 2: Pause
            self.pause(1.0, "before activation")
            
            # Step 3: Bring Claude to front + position
            if not self.bring_claude_to_front():
                result["error"] = "Failed to bring Claude to front"
                return result
            
            # Step 4: Pause
            self.pause(1.0, "after activation")
            
            # Step 5: Paste
            if not self.paste_clipboard():
                result["error"] = "Failed to paste"
                return result
            
            # Step 6: Pause
            self.pause(1.0, "after paste")
            
            # Step 7: Submit if requested
            if auto_submit:
                if not self.press_return():
                    result["error"] = "Failed to press Return"
                    return result
                self.log_step("DONE - Prompt submitted")
            else:
                self.log_step("DONE - Prompt pasted (submit manually)")
            
            result["success"] = True
            result["method"] = "native"
            result["submitted"] = auto_submit
            
        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Error: {e}")
        
        result["elapsed_seconds"] = round(time.time() - start, 2)
        logger.info(f"Completed in {result['elapsed_seconds']}s")
        
        return result


def main():
    parser = argparse.ArgumentParser(description="Submit prompt to Claude Code")
    parser.add_argument('prompt', nargs='?', help='Prompt text')
    parser.add_argument('--file', '-f', help='Read prompt from file')
    parser.add_argument('--stdin', action='store_true', help='Read from stdin')
    parser.add_argument('--submit', '-s', action='store_true', help='Auto-submit')
    parser.add_argument('--km-fallback', action='store_true', help='Use KM macro')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--quiet', '-q', action='store_true', help='Quiet mode')
    
    args = parser.parse_args()
    
    # Get prompt
    if args.file:
        prompt = Path(args.file).read_text()
    elif args.stdin:
        prompt = sys.stdin.read()
    elif args.prompt:
        prompt = args.prompt
    else:
        print("Error: Provide prompt, --file, or --stdin")
        sys.exit(1)
    
    # Run
    auto = ClaudeCodeDesktopAutomation(verbose=args.verbose)
    result = auto.submit_prompt(
        prompt=prompt,
        auto_submit=args.submit,
        use_km_fallback=args.km_fallback
    )
    
    if not args.quiet:
        if result["success"]:
            print(f"✅ Success ({result['method']}, {result['elapsed_seconds']}s)")
            print(f"   {'Submitted' if result.get('submitted') else 'Pasted (submit manually)'}")
        else:
            print(f"❌ Failed: {result['error']}")
    
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
