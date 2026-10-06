import json
import os
import json
import sys
import time
import threading
import subprocess
import traceback
import uuid
import re
import ctypes
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pygetwindow as gw
except ImportError:
    gw = None

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = None
    ImageDraw = None

try:
    import cv2  # noqa: F401
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

APP_NAME = "Gerenciador de Automações 2.2"
TASK_PREFIX = "AutoLogin2"
OLD_TASK_PREFIX = "AutoLogin"
CONFIG_FILE_NAME = "config.json"
LOG_FILE_NAME = "autologin.log"
DEFAULT_TIMER = 30
DEFAULT_WINDOW_TIMEOUT = 180
DEFAULT_QUEUE_INTERVAL = 3
DEFAULT_CONFIRM_STARTUP_QUEUE = True
DEFAULT_START_QUEUE_ON_OPEN = True

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, CONFIG_FILE_NAME)
LOG_FILE = os.path.join(BASE_DIR, LOG_FILE_NAME)

MODO_AUTO = "--auto" in sys.argv
MODO_STARTUP = "--startup" in sys.argv

def argument_value(flag):
    try:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    except Exception:
        pass
    return None

AUTO_ID = argument_value("--id")
AUTO_INDEX = argument_value("--indice")

stop_event = threading.Event()
automation_lock = threading.Lock()
worker_thread = None
capture_running = False
app = None
log_text = None
status_var = None
counter_var = None
progress_var = None
tray_icon = None

# GUI variables
selected_id = None
name_var = None
window_var = None
user_var = None
password_var = None
timer_var = None
window_timeout_var = None
active_var = None
start_windows_var = None
queue_var = None
relative_var = None
recognition_var = None
image_path_var = None
coord_vars = {}
listbox = None
queue_tree = None


def default_automation():
    return {
        "id": uuid.uuid4().hex[:8].upper(),
        "nome": "Nova automação",
        "janela": "",
        "usuario": "admin",
        "senha": "",
        "tempo": DEFAULT_TIMER,
        "timeout_janela": DEFAULT_WINDOW_TIMEOUT,
        "ativa": True,
        "iniciar_windows": False,
        "iniciar_automaticamente": False,
        "coordenadas_relativas": False,
        "reconhecimento_imagem": False,
        "imagem": "",
        "coordenadas": {
            "usuario_x": 898,
            "usuario_y": 564,
            "senha_x": 895,
            "senha_y": 607,
            "login_x": 995,
            "login_y": 673,
        },
    }


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"versao": 2, "confirmar_fila_ao_abrir": DEFAULT_CONFIRM_STARTUP_QUEUE, "iniciar_fila_ao_abrir": DEFAULT_START_QUEUE_ON_OPEN, "automacoes": []}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("config.json inválido")
        automations = data.get("automacoes", [])
        if not isinstance(automations, list):
            automations = []
        changed = False
        normalized = []
        for old in automations:
            if not isinstance(old, dict):
                continue
            a = default_automation()
            a.update(old)
            if not old.get("id"):
                changed = True
            else:
                a["id"] = str(old["id"]).strip().upper()
            coords = default_automation()["coordenadas"]
            coords.update(old.get("coordenadas", {}) if isinstance(old.get("coordenadas", {}), dict) else {})
            a["coordenadas"] = coords
            if "timeout_janela" not in old:
                changed = True
            if "coordenadas_relativas" not in old:
                changed = True
            if "reconhecimento_imagem" not in old:
                changed = True
            if "imagem" not in old:
                changed = True
            normalized.append(a)
        data["versao"] = 2
        data.setdefault("confirmar_fila_ao_abrir", DEFAULT_CONFIRM_STARTUP_QUEUE)
        data.setdefault("iniciar_fila_ao_abrir", DEFAULT_START_QUEUE_ON_OPEN)
        data["automacoes"] = normalized
        if changed and os.path.exists(CONFIG_FILE):
            backup = CONFIG_FILE + ".v1.bak"
            try:
                if not os.path.exists(backup):
                    import shutil
                    shutil.copy2(CONFIG_FILE, backup)
            except Exception:
                pass
            write_config(data)
        return data
    except Exception as e:
        print(f"Erro ao carregar configuração: {e}")
        return {"versao": 2, "automacoes": []}


def write_config(data=None):
    global config
    if data is not None:
        config = data
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


config = load_config()


def log(message):
    text = f"[{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}] {message}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    print(text)
    if app is not None and log_text is not None:
        def update():
            try:
                log_text.configure(state="normal")
                log_text.insert("end", text + "\n")
                log_text.see("end")
                log_text.configure(state="disabled")
            except Exception:
                pass
        try:
            app.after(0, update)
        except Exception:
            pass


def ui_call(fn):
    if app is None:
        return
    try:
        app.after(0, fn)
    except Exception:
        pass


def set_status(text):
    if status_var is not None:
        ui_call(lambda: status_var.set(text))


