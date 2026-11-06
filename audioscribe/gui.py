from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from queue import Empty, Queue
from threading import Thread
from tkinter import messagebox

from audioscribe.core.ingest import ingest


class AudioScribeWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.messages = Queue()
        self.busy = False
        root.protocol("WM_DELETE_WINDOW", self.close_window)
        root.title("AudioScribe")
        root.geometry("720x600")
        root.minsize(560, 480)

        self.media_type = tk.StringVar(value="audio")
        self.allow_playlist = tk.BooleanVar(value=False)
        self.output_dir = tk.StringVar(
            value=str(Path.home() / "Downloads" / "AudioScribe")
        )
        self.status = tk.StringVar(value="Ready")

        frame = ttk.Frame(root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        frame.rowconfigure(7, weight=2)

        ttk.Label(
            frame, text="YouTube URLs (one per line)"
        ).grid(row=0, column=0, sticky="w")

        self.urls = ScrolledText(frame, height=5, wrap=tk.WORD)
        self.urls.grid(
            row=1, column=0, sticky="nsew", pady=(6, 12)
        )

        options = ttk.Frame(frame)
        options.grid(row=2, column=0, sticky="w", pady=(0, 12))

        ttk.Radiobutton(
            options,
            text="Audio (MP3)",
            variable=self.media_type,
            value="audio",
        ).pack(side=tk.LEFT)

        ttk.Radiobutton(
            options,
            text="Video",
            variable=self.media_type,
            value="video",
        ).pack(side=tk.LEFT, padx=(16, 24))

        ttk.Checkbutton(
            options,
            text="Allow playlists",
            variable=self.allow_playlist,
        ).pack(side=tk.LEFT)

        ttk.Label(
            frame, text="Save to"
        ).grid(row=3, column=0, sticky="w")

        folder = ttk.Frame(frame)
        folder.grid(row=4, column=0, sticky="ew", pady=(6, 12))
        folder.columnconfigure(0, weight=1)

        ttk.Entry(
            folder, textvariable=self.output_dir
        ).grid(row=0, column=0, sticky="ew")

        ttk.Button(
            folder, text="Browse…", command=self.choose_folder
        ).grid(row=0, column=1, padx=(8, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0, sticky="ew", pady=(0, 12))

        self.download_button = ttk.Button(
            actions, text="Download", command=self.start_download
        )
        self.download_button.pack(side=tk.LEFT)

        ttk.Label(
            actions, textvariable=self.status
        ).pack(side=tk.LEFT, padx=12)

        ttk.Label(
            frame, text="Results"
        ).grid(row=6, column=0, sticky="w")

        self.results = ScrolledText(
            frame, height=10, wrap=tk.WORD, state=tk.DISABLED
        )
        self.results.grid(
            row=7, column=0, sticky="nsew", pady=(6, 0)
        )

    def choose_folder(self):
        selected = filedialog.askdirectory(
            parent=self.root,
            title="Choose download folder",
        )
        if selected:
            self.output_dir.set(selected)

    def show_results(self, text):
        self.results.configure(state=tk.NORMAL)
        self.results.delete("1.0", tk.END)
        self.results.insert(tk.END, text)
        self.results.configure(state=tk.DISABLED)

    def start_download(self):
        if self.busy:
            return

        urls = [
            line.strip()
            for line in self.urls.get("1.0", tk.END).splitlines()
            if line.strip()
        ]
        output_dir = self.output_dir.get().strip()

        if not urls:
            messagebox.showwarning(
                "Missing URLs", "Enter at least one URL.", parent=self.root
            )
            return

        if not output_dir:
            messagebox.showwarning(
                "Missing folder", "Choose an output folder.", parent=self.root
            )
            return

        # Read all window values before starting the background thread.
        options = {
            "inputs": urls,
            "output_dir": output_dir,
            "allow_playlist": self.allow_playlist.get(),
            "media_type": self.media_type.get(),
        }

        self.busy = True
        self.download_button.configure(state=tk.DISABLED)
        self.status.set("Downloading…")
        self.show_results(
            f"Saving to: {output_dir}\n\n"
            "Downloading and verifying. Results will appear when finished."
        )

        Thread(
            target=self.run_download,
            args=(options,),
            daemon=True,
        ).start()
        self.root.after(100, self.check_download)

    def run_download(self, options):
        # This thread only runs the workflow and passes back its result.
        # All window updates happen on the main thread.
        try:
            result = ingest(**options)
        except Exception as exc:
            self.messages.put(("error", str(exc)))
        else:
            self.messages.put(("result", result))

    def check_download(self):
        try:
            kind, payload = self.messages.get_nowait()
        except Empty:
            self.root.after(100, self.check_download)
            return

        self.busy = False
        self.download_button.configure(state=tk.NORMAL)

        if kind == "error":
            self.status.set("Failed")
            self.show_results(f"Download failed:\n{payload}")
            return

        self.display_result(payload)

    def display_result(self, result):
        if result.get("requires_confirmation"):
            self.status.set("Playlist permission required")
            self.show_results(
                "This request includes a playlist.\n\n"
                "To download it, tick 'Allow playlists' and click Download again."
            )
            return

        items = result.get("items") or []
        succeeded = sum(bool(item.get("ok")) for item in items)
        failed = len(items) - succeeded

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
            messagebox.showinfo(
                "Download in progress",
                "Please wait until the download finishes before closing.",
                parent=self.root,
            )
            return

        self.root.destroy()


def main():
    root = tk.Tk()
    AudioScribeWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()