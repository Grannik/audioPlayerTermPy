#!/usr/bin/env python3
import urwid
import os
import pygame.mixer
import mutagen
import sys
from datetime import datetime, timedelta
import subprocess

# Палитра (без изменений)
palette = [
    ('header', 'light blue', 'default'),
    ('path_label', 'light blue', 'default'),
    ('path_value', 'dark gray', 'default'),
    ('directory', 'dark blue,bold', 'default'),
    ('audio_file', 'light cyan', 'default'),
    ('normal', 'white', 'default'),
    ('selected', 'black', 'light green'),
    ('perm_denied', 'light red', 'default'),
    ('error', 'light red', 'default'),
    ('playing', 'light green', 'default'),
    ('pink_frame', 'light magenta', 'default'),
    ('percent', 'white,bold', 'default'),
]

class PlaybackMode(urwid.ListBox):
    def __init__(self, main_loop, root_dir, input_path=None):
        pygame.mixer.init()
        self.main_loop = main_loop
        self.root_dir = root_dir
        self.current_dir = os.getcwd()
        self.dir_history = []
        self.file_list = urwid.SimpleFocusListWalker([])
        self.playlist = []  # Список для плейлиста
        self.playlist_index = 0  # Текущий индекс в плейлисте
        
        # Левая рамка: Box00 (без изменений)
        self.progress_bar = urwid.Text([('path_value', "  0"), ('percent', '%'), (None, " | " + " " * 83)], align='left')
        self.file_frame = urwid.LineBox(self.progress_bar, title="Playback progress", title_align='center',
                                        tlcorner='┌', tline='─', trcorner='┐',
                                        lline='│', rline='│',
                                        blcorner='└', bline='─', brcorner='┘')
        self.file_frame = urwid.AttrMap(self.file_frame, 'pink_frame')
        
        # Правая рамка: Volume Level (без изменений)