def set_counter(value):
    if counter_var is not None:
        ui_call(lambda: counter_var.set(str(value)))


def set_progress(value):
    if progress_var is not None:
        ui_call(lambda: progress_var.set(max(0, min(100, value))))


def admin_mode():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def windows():
    if gw is None:
        return []
    result = []
    try:
        for w in gw.getAllWindows():
            try:
                title = (w.title or "").strip()
                if title and title not in {"Program Manager", APP_NAME}:
                    result.append(w)
            except Exception:
                pass
    except Exception as e:
        log(f"Erro listando janelas: {e}")
    return result


def window_by_title(saved):
    saved = (saved or "").strip()
    if not saved:
        return None
    items = windows()
    for w in items:
        try:
            if (w.title or "").strip().lower() == saved.lower():
                return w
        except Exception:
            pass
    for w in items:
        try:
            if saved.lower() in (w.title or "").strip().lower():
                return w
        except Exception:
            pass
    return None


def activate_window(w):
    if w is None:
        return False
    try:
        try:
            if w.isMinimized:
                w.restore()
                time.sleep(0.6)
        except Exception:
            pass
        w.activate()
        time.sleep(0.7)
        return True
    except Exception as e:
        log(f"Erro ativando janela: {e}")
        return False


def wait_window(title, timeout=DEFAULT_WINDOW_TIMEOUT):
    start = time.time()
    while time.time() - start < timeout:
        if stop_event.is_set():
            return None
        w = window_by_title(title)
        if w:
            return w
        set_status(f"Aguardando janela: {title}")
        time.sleep(1)
    return None


def window_rect(w):
    try:
        return int(w.left), int(w.top), int(w.width), int(w.height)
    except Exception:
        return None


def coord(automation, key, w=None):
    c = automation.get("coordenadas", {})
    x = int(c.get(key + "_x", 0))
    y = int(c.get(key + "_y", 0))
    if automation.get("coordenadas_relativas") and w is not None:
        rect = window_rect(w)
        if rect and rect[2] > 0 and rect[3] > 0:
            # Coordinates saved in relative mode are percentages 0..10000.
            return rect[0] + int(rect[2] * x / 10000), rect[1] + int(rect[3] * y / 10000)
    return x, y


def capture_coordinate(kind):
    global capture_running
    if pyautogui is None:
        messagebox.showerror("Dependência", "Instale pyautogui para capturar coordenadas.")
        return
    if capture_running:
        set_status("Já existe uma captura em andamento.")
        return
    capture_running = True
    set_status(f"Posicione o mouse para capturar {kind}...")

    def worker():
        global capture_running
        try:
            for n in range(3, 0, -1):
                set_counter(n)
                time.sleep(1)
            x, y = pyautogui.position()
            if relative_var.get():
                aid = selected_id
                a = find_automation(aid) if aid else None
                w = window_by_title(window_var.get())
                rect = window_rect(w) if w else None
                if rect and rect[2] and rect[3]:
                    x = round((x - rect[0]) / rect[2] * 10000)
                    y = round((y - rect[1]) / rect[3] * 10000)
                else:
                    log("⚠ Janela não encontrada; captura salva como coordenada absoluta.")
            ui_call(lambda: set_coord(kind, x, y))
            log(f"✓ {kind}: X={x}, Y={y}")
            set_status(f"✓ {kind.capitalize()} capturado.")
        except Exception as e:
            log(f"✗ Erro capturando coordenada: {e}")
            set_status("Erro na captura.")
        finally:
            capture_running = False
            set_counter("--")
    threading.Thread(target=worker, daemon=True).start()


def set_coord(kind, x, y):
    coord_vars[kind][0].set(str(x))
    coord_vars[kind][1].set(str(y))


def find_automation(aid):
    for a in config.get("automacoes", []):
        if str(a.get("id", "")).upper() == str(aid or "").upper():
            return a
    return None


def current_form_data():
    name = name_var.get().strip()
    title = window_var.get().strip()
    if not name:
        raise ValueError("Digite o nome da automação.")
    if not title:
        raise ValueError("Informe o título da janela.")
    try:
        timer = int(timer_var.get())
        timeout = int(window_timeout_var.get())
        if timer < 0 or timeout <= 0:
            raise ValueError
    except ValueError:
        raise ValueError("Timer deve ser >= 0 e timeout deve ser > 0.")
    coords = {}
    for kind in ("usuario", "senha", "login"):
        try:
            coords[kind + "_x"] = int(coord_vars[kind][0].get())
            coords[kind + "_y"] = int(coord_vars[kind][1].get())
        except ValueError:
            raise ValueError("As coordenadas precisam ser números inteiros.")
    aid = selected_id or uuid.uuid4().hex[:8].upper()
    return {
        "id": aid,
        "nome": name,
        "janela": title,
        "usuario": user_var.get(),
        "senha": password_var.get(),
        "tempo": timer,
        "timeout_janela": timeout,
        "ativa": bool(active_var.get()),
        "iniciar_windows": False,
        "iniciar_automaticamente": bool(queue_var.get()),
        "coordenadas_relativas": bool(relative_var.get()),
        "reconhecimento_imagem": bool(recognition_var.get()),
        "imagem": image_path_var.get().strip(),
        "coordenadas": coords,
    }


