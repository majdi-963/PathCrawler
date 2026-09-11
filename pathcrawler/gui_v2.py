"""Graphical interface for PathCrawler, built with CustomTkinter.

This provides the same functionality as cli.py (pathcrawler's command-line
interface) through a desktop UI. It calls into the same `pathcrawler`
package (config, scanner, reporter, models, errors, logger) so behavior
and validation stay identical to the CLI tool — the GUI is a different
front door onto the same engine, not a reimplementation of it.

Run with:
    python gui.py
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk  # pyright: ignore[reportMissingImports]

from pathcrawler.config import (
    build_scan_config,
    load_config_file,
    parse_extension_argument,
    parse_header_arguments,
    parse_status_argument,
)
from pathcrawler.errors import ConfigurationError, PathCrawlerError
from pathcrawler.logger import setup_logging
from pathcrawler.models import VERSION
from pathcrawler.reporter import write_report
from pathcrawler.scanner import PathCrawlerScanner

ctk.set_widget_scaling(2)
ctk.set_window_scaling(2)

ETHICAL_NOTICE = (
    "Ethical use notice: PathCrawler is intended ONLY for authorized security "
    "testing against systems you own or have explicit permission to assess."
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ---------------------------------------------------------------------------
# Design tokens
#
# A recon tool spends its life showing dense, semantically-colored data
# (status codes, sizes, content types) inside a dark control surface, so the
# palette leans on one quiet neutral base plus a single "signal" accent for
# actions, and reserves color for meaning: green/amber/red/violet map to
# 2xx/3xx/4xx/5xx everywhere in the app, not just in the results table.
# ---------------------------------------------------------------------------
class Palette:
    BG = "#0d0f14"
    SURFACE = "#151822"
    SURFACE_ALT = "#1b1f2b"
    SURFACE_ROW = "#171a24"
    BORDER = "#262b3a"

    TEXT = "#e6e9f0"
    TEXT_DIM = "#8890a3"
    TEXT_FAINT = "#565d70"

    ACCENT = "#35d0c0"
    ACCENT_HOVER = "#2ab5a6"
    ACCENT_SOFT = "#16302f"

    SUCCESS = "#4ade80"  # 2xx
    INFO = "#f2b84b"  # 3xx
    ERROR = "#f56565"  # 4xx
    SPECIAL = "#b18cf5"  # 5xx

    GO = "#3fae63"
    GO_HOVER = "#348f52"
    STOP = "#c9484d"
    STOP_HOVER = "#a93c40"


MONO_FAMILY = "Courier New"


def font_ui(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def font_mono(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=MONO_FAMILY, size=size, weight=weight)


def status_color(status: str) -> str:
    if not status:
        return Palette.TEXT_FAINT
    return {
        "2": Palette.SUCCESS,
        "3": Palette.INFO,
        "4": Palette.ERROR,
        "5": Palette.SPECIAL,
    }.get(status[0], Palette.TEXT_DIM)


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}m {s}s" if m else f"{s}s"


class QueueLogHandler(logging.Handler):
    """Routes stdlib logging records into the GUI's thread-safe queue."""

    def __init__(self, log_queue: "queue.Queue[tuple[str, Any]]") -> None:
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        self.log_queue.put(("log", msg))


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------
class LabeledEntry(ctk.CTkFrame):
    """A labeled entry field, optionally with a browse button."""

    def __init__(
        self,
        master: Any,
        label: str,
        placeholder: str = "",
        browse: Optional[str] = None,  # "file" | "save" | "config" | None
        show: Optional[str] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        self.label = ctk.CTkLabel(
            self,
            text=label,
            anchor="w",
            font=font_ui(size=12),
            text_color=Palette.TEXT_DIM,
        )
        self.label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        self.entry = ctk.CTkEntry(
            self,
            placeholder_text=placeholder,
            height=32,
            show=show or "",
            fg_color=Palette.SURFACE_ALT,
            border_color=Palette.BORDER,
            border_width=1,
            text_color=Palette.TEXT,
            placeholder_text_color=Palette.TEXT_FAINT,
            corner_radius=7,
        )
        self.entry.grid(row=1, column=0, sticky="ew")

        if browse:
            self.browse_btn = ctk.CTkButton(
                self,
                text="Browse",
                width=72,
                height=32,
                corner_radius=7,
                fg_color=Palette.SURFACE_ALT,
                hover_color=Palette.BORDER,
                text_color=Palette.TEXT_DIM,
                border_width=1,
                border_color=Palette.BORDER,
                font=font_ui(size=12),
                command=lambda: self._browse(browse),
            )
            self.browse_btn.grid(row=1, column=1, padx=(8, 0))

    def _browse(self, mode: str) -> None:
        if mode == "file":
            path = filedialog.askopenfilename(title="Select wordlist file")
        elif mode == "config":
            path = filedialog.askopenfilename(
                title="Select JSON config file", filetypes=[("JSON files", "*.json")]
            )
        else:  # save
            path = filedialog.asksaveasfilename(
                title="Save report as",
                defaultextension=".json",
                filetypes=[("JSON", "*.json"), ("CSV", "*.csv")],
            )
        if path:
            self.set(path)

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, value)

    def flash_error(self) -> None:
        self.entry.configure(border_color=Palette.STOP)
        self.after(1600, lambda: self.entry.configure(border_color=Palette.BORDER))


