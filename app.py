from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
import uuid

APP_TITLE = "Notes Desktop"
DATA_PATH = Path(__file__).with_name("notes_data.json")


@dataclass
class Note:
    id: str
    title: str
    content: str
    created_at: str
    updated_at: str


class NotesRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Note]:
        if not self.path.exists():
            return []

        try:
            raw_data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            messagebox.showwarning(
                APP_TITLE,
                f"Could not read {self.path.name}. Starting with an empty note list.",
            )
            return []

        notes: list[Note] = []
        for item in raw_data:
            notes.append(
                Note(
                    id=item.get("id", str(uuid.uuid4())),
                    title=item.get("title", "Untitled"),
                    content=item.get("content", ""),
                    created_at=item.get("created_at", current_timestamp()),
                    updated_at=item.get("updated_at", current_timestamp()),
                )
            )
        return notes

    def save(self, notes: list[Note]) -> None:
        serialized = [asdict(note) for note in notes]
        self.path.write_text(
            json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def current_timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class NotesApp:
    def __init__(self, root: tk.Tk, repository: NotesRepository) -> None:
        self.root = root
        self.repository = repository
        self.notes: list[Note] = self.repository.load()
        self.filtered_note_ids: list[str] = []

        self.selected_note_id: str | None = None
        self.content_modified_by_program = False

        self.root.title(APP_TITLE)
        self.root.geometry("980x640")

        self._build_ui()
        self.refresh_note_list()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = tk.Frame(self.root, padx=8, pady=8)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(2, weight=1)

        tk.Button(toolbar, text="New", command=self.create_note).grid(
            row=0, column=0, padx=(0, 6)
        )
        tk.Button(toolbar, text="Delete", command=self.delete_selected_note).grid(
            row=0, column=1, padx=(0, 10)
        )

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_note_list())
        tk.Entry(toolbar, textvariable=self.search_var).grid(row=0, column=2, sticky="ew")

        tk.Label(toolbar, text="Search").grid(row=0, column=3, padx=(8, 0))

        content = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        content.grid(row=1, column=0, sticky="nsew")

        left_panel = tk.Frame(content, padx=8, pady=8)
        left_panel.rowconfigure(0, weight=1)
        left_panel.columnconfigure(0, weight=1)

        self.notes_listbox = tk.Listbox(left_panel, exportselection=False)
        self.notes_listbox.grid(row=0, column=0, sticky="nsew")
        self.notes_listbox.bind("<<ListboxSelect>>", self.on_note_selected)

        content.add(left_panel, minsize=240)

        right_panel = tk.Frame(content, padx=8, pady=8)
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)

        self.title_var = tk.StringVar()
        title_entry = tk.Entry(right_panel, textvariable=self.title_var, font=("Arial", 14, "bold"))
        title_entry.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        title_entry.bind("<KeyRelease>", lambda _event: self.on_note_changed())

        self.editor = ScrolledText(right_panel, wrap=tk.WORD, undo=True)
        self.editor.grid(row=1, column=0, sticky="nsew")
        self.editor.bind("<<Modified>>", self.on_editor_modified)

        details_frame = tk.Frame(right_panel)
        details_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        self.status_var = tk.StringVar(value="No note selected")
        tk.Label(details_frame, textvariable=self.status_var, anchor="w").pack(fill="x")

        content.add(right_panel)

    def refresh_note_list(self) -> None:
        query = self.search_var.get().strip().lower()

        if query:
            filtered = [
                note
                for note in self.notes
                if query in note.title.lower() or query in note.content.lower()
            ]
        else:
            filtered = self.notes

        self.filtered_note_ids = [note.id for note in sorted(filtered, key=lambda n: n.updated_at, reverse=True)]

        self.notes_listbox.delete(0, tk.END)
        for note_id in self.filtered_note_ids:
            note = self.get_note(note_id)
            if note:
                self.notes_listbox.insert(tk.END, note.title or "Untitled")

        self._restore_selection()

    def _restore_selection(self) -> None:
        if not self.filtered_note_ids:
            self.selected_note_id = None
            self.clear_editor()
            return

        if self.selected_note_id not in self.filtered_note_ids:
            self.selected_note_id = self.filtered_note_ids[0]

        idx = self.filtered_note_ids.index(self.selected_note_id)
        self.notes_listbox.selection_clear(0, tk.END)
        self.notes_listbox.selection_set(idx)
        self.notes_listbox.activate(idx)
        self.load_selected_note_into_editor()

    def get_note(self, note_id: str) -> Note | None:
        for note in self.notes:
            if note.id == note_id:
                return note
        return None

    def create_note(self) -> None:
        title = simpledialog.askstring(APP_TITLE, "Title for the new note:")
        if title is None:
            return

        now = current_timestamp()
        note = Note(
            id=str(uuid.uuid4()),
            title=title.strip() or "Untitled",
            content="",
            created_at=now,
            updated_at=now,
        )
        self.notes.append(note)
        self.selected_note_id = note.id
        self.persist()
        self.refresh_note_list()

    def delete_selected_note(self) -> None:
        if not self.selected_note_id:
            return

        note = self.get_note(self.selected_note_id)
        if not note:
            return

        should_delete = messagebox.askyesno(
            APP_TITLE,
            f"Delete note '{note.title}'? This cannot be undone.",
        )
        if not should_delete:
            return

        self.notes = [n for n in self.notes if n.id != note.id]
        self.selected_note_id = None
        self.persist()
        self.refresh_note_list()

    def on_note_selected(self, _event: tk.Event) -> None:
        selection = self.notes_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx >= len(self.filtered_note_ids):
            return

        self.selected_note_id = self.filtered_note_ids[idx]
        self.load_selected_note_into_editor()

    def load_selected_note_into_editor(self) -> None:
        if not self.selected_note_id:
            self.clear_editor()
            return

        note = self.get_note(self.selected_note_id)
        if not note:
            self.clear_editor()
            return

        self.title_var.set(note.title)
        self.content_modified_by_program = True
        self.editor.delete("1.0", tk.END)
        self.editor.insert("1.0", note.content)
        self.editor.edit_modified(False)
        self.content_modified_by_program = False

        self.status_var.set(
            f"Created: {note.created_at}    Updated: {note.updated_at}"
        )

    def clear_editor(self) -> None:
        self.title_var.set("")
        self.content_modified_by_program = True
        self.editor.delete("1.0", tk.END)
        self.editor.edit_modified(False)
        self.content_modified_by_program = False
        self.status_var.set("No note selected")

    def on_editor_modified(self, _event: tk.Event) -> None:
        if self.content_modified_by_program:
            self.editor.edit_modified(False)
            return

        if self.editor.edit_modified():
            self.on_note_changed()
            self.editor.edit_modified(False)

    def on_note_changed(self) -> None:
        if not self.selected_note_id:
            return

        note = self.get_note(self.selected_note_id)
        if not note:
            return

        note.title = self.title_var.get().strip() or "Untitled"
        note.content = self.editor.get("1.0", tk.END).rstrip("\n")
        note.updated_at = current_timestamp()

        self.persist()
        self.refresh_note_list()
        self.status_var.set(
            f"Created: {note.created_at}    Updated: {note.updated_at}"
        )

    def persist(self) -> None:
        self.repository.save(self.notes)

    def on_close(self) -> None:
        self.persist()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = NotesApp(root, NotesRepository(DATA_PATH))
    if not app.notes:
        app.create_note()
    root.mainloop()


if __name__ == "__main__":
    main()