def load_form(a):
    name_var.set(a.get("nome", ""))
    window_var.set(a.get("janela", ""))
    user_var.set(a.get("usuario", "admin"))
    password_var.set(a.get("senha", ""))
    timer_var.set(str(a.get("tempo", DEFAULT_TIMER)))
    window_timeout_var.set(str(a.get("timeout_janela", DEFAULT_WINDOW_TIMEOUT)))
    active_var.set(a.get("ativa", True))
    start_windows_var.set(a.get("iniciar_windows", False))
    queue_var.set(a.get("iniciar_automaticamente", False))
    relative_var.set(a.get("coordenadas_relativas", False))
    recognition_var.set(a.get("reconhecimento_imagem", False))
    image_path_var.set(a.get("imagem", ""))
    c = a.get("coordenadas", {})
    for kind in ("usuario", "senha", "login"):
        coord_vars[kind][0].set(str(c.get(kind + "_x", 0)))
        coord_vars[kind][1].set(str(c.get(kind + "_y", 0)))


def clear_form():
    global selected_id
    selected_id = None
    load_form(default_automation())
    if listbox:
        listbox.selection_clear(0, "end")
    set_status("Nova automação.")


def refresh_automation_list(select_id=None):
    if listbox is None:
        return
    listbox.delete(0, "end")
    for a in config.get("automacoes", []):
        state = "🟢" if a.get("ativa", True) else "🔴"
        win = ""
        queue = "▶" if a.get("iniciar_automaticamente") else ""
        listbox.insert("end", f"{state} {a.get('nome','Sem nome')}  {win}{queue}")
    if select_id:
        for i, a in enumerate(config.get("automacoes", [])):
            if a.get("id") == select_id:
                listbox.selection_set(i)
                listbox.see(i)
                break


def on_list_select(event=None):
    global selected_id
    sel = listbox.curselection()
    if not sel:
        return
    i = sel[0]
    automations = config.get("automacoes", [])
    if i >= len(automations):
        return
    selected_id = automations[i]["id"]
    load_form(automations[i])
    set_status(f"Selecionada: {automations[i].get('nome')}")
    refresh_queue()


def save_automation():
    global selected_id
    try:
        data = current_form_data()
        found = False
        for i, a in enumerate(config.get("automacoes", [])):
            if a.get("id") == data["id"]:
                config["automacoes"][i] = data
                found = True
                break
        if not found:
            config.setdefault("automacoes", []).append(data)
        selected_id = data["id"]
        config["confirmar_fila_ao_abrir"] = bool(confirm_startup_var.get())
        config["iniciar_fila_ao_abrir"] = bool(start_queue_on_open_var.get())
        write_config()
        refresh_automation_list(selected_id)
        set_status(f"✓ {data['nome']} salva e sincronizada.")
        log(f"✓ Automação salva: {data['nome']} [{data['id']}]")
    except Exception as e:
        messagebox.showerror("Erro", str(e))


def delete_selected_automation():
    global selected_id
    if not selected_id:
        messagebox.showwarning("Atenção", "Selecione uma automação.")
        return
    a = find_automation(selected_id)
    if not a:
        return
    if not messagebox.askyesno("Excluir", f"Excluir '{a.get('nome')}'?\nA automação será removida do aplicativo."):
        return
    config["automacoes"] = [x for x in config.get("automacoes", []) if x.get("id") != selected_id]
    write_config()
    log(f"Automação excluída: {a.get('nome')} [{selected_id}]")
    selected_id = None
    refresh_automation_list()
    refresh_queue()
    clear_form()


def edit_selected():
    if not selected_id:
        messagebox.showwarning("Atenção", "Selecione uma automação.")
        return
    set_status("Edite os campos e clique em SALVAR.")


def refresh_windows():
    titles = []
    for w in windows():
        try:
            title = (w.title or "").strip()
            if title and title not in titles:
                titles.append(title)
        except Exception:
            pass
    combo_window["values"] = titles
    set_status(f"{len(titles)} janela(s) encontrada(s).")


def choose_image():
    path = filedialog.askopenfilename(
        title="Selecionar imagem",
        filetypes=[("Imagens", "*.png;*.jpg;*.jpeg;*.bmp"), ("Todos", "*.*")]
    )
    if path:
        image_path_var.set(path)
        recognition_var.set(True)