class HeaderRow(ctk.CTkFrame):
    """One 'Name: value' custom-header row with a remove button."""

    def __init__(self, master: Any, on_remove) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure((0, 1), weight=1)

        entry_kwargs = dict(
            height=30,
            fg_color=Palette.SURFACE_ALT,
            border_color=Palette.BORDER,
            border_width=1,
            text_color=Palette.TEXT,
            placeholder_text_color=Palette.TEXT_FAINT,
            corner_radius=7,
        )
        self.name_entry = ctk.CTkEntry(
            self, placeholder_text="Header name", **entry_kwargs
        )
        self.name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.value_entry = ctk.CTkEntry(
            self, placeholder_text="Header value", **entry_kwargs
        )
        self.value_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        remove_btn = ctk.CTkButton(
            self,
            text="\u2715",
            width=30,
            height=30,
            corner_radius=7,
            fg_color="transparent",
            hover_color=Palette.STOP,
            border_width=1,
            border_color=Palette.BORDER,
            text_color=Palette.TEXT_DIM,
            command=lambda: on_remove(self),
        )
        remove_btn.grid(row=0, column=2)

    def as_header_string(self) -> Optional[str]:
        name = self.name_entry.get().strip()
        value = self.value_entry.get().strip()
        if not name:
            return None
        return f"{name}: {value}"