#        self.volume_bar = urwid.Text(f" 50% {'░' * 17 + ' ' * 17}")
        self.volume_bar = urwid.Text(f" 50% | {'░' * 22 + ' ' * 22}")
        self.metadata_frame = urwid.LineBox(self.volume_bar, title='Pygame.mixer volume Level', title_align='center',
                                            tlcorner='┌', tline='─', trcorner='┐',
                                            lline='│', rline='│',
                                            blcorner='└', bline='─', brcorner='┘')
        self.metadata_frame = urwid.AttrMap(self.metadata_frame, 'pink_frame')
        
        # Рамка пути (без изменений)
        self.path_text_inner = urwid.Text([('path_value', self.current_dir)], align='left')
        self.path_text = urwid.Padding(self.path_text_inner, left=1)
        self.path_filler = urwid.Filler(self.path_text, valign='top')
        self.path_frame = urwid.LineBox(self.path_filler, title="Path", title_align='center',
                                        tlcorner='┌', tline='─', trcorner='┐',
                                        lline='│', rline='│',
                                        blcorner='└', bline='─', brcorner='┘')
        self.path_widget = urwid.AttrMap(self.path_frame, 'pink_frame')
        
        # Status (без изменений)
        self.status_output = urwid.Text("", align='left')
        self.status_filler = urwid.Filler(self.status_output, valign='top')
        
        self.playing = False
        self.paused = False
        self.volume = 0.5
        self.current_audio_duration = 0
        
        # Инициализация системной громкости (без изменений)
        try:
            result = subprocess.check_output("amixer get Master | grep -o '[0-9]*%' | uniq", shell=True, text=True).strip()
            percent = int(result.rstrip('%'))
            filled = min(34, percent // 3)
            initial_volume_text = f" {percent}% {'░' * filled + ' ' * (34 - filled)}"
        except subprocess.CalledProcessError:
            initial_volume_text = " --% " + " " * 34
        self.system_volume_bar = urwid.Text(initial_volume_text)
        
        # Инициализация прогресс-бара для левого наушника (без изменений)
        try:
            result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
            percent = int(result.rstrip('%'))
            filled = min(29, percent // 3)
            initial_headphone_left_text = f" {percent}% | {'░' * filled + ' ' * (29 - filled)}"
        except (subprocess.CalledProcessError, ValueError):
            initial_headphone_left_text = " --% | " + " " * 29
        self.headphone_left_bar = urwid.Text(initial_headphone_left_text, align='left')
        
        # Инициализация прогресс-бара для правого наушника (без изменений)
        try:
            result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
            percent = int(result.rstrip('%'))
            filled = min(29, percent // 3)
            initial_headphone_right_text = f" {percent}% | {'░' * filled + ' ' * (29 - filled)}"
        except (subprocess.CalledProcessError, ValueError):
            initial_headphone_right_text = " --% | " + " " * 29
        self.headphone_right_bar = urwid.Text(initial_headphone_right_text, align='left')
        
        # Alisa (часы) (без изменений)
        self.alisa_text = urwid.Text("", align='center')
        
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

    def update_clock(self, loop=None, data=None):
        SEASONS = {
            1: "Winter", 2: "Winter", 3: "Spring",
            4: "Spring", 5: "Spring", 6: "Summer",
            7: "Summer", 8: "Summer", 9: "Autumn",
            10: "Autumn", 11: "Autumn", 12: "Winter"
        }
        MONTHS = {
            1: "January", 2: "February", 3: "March",
            4: "April", 5: "May", 6: "June",
            7: "July", 8: "August", 9: "September",
            10: "October", 11: "November", 12: "December"
        }
        WEEKDAYS = {
            0: "Monday", 1: "Tuesday", 2: "Wednesday",
            3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"
        }
        
        now = datetime.now()
        year = "2025"
        season = SEASONS[now.month]
        month = MONTHS[now.month]
        weekday = WEEKDAYS[now.weekday()]
        time_str = now.strftime('%H:%M:%S')
        
        clock_text = f"{year}\n{season} {month} {weekday}\n{time_str}"
        self.alisa_text.set_text(clock_text)
        
        if self.main_loop:
            self.main_loop.set_alarm_in(1 / 30, self.update_clock)

    def format_time(self, seconds):
        return str(timedelta(seconds=int(seconds))).zfill(8)

    def update_progress_bar(self, loop=None, data=None):
        if self.playing and not self.paused and pygame.mixer.music.get_busy():
            elapsed = pygame.mixer.music.get_pos() / 1000
            duration = self.current_audio_duration
            if duration > 0:
                progress_percent = min(100, int((elapsed / duration) * 100))
                filled = min(83, int(progress_percent / 1.2048))
                unfilled = 83 - filled
                progress_str = [('path_value', f"{progress_percent:3d}"), ('percent', '%'), (None, f" | {'░' * filled}{' ' * unfilled}")]
                self.progress_bar.set_text(progress_str)
                elapsed_str = self.format_time(elapsed)
                duration_str = self.format_time(duration)
                self.grannik_text.set_text(f" {elapsed_str} / {duration_str}")
        else:
            self.progress_bar.set_text([('path_value', "  0"), ('percent', '%'), (None, " | " + " " * 83)])
            self.grannik_text.set_text(" 00:00:00 / 00:00:00")
        if self.main_loop:
            self.main_loop.set_alarm_in(1, self.update_progress_bar)

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
        
        box02_clone = urwid.LineBox(self.system_volume_bar, title='Amixer master volume Level', title_align='center',
                                    tlcorner='┌', tline='─', trcorner='┐',
                                    lline='│', rline='│',
                                    blcorner='└', bline='─', brcorner='┘')
        box02_clone = urwid.AttrMap(box02_clone, 'pink_frame')
        
        box02_clone2 = urwid.LineBox(self.headphone_left_bar, title='Amixer headphone left', title_align='center',
                                     tlcorner='┌', tline='─', trcorner='┐',
                                     lline='│', rline='│',
                                     blcorner='└', bline='─', brcorner='┘')
        box02_clone2 = urwid.AttrMap(box02_clone2, 'pink_frame')
        
        box02_clone3 = urwid.LineBox(self.headphone_right_bar, title='Amixer headphone right', title_align='center',
                                     tlcorner='┌', tline='─', trcorner='┐',
                                     lline='│', rline='│',
                                     blcorner='└', bline='─', brcorner='┘')
        box02_clone3 = urwid.AttrMap(box02_clone3, 'pink_frame')
        
        header_height = 3
        frame_border_height = 2
        available_height = term_height - header_height - frame_border_height
        
        upper_boxes_height = 3
        min_footer_height = 8
        
        columns_height = max(21, available_height - upper_boxes_height - min_footer_height - 1)
        
        new_left_frame = urwid.LineBox(self, title="Files and directories of the Linux OS", title_align='center',
                                       tlcorner='┌', tline='─', trcorner='┐',
                                       lline='│', rline='│',
                                       blcorner='└', bline='─', brcorner='┘')
        new_left_frame = urwid.AttrMap(new_left_frame, 'pink_frame')
        new_left_frame_filler = urwid.Filler(new_left_frame, height=columns_height, valign='top')
        
        self.metadata_output = urwid.Text("", align='left')
        self.metadata_filler = urwid.Filler(self.metadata_output, valign='top')
        new_right_frame = urwid.LineBox(self.metadata_filler, title="Info", title_align='center',
                                        tlcorner='┌', tline='─', trcorner='┐',
                                        lline='│', rline='│',
                                        blcorner='└', bline='─', brcorner='┘')
        new_right_frame = urwid.AttrMap(new_right_frame, 'pink_frame')
        new_right_frame_filler = urwid.Filler(new_right_frame, height=columns_height, valign='top')
        
        new_frames_widget = urwid.Columns([
            (left_width, new_left_frame_filler),
            ('weight', 1, new_right_frame_filler)
        ], dividechars=1)
        
        footer_width = left_width
        footer_height = available_height - columns_height - upper_boxes_height
        box_height = max(min_footer_height + 1, footer_height)
        
        divider_width = 2
        available_footer_width = footer_width - divider_width
        box1_width = available_footer_width // 3
        box2_width = available_footer_width // 3
        box4_width = available_footer_width // 3
        
        self.grannik_text = urwid.Text(" 00:00:00 / 00:00:00", align='left')
        box1 = urwid.LineBox(self.grannik_text, title="Playback time", title_align='center',
                             tlcorner='┌', tline='─', trcorner='┐',
                             lline='│', rline='│',
                             blcorner='└', bline='─', brcorner='┘')
        box1 = urwid.AttrMap(box1, 'pink_frame')
        box1_filler = urwid.Filler(box1, height=box_height, valign='middle')
        
        box2 = urwid.LineBox(self.alisa_text, title="Current time", title_align='center',
                             tlcorner='┌', tline='─', trcorner='┐',
                             lline='│', rline='│',
                             blcorner='└', bline='─', brcorner='┘')
        box2 = urwid.AttrMap(box2, 'pink_frame')
        box2_filler = urwid.Filler(box2, height=box_height, valign='middle')
        
        box4 = urwid.LineBox(self.status_filler, title="Status", title_align='center',
                             tlcorner='┌', tline='─', trcorner='┐',
                             lline='│', rline='│',
                             blcorner='└', bline='─', brcorner='┘')
        box4 = urwid.AttrMap(box4, 'pink_frame')
        box4_filler = urwid.Filler(box4, height=box_height, valign='middle')
        
        footer_columns = urwid.Columns([
            (box1_width, box1_filler),
            (box2_width, box2_filler),
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
            self.status_output.set_text(" Playlist ended")
            self.metadata_output.set_text("")

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
        self.status_output.set_text("")
        self.metadata_output.set_text("")
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
                metadata.append(f" Duration: {audio.info.length:.2f} sec")
                metadata.append(f" Bitrate: {audio.info.bitrate // 1000} kbps")
                metadata.append(f" Channels: {audio.info.channels}")
                metadata.append(f" Sample Rate: {audio.info.sample_rate} Hz")
            if audio.tags:
                for key, value in audio.tags.items():
                    value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                    metadata.append(f" {key}: {value_str}")
            
            max_lines = 10
            if len(metadata) > max_lines:
                metadata = metadata[:max_lines - 1] + [" ... (truncated)"]
            return "\n".join(metadata) if metadata else " No metadata available"
        except Exception as e:
            return f" Error reading metadata: {e}"

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
            self.status_output.set_text([("playing", f" Playing: {os.path.basename(filepath)}")])
            self.metadata_output.set_text(self.get_metadata(filepath))
#            filled = int(self.volume * 40)
#            self.volume_bar.set_text(f" {int(self.volume * 100)}% {'░' * filled + ' ' * (40 - filled)}")
            filled = int(self.volume * 44)
            self.volume_bar.set_text(f" {int(self.volume * 100)}% | {'░' * filled + ' ' * (44 - filled)}")
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
        
        help_text = [
            ('normal,bold', ' left'), ('path_value', ' - Go to parent directory.\n'),
            ('normal,bold', ' right'), ('path_value', ' - Go back in directory history.\n'),
            ('normal,bold', ' up'), ('path_value', ' - Move focus up in file list.\n'),
            ('normal,bold', ' down'), ('path_value', ' - Move focus down in file list.\n'),
            ('normal,bold', ' enter'), ('path_value', ' - Open folder or play file.\n'),
            ('normal,bold', ' space'), ('path_value', ' - Play directory as playlist.\n'),
            ('normal,bold', ' + -'), ('path_value', ' - Increase/Decrease volume (pygame).\n'),
            ('normal,bold', ' a'), ('path_value', ' - Увеличить громкость правого наушника\n'),
            ('normal,bold', ' b'), ('path_value', ' - Уменьшить громкость правого наушника\n'),
            ('normal,bold', ' c'), ('path_value', ' - Увеличить громкость левого наушника\n'),
            ('normal,bold', ' d'), ('path_value', ' - Decrease system volume.\n'),
            ('normal,bold', ' e'), ('path_value', ' - Увеличить громкость обоих наушников\n'),
            ('normal,bold', ' f'), ('path_value', ' - Уменьшить громкость обоих наушников\n'),
            ('normal,bold', ' g'), ('path_value', ' - Уменьшить громкость левого наушника\n'),
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
                self.metadata_output.set_text("")
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
                    self.status_output.set_text([("playing", f" Resumed: {os.path.basename(filepath)}")])
                else:
                    pygame.mixer.music.pause()
                    self.paused = True
                    self.status_output.set_text(" Paused")
        elif key == 's':
            if self.playing:
                pygame.mixer.music.stop()
                self.playing = False
                self.paused = False
                self.status_output.set_text(" Stopped")
                self.metadata_output.set_text("")
        elif key == 'r':
            if self.playing or self.paused:
                filepath = os.path.join(self.current_dir, self.focus.original_widget.original_widget.text.rstrip('/'))
                pygame.mixer.music.stop()
                pygame.mixer.music.load(filepath)
                pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play()
                self.playing = True
                self.paused = False
                self.status_output.set_text([("playing", f" Replaying: {os.path.basename(filepath)}")])
                self.metadata_output.set_text(self.get_metadata(filepath))
        elif key == '+':
            self.volume = min(1.0, self.volume + 0.03)
            if self.playing:
                pygame.mixer.music.set_volume(self.volume)
#            filled = int(self.volume * 34)
            filled = int(self.volume * 44)
#            self.volume_bar.set_text(f" {int(self.volume * 100)}% {'░' * filled + ' ' * (34 - filled)}")
            self.volume_bar.set_text(f" {int(self.volume * 100)}% | {'░' * filled + ' ' * (44 - filled)}")
            self.main_loop.draw_screen()
        elif key == '-':
            self.volume = max(0.0, self.volume - 0.03)
            if self.playing:
                pygame.mixer.music.set_volume(self.volume)
#            filled = int(self.volume * 34)
            filled = int(self.volume * 44)
#            self.volume_bar.set_text(f" {int(self.volume * 100)}% {'░' * filled + ' ' * (34 - filled)}")
            self.volume_bar.set_text(f" {int(self.volume * 100)}% | {'░' * filled + ' ' * (44 - filled)}")
            self.main_loop.draw_screen()
        elif key == 'i':
            try:
                result = subprocess.check_output("amixer set Master 3%+ | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(34, percent // 3)
                self.system_volume_bar.set_text(f" {percent}% {'░' * filled + ' ' * (34 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting system volume: {e}")
        elif key == 'd':
            try:
                result = subprocess.check_output("amixer set Master 3%- | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(34, percent // 3)
                self.system_volume_bar.set_text(f" {percent}% {'░' * filled + ' ' * (34 - filled)}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting system volume: {e}")
        elif key == 'a':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontright 5%+ -q && amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(29, percent // 3)
                self.headphone_right_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (29 - filled)}")
#                self.status_output.set_text(f"Headphone Front Right: {result}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                pass  # Пустой оператор, чтобы блок не был пустым
#                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'b':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontright 5%- -q && amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(29, percent // 3)
                self.headphone_right_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (29 - filled)}")
#                self.status_output.set_text(f"Headphone Front Right: {result}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'c':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontleft 5%+ -q && amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(29, percent // 3)
                self.headphone_left_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (29 - filled)}")
                self.status_output.set_text(f"Headphone Front Left: {result}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'g':
            try:
                result = subprocess.check_output("amixer sset 'Headphone' frontleft 5%- -q && amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                percent = int(result.rstrip('%'))
                filled = min(29, percent // 3)
                self.headphone_left_bar.set_text(f" {percent}% | {'░' * filled + ' ' * (29 - filled)}")
                self.status_output.set_text(f"Headphone Front Left: {result}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'e':
            try:
                # Увеличиваем громкость обоих наушников
                subprocess.check_output("amixer sset 'Headphone' 5%+ -q", shell=True, text=True)
                # Получаем значение для левого наушника
                left_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                left_percent = int(left_result.rstrip('%'))
                left_filled = min(29, left_percent // 3)
                self.headphone_left_bar.set_text(f" {left_percent}% | {'░' * left_filled + ' ' * (29 - left_filled)}")
                # Получаем значение для правого наушника
                right_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                right_percent = int(right_result.rstrip('%'))
                right_filled = min(29, right_percent // 3)
                self.headphone_right_bar.set_text(f" {right_percent}% | {'░' * right_filled + ' ' * (29 - right_filled)}")
                self.status_output.set_text(f"Headphone Left Right: {left_result} {right_result}")
                self.main_loop.draw_screen()
            except subprocess.CalledProcessError as e:
                self.show_message(f"Error adjusting headphone volume: {e}")
        elif key == 'f':
            try:
                # Уменьшаем громкость обоих наушников
                subprocess.check_output("amixer sset 'Headphone' 5%- -q", shell=True, text=True)
                # Получаем значение для левого наушника
                left_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Left' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                left_percent = int(left_result.rstrip('%'))
                left_filled = min(29, left_percent // 3)
                self.headphone_left_bar.set_text(f" {left_percent}% | {'░' * left_filled + ' ' * (29 - left_filled)}")
                # Получаем значение для правого наушника
                right_result = subprocess.check_output("amixer sget 'Headphone' | grep 'Front Right' | grep -o '[0-9]\+%' | head -1", shell=True, text=True).strip()
                right_percent = int(right_result.rstrip('%'))
                right_filled = min(29, right_percent // 3)
                self.headphone_right_bar.set_text(f" {right_percent}% | {'░' * right_filled + ' ' * (29 - right_filled)}")
                self.status_output.set_text(f"Headphone Left Right: {left_result} {right_result}")
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
        framed_widget = urwid.LineBox(
            widget, title="grnManagerTerm", title_align='center',
            tlcorner='╔', tline='═', trcorner='╗',
            lline='║', rline='║',
            blcorner='╚', bline='═', brcorner='╝'
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
        self.main_loop.set_alarm_in(0.1, self.mode.update_clock)
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