def recognize_image(automation):
    if not automation.get("reconhecimento_imagem"):
        return True
    path = automation.get("imagem", "")
    if not path:
        log("⚠ Reconhecimento de imagem ativado, mas nenhuma imagem foi configurada.")
        return True
    if pyautogui is None:
        return False
    if not OPENCV_AVAILABLE:
        log("⚠ OpenCV não instalado; reconhecimento de imagem ignorado.")
        return True
    log(f"Procurando imagem: {path}")
    try:
        location = pyautogui.locateCenterOnScreen(path, confidence=0.85)
        if location:
            log(f"✓ Imagem encontrada em {location}.")
            return True
        log("✗ Imagem não encontrada.")
        return False
    except Exception as e:
        log(f"Erro no reconhecimento: {e}")
        return False


def execute_login(a, w):
    if pyautogui is None:
        raise RuntimeError("pyautogui não está instalado.")
    if not activate_window(w):
        raise RuntimeError("Não foi possível ativar a janela.")
    if not recognize_image(a):
        raise RuntimeError("Imagem de referência não encontrada.")

    positions = {}
    for kind in ("usuario", "senha", "login"):
        positions[kind] = coord(a, kind, w)

    user = str(a.get("usuario", ""))
    password = str(a.get("senha", ""))

    ux, uy = positions["usuario"]
    sx, sy = positions["senha"]
    lx, ly = positions["login"]

    pyautogui.click(ux, uy)
    pyautogui.hotkey("ctrl", "a")
    if user:
        pyautogui.write(user, interval=0.03)
    time.sleep(0.25)
    pyautogui.click(sx, sy)
    pyautogui.hotkey("ctrl", "a")
    if password:
        pyautogui.write(password, interval=0.03)
    time.sleep(0.25)
    pyautogui.click(lx, ly)
    time.sleep(1)


def execute_automation(aid, from_queue=False):
    with automation_lock:
        a = find_automation(aid)
        if not a:
            log(f"✗ Automação ID {aid} não existe.")
            return False
        if not a.get("ativa", True):
            log(f"⚠ Automação desativada: {a.get('nome')}")
            return False
        name = a.get("nome", aid)
        try:
            delay = max(0, int(a.get("tempo", DEFAULT_TIMER)))
        except Exception:
            delay = DEFAULT_TIMER
        try:
            timeout = max(1, int(a.get("timeout_janela", DEFAULT_WINDOW_TIMEOUT)))
        except Exception:
            timeout = DEFAULT_WINDOW_TIMEOUT

        log("==========================================")
        log(f"INICIANDO: {name} [{aid}]")
        if from_queue:
            log("Origem: FILA")
        if delay:
            for remaining in range(delay, 0, -1):
                if stop_event.is_set():
                    log("⏹ Interrompida durante o timer.")
                    return False
                set_counter(remaining)
                set_status(f"{name} iniciando em {remaining}s")
                set_progress((delay - remaining) / delay * 100)
                time.sleep(1)
        w = wait_window(a.get("janela", ""), timeout)
        if not w:
            log(f"✗ Janela não encontrada: {a.get('janela')}")
            set_status(f"✗ Janela não encontrada: {name}")
            set_counter("--")
            return False
        if stop_event.is_set():
            return False
        try:
            execute_login(a, w)
            log(f"✓ AUTOMAÇÃO CONCLUÍDA: {name}")
            set_status(f"✓ {name} concluída.")
            set_counter("--")
            set_progress(100)
            return True
        except Exception as e:
            log(f"✗ Erro em {name}: {e}")
            log(traceback.format_exc())
            set_status(f"✗ Erro em {name}.")
            set_counter("--")
            return False
        finally:
            set_progress(0)


def run_single(aid):
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        messagebox.showwarning("Em execução", "Já existe uma automação ou fila em execução.")
        return
    stop_event.clear()
    worker_thread = threading.Thread(target=lambda: execute_automation(aid), daemon=True)
    worker_thread.start()


def prompt_startup_queue():
    """Inicia a fila conforme as opções globais configuradas."""
    if not config.get("iniciar_fila_ao_abrir", DEFAULT_START_QUEUE_ON_OPEN):
        log("Opção desativada: a fila não será iniciada ao abrir o aplicativo.")
        set_status("Início automático da fila desativado.")
        return
    ids = [a["id"] for a in config.get("automacoes", []) if a.get("ativa", True) and a.get("iniciar_automaticamente", False)]
    if not ids:
        log("Nenhuma automação ativa foi encontrada na fila.")
        return
    if config.get("confirmar_fila_ao_abrir", DEFAULT_CONFIRM_STARTUP_QUEUE):
        nomes = []
        for aid in ids:
            item = find_automation(aid)
            if item:
                nomes.append(str(item.get("nome", aid)))
        resposta = messagebox.askyesno("Iniciar automações", "Deseja iniciar agora a fila de automações?\n\n" + "\n".join(f"{i}. {nome}" for i, nome in enumerate(nomes, 1)))
        if resposta:
            log("Confirmação recebida: iniciar automações.")
            queue_automations(False)
        else:
            log("Usuário escolheu não iniciar a fila agora.")
            set_status("Fila não iniciada.")
    else:
        log("Confirmação desativada; iniciando a fila automaticamente.")
        queue_automations(False)


