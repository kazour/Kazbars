"""
Combat Log Monitor Module for KazBars
Daemon thread that monitors Age of Conan combat logs for boss mechanics.
"""

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class CombatLogMonitor:
    """
    Monitors AoC combat log files for Ethram-Fal boss triggers.

    Runs in a daemon thread, automatically detects new log files,
    and calls the boss_timer methods when triggers are found.

    Usage:
        monitor = CombatLogMonitor(boss_timer)
        monitor.set_log_folder("/path/to/AgeOfConan")
        monitor.start_monitoring()
        # ...later...
        monitor.stop_monitoring()
    """

    # Combat log trigger patterns
    TRIGGER_SEED = "Viscous Seed"
    TRIGGER_FIXATION = "Lotus Fixation"
    TRIGGER_SYPHON = "Syphon hits"

    def __init__(self, boss_timer):
        """
        Initialize the combat log monitor.

        Args:
            boss_timer: BossTimer instance to call when triggers detected
        """
        self.boss_timer = boss_timer
        self.log_path = None
        self.log_folder = None
        self.monitoring = False
        self.monitor_thread = None
        self.last_position = 0
        self.last_file_check = 0
        self.file_handle = None
        self._lock = threading.Lock()

    def set_log_folder(self, folder):
        """
        Set the combat log folder and find the latest log file.

        Args:
            folder: Path to game root folder containing CombatLog files

        Returns:
            str: Path to latest log file, or None if not found
        """
        self.log_folder = folder
        latest = self._find_latest_log()
        if latest:
            self.log_path = latest
            p = Path(latest)
            if p.exists():
                self.last_position = p.stat().st_size
            else:
                self.last_position = 0
        return latest

    def rescan_log(self):
        """
        Manually rescan for the latest combat log file.
        Resets the file handle and position to the end of the new log.

        Returns:
            str: Path to latest log file, or None if not found
        """
        latest = self._find_latest_log()
        if latest:
            if self.file_handle:
                try:
                    self.file_handle.close()
                except OSError:
                    pass
                self.file_handle = None
            self.log_path = latest
            p = Path(latest)
            if p.exists():
                self.last_position = p.stat().st_size
            else:
                self.last_position = 0
        return latest

    def _find_latest_log(self):
        """
        Find the most recently modified CombatLog*.txt file.

        Returns:
            str: Path to latest log, or None if not found
        """
        folder = Path(self.log_folder) if self.log_folder else None
        if not folder or not folder.exists():
            return None

        try:
            combat_logs = []
            for entry in folder.iterdir():
                if entry.name.startswith("CombatLog") and entry.name.endswith(".txt"):
                    mtime = entry.stat().st_mtime
                    combat_logs.append((str(entry), mtime))

            if combat_logs:
                combat_logs.sort(key=lambda x: x[1], reverse=True)
                return combat_logs[0][0]
        except OSError:
            pass

        return None

    def start_monitoring(self):
        """
        Start the monitoring daemon thread.

        Returns:
            bool: True if started, False if no valid log path
        """
        if not self.log_path or not Path(self.log_path).exists():
            return False

        with self._lock:
            if self.monitoring:
                return True  # Already running

            self.monitoring = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="CombatLogMonitor"
            )
            self.monitor_thread.start()

        return True

    def stop_monitoring(self):
        """Stop the monitoring thread and close file handle."""
        with self._lock:
            self.monitoring = False

        if self.file_handle:
            try:
                self.file_handle.close()
            except OSError:
                pass
            self.file_handle = None

    def _check_for_newer_log(self):
        """
        Check for a newer log file every 30 seconds.
        Switches to new log if found.

        Returns:
            bool: True if switched to a new log
        """
        try:
            current_time = time.time()
            if current_time - self.last_file_check < 30:
                return False
            self.last_file_check = current_time

            newest_log = None
            newest_mtime = 0

            for entry in Path(self.log_folder).iterdir():
                if entry.name.startswith("CombatLog") and entry.name.endswith(".txt"):
                    full_path = str(entry)
                    mtime = entry.stat().st_mtime
                    if mtime > newest_mtime:
                        newest_mtime = mtime
                        newest_log = full_path

            if newest_log and newest_log != self.log_path:
                # Switch to newer log
                if self.file_handle:
                    self.file_handle.close()
                    self.file_handle = None
                self.log_path = newest_log
                self.last_position = 0
                return True

        except OSError:
            pass
        return False

    def _monitor_loop(self):
        """Main monitoring loop - runs in daemon thread."""
        while self.monitoring:
            try:
                self._check_for_newer_log()

                # Handle log file truncation/rotation
                log = Path(self.log_path)
                if log.exists():
                    current_size = log.stat().st_size
                    if current_size < self.last_position:
                        # Log was truncated/rotated
                        self.last_position = 0
                        if self.file_handle:
                            self.file_handle.close()
                            self.file_handle = None

                # Open file if needed
                if self.file_handle is None:
                    self.file_handle = open(
                        self.log_path,
                        encoding='utf-8', errors='replace'
                    )

                # Read new content
                self.file_handle.seek(self.last_position)
                new_content = self.file_handle.read()
                self.last_position = self.file_handle.tell()

                # Process new lines
                if new_content:
                    for line in new_content.splitlines():
                        if (self.TRIGGER_SEED in line or
                            self.TRIGGER_FIXATION in line or
                            self.TRIGGER_SYPHON in line):
                            self._process_line(line)

            except OSError:
                # Handle file access errors gracefully
                if self.file_handle:
                    try:
                        self.file_handle.close()
                    except OSError:
                        pass
                    self.file_handle = None

            # 100ms polling interval
            time.sleep(0.1)

    def _process_line(self, line):
        """
        Process a combat log line for triggers.

        Args:
            line: Single line from combat log
        """
        # Syphon check (highest priority - interrupts timer)
        if "Ethram-Fal's Syphon hits" in line:
            self.boss_timer.start_syphon()
            return

        # Seed check
        if "Ethram-Fal afflicts" in line and "with Viscous Seed" in line:
            if "afflicts you with" in line:
                player = "YOU"
            else:
                player = self._extract_player(line, "afflicts", "with Viscous Seed")
            self.boss_timer.start_cycle(player)
            return

        # Fixation check
        if "The Emerald Lotus afflicts" in line and "with Lotus Fixation" in line:
            if "afflicts you with" in line:
                player = "YOU"
            else:
                player = self._extract_player(
                    line, "The Emerald Lotus afflicts", "with Lotus Fixation"
                )
            self.boss_timer.update_fixation(player)
            return

    def _extract_player(self, line, before_text, after_text):
        """
        Extract player name from between two text markers.

        Args:
            line: Full log line
            before_text: Text that appears before the player name
            after_text: Text that appears after the player name

        Returns:
            str: Extracted player name, or "Unknown" if extraction fails
        """
        try:
            start = line.find(before_text) + len(before_text)
            end = line.find(after_text)
            return line[start:end].strip()
        except (ValueError, IndexError):
            return "Unknown"
