#!/usr/bin/env python3
import urwid, time
import os
import pygame.mixer
import mutagen
import sys
from datetime import datetime, timedelta
import subprocess
import signal

palette = [
    ('header', 'light blue', 'default'),
    ('path_label', 'light blue', 'default'),
    ('path_value', 'dark gray', 'default'),
    ('directory', 'dark blue,bold', 'default'),
    ('audio_file', 'light cyan', 'default'),
    ('normal', 'white', 'default'),
    ('selected', 'light green,bold', 'default'),
    ('perm_denied', 'light red', 'default'),
    ('error', 'light red', 'default'),
    ('playing', 'light green', 'default'),
    ('pink_frame', 'light magenta', 'default'),
    ('percent', 'white,bold', 'default'),
    ('time_separator', 'dark gray', 'default'),
    ('time_separator,bold', 'dark gray,bold', 'default'),
]

font = {
    '0': ["┌─┐", "│ │", "└─┘"],
    '1': [" ┌┐", "  │", "  ┘"],
    '2': ["┌─┐", "┌─┘", "└─┘"],
    '3': ["┌─┐", " ─┤", "└─┘"],
    '4': ["┌ ┐", "└─┤", "  ┘"],
    '5': ["┌─┐", "└─┐", "└─┘"],
    '6': ["┌─┐", "├─┐", "└─┘"],
    '7': ["┌─┐", "  ┤", "  ┘"],
    '8': ["┌─┐", "├─┤", "└─┘"],
    '9': ["┌─┐", "└─┤", "└─┘"],
    ':': [" ┌┐ ", " ├┤ ", " └┘ "]
}

empty_char = ["   ", "   ", "   "]

def get_pseudographic_char(c):
    return font.get(c, empty_char)

def print_pseudographic_time(hours, mins, secs):
    if not (0 <= hours <= 23 and 0 <= mins <= 59 and 0 <= secs <= 59):
        return [('error', f"Invalid time: {hours:02d}:{mins:02d}:{secs:02d}")]

    time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
    chars = [get_pseudographic_char(c) for c in time_str]

    result = []
    for row in range(3):
        line = []
        for i, char in enumerate(chars):
            style = 'time_separator' if i in [2, 5] else 'normal'
            line.append((style, char[row].rstrip().ljust(4)))
        result.append(line)
    return result

def get_month_name(month):
    months = ["January", "February", "March", "April", "May", "June",
              "July", "August", "September", "October", "November", "December"]
    return months[month - 1] if 1 <= month <= 12 else "Unknown"

def get_weekday_name(weekday):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return days[weekday] if 0 <= weekday <= 6 else "Unknown"

def get_date_string():
    t = time.localtime()
    month_name = get_month_name(t.tm_mon)
    weekday_name = get_weekday_name(t.tm_wday)
    return " {}/{}|{}/{} ".format(
        t.tm_year,
        month_name,
        t.tm_mday,
        weekday_name
    )