def queue_automations(manual=True):
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        if manual:
            messagebox.showwarning("Em execução", "Já existe uma automação ou fila em execução.")
        return
    ids = [a["id"] for a in config.get("automacoes", []) if a.get("ativa", True) and a.get("iniciar_automaticamente", False)]
    if not ids:
        log("⚠ Nenhuma automação ativa está marcada para a fila automática.")
        if manual:
            messagebox.showinfo("Fila", "Nenhuma automação ativa está marcada para a fila automática.")
        return
    stop_event.clear()

    def worker():
        title = "FILA INICIADA PELO APLICATIVO"
        log("==========================================")
        log(title)
        log(f"Total: {len(ids)} automações")
        for pos, aid in enumerate(ids, 1):
            if stop_event.is_set():
                log("⏹ Fila interrompida.")
                break
            a = find_automation(aid)
            if not a:
                log(f"✗ [{pos}/{len(ids)}] Automação não encontrada: {aid}")
                continue
            log(f"[{pos}/{len(ids)}] Iniciando: {a.get('nome')}")
            ok = execute_automation(aid, from_queue=True)
            if ok:
                log(f"✓ {a.get('nome')} concluída")
            else:
                log(f"✗ {a.get('nome')} falhou")
            if pos < len(ids) and not stop_event.is_set():
                log(f"Aguardando {DEFAULT_QUEUE_INTERVAL} segundos...")
                for _ in range(DEFAULT_QUEUE_INTERVAL):
                    if stop_event.is_set():
                        break
                    time.sleep(1)
                if not stop_event.is_set():
                    log("Próxima automação")
        log("==========================================")
        log("FIM DA FILA DO APLICATIVO")
        set_status("Fila finalizada.")

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

def stop_execution():
    stop_event.set()
    set_status("⏹ Solicitação de parada enviada.")
    log("⏹ PARAR pressionado pelo usuário.")


def test_selected():
    if not selected_id:
        messagebox.showwarning("Atenção", "Selecione uma automação.")
        return
    run_single(selected_id)


def minimize_to_tray():
    if pystray is None or Image is None:
        app.withdraw()
        set_status("Aplicativo minimizado. Instale pystray + Pillow para bandeja.")
        return
    app.withdraw()
    if tray_icon is not None:
        return
    def make_icon():
        img = Image.new("RGB", (64, 64), "#111827")
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((8, 8, 56, 56), radius=12, fill="#2563eb")
        d.text((18, 18), "A", fill="white")
        return img
    def show(icon, item):
        app.after(0, app.deiconify)
        icon.stop()
    def quit_app(icon, item):
        icon.stop()
        app.after(0, real_close)
    menu = pystray.Menu(
        pystray.MenuItem("Abrir", show),
        pystray.MenuItem("Sair", quit_app),
    )
    globals()["tray_icon"] = pystray.Icon("Automacoes", make_icon(), APP_NAME, menu)
    threading.Thread(target=tray_icon.run, daemon=True).start()


def real_close():
    stop_execution()
    try:
        if tray_icon:
            tray_icon.stop()
    except Exception:
        pass
    app.destroy()


def close_app():
    if pystray is not None and messagebox.askyesno("Sair", "Deseja realmente fechar o Gerenciador de Automações?"):
        real_close()
    elif pystray is None:
        real_close()


def build_style():
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TNotebook", background="#111827", borderwidth=0)
    style.configure("TNotebook.Tab", padding=(18, 10), font=("Segoe UI", 10, "bold"))
    style.configure("Treeview", rowheight=30, font=("Segoe UI", 9))
    style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
    style.configure("TButton", padding=(10, 7))
    style.configure("TLabel", font=("Segoe UI", 9))
    style.configure("TCheckbutton", font=("Segoe UI", 9))


def make_button(parent, text, command, bg="#2563eb", width=None):
    kw = {"text": text, "command": command, "bg": bg, "fg": "white", "activebackground": bg, "activeforeground": "white", "font": ("Segoe UI", 9, "bold"), "relief": "flat", "cursor": "hand2", "padx": 10, "pady": 7}
    if width:
        kw["width"] = width
    return tk.Button(parent, **kw)


