import os
import sys
import threading
import time
from typing import Any, Tuple

import sdl2
import ui
from __version__ import version
from api import API
from filesystem import Filesystem
from glyps import glyphs
from input import Input
from status import Filter, StartMenuOptions, Status, View

# Redirect stdout to log file
sys.stdout = open("log.txt", "w", buffering=1)


class RomM:
    spinner_speed = 0.05
    start_menu_options = [
        value
        for name, value in StartMenuOptions.__dict__.items()
        if not name.startswith("_")
    ]

    def __init__(self) -> None:
        self.api = API()
        self.fs = Filesystem()
        self.input = Input()
        self.status = Status()

        self.contextual_menu_options: list[Tuple[str, int, Any]] = []
        self.start_menu_selected_position = 0
        self.contextual_menu_selected_position = 0
        self.platforms_selected_position = 0
        self.collections_selected_position = 0
        self.roms_selected_position = 0

        self.max_n_platforms = (ui.screen_height - 130) // 35
        self.max_n_collections = (ui.screen_height - 130) // 35
        self.max_n_roms = (ui.screen_height - 130) // 35
        print(f"Detected resolution: {ui.screen_width} x {ui.screen_height}")
        print(f"Max ROMs per page: {self.max_n_roms}")

        # Calculate button positions dynamically
        self.num_buttons = 5
        self.button_spacing = ui.screen_width / (
            self.num_buttons + 1
        )  # Divide screen into equal segments + 1 for padding
        self.buttonsY = int(ui.screen_height * 0.98)  # Keep Y position consistent
        self.button_positions = [
            (int(self.button_spacing * i + self.button_spacing / 2), self.buttonsY)
            for i in range(self.num_buttons)
        ]

        self.last_spinner_update = time.time()
        self.current_spinner_status = next(glyphs.spinner)

    def _button_pos(self, x_percent: float, y_percent: float) -> Tuple[int, int]:
        """Calculate button position based on screen size percentages."""
        x = int(ui.screen_width * x_percent)
        y = int(ui.screen_height * y_percent)
        return (x, y)

    def _render_platforms_view(self):
        ui.draw_platforms_list(
            self.platforms_selected_position,
            self.max_n_platforms,
            self.status.platforms,
        )
        if not self.status.platforms_ready.is_set():
            current_time = time.time()
            if current_time - self.last_spinner_update >= self.spinner_speed:
                self.last_spinner_update = current_time
                self.current_spinner_status = next(glyphs.spinner)
            ui.draw_log(text_line_1=f"{self.current_spinner_status} Fetching platforms")
        elif not self.status.download_rom_ready.is_set():
            if self.status.extracting_rom:
                ui.draw_loader(self.status.extracted_percent, color=ui.color_yellow)
                ui.draw_log(
                    text_line_1=f"{self.status.downloading_rom_position}/{len(self.status.download_queue)} | {self.status.extracted_percent:.2f}% | Extracting {self.status.downloading_rom.name}",
                    text_line_2=f"({self.status.downloading_rom.fs_name})",
                    background=False,
                )
            elif self.status.downloading_rom:
                ui.draw_loader(self.status.downloaded_percent)
                ui.draw_log(
                    text_line_1=f"{self.status.downloading_rom_position}/{len(self.status.download_queue)} | {self.status.downloaded_percent:.2f}% | {glyphs.download} {self.status.downloading_rom.name}",
                    text_line_2=f"({self.status.downloading_rom.fs_name})",
                    background=False,
                )
        elif not self.status.valid_host:
            ui.draw_log(
                text_line_1=f"Error: Can't connect to host {self.api.host}",
                text_color=ui.color_red,
            )
            self.status.valid_host = True
        elif not self.status.valid_credentials:
            ui.draw_log(text_line_1="Error: Permission denied", text_color=ui.color_red)
            self.status.valid_credentials = True
        else:
            ui.button_circle(
                (self.button_positions[0]), "A", "Select", color=ui.color_red
            )
            ui.button_circle(
                (self.button_positions[1]), "Y", "Refresh", color=ui.color_green
            )
            ui.button_circle(
                (self.button_positions[2]),
                "X",
                (
                    "Collections"
                    if self.status.current_view == View.PLATFORMS
                    else "Platforms"
                ),
                color=ui.color_blue,
            )

    def _update_platforms_view(self):
        if self.input.key("A"):
            if self.status.roms_ready.is_set() and len(self.status.platforms) > 0:
                self.status.roms_ready.clear()
                self.status.roms = []
                self.status.selected_platform = self.status.platforms[
                    self.platforms_selected_position
                ]
                self.status.current_view = View.ROMS
                threading.Thread(target=self.api.fetch_roms).start()
            self.input.reset_input()
        elif self.input.key("Y"):
            if self.status.platforms_ready.is_set():
                self.status.platforms_ready.clear()
                threading.Thread(target=self.api.fetch_platforms).start()
            self.input.reset_input()
        elif self.input.key("X"):
            self.status.current_view = View.COLLECTIONS
            self.input.reset_input()
        elif self.input.key("START"):
            self.status.show_contextual_menu = not self.status.show_contextual_menu
            if self.status.show_contextual_menu:
                self.contextual_menu_options = [
                    (
                        f"{glyphs.about} Platform info",
                        0,
                        lambda: ui.draw_log(
                            text_line_1=f"Platform name: {self.status.platforms[self.platforms_selected_position].display_name}"
                        ),
                    ),
                ]
            self.input.reset_input()
        else:
            self.platforms_selected_position = self.input.handle_navigation(
                self.platforms_selected_position,
                self.max_n_platforms,
                len(self.status.platforms),
            )

    def _render_collections_view(self):
        ui.draw_collections_list(
            self.collections_selected_position,
            self.max_n_collections,
            self.status.collections,
            fill=ui.color_yellow,
        )
        if not self.status.collections_ready.is_set():
            current_time = time.time()
            if current_time - self.last_spinner_update >= self.spinner_speed:
                self.last_spinner_update = current_time
                self.current_spinner_status = next(glyphs.spinner)
            ui.draw_log(
                text_line_1=f"{self.current_spinner_status} Fetching collections"
            )
        elif not self.status.download_rom_ready.is_set():
            if self.status.extracting_rom:
                ui.draw_loader(self.status.extracted_percent, color=ui.color_yellow)
                ui.draw_log(
                    text_line_1=f"{self.status.downloading_rom_position}/{len(self.status.download_queue)} | {self.status.extracted_percent:.2f}% | Extracting {self.status.downloading_rom.name}",
                    text_line_2=f"({self.status.downloading_rom.fs_name})",
                    background=False,
                )
            elif self.status.downloading_rom:
                ui.draw_loader(self.status.downloaded_percent)
                ui.draw_log(
                    text_line_1=f"{self.status.downloading_rom_position}/{len(self.status.download_queue)} | {self.status.downloaded_percent:.2f}% | {glyphs.download} {self.status.downloading_rom.name}",
                    text_line_2=f"({self.status.downloading_rom.fs_name})",
                    background=False,
                )
        elif not self.status.valid_host:
            ui.draw_log(
                text_line_1=f"Error: Can't connect to host {self.api.host}",
                text_color=ui.color_red,
            )
            self.status.valid_host = True
        elif not self.status.valid_credentials:
            ui.draw_log(text_line_1="Error: Permission denied", text_color=ui.color_red)
            self.status.valid_credentials = True
        else:
            ui.button_circle(
                (self.button_positions[0]), "A", "Select", color=ui.color_red
            )
            ui.button_circle(
                (self.button_positions[1]), "Y", "Refresh", color=ui.color_green
            )
            ui.button_circle(
                (self.button_positions[2]),
                "X",
                (
                    "Collections"
                    if self.status.current_view == View.PLATFORMS
                    else "Platforms"
                ),
                color=ui.color_blue,
            )

    def _update_collections_view(self):
        if self.input.key("A"):
            if self.status.roms_ready.is_set() and len(self.status.collections) > 0:
                self.status.roms_ready.clear()
                self.status.roms = []
                selected_collection = self.status.collections[
                    self.collections_selected_position
                ]
                if selected_collection.virtual:
                    self.status.selected_virtual_collection = selected_collection
                else:
                    self.status.selected_collection = selected_collection
                self.status.current_view = View.ROMS
                threading.Thread(target=self.api.fetch_roms).start()
            self.input.reset_input()
        elif self.input.key("Y"):
            if self.status.collections_ready.is_set():
                self.status.collections_ready.clear()
                threading.Thread(target=self.api.fetch_collections).start()
            self.input.reset_input()
        elif self.input.key("X"):
            self.status.current_view = View.PLATFORMS
            self.input.reset_input()
        elif self.input.key("START"):
            self.status.show_contextual_menu = not self.status.show_contextual_menu
            if self.status.show_contextual_menu:
                self.contextual_menu_options = [
                    (
                        f"{glyphs.about} Collection info",
                        0,
                        lambda: ui.draw_log(
                            text_line_1=f"Collection name: {self.status.collections[self.collections_selected_position].name}"
                        ),
                    ),
                ]
            self.input.reset_input()
        else:
            self.collections_selected_position = self.input.handle_navigation(
                self.collections_selected_position,
                self.max_n_collections,
                len(self.status.collections),
            )

    def _render_roms_view(self):
        if self.status.selected_platform:
            header_text = self.status.platforms[
                self.platforms_selected_position
            ].display_name
            header_color = ui.color_violet
            prepend_platform_slug = False
        elif self.status.selected_collection or self.status.selected_virtual_collection:
            header_text = self.status.collections[
                self.collections_selected_position
            ].name
            header_color = ui.color_yellow
            prepend_platform_slug = True
        total_pages = (
            len(self.status.roms_to_show) + self.max_n_roms - 1
        ) // self.max_n_roms
        current_page = (self.roms_selected_position // self.max_n_roms) + 1
        header_text += f" [{current_page if total_pages > 0 else 0}/{total_pages}]"
        if self.status.current_filter == Filter.ALL:
            self.status.roms_to_show = self.status.roms
        elif self.status.current_filter == Filter.LOCAL:
            self.status.roms_to_show = [
                r for r in self.status.roms if self.fs.is_rom_in_device(r)
            ]
        elif self.status.current_filter == Filter.REMOTE:
            self.status.roms_to_show = [
                r for r in self.status.roms if not self.fs.is_rom_in_device(r)
            ]
        ui.draw_roms_list(
            self.roms_selected_position,
            self.max_n_roms,
            self.status.roms_to_show,
            header_text,
            header_color,
            self.status.multi_selected_roms,
            prepend_platform_slug=prepend_platform_slug,
        )
        if not self.status.roms_ready.is_set():
            current_time = time.time()
            if current_time - self.last_spinner_update >= self.spinner_speed:
                self.last_spinner_update = current_time
                self.current_spinner_status = next(glyphs.spinner)
            ui.draw_log(text_line_1=f"{self.current_spinner_status} Fetching roms")
        elif not self.status.download_rom_ready.is_set():
            if self.status.extracting_rom:
                ui.draw_loader(self.status.extracted_percent, color=ui.color_yellow)
                ui.draw_log(
                    text_line_1=f"{self.status.downloading_rom_position}/{len(self.status.download_queue)} | {self.status.extracted_percent:.2f}% | Extracting {self.status.downloading_rom.name}",
                    text_line_2=f"({self.status.downloading_rom.fs_name})",
                    background=False,
                )
            elif self.status.downloading_rom:
                ui.draw_loader(self.status.downloaded_percent)
                ui.draw_log(
                    text_line_1=f"{self.status.downloading_rom_position}/{len(self.status.download_queue)} | {self.status.downloaded_percent:.2f}% | {glyphs.download} {self.status.downloading_rom.name}",
                    text_line_2=f"({self.status.downloading_rom.fs_name})",
                    background=False,
                )
        elif not self.status.valid_host:
            ui.draw_log(
                text_line_1=f"Error: Can't connect to host {self.api.host}",
                text_color=ui.color_red,
            )
            self.status.valid_host = True
        elif not self.status.valid_credentials:
            ui.draw_log(text_line_1="Error: Permission denied", text_color=ui.color_red)
            self.status.valid_credentials = True
        else:
            ui.button_circle(
                (self.button_positions[0]), "A", "Download", color=ui.color_red
            )
            ui.button_circle(
                (self.button_positions[1]), "B", "Back", color=ui.color_yellow
            )
            ui.button_circle(
                (self.button_positions[2]), "Y", "Refresh", color=ui.color_green
            )
            ui.button_circle(
                (self.button_positions[3]),
                "X",
                f"Filter: {self.status.current_filter}",
                color=ui.color_blue,
            )
            ui.button_circle(
                (self.button_positions[4]),
                "R1",
                (
                    "Deselect all"
                    if len(self.status.multi_selected_roms) > 0
                    and len(self.status.multi_selected_roms)
                    >= len(self.status.roms_to_show)
                    else "Select all"
                ),
                color=ui.color_gray_1,
            )

    def _update_roms_view(self):
        if self.input.key("A"):
            if (
                self.status.roms_ready.is_set()
                and self.status.download_rom_ready.is_set()
            ):
                self.status.download_rom_ready.clear()
                # If no game is "multi-selected" the current game is added to the download list
                if len(self.status.multi_selected_roms) == 0:
                    self.status.multi_selected_roms.append(
                        self.status.roms_to_show[self.roms_selected_position]
                    )
                self.status.download_queue = self.status.multi_selected_roms
                self.status.abort_download.clear()
                threading.Thread(target=self.api.download_rom).start()
                self.input.reset_input()
        elif self.input.key("B"):
            if self.status.selected_platform:
                self.status.current_view = View.PLATFORMS
                self.status.selected_platform = None
            elif self.status.selected_collection:
                self.status.current_view = View.COLLECTIONS
                self.status.selected_collection = None
            elif self.status.selected_virtual_collection:
                self.status.current_view = View.COLLECTIONS
                self.status.selected_virtual_collection = None
            else:
                self.status.current_view = View.PLATFORMS
                self.status.selected_platform = None
                self.status.selected_collection = None
                self.status.selected_virtual_collection = None
            self.status.reset_roms_list()
            self.roms_selected_position = 0
            self.status.multi_selected_roms = []
            self.input.reset_input()
        elif self.input.key("Y"):
            if self.status.roms_ready.is_set():
                self.status.roms_ready.clear()
                threading.Thread(target=self.api.fetch_roms).start()
                self.status.multi_selected_roms = []
            self.input.reset_input()
        elif self.input.key("X"):
            self.status.current_filter = next(self.status.filters)
            self.roms_selected_position = 0
            self.input.reset_input()
        elif self.input.key("R1"):
            if len(self.status.multi_selected_roms) == len(self.status.roms_to_show):
                self.status.multi_selected_roms = []
            else:
                self.status.multi_selected_roms = self.status.roms_to_show.copy()
            self.input.reset_input()
        elif self.input.key("SELECT"):
            if self.status.download_rom_ready.is_set():
                if (
                    self.status.roms_to_show[self.roms_selected_position]
                    not in self.status.multi_selected_roms
                ):
                    self.status.multi_selected_roms.append(
                        self.status.roms_to_show[self.roms_selected_position]
                    )
                else:
                    self.status.multi_selected_roms.remove(
                        self.status.roms_to_show[self.roms_selected_position]
                    )
            self.input.reset_input()
        elif self.input.key("START"):
            self.status.show_contextual_menu = not self.status.show_contextual_menu
            if self.status.show_contextual_menu:
                selected_rom = self.status.roms_to_show[self.roms_selected_position]
                self.contextual_menu_options = [
                    (
                        f"{glyphs.about} Rom info",
                        0,
                        lambda: ui.draw_log(
                            text_line_1=f"Rom name: {selected_rom.name}"
                        ),
                    ),
                ]
                is_in_device = os.path.exists(
                    os.path.join(
                        self.fs.get_storage_platform_path(selected_rom.platform_slug),
                        selected_rom.fs_name,
                    )
                )
                if is_in_device:
                    self.contextual_menu_options.append(
                        (
                            f"{glyphs.delete} Remove from device",
                            1,
                            lambda: os.remove(
                                os.path.join(
                                    self.fs.get_storage_platform_path(
                                        self.status.roms_to_show[
                                            self.roms_selected_position
                                        ].platform_slug
                                    ),
                                    self.status.roms_to_show[
                                        self.roms_selected_position
                                    ].fs_name,
                                )
                            ),
                        ),
                    )
            self.input.reset_input()
        else:
            self.roms_selected_position = self.input.handle_navigation(
                self.roms_selected_position,
                self.max_n_roms,
                len(self.status.roms_to_show),
            )

    def _render_contextual_menu(self):
        pos = [ui.screen_width / 3, ui.screen_height / 3]
        padding = 5
        width = 200
        n_options = len(self.contextual_menu_options)
        option_height = 32
        gap = 3
        if self.status.current_view == View.PLATFORMS:
            ui.draw_menu_background(
                pos,
                width,
                n_options,
                option_height,
                gap,
                padding,
            )
        elif self.status.current_view == View.COLLECTIONS:
            ui.draw_menu_background(pos, width, n_options, option_height, gap, padding)
        elif self.status.current_view == View.ROMS:
            ui.draw_menu_background(pos, width, n_options, option_height, gap, padding)
        else:
            ui.draw_menu_background(pos, width, n_options, option_height, gap, padding)
        start_idx = int(self.contextual_menu_selected_position / n_options) * n_options
        end_idx = start_idx + n_options
        for i, option in enumerate(self.contextual_menu_options[start_idx:end_idx]):
            is_selected = i == (self.contextual_menu_selected_position % n_options)
            ui.row_list(
                option[0],
                (pos[0] + padding, pos[1] + padding + (i * (option_height + gap))),
                width,
                option_height,
                is_selected,
            )

    def _update_contextual_menu(self):
        if self.input.key("A"):
            self.contextual_menu_options[self.contextual_menu_selected_position][2]()
            self.status.show_contextual_menu = False
            self.input.reset_input()
        elif self.input.key("B"):
            self.status.show_contextual_menu = not self.status.show_contextual_menu
            self.contextual_menu_options = []
            self.input.reset_input()
        else:
            self.contextual_menu_selected_position = self.input.handle_navigation(
                self.contextual_menu_selected_position,
                len(self.contextual_menu_options),
                len(self.contextual_menu_options),
            )

    def _render_start_menu(self):
        pos = [ui.screen_width / 3, ui.screen_height / 3]
        padding = 5
        width = 200
        n_options = len(self.start_menu_options)
        option_height = 32
        gap = 3
        title = "Main menu"
        title_x_adjustement = 35
        version_x_adjustement = 50 / 6 * (len(version) + 2)
        version_height = 20
        ui.draw_menu_background(
            pos,
            width,
            n_options,
            option_height,
            gap,
            padding,
            extra_top_offset=version_height,
            extra_bottom_offset=version_height,
        )
        start_idx = int(self.start_menu_selected_position / n_options) * n_options
        end_idx = start_idx + n_options
        for i, option in enumerate(self.start_menu_options[start_idx:end_idx]):
            is_selected = i == (self.start_menu_selected_position % n_options)
            ui.row_list(
                option[0],
                (pos[0] + padding, pos[1] + padding + (i * (option_height + gap))),
                width,
                option_height,
                is_selected,
            )
        ui.draw_text(
            (
                pos[0] + width - version_x_adjustement,
                pos[1] + padding + len(self.start_menu_options) * (option_height + gap),
            ),
            f"v{version}",
        )
        ui.draw_text(
            (
                pos[0] + width / 2 - title_x_adjustement,
                pos[1] - option_height + version_height - padding,
            ),
            title,
        )

    def _update_start_menu(self):
        if self.input.key("A"):
            if self.start_menu_selected_position == StartMenuOptions.ABORT_DOWNLOAD[1]:
                self.status.abort_download.set()
                self.input.reset_input()
                self.status.show_start_menu = False
            elif self.start_menu_selected_position == StartMenuOptions.SD_SWITCH[1]:
                current = self.fs.get_sd_storage()
                self.fs.switch_sd_storage()
                new = self.fs.get_sd_storage()
                if new == current:
                    ui.draw_log(
                        text_line_1=f"Error: Couldn't find path {self.fs.get_sd2_storage_path()}",
                        text_color=ui.color_red,
                    )
                else:
                    ui.draw_log(
                        text_line_1=f"Set download path to SD {self.fs.get_sd_storage()}: {self.fs.get_sd_storage_path()}",
                        text_color=ui.color_green,
                    )
                self.input.reset_input()
            elif self.start_menu_selected_position == StartMenuOptions.EXIT[1]:
                ui.draw_end()
                self.input.cleanup()
                sys.exit()
        elif self.input.key("B"):
            self.status.show_start_menu = not self.status.show_start_menu
            self.input.reset_input()
        else:
            self.start_menu_selected_position = self.input.handle_navigation(
                self.start_menu_selected_position,
                len(self.start_menu_options),
                len(self.start_menu_options),
            )

    def _update_common(self):
        if self.input.key("MENUF") and not self.status.show_contextual_menu:
            self.status.show_start_menu = not self.status.show_start_menu
            self.input.reset_input()
        if self.input.key("START") and not self.status.show_start_menu:
            self.status.show_contextual_menu = not self.status.show_contextual_menu
            self.input.reset_input()

    def start(self):
        threading.Thread(target=self.input.check, daemon=True).start()
        self._render_platforms_view()
        threading.Thread(target=self.api.fetch_platforms).start()
        threading.Thread(target=self.api.fetch_collections).start()
        threading.Thread(target=self.api.fetch_me).start()

    def update(self):
        ui.draw_clear()

        # Poll SDL2 events
        event = sdl2.SDL_Event()
        while sdl2.SDL_PollEvent(event) != 0:
            if event.type == sdl2.SDL_QUIT:
                ui.draw_end()
                self.input.cleanup()
                sys.exit(0)
            self.input.check(event)

        self.input.check()  # Poll controller state

        if self.status.me_ready.is_set():
            ui.draw_header(self.api.host, self.api.username)

        if not self.status.valid_host:
            if self.input.key("Y"):
                if self.status.platforms_ready.is_set():
                    self.status.platforms_ready.clear()
                    threading.Thread(target=self.api.fetch_platforms).start()
                self.input.reset_input()
            ui.button_circle(
                (self.button_positions[0]), "Y", "Refresh", color=ui.color_green
            )
            ui.draw_text(
                (ui.screen_width / 2, ui.screen_height / 2),
                f"Error: Can't connect to host\n{self.api.host}",
                color=ui.color_red,
                anchor="mm",
            )
        elif not self.status.valid_credentials:
            if self.input.key("Y"):
                if self.status.platforms_ready.is_set():
                    self.status.platforms_ready.clear()
                    threading.Thread(target=self.api.fetch_platforms).start()
                self.input.reset_input()
            ui.button_circle(
                (self.button_positions[0]), "Y", "Refresh", color=ui.color_green
            )
            ui.draw_text(
                (ui.screen_width / 2, ui.screen_height / 2),
                "Error: Permission denied",
                color=ui.color_red,
                anchor="mm",
            )
        else:
            if self.status.current_view == View.PLATFORMS:
                self._render_platforms_view()
                if (
                    not self.status.show_start_menu
                    and not self.status.show_contextual_menu
                ):
                    self._update_platforms_view()
            elif self.status.current_view == View.COLLECTIONS:
                self._render_collections_view()
                if (
                    not self.status.show_start_menu
                    and not self.status.show_contextual_menu
                ):
                    self._update_collections_view()
            elif self.status.current_view == View.ROMS:
                self._render_roms_view()
                if (
                    not self.status.show_start_menu
                    and not self.status.show_contextual_menu
                ):
                    self._update_roms_view()
            else:
                self._render_platforms_view()
                if (
                    not self.status.show_start_menu
                    and not self.status.show_contextual_menu
                ):
                    self._update_platforms_view()
        # Render start menu
        if self.status.show_start_menu:
            self._render_start_menu()
            self._update_start_menu()
        elif self.status.show_contextual_menu:
            self._render_contextual_menu()
            self._update_contextual_menu()

        self._update_common()

        ui.draw_update()
