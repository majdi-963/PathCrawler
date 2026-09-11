"""Graphical interface for PathCrawler, built with CustomTkinter.

This provides the same functionality as cli.py (pathcrawler's command-line
interface) through a modern desktop UI. It calls into the same
`pathcrawler` package (config, scanner, reporter, models, errors, logger)
so behavior and validation stay identical to the CLI tool.

Run with:
    python gui.py
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, Optional

import customtkinter as ctk # pyright: ignore[reportMissingImports]



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


class LabeledEntry(ctk.CTkFrame):
    """A labeled entry field, optionally with a browse button."""

    def __init__(
        self,
        master: Any,
        label: str,
        placeholder: str = "",
        browse: Optional[str] = None,  # "file" | "save" | None
        show: Optional[str] = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)

        self.label = ctk.CTkLabel(
            self, text=label, anchor="w", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.entry = ctk.CTkEntry(
            self, placeholder_text=placeholder, height=34, show=show or ""
        )
        self.entry.grid(row=1, column=0, sticky="ew")

        if browse:
            self.browse_btn = ctk.CTkButton(
                self,
                text="Browse",
                width=80,
                height=34,
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
            self.entry.delete(0, "end")
            self.entry.insert(0, path)

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, value: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, value)


class HeaderRow(ctk.CTkFrame):
    """One 'Name: value' custom-header row with a remove button."""

    def __init__(self, master: Any, on_remove) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.name_entry = ctk.CTkEntry(self, placeholder_text="Header name", height=30)
        self.name_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.value_entry = ctk.CTkEntry(
            self, placeholder_text="Header value", height=30
        )
        self.value_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        self.grid_columnconfigure(1, weight=1)
        remove_btn = ctk.CTkButton(
            self,
            text="✕",
            width=30,
            height=30,
            fg_color="transparent",
            border_width=1,
            command=lambda: on_remove(self),
        )
        remove_btn.grid(row=0, column=2)

    def as_header_string(self) -> Optional[str]:
        name = self.name_entry.get().strip()
        value = self.value_entry.get().strip()
        if not name:
            return None
        return f"{name}: {value}"


class PathCrawlerApp(ctk.CTk):
    STATUS_COLORS = {
        "2": "#3fb950",
        "3": "#d29922",
        "4": "#f85149",
        "5": "#a371f7",
    }

    def __init__(self) -> None:
        super().__init__()
        self.title(f"PathCrawler {VERSION}")
        self.geometry("1180x760")
        self.minsize(980, 640)

        self.log_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue()
        self.scan_thread: Optional[threading.Thread] = None
        self.is_scanning = False
        self.last_results: list[Any] = []
        self.last_stats: Any = None
        self.last_wordlist_stats: Any = None
        self.header_rows: list[HeaderRow] = []

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

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkScrollableFrame(self, width=360, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            sidebar,
            text="PathCrawler",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w", padx=16, pady=(20, 0))

        version_lbl = ctk.CTkLabel(
            sidebar, text=f"v{VERSION}", text_color="gray60"
        )
        version_lbl.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        notice = ctk.CTkLabel(
            sidebar,
            text=ETHICAL_NOTICE,
            wraplength=320,
            justify="left",
            font=ctk.CTkFont(size=11),
            text_color="#d29922",
        )
        notice.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))

        row = 3

        def section(text: str) -> int:
            nonlocal row
            lbl = ctk.CTkLabel(
                sidebar,
                text=text,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#8ab4f8",
            )
            lbl.grid(row=row, column=0, sticky="w", padx=16, pady=(14, 4))
            row += 1
            return row

        # --- Target section ---
        section("TARGET")
        self.url_field = LabeledEntry(
            sidebar, "Target URL", placeholder="http://127.0.0.1:8000"
        )
        self.url_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        self.wordlist_field = LabeledEntry(
            sidebar, "Wordlist", placeholder="wordlists/common.txt", browse="file"
        )
        self.wordlist_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        self.config_field = LabeledEntry(
            sidebar, "Config file (optional)", browse="config"
        )
        self.config_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        # --- Request options ---
        section("REQUEST OPTIONS")
        opts_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        opts_frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        opts_frame.grid_columnconfigure((0, 1), weight=1)
        row += 1

        self.threads_field = LabeledEntry(opts_frame, "Threads", placeholder="10")
        self.threads_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.timeout_field = LabeledEntry(opts_frame, "Timeout (s)", placeholder="5")
        self.timeout_field.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.extensions_field = LabeledEntry(
            sidebar, "Extensions", placeholder="php,html,txt,bak"
        )
        self.extensions_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        status_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        status_frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        status_frame.grid_columnconfigure((0, 1), weight=1)
        row += 1
        self.status_field = LabeledEntry(
            status_frame, "Include status", placeholder="200,301,302,403"
        )
        self.status_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.exclude_status_field = LabeledEntry(
            status_frame, "Exclude status", placeholder="404"
        )
        self.exclude_status_field.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.user_agent_field = LabeledEntry(sidebar, "User-Agent (optional)")
        self.user_agent_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        # --- Custom headers ---
        section("CUSTOM HEADERS")
        self.headers_container = ctk.CTkFrame(sidebar, fg_color="transparent")
        self.headers_container.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        self.headers_container.grid_columnconfigure(0, weight=1)
        row += 1

        add_header_btn = ctk.CTkButton(
            sidebar, text="+ Add header", height=28, command=self._add_header_row
        )
        add_header_btn.grid(row=row, column=0, sticky="w", padx=16, pady=(0, 4))
        row += 1

        # --- Recursion ---
        section("RECURSION")
        rec_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        rec_frame.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        rec_frame.grid_columnconfigure(1, weight=1)
        row += 1

        self.recursive_var = tk.BooleanVar(value=False)
        recursive_switch = ctk.CTkSwitch(
            rec_frame, text="Recursive scan", variable=self.recursive_var
        )
        recursive_switch.grid(row=0, column=0, sticky="w")

        self.depth_field = LabeledEntry(sidebar, "Max depth", placeholder="1")
        self.depth_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        # --- Behavior ---
        section("BEHAVIOR")
        self.follow_redirects_var = tk.BooleanVar(value=True)
        follow_switch = ctk.CTkSwitch(
            sidebar,
            text="Follow redirects",
            variable=self.follow_redirects_var,
        )
        follow_switch.grid(row=row, column=0, sticky="w", padx=16, pady=4)
        row += 1

        self.delay_field = LabeledEntry(
            sidebar, "Delay between requests (s)", placeholder="0"
        )
        self.delay_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        self.log_level_menu_label = ctk.CTkLabel(
            sidebar, text="Log level", anchor="w", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.log_level_menu_label.grid(row=row, column=0, sticky="w", padx=16, pady=(8, 2))
        row += 1
        self.log_level_var = tk.StringVar(value="INFO")
        log_level_menu = ctk.CTkOptionMenu(
            sidebar,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            variable=self.log_level_var,
        )
        log_level_menu.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 4))
        row += 1

        # --- Output ---
        section("OUTPUT")
        self.output_field = LabeledEntry(
            sidebar, "Report path (optional)", browse="save"
        )
        self.output_field.grid(row=row, column=0, sticky="ew", padx=16, pady=4)
        row += 1

        # --- Actions ---
        action_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        action_frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(16, 24))
        action_frame.grid_columnconfigure((0, 1), weight=1)
        row += 1

        self.start_btn = ctk.CTkButton(
            action_frame,
            text="▶  Start Scan",
            height=40,
            fg_color="#2f9e44",
            hover_color="#268040",
            command=self.start_scan,
        )
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            action_frame,
            text="■  Stop",
            height=40,
            fg_color="#c92a2a",
            hover_color="#a61e1e",
            state="disabled",
            command=self.stop_scan,
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

    def _build_main_panel(self) -> None:
        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=(4, 12), pady=12)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        main.grid_rowconfigure(4, weight=1)

        # Status bar
        status_bar = ctk.CTkFrame(main, height=48)
        status_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_bar.grid_columnconfigure(1, weight=1)

        self.status_dot = ctk.CTkLabel(
            status_bar, text="●", text_color="gray50", font=ctk.CTkFont(size=18)
        )
        self.status_dot.grid(row=0, column=0, padx=(14, 4), pady=8)
        self.status_label = ctk.CTkLabel(
            status_bar, text="Idle", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.status_label.grid(row=0, column=1, sticky="w", pady=8)

        self.progress_bar = ctk.CTkProgressBar(status_bar, mode="indeterminate")
        self.progress_bar.grid(row=0, column=2, sticky="e", padx=14, pady=8)
        self.progress_bar.set(0)

        # Stat cards
        stats_frame = ctk.CTkFrame(main, fg_color="transparent")
        stats_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        stats_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_found_val, _ = self._make_stat_card(stats_frame, 0, "Found")
        self.stat_requests_val, _ = self._make_stat_card(stats_frame, 1, "Requests")
        self.stat_errors_val, _ = self._make_stat_card(stats_frame, 2, "Errors")
        self.stat_elapsed_val, _ = self._make_stat_card(stats_frame, 3, "Elapsed")

        # Results table (as a scrollable frame of rows)
        results_label = ctk.CTkLabel(
            main, text="Results", font=ctk.CTkFont(size=14, weight="bold")
        )
        results_label.grid(row=2, column=0, sticky="nw")

        self.results_frame = ctk.CTkScrollableFrame(main)
        self.results_frame.grid(row=3, column=0, sticky="nsew", pady=(4, 10))
        self.results_frame.grid_columnconfigure(0, weight=0)
        self.results_frame.grid_columnconfigure(1, weight=1)
        self.results_frame.grid_columnconfigure(2, weight=0)
        self.results_frame.grid_columnconfigure(3, weight=0)
        self._add_results_header()
        self._result_row_index = 1

        # Log console
        log_label = ctk.CTkLabel(
            main, text="Log", font=ctk.CTkFont(size=14, weight="bold")
        )
        log_label.grid(row=4, column=0, sticky="nw")

        self.log_box = ctk.CTkTextbox(main, height=160, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.grid(row=5, column=0, sticky="nsew", pady=(4, 0))
        self.log_box.configure(state="disabled")

        main.grid_rowconfigure(3, weight=2)
        main.grid_rowconfigure(5, weight=1)

    def _make_stat_card(self, parent: Any, col: int, label: str):
        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=0, column=col, sticky="ew", padx=6)
        val = ctk.CTkLabel(card, text="0", font=ctk.CTkFont(size=22, weight="bold"))
        val.pack(pady=(12, 0))
        lbl = ctk.CTkLabel(card, text=label, text_color="gray60", font=ctk.CTkFont(size=12))
        lbl.pack(pady=(0, 12))
        return val, lbl

    def _add_results_header(self) -> None:
        headers = ["Status", "Path", "Size", "Type"]
        for i, h in enumerate(headers):
            lbl = ctk.CTkLabel(
                self.results_frame,
                text=h,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="gray60",
            )
            lbl.grid(row=0, column=i, sticky="w", padx=10, pady=(0, 6))

    # ------------------------------------------------------------------
    # Header rows
    # ------------------------------------------------------------------
    def _add_header_row(self) -> None:
        row = HeaderRow(self.headers_container, self._remove_header_row)
        row.grid(sticky="ew", pady=2)
        self.header_rows.append(row)

    def _remove_header_row(self, row: HeaderRow) -> None:
        row.destroy()
        self.header_rows.remove(row)

    # ------------------------------------------------------------------
    # Scan lifecycle
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

    def start_scan(self) -> None:
        if self.is_scanning:
            return

        try:
            cli_values = self._collect_cli_values()
            config_path = self.config_field.get() or None
            config_values = load_config_file(config_path)
            config = build_scan_config(cli_values, config_values)
        except ConfigurationError as exc:
            messagebox.showerror("Configuration error", str(exc))
            return
        except PathCrawlerError as exc:
            messagebox.showerror("Error", str(exc))
            return
        except Exception as exc:  # unexpected parsing issue
            messagebox.showerror("Error", f"Unexpected error: {exc}")
            return

        # Reset UI state
        for widget in self.results_frame.winfo_children():
            widget.destroy()
        self._add_results_header()
        self._result_row_index = 1
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.last_results = []
        self._update_stat_cards(found=0, requests=0, errors=0, elapsed="0s")

        setup_logging(config.log_level)
        handler = QueueLogHandler(self.log_queue)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        self._active_log_handler = handler

        self.is_scanning = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_dot.configure(text_color="#d29922")
        self.status_label.configure(text="Scanning…")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()

        self.scanner = PathCrawlerScanner(config)
        self.scan_thread = threading.Thread(
            target=self._run_scan_thread, args=(config,), daemon=True
        )
        self.scan_thread.start()

    def _run_scan_thread(self, config: Any) -> None:
        try:
            results, stats, wordlist_stats, _baseline = self.scanner.scan()
            self.log_queue.put(
                ("done", (config, results, stats, wordlist_stats))
            )
        except PathCrawlerError as exc:
            self.log_queue.put(("error", str(exc)))
        except Exception as exc:  # noqa: BLE001
            logging.debug("Unexpected error", exc_info=True)
            self.log_queue.put(("error", f"Unexpected error: {exc}"))

    def stop_scan(self) -> None:
        stopper = getattr(self.scanner, "stop", None)
        if callable(stopper):
            stopper()
        self.status_label.configure(text="Stopping…")

    def _finish_scan(self) -> None:
        self.is_scanning = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(1)
        if hasattr(self, "_active_log_handler"):
            logging.getLogger().removeHandler(self._active_log_handler)

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
                    self.status_dot.configure(text_color="#3fb950")
                    self.status_label.configure(text="Scan complete")
                    self._finish_scan()
                elif kind == "error":
                    self.status_dot.configure(text_color="#f85149")
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

    def _append_result(self, result: Any) -> None:
        status = getattr(result, "status_code", getattr(result, "status", ""))
        path = getattr(result, "path", getattr(result, "url", str(result)))
        size = getattr(result, "size", getattr(result, "content_length", ""))
        content_type = getattr(result, "content_type", "")

        color = "gray80"
        if status:
            color = self.STATUS_COLORS.get(str(status)[0], "gray80")

        r = self._result_row_index
        self._result_row_index += 1

        ctk.CTkLabel(
            self.results_frame, text=str(status), text_color=color,
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=r, column=0, sticky="w", padx=10, pady=2)
        ctk.CTkLabel(self.results_frame, text=str(path)).grid(
            row=r, column=1, sticky="w", padx=10, pady=2
        )
        ctk.CTkLabel(self.results_frame, text=str(size)).grid(
            row=r, column=2, sticky="w", padx=10, pady=2
        )
        ctk.CTkLabel(self.results_frame, text=str(content_type)).grid(
            row=r, column=3, sticky="w", padx=10, pady=2
        )

    def _update_stat_cards(
        self, found: int, requests: int, errors: int, elapsed: str
    ) -> None:
        self.stat_found_val.configure(text=str(found))
        self.stat_requests_val.configure(text=str(requests))
        self.stat_errors_val.configure(text=str(errors))
        self.stat_elapsed_val.configure(text=str(elapsed))

    def _apply_stats(self, stats: Any) -> None:
        found = getattr(stats, "found_count", getattr(stats, "found", len(self.last_results)))
        requests = getattr(stats, "requests_made", getattr(stats, "total_requests", ""))
        errors = getattr(stats, "errors", getattr(stats, "error_count", 0))
        elapsed = getattr(stats, "elapsed", getattr(stats, "duration", ""))
        self._update_stat_cards(found=found, requests=requests, errors=errors, elapsed=elapsed)


def main() -> int:
    app = PathCrawlerApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