def build_automation_tab(notebook):
    global listbox, combo_window
    tab = tk.Frame(notebook, bg="#f3f4f6")
    notebook.add(tab, text="  Automações  ")
    left = tk.Frame(tab, bg="#ffffff", bd=1, relief="solid")
    left.pack(side="left", fill="both", expand=False, padx=(10, 5), pady=10)
    tk.Label(left, text="AUTOMAÇÕES", bg="#ffffff", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 4))
    tk.Label(left, text="🟢 ativa   ⚙ Windows   ▶ fila", bg="#ffffff", fg="#6b7280").pack(anchor="w", padx=12, pady=(0, 8))
    listbox = tk.Listbox(left, width=36, height=24, font=("Segoe UI", 10), bd=0, highlightthickness=0, activestyle="none")
    listbox.pack(fill="both", expand=True, padx=8, pady=5)
    listbox.bind("<<ListboxSelect>>", on_list_select)
    buttons = tk.Frame(left, bg="#ffffff")
    buttons.pack(fill="x", padx=8, pady=8)
    make_button(buttons, "＋ NOVA", clear_form, "#16a34a", 9).pack(side="left", padx=2)
    make_button(buttons, "✎ EDITAR", edit_selected, "#2563eb", 9).pack(side="left", padx=2)
    make_button(buttons, "🗑 EXCLUIR", delete_selected_automation, "#dc2626", 9).pack(side="left", padx=2)

    right = tk.Frame(tab, bg="#ffffff", bd=1, relief="solid")
    right.pack(side="left", fill="both", expand=True, padx=(5, 10), pady=10)
    right.columnconfigure(1, weight=1)
    tk.Label(right, text="CONFIGURAÇÃO DA AUTOMAÇÃO", bg="#ffffff", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=12)

    def row(label, var, r, show=None):
        tk.Label(right, text=label, bg="#ffffff").grid(row=r, column=0, sticky="w", padx=14, pady=4)
        e = tk.Entry(right, textvariable=var, show=show, relief="solid", bd=1)
        e.grid(row=r, column=1, columnspan=2, sticky="ew", padx=8, pady=4)
        return e

    row("Nome", name_var, 1)
    tk.Label(right, text="Janela", bg="#ffffff").grid(row=2, column=0, sticky="w", padx=14, pady=4)
    combo_window = ttk.Combobox(right, textvariable=window_var)
    combo_window.grid(row=2, column=1, sticky="ew", padx=8, pady=4)
    make_button(right, "↻ Janelas", refresh_windows, "#4b5563", 10).grid(row=2, column=2, padx=8, pady=4)
    row("Usuário", user_var, 3)
    row("Senha", password_var, 4, "*")
    row("Timer inicial (s)", timer_var, 5)
    row("Tempo aguardando janela (s)", window_timeout_var, 6)

    tk.Label(right, text="COORDENADAS", bg="#ffffff", font=("Segoe UI", 10, "bold")).grid(row=7, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 5))
    for r, kind, label in [(8, "usuario", "Usuário"), (9, "senha", "Senha"), (10, "login", "Login")]:
        tk.Label(right, text=label, bg="#ffffff").grid(row=r, column=0, sticky="w", padx=14, pady=3)
        frame = tk.Frame(right, bg="#ffffff")
        frame.grid(row=r, column=1, columnspan=2, sticky="w", padx=8, pady=3)
        tk.Label(frame, text="X", bg="#ffffff").pack(side="left")
        tk.Entry(frame, textvariable=coord_vars[kind][0], width=7).pack(side="left", padx=3)
        tk.Label(frame, text="Y", bg="#ffffff").pack(side="left")
        tk.Entry(frame, textvariable=coord_vars[kind][1], width=7).pack(side="left", padx=3)
        make_button(frame, "📍 Capturar", lambda k=kind: capture_coordinate(k), "#4b5563", 11).pack(side="left", padx=6)

    tk.Label(right, text="OPÇÕES", bg="#ffffff", font=("Segoe UI", 10, "bold")).grid(row=11, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 3))
    tk.Checkbutton(right, text="Automação ativa", variable=active_var, bg="#ffffff", anchor="w").grid(row=12, column=0, columnspan=3, sticky="w", padx=14)
    tk.Checkbutton(right, text="Incluir na fila automática", variable=queue_var, bg="#ffffff", anchor="w").grid(row=14, column=0, columnspan=3, sticky="w", padx=14)
    tk.Checkbutton(right, text="Perguntar antes de iniciar a fila ao abrir o aplicativo", variable=confirm_startup_var, bg="#ffffff", anchor="w").grid(row=15, column=0, columnspan=3, sticky="w", padx=14)
    tk.Checkbutton(right, text="Iniciar automações ao abrir o aplicativo", variable=start_queue_on_open_var, bg="#ffffff", anchor="w").grid(row=16, column=0, columnspan=3, sticky="w", padx=14)
    tk.Checkbutton(right, text="Usar coordenadas relativas à janela", variable=relative_var, bg="#ffffff", anchor="w").grid(row=17, column=0, columnspan=3, sticky="w", padx=14)
    tk.Checkbutton(right, text="Usar reconhecimento de imagem antes do login", variable=recognition_var, bg="#ffffff", anchor="w").grid(row=18, column=0, columnspan=3, sticky="w", padx=14)
    image_frame = tk.Frame(right, bg="#ffffff")
    image_frame.grid(row=19, column=0, columnspan=3, sticky="ew", padx=14, pady=3)
    image_frame.columnconfigure(0, weight=1)
    tk.Entry(image_frame, textvariable=image_path_var).grid(row=0, column=0, sticky="ew")
    make_button(image_frame, "Selecionar imagem", choose_image, "#4b5563", 17).grid(row=0, column=1, padx=6)

    actions = tk.Frame(right, bg="#ffffff")
    actions.grid(row=20, column=0, columnspan=3, pady=14)
    make_button(actions, "▶ TESTAR", test_selected, "#16a34a", 12).pack(side="left", padx=4)
    make_button(actions, "⏹ PARAR", stop_execution, "#dc2626", 12).pack(side="left", padx=4)
    make_button(actions, "💾 SALVAR E APLICAR", save_automation, "#2563eb", 22).pack(side="left", padx=4)


