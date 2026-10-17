import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from web3 import Web3
from client import LotteryClient


STATES = ("Прийом внесків", "Очікування розіграшу", "Переможця визначено", "Скасовано")
ERRORS = {
    "Only owner": "Ця дія доступна лише організатору.",
    "Only winner": "Отримати приз може лише переможець.",
    "Already entered": "Цей акаунт уже придбав квиток.",
    "Need two participants": "Для розіграшу потрібні щонайменше два учасники.",
    "Entries closed": "Прийом внесків уже закрито.",
    "Wait for draw block": "Створіть 3 тестові блоки, потім завершіть розіграш.",
    "Draw expired": "Строк розіграшу минув. Скасуйте його та поверніть внески.",
    "Draw not expired": "Строк розіграшу ще не минув.",
    "Not drawing": "Спочатку організатор має розпочати розіграш.",
    "Nothing to claim": "Виграш уже отримано або відсутній.",
    "Nothing to refund": "Для цього акаунта немає внеску до повернення.",
    "Not cancelled": "Повернення доступне лише після скасування.",
    "Not open": "Скасувати цим способом можна лише відкриту лотерею.",
    "insufficient funds": "Недостатньо тестових ETH для внеску та газу.",
}


class LotteryApp:
    def __init__(self, root):
        self.root = root
        self.client = None
        self.busy = False
        self.events = queue.Queue()
        self.buttons = []
        self.last_error = None
        self.closed = False
        root.title("Лотерея | Війтенко Максим | Варіант 6")
        root.geometry("1100x850")
        root.minsize(950, 760)
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", padding=7)
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Value.TLabel", font=("Segoe UI", 11, "bold"))
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Лотерея з призовим фондом", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Війтенко Максим  •  Фінальний проєкт  •  Варіант 6").pack(anchor="w", pady=(3, 12))

        connection = ttk.LabelFrame(frame, text="1. Локальна мережа та акаунт", padding=10)
        connection.pack(fill="x")
        self.rpc = tk.StringVar(value="http://127.0.0.1:8545")
        ttk.Label(connection, text="RPC:").grid(row=0, column=0, sticky="w")
        ttk.Entry(connection, textvariable=self.rpc, width=36).grid(row=0, column=1, sticky="ew", padx=8)
        self._button(connection, "Підключитися", self.connect).grid(row=0, column=2, padx=4)
        self._button(connection, "Оновити", self.refresh).grid(row=0, column=3, padx=4)
        ttk.Label(connection, text="Приватний ключ:").grid(row=1, column=0, sticky="w", pady=8)
        self.key_entry = ttk.Entry(connection, show="*", width=36)
        self.key_entry.grid(row=1, column=1, sticky="ew", padx=8)
        self._button(connection, "Використати ключ", self.load_key).grid(row=1, column=2, padx=4)
        self._button(connection, "Забути ключ", self.forget_key).grid(row=1, column=3, padx=4)
        connection.columnconfigure(1, weight=1)
        self.account_label = tk.StringVar(value="Акаунт: не підключено")
        ttk.Label(connection, textvariable=self.account_label).grid(row=2, column=0, columnspan=4, sticky="w")
        ttk.Label(connection, text="Ключ не записується у файли. Використовуйте лише тестові акаунти Hardhat.").grid(row=3, column=0, columnspan=4, sticky="w", pady=(5, 0))

        summary = ttk.LabelFrame(frame, text="2. Стан лотереї", padding=10)
        summary.pack(fill="x", pady=10)
        self.values = {}
        for index, (key, label) in enumerate([
            ("state", "Статус"), ("ticket", "Ціна квитка"), ("pool", "Призовий фонд"),
            ("count", "Учасників"), ("prize", "Приз до отримання"), ("blocks", "Блок / ціль розіграшу"),
        ]):
            row, group = divmod(index, 2)
            ttk.Label(summary, text=label + ":").grid(row=row, column=group * 2, sticky="w", padx=(0, 10), pady=3)
            self.values[key] = tk.StringVar(value="—")
            ttk.Label(summary, textvariable=self.values[key], style="Value.TLabel").grid(row=row, column=group * 2 + 1, sticky="w", padx=(0, 22))
        self.owner_label = tk.StringVar(value="Організатор: —")
        self.winner_label = tk.StringVar(value="Переможець: —")
        ttk.Label(summary, textvariable=self.owner_label).grid(row=3, column=0, columnspan=4, sticky="w", pady=4)
        ttk.Label(summary, textvariable=self.winner_label).grid(row=4, column=0, columnspan=4, sticky="w")

        actions = ttk.LabelFrame(frame, text="3. Дії", padding=10)
        actions.pack(fill="x")
        self.join_button = self._button(actions, "Придбати квиток", lambda: self.action("enter"))
        self.join_button.grid(row=0, column=0, padx=3, pady=3, sticky="ew")
        self.draw_button = self._button(actions, "Розпочати розіграш", lambda: self.action("request_draw"))
        self.draw_button.grid(row=0, column=1, padx=3, pady=3, sticky="ew")
        self.mine_button = self._button(actions, "+3 блоки Hardhat", lambda: self.action("mine_demo_blocks"))
        self.mine_button.grid(row=0, column=2, padx=3, pady=3, sticky="ew")
        self.finish_button = self._button(actions, "Визначити переможця", lambda: self.action("finalize_draw"))
        self.finish_button.grid(row=0, column=3, padx=3, pady=3, sticky="ew")
        self.recipient = tk.StringVar()
        ttk.Label(actions, text="Отримувач ETH:").grid(row=1, column=0, sticky="w", pady=7)
        ttk.Entry(actions, textvariable=self.recipient).grid(row=1, column=1, columnspan=3, sticky="ew", padx=3)
        self.claim_button = self._button(actions, "Отримати виграш", lambda: self.action("claim", self.recipient.get()))
        self.claim_button.grid(row=2, column=0, padx=3, pady=3, sticky="ew")
        self._button(actions, "Скасувати відкриту", lambda: self.action("cancel")).grid(row=2, column=1, padx=3, pady=3, sticky="ew")
        self._button(actions, "Скасувати прострочену", lambda: self.action("cancel_expired")).grid(row=2, column=2, padx=3, pady=3, sticky="ew")
        self._button(actions, "Повернути внесок", lambda: self.action("refund", self.recipient.get())).grid(row=2, column=3, padx=3, pady=3, sticky="ew")
        for column in range(4):
            actions.columnconfigure(column, weight=1)

        bottom = ttk.Panedwindow(frame, orient="horizontal")
        bottom.pack(fill="both", expand=True, pady=10)
        participants = ttk.LabelFrame(bottom, text="Учасники", padding=5)
        journal = ttk.LabelFrame(bottom, text="Журнал операцій", padding=5)
        bottom.add(participants, weight=1)
        bottom.add(journal, weight=1)
        self.participant_list = tk.Listbox(participants, height=7, font=("Consolas", 9))
        participant_scroll = ttk.Scrollbar(participants, orient="horizontal", command=self.participant_list.xview)
        participant_scroll.pack(side="bottom", fill="x")
        self.participant_list.configure(xscrollcommand=participant_scroll.set)
        self.participant_list.pack(fill="both", expand=True)
        self.log = tk.Text(journal, height=7, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        root.after_idle(lambda: bottom.sashpos(0, 440))
        self.status = tk.StringVar(value="Запустіть Hardhat, виконайте npm run deploy та підключіться.")
        ttk.Label(frame, textvariable=self.status, wraplength=1030).pack(anchor="w")
        ttk.Label(frame, text="Навчальна мережа 31337. Вибір за хешем майбутнього блоку не підходить для лотереї зі справжніми коштами.", wraplength=1030).pack(anchor="w", pady=(5, 0))
        self.poll_id = root.after(100, self.poll)

    def _button(self, parent, title, command):
        button = ttk.Button(parent, text=title, command=command)
        self.buttons.append(button)
        return button

    def set_busy(self, value):
        self.busy = value
        for button in self.buttons:
            button.configure(state="disabled" if value else "normal")
        self.key_entry.configure(state="disabled" if value else "normal")

    def run(self, operation):
        if self.busy:
            return
        self.last_error = None
        self.set_busy(True)
        self.status.set("Виконується операція…")
        def worker():
            try:
                self.events.put((True, operation()))
            except Exception as error:
                self.events.put((False, self.safe_error(error)))
        threading.Thread(target=worker, daemon=True).start()

    def safe_error(self, error):
        text = str(error)
        for fragment, explanation in ERRORS.items():
            if fragment.lower() in text.lower():
                return explanation
        if isinstance(error, (ValueError, ConnectionError)) and text.startswith(("Hardhat", "Дозволена", "Некорект", "Контракти", "Адреси", "Спочатку")):
            return text
        return "Не вдалося виконати операцію. Перевірте мережу, акаунт, адресу отримувача та стан лотереї."

    def poll(self):
        if self.closed:
            return
        try:
            success, result = self.events.get_nowait()
            self.set_busy(False)
            if success:
                message, snapshot = result
                self.update_snapshot(snapshot)
                self.status.set(message)
                self.append_log(message)
            else:
                self.last_error = result
                self.status.set(result)
                self.append_log(result)
                messagebox.showerror("Помилка", result, parent=self.root)
        except queue.Empty:
            pass
        self.poll_id = self.root.after(100, self.poll)

    def connect(self):
        rpc = self.rpc.get().strip()
        def operation():
            client = LotteryClient(rpc)
            self.client = client
            return "Підключено до локального Hardhat.", client.snapshot()
        self.run(operation)

    def refresh(self):
        if self.client is None:
            self.connect()
        else:
            self.run(lambda: ("Стан оновлено.", self.client.snapshot()))

    def load_key(self):
        if self.busy:
            return
        private_key = self.key_entry.get()
        self.key_entry.delete(0, "end")
        def operation():
            nonlocal private_key
            try:
                if self.client is None:
                    raise ValueError("Спочатку підключіться до Hardhat.")
                self.client.set_key(private_key)
            finally:
                private_key = ""
            return "Тестовий акаунт підключено. Поле ключа очищено.", self.client.snapshot()
        self.run(operation)

    def forget_key(self):
        if self.client:
            self.client.forget_key()
        self.key_entry.delete(0, "end")
        self.recipient.set("")
        self.refresh()

    def action(self, method, *args):
        def operation():
            if self.client is None:
                raise ValueError("Спочатку підключіться до Hardhat.")
            result = getattr(self.client, method)(*args)
            return f"Успішно: {result}", self.client.snapshot()
        self.run(operation)

    def update_snapshot(self, data):
        eth = lambda amount: f"{Web3.from_wei(amount, 'ether')} ETH"
        self.values["state"].set(STATES[data["state"]])
        self.values["ticket"].set(eth(data["ticket"]))
        self.values["pool"].set(eth(data["pool"]))
        self.values["count"].set(str(len(data["participants"])))
        self.values["prize"].set(eth(data["claimable"]))
        self.values["blocks"].set(f"{data['block']} / {data['draw_block'] or '—'}")
        self.owner_label.set(f"Організатор: {data['owner']}")
        winner = data["winner"] if int(data["winner"], 16) else "ще не визначено"
        self.winner_label.set(f"Переможець: {winner}")
        address = data["account"]
        self.account_label.set(f"Акаунт: {address} | {eth(data['balance'])}" if address else "Акаунт: режим перегляду")
        if address != getattr(self, "last_address", None):
            self.recipient.set(address or "")
        self.last_address = address
        self.participant_list.delete(0, "end")
        for index, participant in enumerate(data["participants"], 1):
            self.participant_list.insert("end", f"{index}. {participant}")

    def append_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def close(self):
        if self.busy:
            self.status.set("Дочекайтеся завершення поточної операції перед закриттям.")
            return
        self.closed = True
        if self.client:
            self.client.forget_key()
        self.key_entry.delete(0, "end")
        self.root.after_cancel(self.poll_id)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    LotteryApp(root)
    root.mainloop()
