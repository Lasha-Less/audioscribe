from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, font as tkfont, ttk

from audioscribe.core.ingest import ingest


# Edit these five values to change the application's color theme.
COLORS = {
    "text": "#e8e5ff",
    "background": "#2d3143",
    "primary": "#d9d6dc",
    "secondary": "#acabb5",
    "accent": "#b3d9ff",
}


def _blend_color(first, second, amount):
    """Derive surface and interaction shades from the five theme colors."""
    channels = []
    for offset in (1, 3, 5):
        first_channel = int(first[offset:offset + 2], 16)
        second_channel = int(second[offset:offset + 2], 16)
        channel = round(first_channel + (second_channel - first_channel) * amount)
        channels.append(f"{channel:02x}")
    return "#" + "".join(channels)


SHADES = {
    "panel": _blend_color(COLORS["background"], COLORS["text"], 0.07),
    "input": _blend_color(COLORS["background"], "#000000", 0.12),
    "border": _blend_color(COLORS["background"], COLORS["secondary"], 0.45),
    "primary_hover": _blend_color(COLORS["primary"], COLORS["accent"], 0.25),
    "primary_disabled": _blend_color(COLORS["background"], COLORS["primary"], 0.5),
    "secondary_hover": _blend_color(COLORS["secondary"], COLORS["primary"], 0.3),
}


def _choose_body_font(root):
    available = {family.casefold(): family for family in tkfont.families(root)}
    for candidate in ("ABeeZee", "Century Gothic", "Trebuchet MS"):
        if candidate.casefold() in available:
            return available[candidate.casefold()]
    return tkfont.nametofont("TkDefaultFont", root=root).actual("family")


class AudioScribeWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.messages = Queue()
        self.busy = False
        self.media_type = tk.StringVar(value="audio")
        self.allow_playlist = tk.BooleanVar(value=False)
        self.output_dir = tk.StringVar(
            value=str(Path.home() / "Downloads" / "AudioScribe")
        )
        self.status = tk.StringVar(value="Ready to download")
        self.progress_detail = tk.StringVar(value="Add your links to get started.")
        self.completed_count = tk.StringVar(value="No items processed yet")
        self.total_items = 0
        self._options_wrapped = False
        self._results_fraction = 0.25
        self._configure_window()
        self._build_window()

    def _configure_window(self):
        self.root.title("AudioScribe")
        self.root.geometry("500x510")
        # Both dimensions are 25% below the previous 660 x 680 minimum.
        self.root.minsize(495, 510)
        self.root.configure(background=COLORS["background"])
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        family = _choose_body_font(self.root)
        self.body_font = ("Segoe UI Semibold", 12)
        self.small_font = ("Segoe UI Semibold", 11)
        families = {name.casefold() for name in tkfont.families(self.root)}
        self.heading_family = ("Segoe UI" if "segoe ui" in families else
                               tkfont.nametofont("TkDefaultFont", root=self.root).actual("family"))
        self._configure_styles()

    def _configure_styles(self):
        style = ttk.Style(self.root)
        # Clam supports custom widget colors on Windows.
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=SHADES["panel"])
        style.configure("TLabel", background=COLORS["background"],
                        foreground=COLORS["text"], font=self.body_font)
        style.configure("Title.TLabel", foreground=COLORS["accent"],
                        font=(self.heading_family, 26, "bold"))
        style.configure("Muted.TLabel", foreground=COLORS["secondary"], font=self.small_font)
        style.configure("Section.TLabel", foreground=COLORS["text"],
                        font=(self.heading_family, 11, "bold"))
        style.configure("Status.TLabel", background=SHADES["panel"],
                        foreground=COLORS["accent"], font=(self.heading_family, 14, "bold"))
        style.configure("Detail.TLabel", background=SHADES["panel"],
                        foreground=COLORS["secondary"], font=self.small_font)
        style.configure("DialogTitle.TLabel", background=SHADES["panel"],
                        foreground=COLORS["accent"], font=(self.heading_family, 16, "bold"))
        style.configure("DialogText.TLabel", background=SHADES["panel"],
                        foreground=COLORS["text"], font=self.body_font)
        style.configure("TEntry", fieldbackground=SHADES["input"],
                        foreground=COLORS["text"], insertcolor=COLORS["text"],
                        bordercolor=SHADES["border"], lightcolor=SHADES["border"],
                        darkcolor=SHADES["border"], padding=6,
                        selectbackground=COLORS["accent"],
                        selectforeground=COLORS["background"])
        style.configure("TButton", background=COLORS["secondary"], foreground=COLORS["background"],
                        padding=(12, 6), font=self.small_font,
                        bordercolor=SHADES["border"], lightcolor=SHADES["border"],
                        darkcolor=SHADES["border"])
        style.map("TButton", background=[("active", SHADES["secondary_hover"])])
        style.configure("Download.TButton", background=COLORS["primary"],
                        foreground=COLORS["background"], font=(self.heading_family, 12, "bold"),
                        padding=(12, 8), borderwidth=0)
        style.map("Download.TButton",
                  background=[("disabled", SHADES["primary_disabled"]),
                              ("active", SHADES["primary_hover"])],
                  foreground=[("disabled", COLORS["background"]),
                              ("active", COLORS["background"])])
        for widget_style in ("TRadiobutton", "TCheckbutton"):
            style.configure(widget_style, background=COLORS["background"],
                            foreground=COLORS["text"], font=self.body_font,
                            indicatorbackground=SHADES["input"],
                            indicatorforeground=COLORS["background"])
            style.map(widget_style,
                      background=[("active", COLORS["background"])],
                      indicatorbackground=[("selected", COLORS["accent"]),
                                           ("!selected", SHADES["input"])])
        style.configure("Items.Horizontal.TProgressbar", troughcolor=SHADES["input"],
                        background=COLORS["accent"], bordercolor=SHADES["input"],
                        lightcolor=COLORS["accent"], darkcolor=COLORS["accent"],
                        borderwidth=0, thickness=8)
        style.configure("Vertical.TScrollbar", background=SHADES["border"],
                        troughcolor=SHADES["input"], arrowcolor=COLORS["secondary"],
                        bordercolor=SHADES["input"], lightcolor=SHADES["border"],
                        darkcolor=SHADES["border"])
        style.map("Vertical.TScrollbar", background=[("active", COLORS["secondary"])])

    def _text_box(self, parent, *, height, state=tk.NORMAL):
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        # A themed scrollbar avoids the native white scrollbar on Windows.
        text = tk.Text(
            frame, width=1, height=height, wrap=tk.WORD, state=state,
            font=self.body_font, background=SHADES["input"],
            foreground=COLORS["text"], insertbackground=COLORS["text"],
            selectbackground=COLORS["accent"], selectforeground=COLORS["background"],
            relief=tk.FLAT, borderwidth=0, highlightthickness=1,
            highlightbackground=SHADES["border"],
            highlightcolor=COLORS["accent"], padx=8, pady=6,
        )
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return frame, text

    def _build_window(self):
        self.split_frame = ttk.Frame(self.root)
        self.split_frame.grid(row=0, column=0, sticky="nsew")
        self.split_frame.columnconfigure(0, weight=1)
        controls = ttk.Frame(self.split_frame)
        self.controls_panel = controls
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(0, weight=1)
        self.viewport = tk.Canvas(
            controls, background=COLORS["background"], highlightthickness=0,
            width=1, height=1,
        )
        self.viewport.grid(row=0, column=0, sticky="nsew")
        self.page_scrollbar = ttk.Scrollbar(
            controls, orient=tk.VERTICAL, command=self.viewport.yview)
        self.viewport.configure(yscrollcommand=self.page_scrollbar.set)
        self.page = ttk.Frame(self.viewport, padding=16)
        self.page_window = self.viewport.create_window((0, 0), window=self.page, anchor="nw")
        self.page.columnconfigure(0, weight=1)
        self.page.rowconfigure(3, weight=1)
        frame = self.page

        ttk.Label(frame, text="AudioScribe", style="Title.TLabel").grid(
            row=0, column=0, sticky="w")
        self.subtitle = ttk.Label(
            frame, text="Your YouTube links, saved as audio or video.",
            style="Muted.TLabel", wraplength=440)
        self.subtitle.grid(row=1, column=0, sticky="w", pady=(0, 12))
        ttk.Label(frame, text="YouTube URLs · one per line", style="Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=(0, 5))
        urls_frame, self.urls = self._text_box(frame, height=3)
        urls_frame.grid(row=3, column=0, sticky="nsew")
        self._build_options(frame)
        ttk.Label(frame, text="Save to", style="Section.TLabel").grid(
            row=5, column=0, sticky="w", pady=(0, 5))
        self._build_folder_picker(frame)
        self.download_button = ttk.Button(
            frame, text="Download", style="Download.TButton", command=self.start_download)
        self.download_button.grid(row=7, column=0, sticky="ew", pady=10)
        self._build_progress_card(frame)
        self._build_results_section()
        self.split_frame.bind("<Configure>", self._resize_results)
        self.viewport.bind("<Configure>", self._resize_viewport)
        self.page.bind("<Configure>", self._resize_page)
        self.root.bind("<MouseWheel>", self._scroll_page)
        self.root.bind("<Button-4>", self._scroll_page)
        self.root.bind("<Button-5>", self._scroll_page)

    def _build_results_section(self):
        divider = tk.Frame(
            self.split_frame, height=10, background=COLORS["background"],
            cursor="sb_v_double_arrow",
        )
        self.results_divider = divider
        divider.pack_propagate(False)
        grip = tk.Frame(divider, width=48, height=3,
                        background=COLORS["secondary"], cursor="sb_v_double_arrow")
        grip.pack(expand=True)
        for widget in (divider, grip):
            widget.bind("<ButtonPress-1>", self._start_results_drag)
            widget.bind("<B1-Motion>", self._drag_results)

        self.results_panel = ttk.Frame(self.split_frame, padding=(16, 0, 16, 16))
        # The divider sets this panel's height instead of its text requesting it.
        self.results_panel.grid_propagate(False)
        self.results_panel.columnconfigure(0, weight=1)
        self.results_panel.rowconfigure(1, weight=1)
        ttk.Label(self.results_panel, text="Results", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5))
        results_frame, self.results = self._text_box(
            self.results_panel, height=3, state=tk.DISABLED)
        results_frame.grid(row=1, column=0, sticky="nsew")
        self.results.tag_configure("success", foreground=COLORS["text"])
        self.results.tag_configure("failure", foreground=COLORS["accent"])
        self.show_results("Your download results will appear here.")

    def _start_results_drag(self, event):
        self._results_drag_y = event.y_root
        self._results_drag_height = self.results_panel.winfo_height()

    def _drag_results(self, event):
        available = self.split_frame.winfo_height()
        if available <= 1:
            return
        requested = self._results_drag_height + self._results_drag_y - event.y_root
        minimum = min(96, available // 2)
        height = max(minimum, min(available // 2, requested))
        self._results_fraction = height / available
        self._resize_results()

    def _resize_results(self, event=None):
        available = self.split_frame.winfo_height()
        if available <= 1:
            return
        minimum = min(96, available // 2)
        height = max(minimum, min(available // 2,
                                 round(available * self._results_fraction)))
        divider_height = 10
        divider_y = available - height - divider_height
        self.controls_panel.place(x=0, y=0, relwidth=1, height=divider_y)
        self.results_divider.place(x=0, y=divider_y, relwidth=1, height=divider_height)
        self.results_panel.place(x=0, y=available - height, relwidth=1, height=height)

    def _resize_viewport(self, event):
        self.viewport.itemconfigure(self.page_window, width=event.width)
        self.root.after_idle(self._update_page_height)

    def _resize_page(self, event):
        wraplength = max(150, event.width - 32)
        if int(self.subtitle.cget("wraplength")) != wraplength:
            self.subtitle.configure(wraplength=wraplength)
        self.root.after_idle(self._update_page_height)

    def _update_page_height(self):
        requested = self.page.winfo_reqheight()
        available = self.viewport.winfo_height()
        height = max(requested, available)
        self.viewport.itemconfigure(self.page_window, height=height)
        self.viewport.configure(scrollregion=(0, 0, self.viewport.winfo_width(), height))
        # High display scaling can need more space than a compact window provides.
        if requested > available:
            self.page_scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.page_scrollbar.grid_remove()
            self.viewport.yview_moveto(0)

    def _scroll_page(self, event):
        # Text fields keep their own scrolling; the outer page scrolls elsewhere.
        if (event.widget in (self.urls, self.results) or
                str(event.widget).startswith(str(self.results_panel))):
            return
        if self.viewport.yview() == (0.0, 1.0):
            return
        if event.num == 4:
            steps = -1
        elif event.num == 5:
            steps = 1
        else:
            steps = -1 if event.delta > 0 else 1
        self.viewport.yview_scroll(steps, "units")
        return "break"

    def _build_options(self, frame):
        options = ttk.Frame(frame)
        options.grid(row=4, column=0, sticky="ew", pady=10)
        self.audio_option = ttk.Radiobutton(
            options, text="Audio (MP3)", variable=self.media_type, value="audio")
        self.audio_option.grid(row=0, column=0, sticky="w")
        self.video_option = ttk.Radiobutton(
            options, text="Video", variable=self.media_type, value="video")
        self.video_option.grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.playlist_option = ttk.Checkbutton(
            options, text="Allow playlists", variable=self.allow_playlist)
        self.playlist_option.grid(row=0, column=2, sticky="w", padx=(20, 0))
        options.bind("<Configure>", self._layout_options)

    def _layout_options(self, event):
        required = sum(widget.winfo_reqwidth() for widget in (
            self.audio_option, self.video_option, self.playlist_option)) + 36
        wrapped = event.width < required
        if wrapped == self._options_wrapped:
            return
        self._options_wrapped = wrapped
        self.playlist_option.grid_configure(
            row=1 if wrapped else 0, column=0 if wrapped else 2,
            columnspan=3 if wrapped else 1,
            padx=0 if wrapped else (20, 0), pady=(6, 0) if wrapped else 0,
        )

    def _build_folder_picker(self, frame):
        folder = ttk.Frame(frame)
        folder.grid(row=6, column=0, sticky="ew")
        folder.columnconfigure(0, weight=1)
        ttk.Entry(folder, textvariable=self.output_dir, width=1, font=self.body_font).grid(
            row=0, column=0, sticky="ew")
        ttk.Button(folder, text="Browse…", command=self.choose_folder).grid(
            row=0, column=1, padx=(8, 0))

    def _build_progress_card(self, frame):
        card = ttk.Frame(frame, padding=12, style="Card.TFrame")
        card.grid(row=8, column=0, sticky="ew")
        card.columnconfigure(0, weight=1)
        ttk.Label(card, textvariable=self.status, style="Status.TLabel").grid(
            row=0, column=0, sticky="w")
        detail = ttk.Label(card, textvariable=self.progress_detail, style="Detail.TLabel")
        detail.grid(row=1, column=0, sticky="ew", pady=(3, 8))
        card.bind("<Configure>", lambda event: detail.configure(
            wraplength=max(150, event.width - 24)))
        self.progress_bar = ttk.Progressbar(
            card, style="Items.Horizontal.TProgressbar", mode="determinate",
            maximum=1, value=0)
        self.progress_bar.grid(row=2, column=0, sticky="ew")
        ttk.Label(card, textvariable=self.completed_count, style="Detail.TLabel").grid(
            row=3, column=0, sticky="w", pady=(6, 0))

    def _show_notice(self, title, message):
        dialog = tk.Toplevel(self.root, background=SHADES["panel"])
        dialog.withdraw()
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        width = min(400, max(280, self.root.winfo_width() - 48))
        body = ttk.Frame(dialog, padding=20, style="Card.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        icon = tk.Canvas(body, width=48, height=52,
                         background=SHADES["panel"], highlightthickness=0)
        icon.create_polygon(
            4, 47, 24, 5, 44, 47,
            outline=COLORS["accent"],
            fill=SHADES["panel"],
            width=2,
        )
        icon.create_line(
            24, 21, 24, 32,
            fill=COLORS["accent"],
            width=3,
        )
        icon.create_oval(
            23, 38, 25, 40,
            fill=COLORS["accent"],
            outline=COLORS["accent"],
        )
        icon.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, 14))
        ttk.Label(body, text=title, style="DialogTitle.TLabel",
                  wraplength=width - 104).grid(row=0, column=1, sticky="w")
        ttk.Label(body, text=message, style="DialogText.TLabel",
                  wraplength=width - 104).grid(row=1, column=1, sticky="w", pady=(12, 20))
        button = ttk.Button(body, text="OK", style="Download.TButton", command=dialog.destroy)
        button.grid(row=2, column=0, columnspan=2, sticky="ew")
        dialog.bind("<Return>", lambda event: dialog.destroy())
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.update_idletasks()
        x = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2)
        y = max(0, self.root.winfo_rooty() +
                (self.root.winfo_height() - dialog.winfo_reqheight()) // 2)
        dialog.geometry(f"{width}x{dialog.winfo_reqheight()}+{x}+{y}")
        previous_focus = self.root.focus_get()
        dialog.deiconify()
        dialog.wait_visibility()
        dialog.grab_set()
        button.focus_set()
        self.root.wait_window(dialog)
        if previous_focus is not None and previous_focus.winfo_exists():
            previous_focus.focus_set()

    def choose_folder(self):
        selected = filedialog.askdirectory(parent=self.root, title="Choose download folder")
        if selected:
            self.output_dir.set(selected)

    def show_results(self, text):
        self.results.configure(state=tk.NORMAL)
        self.results.delete("1.0", tk.END)
        self.results.insert(tk.END, text)
        self.results.configure(state=tk.DISABLED)

    def append_result(self, text, *, succeeded):
        self.results.configure(state=tk.NORMAL)
        self.results.insert(tk.END, text + "\n", "success" if succeeded else "failure")
        self.results.see(tk.END)
        self.results.configure(state=tk.DISABLED)

    def start_download(self):
        if self.busy:
            return
        urls = [line.strip() for line in self.urls.get("1.0", tk.END).splitlines()
                if line.strip()]
        output_dir = self.output_dir.get().strip()
        if not urls:
            self._show_notice("Missing URLs", "Enter at least one URL.")
            return
        if not output_dir:
            self._show_notice("Missing folder", "Choose an output folder.")
            return
        options = {
            "inputs": urls,
            "output_dir": output_dir,
            "allow_playlist": self.allow_playlist.get(),
            "media_type": self.media_type.get(),
        }
        self.busy = True
        self.total_items = 0
        self.download_button.configure(state=tk.DISABLED, text="Downloading…")
        self.status.set("Preparing downloads…")
        self.progress_detail.set("Reading links and playlists. This may take a moment.")
        self.completed_count.set("Waiting for item count…")
        self.progress_bar.configure(maximum=1, value=0)
        self.show_results(f"Saving to: {output_dir}\n\n")
        Thread(target=self.run_download, args=(options,), daemon=True).start()
        self.root.after(100, self.check_download)

    def queue_progress(self, event):
        # The worker sends snapshots; only the main thread updates widgets.
        self.messages.put(("progress", dict(event)))

    def run_download(self, options):
        try:
            result = ingest(**options, on_event=self.queue_progress)
        except Exception as exc:
            self.messages.put(("error", str(exc)))
        else:
            self.messages.put(("result", result))

    def check_download(self):
        # Bound each batch so a large queue cannot starve window input.
        for _ in range(100):
            try:
                kind, payload = self.messages.get_nowait()
            except Empty:
                break
            if kind == "progress":
                self.display_progress(payload)
                continue
            self.busy = False
            self.download_button.configure(state=tk.NORMAL, text="Download")
            if kind == "error":
                self.status.set("Failed")
                self.progress_detail.set("Download stopped. See the error below.")
                self.show_results(f"Download failed:\n{payload}")
            else:
                self.display_result(payload)
            return
        if self.busy:
            self.root.after(100, self.check_download)

    def display_progress(self, event):
        # Job-level starting/finished events have no item counters.
        total = event.get("total_items")
        index = event.get("item_index")
        if not total or not index:
            return
        completed = event.get("completed_items", 0)
        self.total_items = total
        self.progress_bar.configure(maximum=total, value=completed)
        self.completed_count.set(f"Processed {completed} of {total} items")
        stage = event.get("stage")
        if stage == "downloading":
            self.status.set(f"Downloading {index} of {total}")
            self.progress_detail.set(event.get("title") or event.get("url") or "Processing item…")
        elif stage in {"finished", "failed"}:
            succeeded = stage == "finished"
            title = event.get("title") or event.get("url") or "Unknown item"
            self.append_result(f"{'OK' if succeeded else 'FAILED'}: {title}", succeeded=succeeded)

    def display_result(self, result):
        if result.get("requires_confirmation"):
            self.status.set("Playlist permission required")
            self.progress_detail.set("Enable 'Allow playlists' to continue.")
            self.completed_count.set("No items downloaded")
            self.show_results(
                "This request includes a playlist.\n\n"
                "To download it, tick 'Allow playlists' and click Download again."
            )
            return

        items = result.get("items") or []
        succeeded = sum(bool(item.get("ok")) for item in items)
        failed = len(items) - succeeded

        if self.total_items:
            self.progress_bar.configure(maximum=self.total_items, value=len(items))
        self.completed_count.set(f"Successful: {succeeded}  |  Failed: {failed}")
        self.progress_detail.set("Finished. See the results below.")

        if result.get("ok"):
            self.status.set("Completed")
        elif succeeded:
            self.status.set("Completed with errors")
        else:
            self.status.set("Failed")

        lines = [
            result.get("message") or "Download finished.",
            f"Successful: {succeeded} | Failed: {failed}",
            "",
        ]

        for item in items:
            title = item.get("title") or item.get("url") or "Unknown item"
            label = "OK" if item.get("ok") else "FAILED"
            lines.append(f"{label}: {title}")

            if item.get("file_path"):
                lines.append(f"Saved to: {item['file_path']}")

            if item.get("error"):
                lines.append(
                    f"Error: {item['error'].get('message', 'Download failed')}"
                )

            for warning in item.get("warnings") or []:
                lines.append(f"Warning: {warning}")

            lines.append("")

        for error in result.get("errors") or []:
            lines.append(f"Error: {error}")

        for warning in result.get("warnings") or []:
            lines.append(f"Warning: {warning}")

        self.show_results("\n".join(lines))

    def close_window(self):
        if self.busy:
            self._show_notice(
                "Download in progress",
                "Please wait until the download finishes before closing.",
            )
            return

        self.root.destroy()


def main():
    root = tk.Tk()
    AudioScribeWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