def refresh_queue():
    """Atualiza a lista visual da fila sem depender do Agendador do Windows."""
    if queue_tree is None:
        return
    for item in queue_tree.get_children():
        queue_tree.delete(item)
    pos = 1
    for automation in config.get("automacoes", []):
        if automation.get("iniciar_automaticamente", False):
            queue_tree.insert(
                "", "end", iid=automation["id"],
                values=(
                    pos,
                    automation.get("nome", ""),
                    "ATIVA" if automation.get("ativa", True) else "DESATIVADA",
                    automation["id"],
                ),
            )
            pos += 1


def move_queue(direction):
    """Move uma automação na ordem da fila e salva a configuração."""
    if queue_tree is None:
        return
    selection = queue_tree.selection()
    if not selection:
        return
    aid = selection[0]
    indices = [
        index for index, automation in enumerate(config.get("automacoes", []))
        if automation.get("iniciar_automaticamente", False)
    ]
    current = next(
        (position for position, index in enumerate(indices)
         if config["automacoes"][index].get("id") == aid),
        None,
    )
    if current is None:
        return
    target = current + direction
    if target < 0 or target >= len(indices):
        return
    first, second = indices[current], indices[target]
    config["automacoes"][first], config["automacoes"][second] = (
        config["automacoes"][second], config["automacoes"][first]
    )
    write_config()
    refresh_automation_list(aid)
    refresh_queue()
    set_status("Ordem da fila atualizada.")


def build_queue_tab(notebook):
    global queue_tree
    tab = tk.Frame(notebook, bg="#f3f4f6")
    notebook.add(tab, text="  Fila  ")
    top = tk.Frame(tab, bg="#f3f4f6")
    top.pack(fill="x", padx=10, pady=10)
    tk.Label(top, text="FILA DE AUTOMAÇÕES", bg="#f3f4f6", font=("Segoe UI", 14, "bold")).pack(side="left")
    tk.Label(top, text="A ordem abaixo será respeitada.", bg="#f3f4f6", fg="#6b7280").pack(side="left", padx=15)
    frame = tk.Frame(tab, bg="#ffffff", bd=1, relief="solid")
    frame.pack(fill="both", expand=True, padx=10, pady=5)
    queue_tree = ttk.Treeview(frame, columns=("ordem", "nome", "status", "id"), show="headings")
    for c, h, w in [("ordem", "Ordem", 80), ("nome", "Automação", 400), ("status", "Status", 150), ("id", "ID", 120)]:
        queue_tree.heading(c, text=h)
        queue_tree.column(c, width=w, anchor="center" if c != "nome" else "w")
    queue_tree.pack(fill="both", expand=True, padx=5, pady=5)
    buttons = tk.Frame(tab, bg="#f3f4f6")
    buttons.pack(pady=10)
    make_button(buttons, "⬆ SUBIR", lambda: move_queue(-1), "#4b5563", 12).pack(side="left", padx=4)
    make_button(buttons, "⬇ DESCER", lambda: move_queue(1), "#4b5563", 12).pack(side="left", padx=4)
    make_button(buttons, "▶ EXECUTAR FILA", lambda: queue_automations(True), "#16a34a", 17).pack(side="left", padx=4)
    make_button(buttons, "⏹ PARAR", stop_execution, "#dc2626", 12).pack(side="left", padx=4)


def build_log_area(root):
    global log_text, status_var, counter_var, progress_var
    frame = tk.Frame(root, bg="#111827")
    frame.pack(fill="x", padx=10, pady=(0, 10))
    status_var = tk.StringVar(value="Pronto.")
    counter_var = tk.StringVar(value="--")
    progress_var = tk.DoubleVar(value=0)
    header = tk.Frame(frame, bg="#111827")
    header.pack(fill="x", padx=8, pady=5)
    tk.Label(header, textvariable=status_var, bg="#111827", fg="white", font=("Segoe UI", 9, "bold")).pack(side="left")
    tk.Label(header, textvariable=counter_var, bg="#111827", fg="#60a5fa", font=("Segoe UI", 14, "bold")).pack(side="right")
    bar = ttk.Progressbar(frame, variable=progress_var, maximum=100)
    bar.pack(fill="x", padx=8, pady=(0, 5))
    log_text = tk.Text(frame, height=7, bg="#0b1120", fg="#d1d5db", insertbackground="white", font=("Consolas", 9), state="disabled", relief="flat")
    log_text.pack(fill="x", padx=8, pady=(0, 8))