class ResultRow(ctk.CTkFrame):
    """One discovered-path row: a status pill plus path / size / type."""

    def __init__(
        self, master: Any, status: Any, path: Any, size: Any, ctype: Any, alt: bool
    ) -> None:
        bg = Palette.SURFACE_ROW if alt else "transparent"
        super().__init__(master, fg_color=bg, corner_radius=6)
        self.grid_columnconfigure(1, weight=1)

        self.status = str(status) if status not in (None, "") else "?"
        self.path = str(path)
        self.size = str(size) if size not in (None, "") else "\u2013"
        self.ctype = str(ctype) if ctype not in (None, "") else "\u2013"

        pill = ctk.CTkLabel(
            self,
            text=self.status,
            width=46,
            height=20,
            corner_radius=6,
            fg_color=status_color(self.status),
            text_color=Palette.BG,
            font=font_mono(11, "bold"),
            anchor="center",
        )
        pill.grid(row=0, column=0, padx=(10, 12), pady=5, sticky="w")

        ctk.CTkLabel(
            self,
            text=self.path,
            anchor="w",
            font=font_mono(12),
            text_color=Palette.TEXT,
        ).grid(row=0, column=1, sticky="ew", pady=5)

        ctk.CTkLabel(
            self,
            text=self.size,
            width=72,
            anchor="e",
            font=font_mono(11),
            text_color=Palette.TEXT_DIM,
        ).grid(row=0, column=2, padx=(6, 6), pady=5, sticky="e")

        ctk.CTkLabel(
            self,
            text=self.ctype,
            width=150,
            anchor="w",
            font=font_mono(11),
            text_color=Palette.TEXT_DIM,
        ).grid(row=0, column=3, padx=(0, 10), pady=5, sticky="w")

    def matches(self, status_filter: str, search: str) -> bool:
        if status_filter != "All" and not self.status.startswith(status_filter[0]):
            return False
        if search and search.lower() not in self.path.lower():
            return False
        return True


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class PathCrawlerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"PathCrawler {VERSION}")
        self.geometry("1220x780")
        self.minsize(1040, 680)
        self.configure(fg_color=Palette.BG)

        self.log_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self.scan_thread: Optional[threading.Thread] = None
        self.is_scanning = False
        self.last_results: list[Any] = []
        self.last_stats: Any = None
        self.last_wordlist_stats: Any = None
        self.header_rows: list[HeaderRow] = []
        self.result_rows: list[ResultRow] = []
        self._result_row_index = 0
        self._scan_start_time: Optional[float] = None

        self._build_layout()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_panel()

    # -- Sidebar ---------------------------------------------------------
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self, width=380, corner_radius=0, fg_color=Palette.SURFACE
        )
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)

        # Brand header
        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 14))
        brand.grid_columnconfigure(1, weight=1)

        mark = ctk.CTkLabel(
            brand,
            text="PC",
            width=38,
            height=38,
            corner_radius=9,
            fg_color=Palette.ACCENT_SOFT,
            text_color=Palette.ACCENT,
            font=font_mono(14, "bold"),
            anchor="center",
        )
        mark.grid(row=0, column=0, rowspan=2, sticky="w")

        ctk.CTkLabel(
            brand,
            text="PathCrawler",
            font=font_ui(19, "bold"),
            text_color=Palette.TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ctk.CTkLabel(
            brand,
            text=f"version {VERSION}",
            font=font_mono(11),
            text_color=Palette.TEXT_DIM,
            anchor="w",
        ).grid(row=1, column=1, sticky="w", padx=(12, 0))

        # Ethical-use notice, styled as a callout rather than a wall of text
        notice = ctk.CTkFrame(sidebar, fg_color=Palette.SURFACE_ALT, corner_radius=8)
        notice.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 16))
        notice.grid_columnconfigure(1, weight=1)
        ctk.CTkFrame(notice, width=3, fg_color=Palette.INFO, corner_radius=0).grid(
            row=0, column=0, sticky="ns"
        )
        ctk.CTkLabel(
            notice,
            text=ETHICAL_NOTICE,
            wraplength=310,
            justify="left",
            font=font_ui(11),
            text_color=Palette.TEXT_DIM,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(10, 12), pady=9)

        # Tabbed configuration
        tabview = ctk.CTkTabview(
            sidebar,
            fg_color=Palette.SURFACE,
            segmented_button_fg_color=Palette.SURFACE_ALT,
            segmented_button_selected_color=Palette.ACCENT,
            segmented_button_selected_hover_color=Palette.ACCENT_HOVER,
            segmented_button_unselected_color=Palette.SURFACE_ALT,
            segmented_button_unselected_hover_color=Palette.BORDER,
            text_color=Palette.TEXT,
            text_color_disabled=Palette.TEXT_FAINT,
            corner_radius=10,
        )
        tabview.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 14))
        tab_target = tabview.add("Target")
        tab_request = tabview.add("Request")
        tab_advanced = tabview.add("Advanced")

        self._build_target_tab(tab_target)
        self._build_request_tab(tab_request)
        self._build_advanced_tab(tab_advanced)

        # Actions
        actions = ctk.CTkFrame(sidebar, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 22))
        actions.grid_columnconfigure((0, 1), weight=1)

        self.start_btn = ctk.CTkButton(
            actions,
            text="\u25b6  Start scan",
            height=40,
            corner_radius=8,
            fg_color=Palette.GO,
            hover_color=Palette.GO_HOVER,
            font=font_ui(13, "bold"),
            command=self.start_scan,
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            actions,
            text="\u25a0  Stop",
            height=40,
            corner_radius=8,
            fg_color=Palette.STOP,
            hover_color=Palette.STOP_HOVER,
            font=font_ui(13, "bold"),
            state="disabled",
            command=self.stop_scan,
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    @staticmethod
    def _scroll_tab(tab: Any) -> ctk.CTkScrollableFrame:
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        body = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        return body

    def _build_target_tab(self, tab: Any) -> None:
        body = self._scroll_tab(tab)

        self.url_field = LabeledEntry(
            body, "Target URL", placeholder="http://127.0.0.1:8000"
        )
        self.url_field.grid(row=0, column=0, sticky="ew", pady=(4, 10))
        self.url_field.entry.bind("<Return>", lambda _e: self.start_scan())

        self.wordlist_field = LabeledEntry(
            body, "Wordlist", placeholder="wordlists/common.txt", browse="file"
        )
        self.wordlist_field.grid(row=1, column=0, sticky="ew", pady=10)

        self.config_field = LabeledEntry(
            body, "Config file (optional)", browse="config"
        )
        self.config_field.grid(row=2, column=0, sticky="ew", pady=10)

        self.extensions_field = LabeledEntry(
            body, "Extensions", placeholder="php,html,txt,bak"
        )
        self.extensions_field.grid(row=3, column=0, sticky="ew", pady=10)

        status_row = ctk.CTkFrame(body, fg_color="transparent")
        status_row.grid(row=4, column=0, sticky="ew", pady=10)
        status_row.grid_columnconfigure((0, 1), weight=1)
        self.status_field = LabeledEntry(
            status_row, "Include status", placeholder="200,301,302,403"
        )
        self.status_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.exclude_status_field = LabeledEntry(
            status_row, "Exclude status", placeholder="404"
        )
        self.exclude_status_field.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _build_request_tab(self, tab: Any) -> None:
        body = self._scroll_tab(tab)

        rate_row = ctk.CTkFrame(body, fg_color="transparent")
        rate_row.grid(row=0, column=0, sticky="ew", pady=(4, 10))
        rate_row.grid_columnconfigure((0, 1), weight=1)
        self.threads_field = LabeledEntry(rate_row, "Threads", placeholder="10")
        self.threads_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.timeout_field = LabeledEntry(rate_row, "Timeout (s)", placeholder="5")
        self.timeout_field.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.delay_field = LabeledEntry(
            body, "Delay between requests (s)", placeholder="0"
        )
        self.delay_field.grid(row=1, column=0, sticky="ew", pady=10)

        self.user_agent_field = LabeledEntry(body, "User-Agent (optional)")
        self.user_agent_field.grid(row=2, column=0, sticky="ew", pady=10)

        self.follow_redirects_var = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            body,
            text="Follow redirects",
            variable=self.follow_redirects_var,
            font=font_ui(12),
            text_color=Palette.TEXT,
            progress_color=Palette.ACCENT,
        ).grid(row=3, column=0, sticky="w", pady=(8, 14))

        ctk.CTkLabel(
            body,
            text="Custom headers",
            font=font_ui(12),
            text_color=Palette.TEXT_DIM,
            anchor="w",
        ).grid(row=4, column=0, sticky="w", pady=(2, 6))
        self.headers_container = ctk.CTkFrame(body, fg_color="transparent")
        self.headers_container.grid(row=5, column=0, sticky="ew")
        self.headers_container.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            body,
            text="+ Add header",
            height=28,
            corner_radius=7,
            fg_color=Palette.SURFACE_ALT,
            hover_color=Palette.BORDER,
            text_color=Palette.ACCENT,
            border_width=1,
            border_color=Palette.BORDER,
            font=font_ui(12),
            command=self._add_header_row,
        ).grid(row=6, column=0, sticky="w", pady=(6, 4))

    def _build_advanced_tab(self, tab: Any) -> None:
        body = self._scroll_tab(tab)

        self.recursive_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            body,
            text="Recursive scan",
            variable=self.recursive_var,
            font=font_ui(12),
            text_color=Palette.TEXT,
            progress_color=Palette.ACCENT,
        ).grid(row=0, column=0, sticky="w", pady=(4, 12))

        self.depth_field = LabeledEntry(body, "Max recursion depth", placeholder="1")
        self.depth_field.grid(row=1, column=0, sticky="ew", pady=10)

        ctk.CTkLabel(
            body,
            text="Log level",
            font=font_ui(12),
            text_color=Palette.TEXT_DIM,
            anchor="w",
        ).grid(row=2, column=0, sticky="w", pady=(10, 5))
        self.log_level_var = tk.StringVar(value="INFO")
        ctk.CTkOptionMenu(
            body,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            variable=self.log_level_var,
            fg_color=Palette.SURFACE_ALT,
            button_color=Palette.BORDER,
            button_hover_color=Palette.ACCENT_HOVER,
            text_color=Palette.TEXT,
            dropdown_fg_color=Palette.SURFACE_ALT,
            dropdown_text_color=Palette.TEXT,
            font=font_ui(12),
            height=32,
            corner_radius=7,
        ).grid(row=3, column=0, sticky="ew", pady=(0, 10))

        self.output_field = LabeledEntry(body, "Report path (optional)", browse="save")
        self.output_field.grid(row=4, column=0, sticky="ew", pady=10)

    # ------------------------------------------------------------------
    # Header rows
    # ------------------------------------------------------------------
    def _add_header_row(self) -> None:
        row = HeaderRow(self.headers_container, self._remove_header_row)
        row.grid(sticky="ew", pady=3)
        self.header_rows.append(row)

    def _remove_header_row(self, row: HeaderRow) -> None:
        row.destroy()
        self.header_rows.remove(row)

    # -- Main panel --------------------------------------------------------
    def _build_main_panel(self) -> None:
        main = ctk.CTkFrame(self, corner_radius=0, fg_color=Palette.BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)

        content = ctk.CTkFrame(main, fg_color="transparent")
        content.grid(row=0, column=0, sticky="nsew", padx=24, pady=20)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(4, weight=3)
        content.grid_rowconfigure(6, weight=2)

        self._build_status_bar(content)
        self._build_stat_strip(content)
        self._build_results_toolbar(content)
        self._build_results_header(content)
        self._build_results_body(content)
        self._build_log_panel(content)

    def _build_status_bar(self, parent: Any) -> None:
        bar = ctk.CTkFrame(
            parent, fg_color=Palette.SURFACE, corner_radius=10, height=48
        )
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        bar.grid_columnconfigure(1, weight=1)

        self.status_dot = ctk.CTkLabel(
            bar,
            text="\u25cf",
            text_color=Palette.TEXT_FAINT,
            font=font_ui(16),
        )
        self.status_dot.grid(row=0, column=0, padx=(16, 6), pady=10)
        self.status_label = ctk.CTkLabel(
            bar,
            text="Idle",
            font=font_ui(13, "bold"),
            text_color=Palette.TEXT,
        )
        self.status_label.grid(row=0, column=1, sticky="w", pady=10)

        self.progress_bar = ctk.CTkProgressBar(
            bar,
            mode="indeterminate",
            width=220,
            progress_color=Palette.ACCENT,
            fg_color=Palette.SURFACE_ALT,
        )
        self.progress_bar.grid(row=0, column=2, sticky="e", padx=16, pady=10)
        self.progress_bar.set(0)

    def _build_stat_strip(self, parent: Any) -> None:
        strip = ctk.CTkFrame(
            parent,
            fg_color=Palette.SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=Palette.BORDER,
        )
        strip.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        strip.grid_columnconfigure((0, 2, 4, 6), weight=1)

        def block(col: int, label: str) -> ctk.CTkLabel:
            wrap = ctk.CTkFrame(strip, fg_color="transparent")
            wrap.grid(row=0, column=col, sticky="w", padx=20, pady=14)
            val = ctk.CTkLabel(
                wrap, text="0", font=font_mono(24, "bold"), text_color=Palette.TEXT
            )
            val.pack(anchor="w")
            ctk.CTkLabel(
                wrap, text=label, font=font_ui(11), text_color=Palette.TEXT_DIM
            ).pack(anchor="w")
            return val

        def divider(col: int) -> None:
            ctk.CTkFrame(strip, width=1, fg_color=Palette.BORDER).grid(
                row=0, column=col, sticky="ns", pady=12
            )

        self.stat_found_val = block(0, "Found")
        divider(1)
        self.stat_requests_val = block(2, "Requests")
        divider(3)
        self.stat_errors_val = block(4, "Errors")
        divider(5)
        self.stat_elapsed_val = block(6, "Elapsed")

    def _build_results_toolbar(self, parent: Any) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)

        title_wrap = ctk.CTkFrame(bar, fg_color="transparent")
        title_wrap.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_wrap,
            text="Results",
            font=font_ui(15, "bold"),
            text_color=Palette.TEXT,
        ).pack(side="left")
        self.results_count_label = ctk.CTkLabel(
            title_wrap,
            text="0 found",
            font=font_ui(11),
            text_color=Palette.TEXT_FAINT,
        )
        self.results_count_label.pack(side="left", padx=(10, 0))

        controls = ctk.CTkFrame(bar, fg_color="transparent")
        controls.grid(row=0, column=2, sticky="e")

        self.search_var = tk.StringVar(value="")
        search_entry = ctk.CTkEntry(
            controls,
            placeholder_text="Filter by path\u2026",
            width=180,
            height=30,
            fg_color=Palette.SURFACE_ALT,
            border_color=Palette.BORDER,
            border_width=1,
            text_color=Palette.TEXT,
            placeholder_text_color=Palette.TEXT_FAINT,
            corner_radius=7,
            textvariable=self.search_var,
        )
        search_entry.pack(side="left", padx=(0, 8))
        self.search_var.trace_add("write", lambda *_: self._apply_filters())

        self.status_filter_var = tk.StringVar(value="All")
        ctk.CTkSegmentedButton(
            controls,
            values=["All", "2xx", "3xx", "4xx", "5xx"],
            variable=self.status_filter_var,
            command=lambda _v: self._apply_filters(),
            height=30,
            corner_radius=7,
            fg_color=Palette.SURFACE_ALT,
            selected_color=Palette.ACCENT,
            selected_hover_color=Palette.ACCENT_HOVER,
            unselected_color=Palette.SURFACE_ALT,
            unselected_hover_color=Palette.BORDER,
            text_color=Palette.TEXT_DIM,
            font=font_ui(11),
        ).pack(side="left")

    def _build_results_header(self, parent: Any) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=3, column=0, sticky="ew", pady=(0, 2))
        header.grid_columnconfigure(1, weight=1)

        def col(text: str, c: int, width: int, anchor: str, pad: tuple) -> None:
            ctk.CTkLabel(
                header,
                text=text,
                width=width,
                anchor=anchor,
                font=font_ui(11, "bold"),
                text_color=Palette.TEXT_FAINT,
            ).grid(row=0, column=c, padx=pad, sticky=anchor)

        col("Status", 0, 46, "w", (10, 12))
        col("Path", 1, 0, "w", (0, 0))
        col("Size", 2, 72, "e", (6, 6))
        col("Type", 3, 150, "w", (0, 10))

    def _build_results_body(self, parent: Any) -> None:
        self.results_frame = ctk.CTkScrollableFrame(
            parent,
            fg_color=Palette.SURFACE,
            corner_radius=10,
            border_width=1,
            border_color=Palette.BORDER,
        )
        self.results_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 18))
        self.results_frame.grid_columnconfigure(0, weight=1)

        self.results_placeholder = ctk.CTkLabel(
            self.results_frame,
            text="No results yet \u2014 start a scan to see discovered paths here.",
            font=font_ui(12),
            text_color=Palette.TEXT_FAINT,
            anchor="w",
        )
        self.results_placeholder.grid(row=0, column=0, sticky="w", padx=10, pady=16)

    def _build_log_panel(self, parent: Any) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            bar, text="Activity log", font=font_ui(15, "bold"), text_color=Palette.TEXT
        ).grid(row=0, column=0, sticky="w")

        btns = ctk.CTkFrame(bar, fg_color="transparent")
        btns.grid(row=0, column=1, sticky="e")
        self.copy_log_btn = ctk.CTkButton(
            btns,
            text="Copy",
            width=64,
            height=28,
            corner_radius=7,
            fg_color=Palette.SURFACE_ALT,
            hover_color=Palette.BORDER,
            text_color=Palette.TEXT_DIM,
            border_width=1,
            border_color=Palette.BORDER,
            font=font_ui(11),
            command=self._copy_log,
        )
        self.copy_log_btn.pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btns,
            text="Clear",
            width=64,
            height=28,
            corner_radius=7,
            fg_color=Palette.SURFACE_ALT,
            hover_color=Palette.BORDER,
            text_color=Palette.TEXT_DIM,
            border_width=1,
            border_color=Palette.BORDER,
            font=font_ui(11),
            command=self._clear_log,
        ).pack(side="left")

        self.log_box = ctk.CTkTextbox(
            parent,
            fg_color=Palette.SURFACE,
            border_width=1,
            border_color=Palette.BORDER,
            text_color=Palette.TEXT_DIM,
            corner_radius=10,
            font=font_mono(11),
        )
        self.log_box.grid(row=6, column=0, sticky="nsew")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Log panel actions
    # ------------------------------------------------------------------
    def _copy_log(self) -> None:
        text = self.log_box.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.copy_log_btn.configure(text="Copied")
        self.after(1200, lambda: self.copy_log_btn.configure(text="Copy"))

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Scan configuration collection
    # ------------------------------------------------------------------
    def _collect_cli_values(self) -> dict[str, Any]:
        header_strings = [
            h for row in self.header_rows if (h := row.as_header_string())
        ]

        def as_int(text: str) -> Optional[int]:
            return int(text) if text else None

        def as_float(text: str) -> Optional[float]:
            return float(text) if text else None

        status_codes = parse_status_argument(self.status_field.get() or None)
        exclude_status = parse_status_argument(self.exclude_status_field.get() or None)
        extensions = parse_extension_argument(self.extensions_field.get() or None)
        headers = parse_header_arguments(header_strings or None)

        values: dict[str, Any] = {
            "target_url": self.url_field.get() or None,
            "wordlist_path": self.wordlist_field.get() or None,
            "threads": as_int(self.threads_field.get()),
            "timeout": as_float(self.timeout_field.get()),
            "extensions": extensions,
            "status_codes": status_codes,
            "exclude_status": exclude_status,
            "output_path": self.output_field.get() or None,
            "recursive": self.recursive_var.get() or None,
            "depth": as_int(self.depth_field.get()),
            "user_agent": self.user_agent_field.get() or None,
            "headers": headers,
            "log_level": self.log_level_var.get(),
            "delay": as_float(self.delay_field.get()),
            "follow_redirects": self.follow_redirects_var.get(),
        }
        return values

    # ------------------------------------------------------------------
    # Scan lifecycle
    # ------------------------------------------------------------------
    def start_scan(self) -> None:
        if self.is_scanning:
            return

        try:
            cli_values = self._collect_cli_values()
            config_path = self.config_field.get() or None
            config_values = load_config_file(config_path)
            config = build_scan_config(cli_values, config_values)
        except ConfigurationError as exc:
            self._flag_missing_fields()
            messagebox.showerror("Configuration error", str(exc))
            return
        except PathCrawlerError as exc:
            messagebox.showerror("Error", str(exc))
            return
        except Exception as exc:  # unexpected parsing issue
            messagebox.showerror("Error", f"Unexpected error: {exc}")
            return

        self._reset_results()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.last_results = []
        self._update_stat_values(found=0, requests=0, errors=0, elapsed="0s")

        setup_logging(config.log_level)
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        self._active_log_handler = handler

        self.is_scanning = True
        self._scan_start_time = time.time()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_dot.configure(text_color=Palette.INFO)
        self.status_label.configure(text="Scanning\u2026")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self._tick_elapsed()

        self.scanner = PathCrawlerScanner(config)
        self.scan_thread = threading.Thread(
            target=self._run_scan_thread, args=(config,), daemon=True
        )
        self.scan_thread.start()

    def _flag_missing_fields(self) -> None:
        if not self.url_field.get():
            self.url_field.flash_error()
        if not self.wordlist_field.get():
            self.wordlist_field.flash_error()

    def _reset_results(self) -> None:
        for row in self.result_rows:
            row.destroy()
        self.result_rows = []
        self._result_row_index = 0
        self.results_placeholder.configure(
            text="No results yet \u2014 start a scan to see discovered paths here."
        )
        self.results_placeholder.grid()
        self.status_filter_var.set("All")
        self.search_var.set("")
        self._update_results_count(0)

    def _run_scan_thread(self, config: Any) -> None:
        try:
            results, stats, wordlist_stats, _baseline = self.scanner.scan()
            self.log_queue.put(("done", (config, results, stats, wordlist_stats)))
        except PathCrawlerError as exc:
            self.log_queue.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001
            logging.debug("Unexpected error", exc_info=True)
            self.log_queue.put(("error", f"Unexpected error: {exc}"))

    def stop_scan(self) -> None:
        stopper = getattr(self.scanner, "stop", None)
        if callable(stopper):
            stopper()
        self.status_label.configure(text="Stopping\u2026")

    def _finish_scan(self) -> None:
        self.is_scanning = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1)
        if hasattr(self, "_active_log_handler"):
            logging.getLogger().removeHandler(self._active_log_handler)

    def _tick_elapsed(self) -> None:
        if not self.is_scanning or self._scan_start_time is None:
            return
        elapsed = time.time() - self._scan_start_time
        self.stat_elapsed_val.configure(text=format_elapsed(elapsed))
        self.after(1000, self._tick_elapsed)

    # ------------------------------------------------------------------
    # Queue polling (runs on main thread)
    # ------------------------------------------------------------------
    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "result":
                    self._append_result(payload)
                elif kind == "done":
                    config, results, stats, wordlist_stats = payload
                    self.last_results = results
                    self.last_stats = stats
                    self.last_wordlist_stats = wordlist_stats
                    for r in results:
                        self._append_result(r)
                    self._apply_stats(stats)
                    report_path = None
                    if config.output_path:
                        try:
                            report_path = write_report(
                                config.output_path,
                                config,
                                stats,
                                results,
                                wordlist_stats,
                            )
                            self._append_log(f"Report written to {report_path}")
                        except Exception as exc:  # noqa: BLE001
                            self._append_log(f"Failed to write report: {exc}")
                    self.status_dot.configure(text_color=Palette.SUCCESS)
                    self.status_label.configure(text="Scan complete")
                    self._finish_scan()
                elif kind == "error":
                    self.status_dot.configure(text_color=Palette.STOP)
                    self.status_label.configure(text="Error")
                    self._append_log(f"[ERROR] {payload}")
                    messagebox.showerror("Scan error", str(payload))
                    self._finish_scan()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _append_log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Results table
    # ------------------------------------------------------------------
    def _append_result(self, result: Any) -> None:
        status = getattr(result, "status_code", getattr(result, "status", ""))
        path = getattr(result, "path", getattr(result, "url", str(result)))
        size = getattr(result, "size", getattr(result, "content_length", ""))
        content_type = getattr(result, "content_type", "")

        alt = len(self.result_rows) % 2 == 1
        row = ResultRow(self.results_frame, status, path, size, content_type, alt)
        row.grid(row=self._result_row_index, column=0, sticky="ew", padx=2, pady=1)
        self._result_row_index += 1
        self.result_rows.append(row)

        if len(self.result_rows) == 1:
            self.results_placeholder.grid_remove()

        if row.matches(self.status_filter_var.get(), self.search_var.get()):
            self._update_results_count(self._visible_count())
        else:
            row.grid_remove()
            self._update_results_count(self._visible_count())

    def _visible_count(self) -> int:
        return sum(1 for r in self.result_rows if r.grid_info())

    def _apply_filters(self) -> None:
        status_filter = self.status_filter_var.get()
        search = self.search_var.get()
        visible = 0
        for row in self.result_rows:
            if row.matches(status_filter, search):
                row.grid()
                visible += 1
            else:
                row.grid_remove()

        if not self.result_rows:
            self.results_placeholder.configure(
                text="No results yet \u2014 start a scan to see discovered paths here."
            )
            self.results_placeholder.grid()
        elif visible == 0:
            self.results_placeholder.configure(
                text="No results match the current filter."
            )
            self.results_placeholder.grid()
        else:
            self.results_placeholder.grid_remove()

        self._update_results_count(visible)

    def _update_results_count(self, visible: int) -> None:
        total = len(self.result_rows)
        if total and visible != total:
            self.results_count_label.configure(text=f"{visible} of {total} found")
        else:
            self.results_count_label.configure(text=f"{total} found")

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    def _update_stat_values(
        self, found: int, requests: int, errors: int, elapsed: str
    ) -> None:
        self.stat_found_val.configure(text=str(found))
        self.stat_requests_val.configure(text=str(requests))
        self.stat_errors_val.configure(text=str(errors))
        self.stat_elapsed_val.configure(text=str(elapsed))

    def _apply_stats(self, stats: Any) -> None:
        fallback_elapsed = (
            format_elapsed(time.time() - self._scan_start_time)
            if self._scan_start_time
            else "0s"
        )
        found = getattr(
            stats, "found_count", getattr(stats, "found", len(self.last_results))
        )
        requests = getattr(stats, "requests_made", getattr(stats, "total_requests", ""))
        errors = getattr(stats, "errors", getattr(stats, "error_count", 0))
        elapsed = getattr(
            stats, "elapsed", getattr(stats, "duration", fallback_elapsed)
        )
        self._update_stat_values(
            found=found, requests=requests, errors=errors, elapsed=elapsed
        )
        self._update_results_count(self._visible_count())


def main() -> int:
    app = PathCrawlerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