class PlaybackMode(urwid.ListBox):
    def __init__(self, main_loop, root_dir, input_path=None):
        pygame.mixer.init()
        self.main_loop = main_loop
        self.root_dir = root_dir
        self.current_dir = os.getcwd()
        self.dir_history = []
        self.file_list = urwid.SimpleFocusListWalker([])
        self.playlist = []
        self.playlist_index = 0

        self.progress_bar = urwid.Text([('normal', "  0"), ('time_separator', '%'), (None, " | " + " " * 83)], align='left') #self.progress_bar = urwid.Text([('path_value', "  0"), ('percent', '%'), (None, " | " + " " * 83)], align='left')
        term_size = os.get_terminal_size()
        term_width = term_size.columns
        total_width = term_width - 1
        left_width = int(total_width * 0.62)

        title = "PLAYBACK PROGRESS"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = left_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)

        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        if len(top_line) > left_width:
            top_line = top_line[:left_width - 1] + '┐'
        elif len(top_line) < left_width:
            top_line = top_line[:-1] + '─' * (left_width - len(top_line)) + '┐'

        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')

        side_borders = urwid.LineBox(self.progress_bar, lline='│', rline='│',
                                     tline='', bline='',
                                     tlcorner='', trcorner='',
                                     blcorner='', brcorner='')

        footer_line = f'└{"─" * (left_width - 2)}┘'
        footer_text = urwid.Filler(urwid.Text(('pink_frame', footer_line), align='left'), valign='top')

        framed_widget = urwid.Pile([(1, top_text), ('weight', 1, side_borders), (1, footer_text)])
        self.file_frame = urwid.AttrMap(framed_widget, 'pink_frame')

        self.volume_bar = urwid.Text([('normal', " 50"), ('time_separator', '%'), (None, " | " + '░' * 25 + ' ' * 25)]) #self.volume_bar = urwid.Text(f" 50% | {'░' * 25 + ' ' * 25}")
        term_size = os.get_terminal_size()
        term_width = term_size.columns
        total_border_chars = 6
        available_width = term_width - total_border_chars
        num_upper_boxes = 3
        base_status_width = (available_width // 3 + available_width // 4) // 2
        status_width = max(15, base_status_width + 3)
        remaining_width = available_width - status_width - 7
        files_width = remaining_width // 2
        metadata_width = available_width - files_width - status_width + 2
        total_width_so_far = files_width + status_width + metadata_width + 8
        if total_width_so_far < available_width:
            metadata_width += available_width - total_width_so_far
        title = "PYGAME.MIXER VOLUME LEVEL"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = metadata_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        if len(top_line) > metadata_width:
            top_line = top_line[:metadata_width - 1] + '┐'
        elif len(top_line) < metadata_width:
            top_line = top_line[:-1] + '─' * (metadata_width - len(top_line)) + '┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')
        side_borders = urwid.LineBox(self.volume_bar, lline='│', rline='│', tline='', bline='─', tlcorner='', trcorner='', blcorner='└', brcorner='┘')
        new_right_frame = urwid.Pile([(1, top_text), ('weight', 1, side_borders)])
        self.metadata_frame = urwid.AttrMap(new_right_frame, 'pink_frame')

        self.path_text_inner = urwid.Text([('path_value', self.current_dir)], align='left')
        self.path_text = urwid.Padding(self.path_text_inner, left=1)
        self.path_filler = urwid.Filler(self.path_text, valign='top')
        term_width = os.get_terminal_size().columns
        title = "Path"
        title_len = len("┤ Path ├")
        adjusted_width = term_width - 4
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}┤ PATH ├{"─" * side_len}'
        if len(top_line) < term_width - 2:
            top_line += "─" * (term_width - len(top_line) - 3) + "┐"
        elif len(top_line) >= term_width - 1:
            top_line = top_line[:term_width - 3] + "┐"
        else:
            top_line += "┐"
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')
        side_borders = urwid.LineBox(self.path_filler, lline='│', rline='│', tline='', bline='', tlcorner='', trcorner='', blcorner='', brcorner='')
        footer_line = f'└{"─" * (len(top_line) - 2)}┘'
        if len(footer_line) > term_width - 1:
            footer_line = footer_line[:term_width - 2]
        footer_text = urwid.Filler(urwid.Text(('pink_frame', footer_line), align='left'), valign='top')
        framed_widget = urwid.Pile([(1, top_text), ('weight', 1, side_borders), (1, footer_text)])
        self.path_widget = urwid.AttrMap(framed_widget, 'pink_frame')

        self.status_output = urwid.Text("", align='left')
        self.status_filler = urwid.Filler(self.status_output, valign='top')

        self.playing = False
        self.paused = False
        self.volume = 0.5
        self.current_audio_duration = 0

        try:
            result = subprocess.check_output("amixer get Master | grep -o '[0-9]*%' | uniq", shell=True, text=True).strip()
            percent = int(result.rstrip('%'))
            filled = min(50, int(percent / 2))
            initial_volume_text = [('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")] #initial_volume_text = f" {percent}% | {'░' * filled + ' ' * (50 - filled)}"
        except subprocess.CalledProcessError:
            initial_volume_text = " --% " + " " * 50
        self.system_volume_bar = urwid.Text(initial_volume_text)

        try:
            result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
            percent = int(result.rstrip('%'))
            filled = min(50, int(percent / 2))
            initial_headphone_left_text = [('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")] #initial_headphone_left_text = f" {percent}% | {'░' * filled + ' ' * (50 - filled)}"
        except (subprocess.CalledProcessError, ValueError):
            initial_headphone_left_text = " --% | " + " " * 50
        self.headphone_left_bar = urwid.Text(initial_headphone_left_text, align='left')

        try:
            result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
            percent = int(result.rstrip('%'))
            filled = min(50, int(percent / 2))
            initial_headphone_right_text = [('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")] #initial_headphone_right_text = f" {percent}% | {'░' * filled + ' ' * (50 - filled)}"
        except (subprocess.CalledProcessError, ValueError):
            initial_headphone_right_text = " --% | " + " " * 50
        self.headphone_right_bar = urwid.Text(initial_headphone_right_text, align='left')
        super().__init__(self.file_list)
        self.input_path = input_path
        if not input_path:
            self.refresh_list()
        self.widget = None
        self.initialize_widget()

    def start(self):
        if self.input_path:
            if os.path.isdir(self.input_path):
                self.load_and_play_directory(self.input_path)
            elif os.path.isfile(self.input_path):
                self.load_and_play_audio(self.input_path)

    def format_time(self, seconds):
        return str(timedelta(seconds=int(seconds))).zfill(8)

    def format_time(self, seconds):
        return str(timedelta(seconds=int(seconds))).zfill(8)

    def format_active_time(self, elapsed_str, duration_str):
        result = [('normal', " ")]
        for i, char in enumerate(elapsed_str):
            if char.isdigit():
                result.append(('normal', char))
            else:
                result.append(('time_separator,bold', char))
        result.append(('time_separator,bold', " / "))
        for i, char in enumerate(duration_str):
            if char.isdigit():
                result.append(('normal', char))
            else:
                result.append(('time_separator,bold', char))
        return result

    def update_progress_bar(self, loop=None, data=None):
        if self.playing and not self.paused and pygame.mixer.music.get_busy():
            elapsed = pygame.mixer.music.get_pos() / 1000
            duration = self.current_audio_duration
            if duration > 0:
                progress_percent = min(100, int((elapsed / duration) * 100))
                filled = min(83, int(progress_percent / 1.2048))
                unfilled = 83 - filled
                progress_str = [('normal', f"{progress_percent:3d}"), ('time_separator', '%'), (None, f" | {'░' * filled}{' ' * unfilled}")] #progress_str = [('path_value', f"{progress_percent:3d}"), ('percent', '%'), (None, f" | {'░' * filled}{' ' * unfilled}")]
                self.progress_bar.set_text(progress_str)
                elapsed_str = self.format_time(elapsed)
                duration_str = self.format_time(duration)
                self.grannik_text.set_text(self.format_active_time(elapsed_str, duration_str))
        else:
            self.progress_bar.set_text([('normal', "  0"), ('time_separator', '%'), (None, " | " + " " * 83)])
            self.grannik_text.set_text([('pink_frame', " 00:00:00 / 00:00:00")])
        if self.main_loop:
            self.main_loop.set_alarm_in(1, self.update_progress_bar)

    def update_clock(self, loop=None, data=None):
        current_time = time.localtime()
        self.clock_text.set_text(print_pseudographic_time(current_time.tm_hour, current_time.tm_min, current_time.tm_sec))
        if self.main_loop:
            self.main_loop.set_alarm_in(1, self.update_clock)
    def initialize_widget(self):

        self.widget = self.wrap_in_three_frames()

    def wrap_in_three_frames(self):
        term_size = os.get_terminal_size()
        term_width = term_size.columns
        term_height = term_size.lines
        total_border_chars = 6

        available_width = term_width - total_border_chars
        num_upper_boxes = 3
        base_status_width = (available_width // 3 + available_width // 4) // 2
        status_width = max(15, base_status_width + 3)
        remaining_width = available_width - status_width - 7
        files_width = remaining_width // 2
        metadata_width = available_width - files_width - status_width + 2

        total_width_so_far = files_width + status_width + metadata_width + 8
        if total_width_so_far < available_width:
            metadata_width += available_width - total_width_so_far

        total_width = term_width - 1
        left_width = int(total_width * 0.62)

        combined_widget = urwid.Columns([
            (left_width, self.file_frame),
            ('weight', 1, self.metadata_frame),
        ], dividechars=1, box_columns=[0, 1])
        height_limited_widget = urwid.Filler(combined_widget, height=3, valign='top')

        term_size = os.get_terminal_size()
        term_width = term_size.columns
        total_border_chars = 6
        available_width = term_width - total_border_chars
        num_upper_boxes = 3
        base_status_width = (available_width // 3 + available_width // 4) // 2
        status_width = max(15, base_status_width + 3)
        remaining_width = available_width - status_width - 7
        files_width = remaining_width // 2
        metadata_width = available_width - files_width - status_width + 2
        total_width_so_far = files_width + status_width + metadata_width + 8
        if total_width_so_far < available_width:
            metadata_width += available_width - total_width_so_far
        title = "AMIXER MASTER VOLUME LEVEL"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = metadata_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        if len(top_line) > metadata_width:
            top_line = top_line[:metadata_width - 1] + '┐'
        elif len(top_line) < metadata_width:
            top_line = top_line[:-1] + '─' * (metadata_width - len(top_line)) + '┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')
        side_borders = urwid.LineBox(self.system_volume_bar, lline='│', rline='│', tline='', bline='─', tlcorner='', trcorner='', blcorner='└', brcorner='┘')
        new_right_frame = urwid.Pile([(1, top_text), ('weight', 1, side_borders)])
        box02_clone = urwid.AttrMap(new_right_frame, 'pink_frame')

        term_size = os.get_terminal_size()
        term_width = term_size.columns
        total_border_chars = 6
        available_width = term_width - total_border_chars
        num_upper_boxes = 3
        base_status_width = (available_width // 3 + available_width // 4) // 2
        status_width = max(15, base_status_width + 3)
        remaining_width = available_width - status_width - 7
        files_width = remaining_width // 2
        metadata_width = available_width - files_width - status_width + 2
        total_width_so_far = files_width + status_width + metadata_width + 8
        if total_width_so_far < available_width:
            metadata_width += available_width - total_width_so_far

        title = "AMIXER HEADPHONE LEFT VOLUME LEVEL"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = metadata_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        if len(top_line) > metadata_width:
            top_line = top_line[:metadata_width - 1] + '┐'
        elif len(top_line) < metadata_width:
            top_line = top_line[:-1] + '─' * (metadata_width - len(top_line)) + '┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')
        side_borders = urwid.LineBox(self.headphone_left_bar, lline='│', rline='│', tline='', bline='─', tlcorner='', trcorner='', blcorner='└', brcorner='┘')
        new_right_frame = urwid.Pile([(1, top_text), ('weight', 1, side_borders)])
        box02_clone2 = urwid.AttrMap(new_right_frame, 'pink_frame')

        term_size = os.get_terminal_size()
        term_width = term_size.columns
        total_border_chars = 6
        available_width = term_width - total_border_chars
        num_upper_boxes = 3
        base_status_width = (available_width // 3 + available_width // 4) // 2
        status_width = max(15, base_status_width + 3)
        remaining_width = available_width - status_width - 7
        files_width = remaining_width // 2
        metadata_width = available_width - files_width - status_width + 2
        total_width_so_far = files_width + status_width + metadata_width + 8
        if total_width_so_far < available_width:
            metadata_width += available_width - total_width_so_far

        title = "AMIXER HEADPHONE RIGHT VOLUME LEVEL"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = metadata_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        if len(top_line) > metadata_width:
            top_line = top_line[:metadata_width - 1] + '┐'
        elif len(top_line) < metadata_width:
            top_line = top_line[:-1] + '─' * (metadata_width - len(top_line)) + '┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')
        side_borders = urwid.LineBox(self.headphone_right_bar, lline='│', rline='│', tline='', bline='─', tlcorner='', trcorner='', blcorner='└', brcorner='┘')
        new_right_frame = urwid.Pile([(1, top_text), ('weight', 1, side_borders)])
        box02_clone3 = urwid.AttrMap(new_right_frame, 'pink_frame')

        header_height = 3
        frame_border_height = 2
        available_height = term_height - header_height - frame_border_height

        upper_boxes_height = 3
        min_footer_height = 8

        columns_height = max(21, available_height - upper_boxes_height - min_footer_height - 1) # 21 -1

        title = "FILES AND DIRECTORIES OF THE LINUX OS"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = left_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        if len(top_line) > left_width:
            top_line = top_line[:left_width - 1] + '┐'
        elif len(top_line) < left_width:
            top_line = top_line[:-1] + '─' * (left_width - len(top_line)) + '┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')
        side_borders = urwid.LineBox(self, lline='│', rline='│', tline='', bline='─', tlcorner='', trcorner='', blcorner='└', brcorner='┘')
        new_left_frame = urwid.Pile([(1, top_text), ('weight', 1, side_borders)])
        new_left_frame = urwid.AttrMap(new_left_frame, 'pink_frame')
        new_left_frame_filler = urwid.Filler(new_left_frame, height=columns_height, valign='top')
        self.metadata_output = urwid.Text("", align='left')
        self.metadata_filler = urwid.Filler(self.metadata_output, valign='top')

        self.metadata_output = urwid.Text("", align='left')
        self.metadata_filler = urwid.Filler(self.metadata_output, valign='top')
        title = "INFO"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = metadata_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}┤ {title} ├{"─" * (adjusted_width - title_len - side_len)}┐'
        if len(top_line) > metadata_width:
            top_line = top_line[:metadata_width - 1] + '┐'
        elif len(top_line) < metadata_width:
            top_line = top_line[:-1] + '─' * (metadata_width - len(top_line)) + '┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')
        side_borders = urwid.LineBox(self.metadata_filler, lline='│', rline='│', tline='', bline='─', tlcorner='', trcorner='', blcorner='└', brcorner='┘')
        new_right_frame = urwid.Pile([(1, top_text), ('weight', 1, side_borders)])
        new_right_frame = urwid.AttrMap(new_right_frame, 'pink_frame')
        new_right_frame_filler = urwid.Filler(new_right_frame, height=columns_height, valign='top')
        new_frames_widget = urwid.Columns([
            (left_width, new_left_frame_filler),
            ('weight', 1, new_right_frame_filler)
        ], dividechars=1)

        new_frames_widget = urwid.Columns([
            (left_width, new_left_frame_filler),
            ('weight', 1, new_right_frame_filler)
        ], dividechars=1)

        footer_width = left_width
        footer_height = available_height - columns_height - upper_boxes_height
        box_height = max(min_footer_height + 1, footer_height)

        divider_width = 2
        available_footer_width = footer_width - divider_width
        box1_width = 23
        box2_width = 33
        box4_width = available_footer_width - box1_width - box2_width - divider_width + 2

        self.grannik_text = urwid.Text(" 00:00:00 / 00:00:00", align='left')
        title = "PLAYBACK TIME"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = box1_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')

        side_borders = urwid.LineBox(self.grannik_text, lline='│', rline='│',
                                     tline='', bline='',
                                     tlcorner='', trcorner='',
                                     blcorner='', brcorner='')

        footer_line = f'└{"─" * (len(top_line) - 2)}┘'
        footer_text = urwid.Filler(urwid.Text(('pink_frame', footer_line), align='left'), valign='top')

        framed_widget = urwid.Pile([(1, top_text), ('weight', 1, side_borders), (1, footer_text)])
        box1 = urwid.AttrMap(framed_widget, 'pink_frame')
        box1_filler = urwid.Filler(box1, height=box_height, valign='middle')

        title = "CURRENT DATE"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = box2_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')

        side_borders = urwid.LineBox(urwid.Text([
            ('normal', get_date_string().split('|')[0].split('/')[0]),
            ('path_value', '/'),
            ('normal', get_date_string().split('|')[0].split('/')[1]),
            ('path_value', '|'),
            ('normal', get_date_string().split('|')[1].split('/')[0]),
            ('path_value', '/'),
            ('normal', get_date_string().split('|')[1].split('/')[1]),
        ], align='center'), lline='│', rline='│', tline='', bline='', tlcorner='', trcorner='', blcorner='', brcorner='')

        footer_line = f'└{"─" * (len(top_line) - 2)}┘'
        footer_text = urwid.Filler(urwid.Text(('pink_frame', footer_line), align='left'), valign='top')

        framed_widget = urwid.Pile([(1, top_text), ('weight', 1, side_borders), (1, footer_text)])
        box2 = urwid.AttrMap(framed_widget, 'pink_frame')
        box2_filler = urwid.Filler(box2, height=3, valign='middle')

        current_time = time.localtime()
        test_text = urwid.Text(print_pseudographic_time(current_time.tm_hour, current_time.tm_min, current_time.tm_sec), align='center')
        self.clock_text = test_text
        title = "CURRENT TIME"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = box2_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')

        side_borders = urwid.LineBox(test_text, lline='│', rline='│',
                                     tline='', bline='',
                                     tlcorner='', trcorner='',
                                     blcorner='', brcorner='')

        footer_line = f'└{"─" * (len(top_line) - 2)}┘'
        footer_text = urwid.Filler(urwid.Text(('pink_frame', footer_line), align='left'), valign='top')

        framed_widget = urwid.Pile([(1, top_text), ('weight', 1, side_borders), (1, footer_text)])
        test_box_attr = urwid.AttrMap(framed_widget, 'pink_frame')
        test_box_filler = urwid.Filler(test_box_attr, height=6, valign='top')

        box2_with_test = urwid.Pile([
            (3, box2_filler),
            (6, test_box_filler)
        ])

        title = "STATUS"
        title_with_symbols = f"┤ {title} ├"
        title_len = len(title_with_symbols)
        adjusted_width = box4_width - 2
        side_len = max(0, (adjusted_width - title_len) // 2)
        top_line = f'┌{"─" * side_len}{title_with_symbols}{"─" * (adjusted_width - title_len - side_len)}┐'
        top_text = urwid.Filler(urwid.Text(('pink_frame', top_line), align='left'), valign='top')

        side_borders = urwid.LineBox(self.status_filler, lline='│', rline='│',
                                     tline='', bline='',
                                     tlcorner='', trcorner='',
                                     blcorner='', brcorner='')

        footer_line = f'└{"─" * (len(top_line) - 2)}┘'
        footer_text = urwid.Filler(urwid.Text(('pink_frame', footer_line), align='left'), valign='top')

        framed_widget = urwid.Pile([(1, top_text), ('weight', 1, side_borders), (1, footer_text)])
        box4 = urwid.AttrMap(framed_widget, 'pink_frame')
        box4_filler = urwid.Filler(box4, height=box_height, valign='middle')

        footer_columns = urwid.Columns([
            (box1_width, box1_filler),
            (box2_width, box2_with_test),
            (box4_width, box4_filler),
        ], dividechars=1, box_columns=[0, 1, 2])

        clone_width = metadata_width
        clones_pile = urwid.Pile([
            (3, box02_clone),
            (3, box02_clone2),
            (3, box02_clone3),
        ])
        clones_filler = urwid.Filler(clones_pile, height=9, valign='middle')
        footer_with_clones = urwid.Columns([
            (footer_width, footer_columns),
            (clone_width, clones_filler),
        ], dividechars=1, box_columns=[0, 1])
        footer_widget = urwid.Filler(footer_with_clones, height=box_height, valign='middle')
        body_widget = urwid.Pile([
            (columns_height, new_frames_widget),
            (upper_boxes_height, height_limited_widget),
            (box_height, footer_widget),
        ])
        frame_with_path = urwid.Frame(
            body=body_widget,
            header=self.path_widget,
        )
        return frame_with_path

    def load_and_play_audio(self, audio_file):
        full_path = os.path.abspath(audio_file)
        self.current_dir = os.path.dirname(full_path)
        file_name = os.path.basename(full_path)
        self.file_list.clear()
        padded_text = urwid.Padding(urwid.Text(file_name), left=1, right=1)
        self.file_list.append(urwid.AttrMap(padded_text, 'normal', 'selected'))
        self.set_focus(0)
        self.path_text_inner.set_text([('path_value', self.current_dir)])
        self.play_media(full_path)

    def load_and_play_directory(self, directory):
        full_path = os.path.abspath(directory)
        self.current_dir = full_path
        self.path_text_inner.set_text([('path_value', self.current_dir)])
        AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma', 'opus'}
        try:
            all_files = sorted(os.listdir(self.current_dir))
            audio_files = [f for f in all_files 
                          if not f.startswith('.') and 
                          f.lower().split('.')[-1] in AUDIO_EXTENSIONS]
            if not audio_files:
                self.file_list.clear()
                self.file_list.append(urwid.AttrMap(urwid.Padding(urwid.Text("(empty)"), left=1, right=1), 'normal', 'selected'))
                return

            self.file_list.clear()
            self.playlist = [os.path.join(self.current_dir, f) for f in audio_files]
            self.playlist_index = 0

            for file in audio_files:
                padded_text = urwid.Padding(urwid.Text(file), left=1, right=1)
                self.file_list.append(urwid.AttrMap(padded_text, 'audio_file', 'selected'))

            self.set_focus(0)
            self.play_media(self.playlist[self.playlist_index])
        except PermissionError:
            self.file_list.clear()
            self.file_list.append(urwid.AttrMap(urwid.Padding(urwid.Text("(access denied)"), left=1, right=1), 'perm_denied', 'selected'))

    def check_playback_end(self):
        if self.main_loop is not None and self.playing and not pygame.mixer.music.get_busy() and not self.paused:
            self.next_track()
        if self.main_loop is not None:
            self.main_loop.set_alarm_in(0.1, lambda loop, data: self.check_playback_end())

    def next_track(self):
        if self.playlist and self.playlist_index < len(self.playlist) - 1:
            self.playlist_index += 1
            self.set_focus(self.playlist_index)
            self.play_media(self.playlist[self.playlist_index])
        else:
            pygame.mixer.music.stop()
            self.playing = False
            self.status_output.set_text([('time_separator,bold', " Playlist ended")])
            self.metadata_output.set_text([('path_value', ' No metadata available')])

    def update_file_list(self):
        AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a', 'wma', 'opus'}
        try:
            all_files = sorted(os.listdir(self.current_dir))
            files = [f for f in all_files
                     if not f.startswith('.') and
                     (os.path.isdir(os.path.join(self.current_dir, f)) or
                      f.lower().split('.')[-1] in AUDIO_EXTENSIONS)]
            if not files:
                files = ["(empty)"]
        except PermissionError:
            files = ["(access denied)"]

        file_items = []
        for file in files:
            full_path = os.path.join(self.current_dir, file)
            if os.path.isdir(full_path):
                attr = 'directory'
                display_name = file + "/"
            elif os.path.isfile(full_path):
                attr = 'audio_file'
                display_name = file
            else:
                attr = 'normal'
                display_name = file
            padded_text = urwid.Padding(urwid.Text(display_name), left=1, right=1)
            file_items.append(urwid.AttrMap(padded_text, attr, 'selected'))

        return file_items

    def refresh_list(self):
        old_focus = self.focus_position if self.file_list else 0
        self.file_list[:] = self.update_file_list()
        self.path_text_inner.set_text([('path_value', self.current_dir)])
        if self.file_list:
            self.set_focus(min(old_focus, len(self.file_list) - 1))

    def get_widget(self):
        return self.widget

    def cleanup(self):
        if self.playing:
            pygame.mixer.music.stop()
        self.status_output.set_text([('path_value', ' No status available')])
        self.metadata_output.set_text([('path_value', ' No metadata available')])
        self.playing = False
        self.paused = False

    def show_message(self, message, duration=1):
        if "Permission denied" in message:
            self.status_output.set_text([('perm_denied', f" {message}")])
            duration = 0
        elif "not found" in message or "Error" in message:
            self.status_output.set_text([('error', f" {message}")])
            duration = 2
        else:
            self.status_output.set_text([('normal', f" {message}")])
        self.main_loop.draw_screen()
        if duration > 0:
            def clear_message(loop, data):
                if self.status_output.text in ([('perm_denied', f" {message}"), ('error', f" {message}"), ('normal', f" {message}")]):
                    self.status_output.set_text("")
                self.main_loop.draw_screen()
            self.main_loop.set_alarm_in(duration, clear_message)

    def clear_message(self):
        self.status_output.set_text("")
        self.main_loop.draw_screen()

    def get_metadata(self, filepath):
        try:
            audio = mutagen.File(filepath)
            if audio is None:
                return " No metadata available"
            metadata = []
            if hasattr(audio, 'info'):
                metadata.append([('path_value', ' Duration: '), ('normal', f'{audio.info.length:.2f} sec')])
                metadata.append([('path_value', ' Bitrate: '), ('normal', f'{audio.info.bitrate // 1000} kbps')])
                metadata.append([('path_value', ' Channels: '), ('normal', f'{audio.info.channels}')])
                metadata.append([('path_value', ' Sample Rate: '), ('normal', f'{audio.info.sample_rate} Hz')])
            if audio.tags:
                for key, value in audio.tags.items():
                    value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                    metadata.append([('path_value', f' {key}: '), ('normal', value_str)])

                max_lines = 10
                if len(metadata) > max_lines:
                    metadata = metadata[:max_lines - 1] + [[('path_value', ' ... (truncated)')]]
                result = []
                for i, line in enumerate(metadata):
                    result.extend(line)
                    if i < len(metadata) - 1:
                        result.append(('normal', '\n'))
                return result if result else [('path_value', ' No metadata available')]

        except Exception as e:
            return [('path_value', ' Error reading metadata: '), ('normal', str(e))]

    def play_media(self, filepath):
        if not os.path.exists(filepath):
            self.show_message(f"File not found: {filepath}")
            return
        if not os.access(filepath, os.R_OK):
            self.show_message("Permission denied!")
            return
        if self.playing:
            pygame.mixer.music.stop()
        try:
            pygame.mixer.music.load(filepath)
            pygame.mixer.music.set_volume(self.volume)
            pygame.mixer.music.play()
            self.playing = True
            self.paused = False
            self.status_output.set_text([('time_separator,bold', " Playing:\n "), ('normal', f"{os.path.basename(filepath)}")]) 
            self.metadata_output.set_text(self.get_metadata(filepath))
            filled = min(50, int(self.volume * 50))
            self.volume_bar.set_text([('normal', f" {int(self.volume * 100)}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.volume_bar.set_text(f" {int(self.volume * 100)}% | {'░' * filled + ' ' * (50 - filled)}")
            audio = mutagen.File(filepath)
            if audio and hasattr(audio, 'info'):
                self.current_audio_duration = audio.info.length
            else:
                sound = pygame.mixer.Sound(filepath)
                self.current_audio_duration = sound.get_length()
        except Exception as e:
            self.show_message(f"Error playing media: {str(e)}")

    def keypress(self, size, key):
        current_message = self.status_output.text
        is_perm_denied = isinstance(current_message, list) and len(current_message) > 0 and "Permission denied" in current_message[0][1]

    def keypress(self, size, key):
        current_message = self.status_output.text
        is_perm_denied = isinstance(current_message, list) and len(current_message) > 0 and "Permission denied" in current_message[0][1]

        help_text = [
            ('normal,bold', ' left'), ('path_value', ' - Go to parent directory.\n'),
            ('normal,bold', ' right'), ('path_value', ' - Go back in directory history.\n'),
            ('normal,bold', ' up'), ('path_value', ' - Move focus up in file list.\n'),
            ('normal,bold', ' down'), ('path_value', ' - Move focus down in file list.\n'),
            ('normal,bold', ' enter'), ('path_value', ' - Open folder or play file.\n'),
            ('normal,bold', ' space'), ('path_value', ' - Play directory as playlist.\n'),
            ('normal,bold', ' + -'), ('path_value', ' - Increase/Decrease volume (pygame).\n'),
            ('normal,bold', ' a'), ('path_value', ' - Increase right headphone volume\n'),
            ('normal,bold', ' b'), ('path_value', ' - Decrease right headphone volume\n'),
            ('normal,bold', ' c'), ('path_value', ' - Increase left headphone volume\n'),
            ('normal,bold', ' d'), ('path_value', ' - Decrease system volume.\n'),
            ('normal,bold', ' e'), ('path_value', ' - Increase both headphones volume\n'),
            ('normal,bold', ' f'), ('path_value', ' - Decrease both headphones volume\n'),
            ('normal,bold', ' g'), ('path_value', ' - Decrease left headphone volume\n'),
            ('normal,bold', ' p'), ('path_value', ' - Pause or resume playback.\n'),
            ('normal,bold', ' s'), ('path_value', ' - Stop playback.\n'),
            ('normal,bold', ' r'), ('path_value', ' - Restart current track.\n'),
            ('normal,bold', ' i'), ('path_value', ' - Increase system volume.\n'),
            ('normal,bold', ' n'), ('path_value', ' - Next track.\n'),
            ('normal,bold', ' q or Q'), ('path_value', ' - Quit program.\n'),
            ('normal,bold', ' h'), ('path_value', ' - Show help.')
        ]

        if key == 'h' and not self.playing and not self.paused:
            self.metadata_output.set_text(help_text)
            self.main_loop.draw_screen()
        elif key != 'h':
            if self.metadata_output.text == help_text:
                self.metadata_output.set_text([('path_value', ' No metadata available')])
                self.main_loop.draw_screen()
        if key == 'h' and not self.playing and not self.paused:
            self.metadata_output.set_text(help_text)
            self.main_loop.draw_screen()
        elif key != 'h':
            if self.metadata_output.text == help_text:
                self.metadata_output.set_text([('path_value', ' No metadata available')])
                self.main_loop.draw_screen()
 
        if key == 'left':
            if self.current_dir != "/":
                try:
                    self.dir_history.append(self.current_dir)
                    os.chdir("..")
                    self.current_dir = os.getcwd()
                    self.refresh_list()
                    self.clear_message()
                    self.main_loop.draw_screen()
                except PermissionError:
                    self.show_message("Permission denied!")
        elif key == 'right':
            if self.dir_history:
                try:
                    os.chdir(self.dir_history.pop())
                    self.current_dir = os.getcwd()
                    self.refresh_list()
                    self.clear_message()
                    self.main_loop.draw_screen()
                except PermissionError:
                    self.show_message("Permission denied!")
        elif key == 'up' and self.focus_position > 0:
            self.set_focus(self.focus_position - 1)
            if not is_perm_denied:
                self.clear_message()
        elif key == 'down' and self.focus_position < len(self.file_list) - 1:
            self.set_focus(self.focus_position + 1)
            if not is_perm_denied:
                self.clear_message()
        elif key == 'enter':
            if not self.file_list or self.focus.original_widget.original_widget.text.strip() in ["(empty)", "(access denied)"]:
                return
            selected = self.focus.original_widget.original_widget.text.rstrip('/')
            full_path = os.path.join(self.current_dir, selected)
            try:
                if os.path.isdir(full_path):
                    self.dir_history.append(self.current_dir)
                    os.chdir(full_path)
                    self.current_dir = os.getcwd()
                    self.refresh_list()
                    self.clear_message()
                    self.main_loop.draw_screen()
                elif os.path.isfile(full_path):
                    self.play_media(full_path)
                    self.playlist = [full_path]
                    self.playlist_index = 0
            except Exception as e:
                self.show_message(f"Error: {str(e)}")
        elif key == ' ':
            if self.playing or self.paused:
                pygame.mixer.music.stop()
                self.playing = False
                self.paused = False
            self.file_list.clear()
            self.load_and_play_directory(self.current_dir)
            self.check_playback_end()
            self.main_loop.draw_screen()
        elif key == 'p':
            if self.playing:
                if self.paused:
                    pygame.mixer.music.unpause()
                    self.paused = False
                    filepath = os.path.join(self.current_dir, self.focus.original_widget.original_widget.text.rstrip('/'))
                    self.status_output.set_text([('time_separator,bold', " Resumed: "), ('normal', f"{os.path.basename(filepath)}")])
                else:
                    pygame.mixer.music.pause()
                    self.paused = True
                    self.status_output.set_text([('time_separator,bold', " Paused")])
        elif key == 's':
            if self.playing:
                pygame.mixer.music.stop()
                self.playing = False
                self.paused = False
                self.status_output.set_text([('time_separator,bold', " Stopped")])
                self.metadata_output.set_text([('path_value', ' No metadata available')])
        elif key == 'r':
            if self.playing or self.paused:
                filepath = os.path.join(self.current_dir, self.focus.original_widget.original_widget.text.rstrip('/'))
                pygame.mixer.music.stop()
                pygame.mixer.music.load(filepath)
                pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play()
                self.playing = True
                self.paused = False
                self.status_output.set_text([('time_separator,bold', " Replaying: "), ('normal', f"{os.path.basename(filepath)}")])
                self.metadata_output.set_text(self.get_metadata(filepath))
        elif key == '+':
            self.volume = min(1.0, self.volume + 0.02)
            if self.playing:
                pygame.mixer.music.set_volume(self.volume)
            filled = int(self.volume * 50)
            self.volume_bar.set_text([('normal', f" {int(self.volume * 100)}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.volume_bar.set_text(f" {int(self.volume * 100)}% | {'░' * filled + ' ' * (50 - filled)}")
            self.main_loop.draw_screen()
        elif key == '-':
            self.volume = max(0.0, self.volume - 0.02)
            if self.playing:
                pygame.mixer.music.set_volume(self.volume)
            filled = int(self.volume * 44)
            self.volume_bar.set_text([('normal', f" {int(self.volume * 100)}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (44 - filled)}")]) #self.volume_bar.set_text(f" {int(self.volume * 100)}% | {'░' * filled + ' ' * (44 - filled)}")
            self.main_loop.draw_screen()
        elif key == 'i':
            try:
                result = subprocess.check_output("amixer set Master 2%+ | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(50, int(percent / 2))
                self.system_volume_bar.set_text([('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.system_volume_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (50 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting system volume: {e}")
        elif key == 'd':
            try:
                result = subprocess.check_output("amixer set Master 2%- | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(50, int(percent / 2))
                self.system_volume_bar.set_text([('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.system_volume_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (50 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting system volume: {e}")
        elif key == 'a':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontright 2%+ -q && amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(50, int(percent / 2))
                self.headphone_right_bar.set_text([('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.headphone_right_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (50 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                pass
        elif key == 'b':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontright 2%- -q && amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(50, int(percent / 2))
                self.headphone_right_bar.set_text([('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.headphone_right_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (50 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'c':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontleft 2%+ -q && amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(50, int(percent / 2))
                self.headphone_left_bar.set_text([('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.headphone_left_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (50 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'g':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontleft 2%- -q && amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(50, int(percent / 2))
                self.headphone_left_bar.set_text([('normal', f" {percent}"), ('time_separator', '%'), (None, f" | {'░' * filled + ' ' * (50 - filled)}")]) #self.headphone_left_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (50 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'e':
            try:
                subprocess.check_output("amixer sset 'Headphone' 2%+ -q", shell=True, text=True)
                left_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                left_percent = int(left_result.rstrip('%'))
                left_filled = min(50, left_percent // 2)
                self.headphone_left_bar.set_text([('normal', f" {left_percent}"), ('time_separator', '%'), (None, f" | {'░' * left_filled + ' ' * (50 - left_filled)}")]) #self.headphone_left_bar.set_text(f" {left_percent}% | {'░' * left_filled + ' ' * (50 - left_filled)}")
                right_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                right_percent = int(right_result.rstrip('%'))
                right_filled = min(50, right_percent // 2)
                self.headphone_right_bar.set_text([('normal', f" {right_percent}"), ('time_separator', '%'), (None, f" | {'░' * right_filled + ' ' * (50 - right_filled)}")]) #self.headphone_right_bar.set_text(f" {right_percent}% | {'░' * right_filled + ' ' * (50 - right_filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'f':
            try:
                subprocess.check_output("amixer sset 'Headphone' 2%- -q", shell=True, text=True)
                left_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                left_percent = int(left_result.rstrip('%'))
                left_filled = min(50, left_percent // 2)
                self.headphone_left_bar.set_text([('normal', f" {left_percent}"), ('time_separator', '%'), (None, f" | {'░' * left_filled + ' ' * (50 - left_filled)}")]) #self.headphone_left_bar.set_text(f" {left_percent}% | {'░' * left_filled + ' ' * (50 - left_filled)}")
                right_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                right_percent = int(right_result.rstrip('%'))
                right_filled = min(50, right_percent // 2)
                self.headphone_right_bar.set_text([('normal', f" {right_percent}"), ('time_separator', '%'), (None, f" | {'░' * right_filled + ' ' * (50 - right_filled)}")]) #self.headphone_right_bar.set_text(f" {right_percent}% | {'░' * right_filled + ' ' * (50 - right_filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'n':
            self.next_track()
        elif key in ('q', 'Q'):
            self.cleanup()
            return 'q'
        else:
            super().keypress(size, key)
        return key

    def handle_input(self, key):
        if isinstance(key, str):
            return key
        return None

class FileManager:
    def __init__(self, input_path=None):
        self.main_loop = None
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.mode = PlaybackMode(None, self.root_dir, input_path)
        initial_widget = self.wrap_mode_widget(self.mode.get_widget())
        self.frame = urwid.Frame(body=initial_widget)
    def wrap_mode_widget(self, widget):
        title = "╡ AUDIO PLAYER TERM PY ╞"
        term_width = os.get_terminal_size().columns
        title_len = len(title)
        side_len = max(1, (term_width - title_len - 2) // 2)
        top_line = f'╔{"═" * side_len}{title}{"═" * (side_len + term_width % 2)}╗'
        top_text = urwid.Text(('header', top_line), align='center')
        side_borders = urwid.LineBox(widget, lline='║', rline='║', tline='', bline='', tlcorner='', trcorner='', blcorner='', brcorner='')
        side_borders = urwid.AttrMap(side_borders, 'header')
        framed_widget = urwid.Frame(
            body=side_borders,
            header=top_text,
            focus_part='body',
            footer=urwid.Text(('header', '╚' + '═' * (len(top_line) - 2) + '╝'))
        )
        return urwid.AttrMap(framed_widget, 'header')

    def unhandled_input(self, key):
        mode_key = self.mode.handle_input(key)
        if mode_key == 'q':
            self.mode.cleanup()
            raise urwid.ExitMainLoop()

    def run(self):
        os.system('clear')
        self.main_loop = urwid.MainLoop(self.frame, palette=palette, unhandled_input=self.unhandled_input)
        self.mode.main_loop = self.main_loop
        self.mode.start()
        self.mode.check_playback_end()
        self.mode.update_clock()
        self.main_loop.set_alarm_in(0.1, self.mode.update_progress_bar)
        try:
            self.main_loop.run()
        finally:
            os.system('stty sane')
            os.system('clear')

if __name__ == "__main__":
    input_path = None
    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    fm = FileManager(input_path)
    fm.run()
