"""Tkinter interface: the settings window and the results window."""

from __future__ import annotations

import queue
import sys
import tempfile
import threading
import tkinter as tk
import webbrowser
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from allocator import APP_NAME, __version__
from allocator.blockfile import (
    CSV_EXTENSIONS,
    EXCEL_EXTENSIONS,
    BlockFileError,
    find_duplicate_ids,
    load_blocks,
)
from allocator.export import fmt, settings_line, to_clipboard_text, to_csv, to_html
from allocator.logic import DEFAULT_TIME_LIMIT, AllocationResult, allocate
from allocator.settings import (
    MAX_BLOCK_LIMIT,
    NO_LIMIT,
    InputError,
    Settings,
    load_settings,
    parse_capacity,
    parse_container_count,
    parse_max_blocks,
    save_settings,
)


class Theme:
    BACKGROUND = "#f5f0e1"  # warm cream, the app's original background
    CARD = "#ffffff"
    BORDER = "#d8d2c2"
    TEXT = "#1f2328"
    MUTED = "#6b6455"
    HEADER = "#3a7ca5"  # container headings
    WEIGHT = "#2c666e"  # totals
    WARNING = "#9a6700"
    NOTE_BG = "#fff4cc"
    FONT = "Segoe UI" if sys.platform == "win32" else "Helvetica"
    MONO = "Consolas" if sys.platform == "win32" else ("Menlo" if sys.platform == "darwin" else "Courier")