def build_gui():
    global app, name_var, window_var, user_var, password_var, timer_var, window_timeout_var
    global active_var, start_windows_var, queue_var, relative_var, recognition_var, image_path_var, confirm_startup_var, start_queue_on_open_var
    app = tk.Tk()
    app.title(APP_NAME)
    app.geometry("1220x780")
    app.minsize(1050, 700)
    app.configure(bg="#111827")
    build_style()

    name_var = tk.StringVar()
    window_var = tk.StringVar()
    user_var = tk.StringVar(value="admin")
    password_var = tk.StringVar()
    timer_var = tk.StringVar(value=str(DEFAULT_TIMER))
    window_timeout_var = tk.StringVar(value=str(DEFAULT_WINDOW_TIMEOUT))
    active_var = tk.BooleanVar(value=True)
    start_windows_var = tk.BooleanVar(value=False)
    queue_var = tk.BooleanVar(value=False)
    confirm_startup_var = tk.BooleanVar(value=bool(config.get("confirmar_fila_ao_abrir", DEFAULT_CONFIRM_STARTUP_QUEUE)))
    start_queue_on_open_var = tk.BooleanVar(value=bool(config.get("iniciar_fila_ao_abrir", DEFAULT_START_QUEUE_ON_OPEN)))
    relative_var = tk.BooleanVar(value=False)
    recognition_var = tk.BooleanVar(value=False)
    image_path_var = tk.StringVar()
    for kind in ("usuario", "senha", "login"):
        coord_vars[kind] = (tk.StringVar(value="0"), tk.StringVar(value="0"))

    header = tk.Frame(app, bg="#111827")
    header.pack(fill="x", padx=15, pady=(12, 5))
    tk.Label(header, text="⚡", bg="#111827", fg="#60a5fa", font=("Segoe UI", 25, "bold")).pack(side="left")
    tk.Label(header, text=APP_NAME, bg="#111827", fg="white", font=("Segoe UI", 18, "bold")).pack(side="left", padx=8)
    tk.Label(header, text="Automação • Fila", bg="#111827", fg="#9ca3af", font=("Segoe UI", 9)).pack(side="left", padx=10)
    make_button(header, "⌄ MINIMIZAR", minimize_to_tray, "#374151", 13).pack(side="right")

    notebook = ttk.Notebook(app)
    notebook.pack(fill="both", expand=True, padx=10, pady=5)
    build_automation_tab(notebook)
    build_queue_tab(notebook)
    build_log_area(app)

    footer = tk.Frame(app, bg="#111827")
    footer.pack(fill="x", padx=15, pady=(0, 8))
    admin = "SIM" if admin_mode() else "NÃO"
    tk.Label(footer, text=f"Administrador: {admin}   |   Config: {CONFIG_FILE}", bg="#111827", fg="#9ca3af", font=("Segoe UI", 8)).pack(side="left")
    make_button(footer, "Sair", close_app, "#dc2626", 8).pack(side="right")

    app.protocol("WM_DELETE_WINDOW", close_app)
    refresh_windows()
    refresh_automation_list()
    refresh_queue()
    if config.get("automacoes"):
        first = config["automacoes"][0]
        global selected_id
        selected_id = first["id"]
        load_form(first)
        refresh_automation_list(selected_id)
    log("==========================================")
    log(f"{APP_NAME} iniciado.")
    log(f"Automações configuradas: {len(config.get('automacoes', []))}")
    if not admin_mode():
        log("⚠ Programa não está como administrador. Algumas tarefas podem exigir elevação.")
    return app


def auto_mode():
    log("==========================================")
    log("MODO AUTO DO AGENDADOR 2.0")
    log(f"ID recebido: {AUTO_ID}")
    if AUTO_ID:
        a = find_automation(AUTO_ID)
    elif AUTO_INDEX is not None:
        try:
            a = config.get("automacoes", [])[int(AUTO_INDEX)]
        except Exception:
            a = None
    else:
        a = None
    if not a:
        log("✗ A tarefa não corresponde a nenhuma automação configurada.")
        return 1
    if not a.get("ativa", True):
        log("Automação desativada. Encerrando.")
        return 0
    return 0 if execute_automation(a["id"]) else 1


if __name__ == "__main__":
    if MODO_AUTO:
        sys.exit(auto_mode())
    if pyautogui is None or gw is None:
        print("Instale as dependências: pip install pyautogui pygetwindow")
    build_gui()
    log("Gerenciador iniciado pelo próprio aplicativo")
    app.after(2500, prompt_startup_queue)
    app.mainloop()