def resource_path(relative: str) -> Path:
    """Locate a bundled file both from source and inside a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def _set_window_icon(window: tk.Tk | tk.Toplevel) -> None:
    icon = resource_path("assets/icon.png")
    if not icon.exists():
        return
    try:
        image = tk.PhotoImage(file=str(icon))
        window.iconphoto(True, image)
        window._icon_image = image  # type: ignore[union-attr]  # keep a reference
    except tk.TclError:
        pass


def _bind_mousewheel(area: tk.Widget, canvas: tk.Canvas) -> None:
    """Scroll `canvas` with the wheel or trackpad while the pointer is over `area`.

    Windows reports multiples of 120, macOS small deltas, and X11 uses
    buttons 4 and 5. Binding only while the pointer is inside keeps several
    scrollable windows from fighting over the wheel."""

    def scroll(event: tk.Event) -> None:
        if canvas.yview() == (0.0, 1.0):
            return
        if event.num == 4:
            steps = -1
        elif event.num == 5:
            steps = 1
        elif abs(event.delta) >= 120:  # Windows, and Tk 9 everywhere
            steps = -int(event.delta / 120)
        else:  # older Tk on macOS reports small deltas
            steps = -event.delta
        if steps:
            canvas.yview_scroll(steps, "units")

    def enter(_event: tk.Event) -> None:
        canvas.bind_all("<MouseWheel>", scroll)
        canvas.bind_all("<Button-4>", scroll)
        canvas.bind_all("<Button-5>", scroll)

    def leave(_event: tk.Event) -> None:
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    area.bind("<Enter>", enter, add="+")
    area.bind("<Leave>", leave, add="+")


def _configure_styles(root: tk.Misc) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    base = (Theme.FONT, 11)
    style.configure(".", font=base, background=Theme.BACKGROUND, foreground=Theme.TEXT)
    style.configure("TFrame", background=Theme.BACKGROUND)
    style.configure("TLabel", background=Theme.BACKGROUND)
    style.configure("TCheckbutton", background=Theme.BACKGROUND)
    style.map("TCheckbutton", background=[("active", Theme.BACKGROUND)])
    style.configure("TButton", padding=(12, 6))
    style.configure(
        "Accent.TButton",
        font=(Theme.FONT, 11, "bold"),
        padding=(18, 8),
        background=Theme.WEIGHT,
        foreground="#ffffff",
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", "#9bb5b8"), ("active", "#24555b")],
        foreground=[("disabled", "#eef3f3")],
    )
    style.configure("Muted.TLabel", foreground=Theme.MUTED, font=(Theme.FONT, 10))
    style.configure("Title.TLabel", font=(Theme.FONT, 15, "bold"))
    style.configure("Field.TLabel", font=(Theme.FONT, 11))
    style.configure(
        "File.TLabel",
        background=Theme.CARD,
        relief="solid",
        borderwidth=1,
        padding=(8, 5),
        foreground=Theme.TEXT,
    )
    style.configure("Card.TFrame", background=Theme.CARD, relief="solid", borderwidth=1)
    style.configure("Card.TLabel", background=Theme.CARD)
    style.configure(
        "CardTitle.TLabel", background=Theme.CARD, foreground=Theme.HEADER, font=(Theme.FONT, 12, "bold")
    )
    style.configure(
        "CardWarn.TLabel", background=Theme.CARD, foreground=Theme.WARNING, font=(Theme.FONT, 12, "bold")
    )
    style.configure(
        "CardTotal.TLabel", background=Theme.CARD, foreground=Theme.WEIGHT, font=(Theme.FONT, 12, "bold")
    )
    style.configure("CardMuted.TLabel", background=Theme.CARD, foreground=Theme.MUTED, font=(Theme.FONT, 10))
    style.configure(
        "Note.TLabel", background=Theme.NOTE_BG, foreground=Theme.TEXT, padding=(10, 6), font=(Theme.FONT, 10)
    )
    style.configure(
        "Fill.Horizontal.TProgressbar",
        troughcolor="#eceae4",
        background=Theme.WEIGHT,
        bordercolor=Theme.CARD,
        lightcolor=Theme.WEIGHT,
        darkcolor=Theme.WEIGHT,
    )
    style.configure("TCombobox", fieldbackground="#ffffff")
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", "#ffffff")],
        selectbackground=[("readonly", "#ffffff")],
        selectforeground=[("readonly", Theme.TEXT)],
    )


# --------------------------------------------------------------------------
# Settings window
# --------------------------------------------------------------------------


class BlockAllocatorGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {__version__}")
        self.configure(background=Theme.BACKGROUND)
        self.resizable(False, False)
        _set_window_icon(self)
        _configure_styles(self)

        self.settings = load_settings()
        self.results_window: ResultsWindow | None = None
        self._worker_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._busy = False

        self.file_var = tk.StringVar()
        self.count_var = tk.StringVar(value=self.settings.container_count)
        self.capacity_var = tk.StringVar(value=self.settings.capacity)
        self.max_blocks_var = tk.StringVar(value=self.settings.max_blocks)
        self.balance_var = tk.BooleanVar(value=self.settings.balance)
        self.status_var = tk.StringVar()
        self.csv_path: str | None = None
        if self.settings.last_file and Path(self.settings.last_file).exists():
            self._set_file(self.settings.last_file)

        self._build()
        self.bind("<Return>", lambda _e: self.run_allocation())
        self.bind("<KP_Enter>", lambda _e: self.run_allocation())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- layout -------------------------------------------------------------

    def _build(self) -> None:
        main = ttk.Frame(self, padding=(24, 20, 24, 18))
        main.grid(sticky="nsew")
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Plan a container load", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            main, text="Choose a block list, set the container limits, then run.", style="Muted.TLabel"
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))

        # Block list
        ttk.Label(main, text="Block list", style="Field.TLabel").grid(row=2, column=0, sticky="w", pady=6)
        self.file_label = ttk.Label(main, textvariable=self.file_var, style="File.TLabel", width=34)
        self.file_label.grid(row=2, column=1, sticky="ew", padx=(12, 8))
        self.browse_button = ttk.Button(main, text="Browse…", command=self.browse_csv)
        self.browse_button.grid(row=2, column=2, sticky="e")
        ttk.Label(
            main,
            text="CSV or Excel with BlockNo and Weight columns (capitals and spaces don't matter).",
            style="Muted.TLabel",
            wraplength=420,
        ).grid(row=3, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=(0, 10))

        # Numbers
        ttk.Label(main, text="Number of containers", style="Field.TLabel").grid(
            row=4, column=0, sticky="w", pady=6
        )
        self.count_entry = ttk.Spinbox(main, from_=1, to=999, textvariable=self.count_var, width=10)
        self.count_entry.grid(row=4, column=1, sticky="w", padx=12)

        ttk.Label(main, text="Max weight per container", style="Field.TLabel").grid(
            row=5, column=0, sticky="w", pady=6
        )
        self.capacity_entry = ttk.Entry(main, textvariable=self.capacity_var, width=12)
        self.capacity_entry.grid(row=5, column=1, sticky="w", padx=12)

        ttk.Label(main, text="Max blocks per container", style="Field.TLabel").grid(
            row=6, column=0, sticky="w", pady=6
        )
        self.max_blocks_box = ttk.Combobox(
            main,
            textvariable=self.max_blocks_var,
            state="readonly",
            width=10,
            values=[NO_LIMIT] + [str(i) for i in range(1, MAX_BLOCK_LIMIT + 1)],
            height=MAX_BLOCK_LIMIT + 1,
        )
        self.max_blocks_box.grid(row=6, column=1, sticky="w", padx=12)

        self.balance_check = ttk.Checkbutton(
            main, text="Spread the load evenly across containers", variable=self.balance_var
        )
        self.balance_check.grid(row=7, column=1, columnspan=2, sticky="w", padx=12, pady=(8, 0))
        ttk.Label(
            main,
            text="Evens out the container weights instead of filling each one to "
            "the limit in turn. Every block that would be shipped still is.",
            style="Muted.TLabel",
            wraplength=400,
        ).grid(row=8, column=1, columnspan=2, sticky="w", padx=(34, 0))

        ttk.Separator(main).grid(row=9, column=0, columnspan=3, sticky="ew", pady=16)

        bottom = ttk.Frame(main)
        bottom.grid(row=10, column=0, columnspan=3, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        self.run_button = ttk.Button(
            bottom, text="Run allocation", style="Accent.TButton", command=self.run_allocation
        )
        self.run_button.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=160)
        self.status_label = ttk.Label(bottom, textvariable=self.status_var, style="Muted.TLabel")
        self.status_label.grid(row=0, column=2, sticky="e")

    # -- helpers ------------------------------------------------------------

    def _set_file(self, path: str) -> None:
        self.csv_path = path
        self.file_var.set(Path(path).name)

    def _current_settings(self) -> Settings:
        return Settings(
            container_count=self.count_var.get().strip(),
            capacity=self.capacity_var.get().strip(),
            max_blocks=self.max_blocks_var.get(),
            balance=bool(self.balance_var.get()),
            last_file=self.csv_path or "",
            last_dir=str(Path(self.csv_path).parent) if self.csv_path else self.settings.last_dir,
        )

    def _on_close(self) -> None:
        save_settings(self._current_settings())
        self.destroy()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self.run_button,
            self.browse_button,
            self.count_entry,
            self.capacity_entry,
            self.balance_check,
        ):
            widget.configure(state=state)
        self.max_blocks_box.configure(state="disabled" if busy else "readonly")
        self.configure(cursor="watch" if busy else "")
        self.status_var.set(message)
        if busy:
            self.progress.grid(row=0, column=1, sticky="w", padx=12)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()
        self.update_idletasks()

    # -- actions ------------------------------------------------------------

    def browse_csv(self) -> None:
        patterns = " ".join(f"*{e}" for e in CSV_EXTENSIONS + EXCEL_EXTENSIONS)
        initial_dir = self.settings.last_dir if Path(self.settings.last_dir or ".").is_dir() else None
        path = filedialog.askopenfilename(
            parent=self,
            title="Choose a block list",
            initialdir=initial_dir,
            filetypes=[
                ("Block lists", patterns),
                ("CSV files", " ".join(f"*{e}" for e in CSV_EXTENSIONS)),
                ("Excel workbooks", " ".join(f"*{e}" for e in EXCEL_EXTENSIONS)),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._set_file(path)
            self.settings.last_dir = str(Path(path).parent)

    def _read_inputs(self) -> tuple[int, float, int | None] | None:
        checks: list[tuple[Callable[[], object], tk.Widget]] = [
            (lambda: parse_container_count(self.count_var.get()), self.count_entry),
            (lambda: parse_capacity(self.capacity_var.get()), self.capacity_entry),
            (lambda: parse_max_blocks(self.max_blocks_var.get()), self.max_blocks_box),
        ]
        values = []
        for parse, widget in checks:
            try:
                values.append(parse())
            except InputError as exc:
                messagebox.showerror("Check the settings", str(exc), parent=self)
                widget.focus_set()
                return None
        count, capacity, max_blocks = values
        assert isinstance(count, int) and isinstance(capacity, float)
        assert max_blocks is None or isinstance(max_blocks, int)
        return count, capacity, max_blocks

    def run_allocation(self) -> None:
        if self._busy:
            return
        if not self.csv_path:
            messagebox.showerror("No block list", "Choose a block list first (Browse…).", parent=self)
            return
        inputs = self._read_inputs()
        if inputs is None:
            return
        count, capacity, max_blocks = inputs

        self._set_busy(True, "Reading the block list…")
        try:
            blocks = load_blocks(self.csv_path)
        except BlockFileError as exc:
            self._set_busy(False)
            messagebox.showerror("Couldn't read the block list", str(exc), parent=self)
            return
        self._set_busy(False)

        if not blocks:
            messagebox.showerror(
                "No blocks found", f"'{Path(self.csv_path).name}' has no block rows.", parent=self
            )
            return

        duplicates = find_duplicate_ids(blocks)
        if duplicates:
            shown = ", ".join(duplicates[:8]) + ("…" if len(duplicates) > 8 else "")
            if not messagebox.askyesno(
                "Duplicate block numbers",
                f"These block numbers appear more than once in the file:\n{shown}\n\n"
                "Each row will be treated as a separate block, so a number can show up "
                "twice in the results. Continue anyway?",
                icon="warning",
                parent=self,
            ):
                return

        balance = bool(self.balance_var.get())
        source = Path(self.csv_path).name
        save_settings(self._current_settings())
        self._set_busy(True, f"Working out the loading (up to {DEFAULT_TIME_LIMIT:g} s)…")

        def work() -> None:
            try:
                result = allocate(blocks, capacity, count, max_blocks, balance=balance)
                self._worker_queue.put(("ok", result))
            except Exception as exc:  # report anything unexpected to the user
                self._worker_queue.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()
        self.after(100, self._poll_worker, source, count)

    def _poll_worker(self, source: str, count: int) -> None:
        try:
            kind, payload = self._worker_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_worker, source, count)
            return
        self._set_busy(False)
        if kind == "error":
            messagebox.showerror("Allocation failed", f"Something went wrong: {payload}", parent=self)
            return
        assert isinstance(payload, AllocationResult)
        self.show_results(payload, source, count)

    def show_results(self, result: AllocationResult, source: str, count: int) -> None:
        geometry = None
        if self.results_window is not None and self.results_window.winfo_exists():
            geometry = self.results_window.geometry()
            self.results_window.destroy()
        self.results_window = ResultsWindow(self, result, source, count, geometry)


# --------------------------------------------------------------------------
# Results window
# --------------------------------------------------------------------------


class ResultsWindow(tk.Toplevel):
    COLUMNS = 2

    def __init__(
        self,
        master: BlockAllocatorGUI,
        result: AllocationResult,
        source: str,
        count_requested: int,
        geometry: str | None = None,
    ) -> None:
        super().__init__(master)
        self.app = master
        self.result = result
        self.source = source
        self.count_requested = count_requested
        self.title(f"Allocation – {source}")
        self.configure(background=Theme.BACKGROUND)
        self.minsize(560, 400)
        if geometry:
            self.geometry(geometry)
        else:
            scale = max(self.winfo_fpixels("1i") / 96, 1.0)
            self.geometry(f"{int(640 * scale)}x{int(600 * scale)}")

        self._build_header()
        self._build_cards()
        self.bind("<Control-c>", lambda _e: self.copy())
        self.bind("<Command-c>" if sys.platform == "darwin" else "<Control-C>", lambda _e: self.copy())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _build_header(self) -> None:
        r = self.result
        head = ttk.Frame(self, padding=(16, 14, 16, 6))
        head.pack(fill="x")
        head.columnconfigure(0, weight=1)
        n_total = r.placed_count + len(r.unplaced)
        n_containers = len(r.containers)
        stats = [
            f"{n_containers} container{'s' if n_containers != 1 else ''}",
            f"{fmt(r.placed_weight)} loaded",
        ]
        if r.containers:
            stats.append(f"{r.utilisation:.1%} of capacity used")
        wrapping: list[ttk.Label] = [
            ttk.Label(head, text=f"{r.placed_count} of {n_total} blocks placed", style="Title.TLabel"),
            ttk.Label(head, text=" · ".join(stats), style="Field.TLabel"),
            ttk.Label(
                head, text=f"{self.source} · {settings_line(r, self.count_requested)}", style="Muted.TLabel"
            ),
        ]
        for i, label in enumerate(wrapping):
            label.grid(row=i, column=0, sticky="w", pady=(2 if i else 0, 0))

        notes = list(r.notes)
        if len(r.containers) < self.count_requested and r.unplaced:
            notes.append(
                f"Only {len(r.containers)} of {self.count_requested} containers could be filled: "
                "none of the remaining blocks fit within the limits."
            )
        elif len(r.containers) < self.count_requested and not r.balanced:
            notes.append(f"All blocks fit in {len(r.containers)} of the {self.count_requested} containers.")
        for note in notes:
            label = ttk.Label(head, text=note, style="Note.TLabel")
            label.grid(sticky="ew", pady=(8, 0))
            wrapping.append(label)

        # Re-wrap text to the window width as it's resized.
        def rewrap(event: tk.Event) -> None:
            for label in wrapping:
                label.configure(wraplength=max(event.width - 40, 200))

        head.bind("<Configure>", rewrap)

        bar = ttk.Frame(self, padding=(16, 4, 16, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="Copy", command=self.copy).pack(side="left")
        ttk.Button(bar, text="Save as CSV…", command=self.save_csv).pack(side="left", padx=8)
        ttk.Button(bar, text="Print loading sheet…", command=self.print_sheet).pack(side="left")
        self.feedback = tk.StringVar()
        ttk.Label(bar, textvariable=self.feedback, style="Muted.TLabel").pack(side="right")

    def _build_cards(self) -> None:
        outer = ttk.Frame(self, padding=(10, 0, 0, 10))
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0, background=Theme.BACKGROUND)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        grid = ttk.Frame(canvas, padding=(6, 0, 6, 0))
        window = canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        _bind_mousewheel(outer, canvas)

        for col in range(self.COLUMNS):
            grid.columnconfigure(col, weight=1, uniform="cards")

        r = self.result
        for idx, (blocks, total) in enumerate(zip(r.containers, r.container_totals, strict=True)):
            row, col = divmod(idx, self.COLUMNS)
            self._container_card(grid, idx + 1, blocks, total).grid(
                row=row, column=col, sticky="nsew", padx=6, pady=6
            )

        if r.unplaced:
            row = (len(r.containers) + self.COLUMNS - 1) // self.COLUMNS
            self._unplaced_card(grid).grid(
                row=row, column=0, columnspan=self.COLUMNS, sticky="nsew", padx=6, pady=6
            )
        if not r.containers and not r.unplaced:
            ttk.Label(grid, text="No blocks to allocate.").grid(row=0, column=0, pady=20)

    def _block_text(self, parent: tk.Misc, lines: list[str], height: int) -> tk.Text:
        width = max((len(line) for line in lines), default=10)
        text = tk.Text(
            parent,
            height=height,
            width=width,
            wrap="none",
            relief="flat",
            background=Theme.CARD,
            foreground=Theme.TEXT,
            font=(Theme.MONO, 11),
            padx=2,
            pady=2,
            borderwidth=0,
            highlightthickness=0,
            cursor="arrow",
        )
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        return text

    def _container_card(
        self, parent: tk.Misc, cid: int, blocks: list[tuple[str, float]], total: float
    ) -> ttk.Frame:
        cap = self.result.capacity
        card = ttk.Frame(parent, style="Card.TFrame", padding=(12, 10))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=f"Container {cid}", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=fmt(total), style="CardTotal.TLabel").grid(row=0, column=1, sticky="e")
        fill = total / cap if cap else 0
        ttk.Progressbar(
            card, style="Fill.Horizontal.TProgressbar", maximum=100, value=min(fill * 100, 100)
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Label(
            card,
            text=f"{len(blocks)} block{'s' if len(blocks) != 1 else ''} · {fill:.1%} of {cap:g}",
            style="CardMuted.TLabel",
        ).grid(row=2, column=0, columnspan=2, sticky="w")
        width = max((len(b) for b, _ in blocks), default=4)
        lines = [f"{b:<{width}}  {fmt(w):>8}" for b, w in blocks]
        self._block_text(card, lines, len(lines)).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        return card

    def _unplaced_card(self, parent: tk.Misc) -> ttk.Frame:
        r = self.result
        card = ttk.Frame(parent, style="Card.TFrame", padding=(12, 10))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text="Not placed", style="CardWarn.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=fmt(r.unplaced_weight), style="CardTotal.TLabel").grid(
            row=0, column=1, sticky="e"
        )
        ttk.Label(
            card,
            text=f"{len(r.unplaced)} block{'s' if len(r.unplaced) != 1 else ''} didn't fit within the limits",
            style="CardMuted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w")
        width = max(len(b) for b, _ in r.unplaced)
        entries = [f"{b:<{width}}  {fmt(w):>8}" for b, w in r.unplaced]
        # Lay the list out in columns, filled top to bottom.
        n_cols = self.COLUMNS
        per_col = (len(entries) + n_cols - 1) // n_cols
        lines = [
            "     ".join(
                entries[c * per_col + row] for c in range(n_cols) if c * per_col + row < len(entries)
            )
            for row in range(per_col)
        ]
        self._block_text(card, lines, len(lines)).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )
        return card

    # -- actions ------------------------------------------------------------

    def _flash(self, message: str) -> None:
        self.feedback.set(message)
        self.after(3000, lambda: self.feedback.set("") if self.winfo_exists() else None)

    def copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(to_clipboard_text(self.result))
        self._flash("Copied – paste into Excel or an email")

    def save_csv(self) -> None:
        settings = self.app.settings
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save allocation",
            defaultextension=".csv",
            initialfile=f"{Path(self.source).stem}-allocation.csv",
            initialdir=settings.last_dir or None,
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            to_csv(self.result, path)
        except OSError as exc:
            messagebox.showerror("Couldn't save", f"The file couldn't be saved: {exc.strerror}.", parent=self)
            return
        self._flash(f"Saved {Path(path).name}")

    def print_sheet(self) -> None:
        html = to_html(self.result, self.source, self.count_requested, datetime.now())
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = Path(tempfile.gettempdir()) / f"loading-sheet-{stamp}.html"
        try:
            path.write_text(html, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Couldn't create the sheet", str(exc), parent=self)
            return
        webbrowser.open(path.as_uri())
        self._flash("Opened in your browser for printing")
