import os
import sys
import json
import shutil
import threading
import subprocess
import tempfile
from io import BytesIO
from PIL import Image, ImageOps, ImageSequence

# As bibliotecas gráficas do executável precisam ser localizadas antes de importar Tk.
_interface_cwd = None
_interface_env = {}
if getattr(sys, "frozen", False) and os.path.isdir(os.path.join(getattr(sys, "_MEIPASS", ""), "_tcl_data")):
    _interface_cwd = os.getcwd()
    _interface_env = {nome: os.environ.get(nome) for nome in ("TCL_LIBRARY", "TK_LIBRARY")}
    os.chdir(sys._MEIPASS)
    os.environ["TCL_LIBRARY"] = "_tcl_data"
    os.environ["TK_LIBRARY"] = "_tk_data"

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from tkinterdnd2 import TkinterDnD, DND_FILES
from PyPDF2 import PdfReader, PdfWriter

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")
SUPPORTED_EXTENSIONS = (".pdf", ".doc", ".docx") + IMAGE_EXTENSIONS

# Configuração visual inicial
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Paleta visual (tema escuro em tons de azul)
ACCENT_PRIMARY = "#1D4ED8"
ACCENT_PRIMARY_HOVER = "#1E40AF"
ACCENT_SECONDARY = "#2563EB"
ACCENT_SECONDARY_HOVER = "#1D4ED8"
ACCENT_SUCCESS = "#0EA5E9"
ACCENT_SUCCESS_HOVER = "#0284C7"
TEXT_MUTED = "#93A5C3"
STATUS_OK = "#38BDF8"
STATUS_WARN = "#FBBF24"
STATUS_ERROR = "#F87171"

class TkDnD(ctk.CTk, TkinterDnD.DnDWrapper):
    """Wrapper para permitir Drag and Drop no CustomTkinter"""
    def __init__(self, *args, **kwargs):
        global _interface_cwd
        try:
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
            if _interface_cwd is not None:
                self.tk.call("set", "tcl_library", os.path.join(sys._MEIPASS, "_tcl_data"))
                self.tk.call("set", "tk_library", os.path.join(sys._MEIPASS, "_tk_data"))
        finally:
            if _interface_cwd is not None:
                os.chdir(_interface_cwd)
                _interface_cwd = None
                for nome, valor in _interface_env.items():
                    if valor is None:
                        os.environ.pop(nome, None)
                    else:
                        os.environ[nome] = valor

class ILoveCaioPDF(TkDnD):
    def __init__(self):
        super().__init__()

        self.title("iLoveCaioPDF - Gestão Profissional de Arquivos")
        self.geometry("900x700")
        self.minsize(800, 600)

        self.arquivos = []
        self.processando = False
        self.arquivos_processamento = ()
        self.nivel_processamento = None
        self.compression_level = tk.StringVar(value="Nivel 2 - Equilibrado")

        # Sistema de Configuração e Caminhos
        self.base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        self.app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
        self.search_roots = [self.app_dir]
        if self.base_dir not in self.search_roots:
            self.search_roots.append(self.base_dir)
        self.config_file = os.path.join(self.app_dir, "config.json")
        self.libreoffice_path = None
        self.ghostscript_path = None
        self.qpdf_path = None

        self.setup_ui()

        # Inicia a busca automática em segundo plano ao abrir o app
        self.iniciar_verificacao_ferramentas()

    # ==========================================
    # SISTEMA DE BUSCA E MEMÓRIA (NOVO)
    # ==========================================
    def carregar_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"libreoffice": None, "ghostscript": None}

    def salvar_config(self, config_dict):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_dict, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar config: {e}")

    def buscar_libreoffice(self):
        # 1. Tenta achar na pasta local do projeto (Portable)
        local_candidates = []
        for root_dir in self.search_roots:
            local_candidates.extend([
                os.path.join(root_dir, "LibreOffice", "program", "soffice.exe"),
                os.path.join(root_dir, "LibreOffice", "program", "soffice.com"),
                os.path.join(root_dir, "LibreOffice", "soffice.exe"),
                os.path.join(root_dir, "libreoffice", "program", "soffice.exe"),
                os.path.join(root_dir, "libreoffice", "program", "soffice.com"),
            ])
        for path in local_candidates:
            if os.path.exists(path):
                return path

        # Caso exista pasta "LibreOffice" com estrutura diferente, procura executável nela.
        for root_dir in self.search_roots:
            local_lo_folder = os.path.join(root_dir, "LibreOffice")
            if os.path.isdir(local_lo_folder):
                for root, _, files in os.walk(local_lo_folder):
                    if "soffice.exe" in files:
                        return os.path.join(root, "soffice.exe")
                    if "soffice.com" in files:
                        return os.path.join(root, "soffice.com")

        # 2. Varredura nas pastas padrão do Windows
        program_files = [os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                         os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")]

        for pf in program_files:
            if not os.path.isdir(pf):
                continue

            # Modelo padrão de instalação
            direct_candidates = [
                os.path.join(pf, "LibreOffice", "program", "soffice.exe"),
                os.path.join(pf, "LibreOffice", "program", "soffice.com"),
            ]
            for path in direct_candidates:
                if os.path.exists(path):
                    return path

            # Procura por variações da pasta LibreOffice no nível raiz de Program Files.
            try:
                for entry in os.scandir(pf):
                    if not entry.is_dir():
                        continue
                    if not entry.name.lower().startswith("libreoffice"):
                        continue

                    folder_candidates = [
                        os.path.join(entry.path, "program", "soffice.exe"),
                        os.path.join(entry.path, "program", "soffice.com"),
                        os.path.join(entry.path, "soffice.exe"),
                    ]
                    for path in folder_candidates:
                        if os.path.exists(path):
                            return path
            except PermissionError:
                continue

        return None

    def buscar_ghostscript(self):
        # 1. Tenta achar na pasta local do projeto (Portable)
        for root_dir in self.search_roots:
            for exe in ["gswin64c.exe", "gswin32c.exe"]:
                local_path = os.path.join(root_dir, "Ghostscript", "bin", exe)
                if os.path.exists(local_path):
                    return local_path

        # 2. Varredura nas pastas padrão do Windows
        program_files = [os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                         os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")]

        for pf in program_files:
            gs_folder = os.path.join(pf, "gs")
            if os.path.exists(gs_folder):
                # O GS cria subpastas com a versão (ex: gs10.07.0). Vamos procurar dentro delas.
                for root, dirs, files in os.walk(gs_folder):
                    if "gswin64c.exe" in files:
                        return os.path.join(root, "gswin64c.exe")
                    if "gswin32c.exe" in files:
                        return os.path.join(root, "gswin32c.exe")
        return None

    def buscar_qpdf(self):
        # 1. PATH do sistema
        qpdf_cmd = shutil.which("qpdf")
        if qpdf_cmd:
            return qpdf_cmd

        # 2. Pasta local do projeto (portable)
        local_candidates = []
        for root_dir in self.search_roots:
            local_candidates.extend([
                os.path.join(root_dir, "qpdf", "bin", "qpdf.exe"),
                os.path.join(root_dir, "qpdf.exe"),
            ])
        for path in local_candidates:
            if os.path.exists(path):
                return path

        # 3. Caminhos comuns no Windows
        program_files = [
            os.environ.get("PROGRAMFILES", "C:\\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
        ]
        for pf in program_files:
            if not pf:
                continue
            candidates = [
                os.path.join(pf, "qpdf", "bin", "qpdf.exe"),
                os.path.join(pf, "QPDF", "bin", "qpdf.exe"),
            ]
            for path in candidates:
                if os.path.exists(path):
                    return path

        return None

    def iniciar_verificacao_ferramentas(self):
        # Inicia a thread para não travar a tela
        threading.Thread(target=self._tarefa_verificar_ferramentas, daemon=True).start()

    def _tarefa_verificar_ferramentas(self):
        config = self.carregar_config()
        lo_path = config.get("libreoffice")
        gs_path = config.get("ghostscript")

        # Verifica LibreOffice
        if not lo_path or not os.path.exists(lo_path):
            lo_path = self.buscar_libreoffice()
            config["libreoffice"] = lo_path

        # Verifica Ghostscript
        if not gs_path or not os.path.exists(gs_path):
            gs_path = self.buscar_ghostscript()
            config["ghostscript"] = gs_path

        # Salva as novas descobertas na memória
        self.salvar_config(config)
        self.libreoffice_path = lo_path
        self.ghostscript_path = gs_path
        self.qpdf_path = self.buscar_qpdf()

        # Atualiza a interface gráfica de forma segura
        self.after(0, self.atualizar_status_ui)

    def atualizar_status_ui(self):
        if self.libreoffice_path and os.path.exists(self.libreoffice_path):
            self.status_lo.configure(text="[OK] LibreOffice", text_color=STATUS_OK)
        else:
            self.status_lo.configure(text="[ERRO] LibreOffice (Nao encontrado)", text_color=STATUS_ERROR)

        if self.ghostscript_path and os.path.exists(self.ghostscript_path):
            self.status_gs.configure(text="[OK] Ghostscript", text_color=STATUS_OK)
        else:
            self.status_gs.configure(text="[ERRO] Ghostscript (Nao encontrado)", text_color=STATUS_ERROR)


    # ==========================================
    # INTERFACE GRÁFICA E RESTO DO CÓDIGO
    # ==========================================
    def setup_ui(self):
        self.main_container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)

        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(header_frame, text="iLoveCaioPDF", font=ctk.CTkFont(size=32, weight="bold"), text_color=ACCENT_SECONDARY).pack(side="left")

        status_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        status_frame.pack(side="right")

        # Inicia com o status AMARELO (carregando)
        self.status_lo = ctk.CTkLabel(status_frame, text="[BUSCA] Procurando LibreOffice...", font=ctk.CTkFont(size=12), text_color=STATUS_WARN)
        self.status_lo.pack(side="left", padx=10)
        self.status_gs = ctk.CTkLabel(status_frame, text="[BUSCA] Procurando Ghostscript...", font=ctk.CTkFont(size=12), text_color=STATUS_WARN)
        self.status_gs.pack(side="left", padx=10)

        self.drop_frame = ctk.CTkFrame(self.main_container, height=150, corner_radius=15, border_width=2, border_color=TEXT_MUTED)
        self.drop_frame.pack(fill="x", pady=10)
        self.drop_frame.drop_target_register(DND_FILES)
        self.drop_frame.dnd_bind('<<Drop>>', self.on_drop)

        ctk.CTkLabel(self.drop_frame, text="Arraste e solte seus arquivos aqui", font=ctk.CTkFont(size=18)).place(relx=0.5, rely=0.4, anchor="center")
        ctk.CTkButton(self.drop_frame, text="Selecionar Arquivos", command=self.selecionar_arquivos, fg_color=ACCENT_PRIMARY, hover_color=ACCENT_PRIMARY_HOVER).place(relx=0.5, rely=0.65, anchor="center")

        queue_actions = ctk.CTkFrame(self.main_container, fg_color="transparent")
        queue_actions.pack(fill="x", pady=(5, 0))
        self.queue_label = ctk.CTkLabel(queue_actions, text="Fila vazia", text_color=TEXT_MUTED)
        self.queue_label.pack(side="left")
        self.btn_limpar_fila = ctk.CTkButton(
            queue_actions, text="Limpar fila", command=self.limpar_fila, width=120,
            fg_color=ACCENT_SECONDARY, hover_color=ACCENT_SECONDARY_HOVER, state="disabled"
        )
        self.btn_limpar_fila.pack(side="right")

        self.lista_frame = ctk.CTkFrame(self.main_container)
        self.lista_frame.pack(fill="x", pady=10)

        self.tools_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.tools_frame.pack(fill="x", pady=20)

        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", side="bottom", padx=20, pady=20)

        self.progress_bar = ctk.CTkProgressBar(bottom_frame, mode="indeterminate", progress_color=ACCENT_SECONDARY)
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(bottom_frame, text="Aguardando arquivos...", font=ctk.CTkFont(size=14))
        self.status_label.pack(side="left")

        ctk.CTkButton(bottom_frame, text="Como Funciona", command=self.abrir_ajuda, fg_color=ACCENT_SECONDARY, hover_color=ACCENT_SECONDARY_HOVER, width=120).pack(side="right")

    def on_drop(self, event):
        files = self.tk.splitlist(event.data)
        self.adicionar_arquivos(files)

    def selecionar_arquivos(self):
        if self.processando:
            return
        files = filedialog.askopenfilenames(filetypes=[
            ("Arquivos suportados", "*.pdf *.doc *.docx *.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
            ("PDF", "*.pdf"), ("Word", "*.doc *.docx"),
            ("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
        ])
        if files:
            self.adicionar_arquivos(files)

    def adicionar_arquivos(self, files):
        if self.processando:
            return
        for f in files:
            if f not in self.arquivos and f.lower().endswith(SUPPORTED_EXTENSIONS) and os.path.isfile(f):
                self.arquivos.append(f)
        self.atualizar_lista()
        self.atualizar_ferramentas()

    def limpar_fila(self):
        if self.processando:
            return
        self.arquivos.clear()
        self.atualizar_lista()
        self.atualizar_ferramentas()
        self.status_label.configure(text="Aguardando arquivos...")

    def atualizar_lista(self):
        quantidade = len(self.arquivos)
        self.queue_label.configure(text=f"{quantidade} arquivo(s) na fila" if quantidade else "Fila vazia")
        self.btn_limpar_fila.configure(state="normal" if quantidade and not self.processando else "disabled")
        for widget in self.lista_frame.winfo_children():
            widget.destroy()

        for i, file_path in enumerate(self.arquivos):
            row = ctk.CTkFrame(self.lista_frame, fg_color="transparent")
            row.pack(fill="x", pady=2, padx=10)

            nome_arquivo = os.path.basename(file_path)
            ctk.CTkLabel(row, text=nome_arquivo, width=400, anchor="w").pack(side="left")

            ctk.CTkButton(row, text="❌", width=30, command=lambda idx=i: self.remover_arquivo(idx), fg_color="transparent", text_color="red").pack(side="right")
            ctk.CTkButton(row, text="⬇️", width=30, command=lambda idx=i: self.mover_arquivo(idx, 1), fg_color="transparent").pack(side="right")
            ctk.CTkButton(row, text="⬆️", width=30, command=lambda idx=i: self.mover_arquivo(idx, -1), fg_color="transparent").pack(side="right")

    def remover_arquivo(self, idx):
        if self.processando:
            return
        self.arquivos.pop(idx)
        self.atualizar_lista()
        self.atualizar_ferramentas()

    def mover_arquivo(self, idx, direction):
        if self.processando:
            return
        if 0 <= idx + direction < len(self.arquivos):
            self.arquivos[idx], self.arquivos[idx + direction] = self.arquivos[idx + direction], self.arquivos[idx]
            self.atualizar_lista()

    def atualizar_ferramentas(self):
        for widget in self.tools_frame.winfo_children():
            widget.destroy()

        if self.processando:
            ctk.CTkLabel(self.tools_frame, text="Processando a fila. Aguarde para adicionar ou remover arquivos.",
                         text_color=TEXT_MUTED).pack(pady=10)
            return

        pdfs = [f for f in self.arquivos if f.lower().endswith('.pdf')]
        words = [f for f in self.arquivos if f.lower().endswith(('.doc', '.docx'))]
        imagens = [f for f in self.arquivos if f.lower().endswith(IMAGE_EXTENSIONS)]

        if not self.arquivos:
            return
        if words:
            if len(words) == len(self.arquivos):
                self.montar_ferramenta_converter()
            else:
                ctk.CTkLabel(self.tools_frame,
                    text="Para converter Word, deixe apenas arquivos Word na fila.\n"
                         "Para unir, use PDFs e/ou imagens.", text_color=TEXT_MUTED).pack(pady=10)
            return

        if len(imagens) == len(self.arquivos):
            self.montar_ferramenta_converter_imagens()
        if len(pdfs) + len(imagens) >= 2:
            self.montar_ferramentas_unir()
        elif len(pdfs) == 1:
            self.montar_ferramentas_dividir()
        if len(pdfs) == len(self.arquivos):
            self.montar_ferramenta_compactar()

    def montar_ferramentas_unir(self):
        frame = ctk.CTkFrame(self.tools_frame)
        frame.pack(fill="x", pady=10, ipady=10)
        titulo = "Unir PDFs e imagens" if any(f.lower().endswith(IMAGE_EXTENSIONS) for f in self.arquivos) else "Unir PDFs"
        ctk.CTkLabel(frame, text=titulo, font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.chk_compactar_apos_unir = ctk.CTkCheckBox(frame, text="Compactar após unir")
        self.chk_compactar_apos_unir.pack(pady=5)
        ctk.CTkLabel(frame, text="Nível de compactação:", text_color=TEXT_MUTED).pack(pady=(5, 2))
        ctk.CTkOptionMenu(
            frame,
            values=[
                "Nivel 1 - Leve",
                "Nivel 2 - Equilibrado",
                "Nivel 3 - Potente",
            ],
            variable=self.compression_level,
            fg_color=ACCENT_SECONDARY,
            button_color=ACCENT_SECONDARY_HOVER,
            button_hover_color=ACCENT_PRIMARY_HOVER,
        ).pack(pady=(0, 5))
        ctk.CTkButton(frame, text="Unir Arquivos", command=self.executar_unir, fg_color=ACCENT_PRIMARY, hover_color=ACCENT_PRIMARY_HOVER).pack(pady=10)

    def montar_ferramentas_dividir(self):
        frame = ctk.CTkFrame(self.tools_frame)
        frame.pack(fill="x", pady=10, ipady=10)
        ctk.CTkLabel(frame, text="Dividir PDF", font=ctk.CTkFont(weight="bold")).pack(pady=5)

        self.split_mode = tk.StringVar(value="tudo")
        ctk.CTkRadioButton(frame, text="Tudo (Uma página por arquivo)", variable=self.split_mode, value="tudo").pack(anchor="w", padx=20, pady=5)

        interval_frame = ctk.CTkFrame(frame, fg_color="transparent")
        interval_frame.pack(anchor="w", padx=20, pady=5)
        ctk.CTkRadioButton(interval_frame, text="Intervalo (ex: 1-3,5,8-10): ", variable=self.split_mode, value="intervalo").pack(side="left")
        self.entry_intervalo = ctk.CTkEntry(interval_frame, width=150)
        self.entry_intervalo.pack(side="left", padx=10)

        lote_frame = ctk.CTkFrame(frame, fg_color="transparent")
        lote_frame.pack(anchor="w", padx=20, pady=5)
        ctk.CTkRadioButton(lote_frame, text="Lote (A cada X páginas): ", variable=self.split_mode, value="lote").pack(side="left")
        self.entry_lote = ctk.CTkEntry(lote_frame, width=50)
        self.entry_lote.pack(side="left", padx=10)

        ctk.CTkButton(frame, text="Dividir Arquivo", command=self.executar_dividir, fg_color=ACCENT_PRIMARY, hover_color=ACCENT_PRIMARY_HOVER).pack(pady=10)

    def montar_ferramenta_converter(self):
        frame = ctk.CTkFrame(self.tools_frame)
        frame.pack(fill="x", pady=10, ipady=10)
        ctk.CTkLabel(frame, text="Converter Word para PDF", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        ctk.CTkButton(frame, text="Converter Arquivos", command=self.executar_converter, fg_color=ACCENT_SECONDARY, hover_color=ACCENT_SECONDARY_HOVER).pack(pady=10)

    def montar_ferramenta_compactar(self):
        frame = ctk.CTkFrame(self.tools_frame)
        frame.pack(fill="x", pady=10, ipady=10)
        ctk.CTkLabel(frame, text="Compactar PDF (Ghostscript)", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        ctk.CTkLabel(frame, text="Nível de compactação:", text_color=TEXT_MUTED).pack(pady=(5, 2))
        ctk.CTkOptionMenu(
            frame,
            values=[
                "Nivel 1 - Leve",
                "Nivel 2 - Equilibrado",
                "Nivel 3 - Potente",
            ],
            variable=self.compression_level,
            fg_color=ACCENT_SECONDARY,
            button_color=ACCENT_SECONDARY_HOVER,
            button_hover_color=ACCENT_PRIMARY_HOVER,
        ).pack(pady=(0, 5))
        ctk.CTkButton(frame, text="Compactar Arquivo(s)", command=self.executar_compactar, fg_color=ACCENT_SUCCESS, hover_color=ACCENT_SUCCESS_HOVER).pack(pady=10)

    def iniciar_processo(self, mensagem, funcao_alvo):
        if self.processando:
            return
        self.processando = True
        self.arquivos_processamento = tuple(self.arquivos)
        self.nivel_processamento = self.compression_level.get()
        self.btn_limpar_fila.configure(state="disabled")
        self.atualizar_ferramentas()
        self.status_label.configure(text=mensagem)
        self.progress_bar.pack(fill="x", pady=(10, 0))
        self.progress_bar.start()
        threading.Thread(target=funcao_alvo, daemon=True).start()

    def _arquivos_em_processamento(self):
        return self.arquivos_processamento if self.processando else tuple(self.arquivos)

    def _encerrar_processo(self):
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.processando = False
        self.arquivos_processamento = ()
        self.nivel_processamento = None
        self.atualizar_lista()
        self.atualizar_ferramentas()

    def finalizar_processo(self, mensagem_sucesso):
        self._encerrar_processo()
        self.status_label.configure(text=mensagem_sucesso)
        messagebox.showinfo("Concluído", mensagem_sucesso)

    def finalizar_erro(self, titulo, mensagem):
        self._encerrar_processo()
        self.status_label.configure(text="Não foi possível concluir. Confira a mensagem de erro.")
        messagebox.showerror(titulo, mensagem)

    def montar_ferramenta_converter_imagens(self):
        frame = ctk.CTkFrame(self.tools_frame)
        frame.pack(fill="x", pady=10, ipady=10)
        ctk.CTkLabel(frame, text="Converter imagens para PDF", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        ctk.CTkLabel(frame, text="Cria um PDF separado para cada imagem ou arquivo de imagens.",
                     text_color=TEXT_MUTED).pack(pady=5)
        ctk.CTkButton(frame, text="Converter imagens", command=self.executar_converter_imagens,
                      fg_color=ACCENT_SECONDARY, hover_color=ACCENT_SECONDARY_HOVER).pack(pady=10)

    def executar_converter_imagens(self):
        if self.processando or not self.arquivos or not all(
                f.lower().endswith(IMAGE_EXTENSIONS) for f in self.arquivos):
            return
        destino = filedialog.askdirectory(title="Onde salvar os PDFs das imagens?")
        if destino:
            self.iniciar_processo("Convertendo imagens para PDF...", lambda: self._tarefa_converter_imagens(destino))

    def _imagem_para_pdf(self, caminho):
        """Converte em memória, corrige rotação da câmera e usa fundo branco em transparências."""
        paginas = []
        try:
            with Image.open(caminho) as imagem:
                for frame in ImageSequence.Iterator(imagem):
                    pagina = ImageOps.exif_transpose(frame)
                    if pagina.mode in ("RGBA", "LA") or "transparency" in pagina.info:
                        rgba = pagina.convert("RGBA")
                        try:
                            rgb = Image.new("RGB", rgba.size, "white")
                            rgb.paste(rgba, mask=rgba.getchannel("A"))
                        finally:
                            rgba.close()
                    else:
                        rgb = pagina.convert("RGB")
                    paginas.append(rgb)
            if not paginas:
                raise ValueError("A imagem não contém páginas.")
            saida = BytesIO()
            paginas[0].save(saida, format="PDF", save_all=True, append_images=paginas[1:],
                            resolution=150.0, quality=95)
            saida.seek(0)
            return saida
        finally:
            for pagina in paginas:
                pagina.close()

    def _destino_pdf_disponivel(self, destino, nome_base):
        caminho = os.path.join(destino, nome_base + ".pdf")
        numero = 2
        while os.path.exists(caminho):
            caminho = os.path.join(destino, f"{nome_base}_{numero}.pdf")
            numero += 1
        return caminho

    def _tarefa_converter_imagens(self, destino):
        arquivos = self._arquivos_em_processamento()
        erros = []
        convertidos = 0
        for indice, caminho in enumerate(arquivos, 1):
            mensagem = f"Convertendo imagem {indice} de {len(arquivos)}..."
            self.after(0, lambda msg=mensagem: self.status_label.configure(text=msg))
            temporario = None
            try:
                nome = os.path.splitext(os.path.basename(caminho))[0]
                output_path = self._destino_pdf_disponivel(destino, nome)
                with self._imagem_para_pdf(caminho) as pdf:
                    with tempfile.NamedTemporaryFile(dir=destino, suffix=".pdf", delete=False) as out:
                        temporario = out.name
                        out.write(pdf.getbuffer())
                os.replace(temporario, output_path)
                temporario = None
                convertidos += 1
            except Exception as erro:
                erros.append(f"{os.path.basename(caminho)}: {erro}")
            finally:
                if temporario and os.path.exists(temporario):
                    os.remove(temporario)
        mensagem = f"{convertidos} de {len(arquivos)} arquivo(s) convertido(s) para PDF."
        if erros:
            detalhe = mensagem + "\n\nArquivos com erro:\n" + "\n".join(erros)
            self.after(0, lambda msg=detalhe: self.finalizar_erro("Conversão de imagens", msg))
        else:
            self.after(0, lambda msg=mensagem: self.finalizar_processo(msg))

    def executar_unir(self):
        if self.processando or len(self.arquivos) < 2 or not all(
                f.lower().endswith((".pdf",) + IMAGE_EXTENSIONS) for f in self.arquivos):
            return
        if self.chk_compactar_apos_unir.get() and (
                not self.ghostscript_path or not os.path.exists(self.ghostscript_path)):
            messagebox.showerror("Erro", "Ghostscript não foi localizado. Desmarque a compactação para apenas unir.")
            return
        destino = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")], title="Salvar PDF Unido Como...")
        if not destino: return
        compactar = self.chk_compactar_apos_unir.get()
        self.iniciar_processo("Unindo PDFs...", lambda: self._tarefa_unir(destino, compactar))

    def _tarefa_unir(self, destino, compactar):
        temp_path = None
        leitores = []
        buffers = []
        try:
            merger = PdfWriter()
            arquivos = self._arquivos_em_processamento()
            for indice, caminho in enumerate(arquivos, 1):
                mensagem = f"Unindo arquivo {indice} de {len(arquivos)}..."
                self.after(0, lambda msg=mensagem: self.status_label.configure(text=msg))
                if caminho.lower().endswith(IMAGE_EXTENSIONS):
                    buffer = self._imagem_para_pdf(caminho)
                    buffers.append(buffer)
                    leitor = PdfReader(buffer)
                else:
                    leitor = PdfReader(caminho)
                leitores.append(leitor)
                for pagina in leitor.pages:
                    merger.add_page(pagina)

            with tempfile.NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(destino)),
                                             suffix=".pdf", delete=False) as saida:
                temp_path = saida.name
                merger.write(saida)

            if compactar:
                self.after(0, lambda: self.status_label.configure(text="Compactando PDF unido..."))
                compactou, original_bytes, final_bytes = self._tarefa_compactar_arquivo(temp_path, destino)
                if compactou:
                    reducao_kb = max(0, (original_bytes - final_bytes) // 1024)
                    msg = f"Arquivos unidos e compactados com sucesso! ({reducao_kb} KB reduzidos)"
                else:
                    msg = "Arquivos unidos com sucesso! A compactação não reduziu o tamanho e foi ignorada."
            else:
                os.replace(temp_path, destino)
                temp_path = None
                msg = "Arquivos unidos com sucesso!"

            self.after(0, lambda mensagem=msg: self.finalizar_processo(mensagem))
        except Exception as erro:
            self.after(0, lambda mensagem=str(erro): self.finalizar_erro("Erro na união", mensagem))
        finally:
            for buffer in buffers:
                buffer.close()
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def executar_dividir(self):
        if self.processando:
            return
        pasta_destino = filedialog.askdirectory(title="Selecione a pasta para salvar os PDFs")
        if not pasta_destino: return
        modo = self.split_mode.get()
        param = self.entry_intervalo.get() if modo == "intervalo" else self.entry_lote.get()
        self.iniciar_processo("Dividindo PDF...", lambda: self._tarefa_dividir(pasta_destino, modo, param))

    def _tarefa_dividir(self, destino, modo, param):
        try:
            arquivo = self._arquivos_em_processamento()[0]
            nome_base = os.path.splitext(os.path.basename(arquivo))[0]
            leitor = PdfReader(arquivo)
            total_paginas = len(leitor.pages)

            if modo == "tudo":
                for i in range(total_paginas):
                    writer = PdfWriter()
                    writer.add_page(leitor.pages[i])
                    with open(os.path.join(destino, f"{nome_base}_pag_{i+1}.pdf"), "wb") as out:
                        writer.write(out)

            elif modo == "intervalo":
                paginas = set()
                partes = param.split(',')
                for parte in partes:
                    parte = parte.strip()
                    if '-' in parte:
                        inicio, fim = map(int, parte.split('-'))
                        paginas.update(range(inicio, fim + 1))
                    else:
                        paginas.add(int(parte))

                writer = PdfWriter()
                for p in sorted(list(paginas)):
                    if 1 <= p <= total_paginas:
                        writer.add_page(leitor.pages[p-1])
                with open(os.path.join(destino, f"{nome_base}_extraido.pdf"), "wb") as out:
                    writer.write(out)

            elif modo == "lote":
                passo = int(param)
                for i in range(0, total_paginas, passo):
                    writer = PdfWriter()
                    for j in range(i, min(i + passo, total_paginas)):
                        writer.add_page(leitor.pages[j])
                    with open(os.path.join(destino, f"{nome_base}_lote_{i+1}-{min(i + passo, total_paginas)}.pdf"), "wb") as out:
                        writer.write(out)

            self.after(0, lambda: self.finalizar_processo("PDF dividido com sucesso!"))
        except Exception as e:
            self.after(0, lambda mensagem=str(e): self.finalizar_erro("Erro", mensagem))

    def executar_converter(self):
        if self.processando:
            return
        if not self.libreoffice_path or not os.path.exists(self.libreoffice_path):
            messagebox.showerror("Erro", "LibreOffice não foi localizado no sistema.")
            return
        pasta_destino = filedialog.askdirectory(title="Onde salvar os PDFs convertidos?")
        if not pasta_destino: return
        self.iniciar_processo("Convertendo para PDF...", lambda: self._tarefa_converter(pasta_destino))

    def _tarefa_converter(self, destino):
        try:
            for word_file in self._arquivos_em_processamento():
                comando = [
                    self.libreoffice_path, "--headless", "--convert-to", "pdf",
                    word_file, "--outdir", destino
                ]
                subprocess.run(comando, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.after(0, lambda: self.finalizar_processo("Arquivos convertidos com sucesso!"))
        except Exception as e:
            self.after(0, lambda mensagem=str(e): self.finalizar_erro("Erro na conversão", mensagem))

    def executar_compactar(self):
        if self.processando:
            return
        if not self.ghostscript_path or not os.path.exists(self.ghostscript_path):
            messagebox.showerror("Erro", "Ghostscript não foi localizado no sistema.")
            return
        pasta_destino = filedialog.askdirectory(title="Selecione a pasta para salvar os PDFs compactados")
        if not pasta_destino: return
        self.iniciar_processo("Compactando PDFs...", lambda: self._tarefa_compactar_lote(pasta_destino))

    def _obter_perfil_compactacao(self):
        nivel = self.nivel_processamento if self.processando else self.compression_level.get()
        perfis = {
            "Nivel 1 - Leve": {"pdfsettings": "/printer", "dpi": 170, "jpegq": 78, "potente": False},
            "Nivel 2 - Equilibrado": {"pdfsettings": "/ebook", "dpi": 135, "jpegq": 60, "potente": False},
            "Nivel 3 - Potente": {"pdfsettings": "/screen", "dpi": 105, "jpegq": 42, "potente": True},
        }
        return perfis.get(nivel, perfis["Nivel 2 - Equilibrado"])

    def _eh_pdf_texto_predominante(self, input_path, paginas_teste=5):
        """Detecta PDFs de texto para usar perfil de compactação adequado."""
        try:
            leitor = PdfReader(input_path)
            total = min(len(leitor.pages), paginas_teste)
            if total == 0:
                return False

            paginas_com_texto = 0
            for i in range(total):
                texto = leitor.pages[i].extract_text() or ""
                if len(texto.strip()) >= 120:
                    paginas_com_texto += 1

            # Considera texto predominante quando maioria das páginas tem texto extraível.
            return paginas_com_texto >= max(1, int(total * 0.6))
        except Exception:
            return False

    def _otimizar_pdf_texto_lossless(self, input_path, output_path):
        """
        Otimização sem perda para PDFs de texto:
        recomprime streams de conteúdo e remove metadados inchados.
        """
        leitor = PdfReader(input_path)
        escritor = PdfWriter()
        for pagina in leitor.pages:
            try:
                pagina.compress_content_streams()
            except Exception:
                pass
            escritor.add_page(pagina)

        # Metadados costumam inflar alguns PDFs de escritório.
        try:
            escritor.add_metadata({})
        except Exception:
            pass

        with open(output_path, "wb") as out:
            escritor.write(out)

    def _executar_qpdf_otimizacao(self, input_path, output_path):
        """
        Otimizacao estrutural com qpdf (sem alterar visual do PDF).
        Retorna True quando a execução for bem-sucedida.
        """
        if not self.qpdf_path:
            return False

        comandos = [
            [
                self.qpdf_path,
                "--stream-data=compress",
                "--recompress-flate",
                "--compression-level=9",
                "--object-streams=generate",
                input_path,
                output_path,
            ],
            [
                self.qpdf_path,
                "--stream-data=compress",
                "--recompress-flate",
                "--object-streams=generate",
                input_path,
                output_path,
            ],
        ]

        for comando in comandos:
            try:
                subprocess.run(comando, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                return os.path.exists(output_path)
            except Exception:
                continue
        return False

    def _executar_ghostscript_compactacao(self, input_path, output_path, perfil, forcar_cinza=False, texto_predominante=False):
        comando = [
            self.ghostscript_path,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={perfil['pdfsettings']}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-dSubsetFonts=true",
            "-dAutoFilterColorImages=false",
            "-dAutoFilterGrayImages=false",
            "-dColorImageFilter=/DCTEncode",
            "-dGrayImageFilter=/DCTEncode",
            f"-dJPEGQ={perfil['jpegq']}",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dDownsampleMonoImages=true",
            "-dColorImageDownsampleType=/Bicubic",
            "-dGrayImageDownsampleType=/Bicubic",
            "-dMonoImageDownsampleType=/Subsample",
            f"-dColorImageResolution={perfil['dpi']}",
            f"-dGrayImageResolution={perfil['dpi']}",
            "-dMonoImageResolution=200",
        ]

        if texto_predominante:
            # Para texto, evita agressividade que não ajuda e pode piorar.
            comando.extend([
                "-dFastWebView=true",
                "-dEmbedAllFonts=true",
                "-dPreserveAnnots=true",
            ])

        if forcar_cinza:
            comando.extend([
                "-sProcessColorModel=DeviceGray",
                "-sColorConversionStrategy=Gray",
                "-dOverrideICC=true",
            ])

        comando.extend([
            f"-sOutputFile={output_path}",
            input_path,
        ])
        subprocess.run(comando, check=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def _tarefa_compactar_arquivo(self, input_path, output_path):
        perfil = self._obter_perfil_compactacao()
        texto_predominante = self._eh_pdf_texto_predominante(input_path)
        candidatos = []

        # 1) Texto: otimização lossless primeiro (costuma funcionar melhor sem perder qualidade).
        if texto_predominante:
            temp_texto = output_path + ".text.tmp"
            try:
                self._otimizar_pdf_texto_lossless(input_path, temp_texto)
                candidatos.append(temp_texto)
            except Exception:
                if os.path.exists(temp_texto):
                    os.remove(temp_texto)

            # qpdf costuma ser eficiente em PDFs com muito texto/estrutura.
            temp_qpdf = output_path + ".qpdf.tmp"
            if self._executar_qpdf_otimizacao(input_path, temp_qpdf):
                candidatos.append(temp_qpdf)

        # 2) Compactação Ghostscript no arquivo original.
        temp_output = output_path + ".tmp"
        self._executar_ghostscript_compactacao(input_path, temp_output, perfil, texto_predominante=texto_predominante)
        candidatos.append(temp_output)

        # 3) Se texto e nível potente, roda GS também em cima do arquivo lossless.
        if texto_predominante and perfil.get("potente"):
            temp_texto_gs = output_path + ".textgs.tmp"
            if any(c.endswith(".text.tmp") for c in candidatos):
                base_texto = [c for c in candidatos if c.endswith(".text.tmp")][0]
                self._executar_ghostscript_compactacao(base_texto, temp_texto_gs, perfil, texto_predominante=True)
                candidatos.append(temp_texto_gs)

            # Se qpdf existir, tenta otimizar também o resultado de texto lossless.
            if any(c.endswith(".text.tmp") for c in candidatos):
                base_texto = [c for c in candidatos if c.endswith(".text.tmp")][0]
                temp_texto_qpdf = output_path + ".textqpdf.tmp"
                if self._executar_qpdf_otimizacao(base_texto, temp_texto_qpdf):
                    candidatos.append(temp_texto_qpdf)

        # 4) Se não for texto e nível potente, tenta uma segunda passada em cinza.
        if (not texto_predominante) and perfil.get("potente"):
            temp_gray = output_path + ".gray.tmp"
            self._executar_ghostscript_compactacao(input_path, temp_gray, perfil, forcar_cinza=True, texto_predominante=False)
            candidatos.append(temp_gray)

        # Escolhe o menor resultado entre os candidatos gerados.
        melhor_saida = min(candidatos, key=os.path.getsize)
        menor_tamanho = os.path.getsize(melhor_saida)

        tamanho_original = os.path.getsize(input_path)
        tamanho_compactado = menor_tamanho

        # Evita regressão: se compactação não ajudar, mantém o original.
        if tamanho_compactado >= tamanho_original:
            shutil.copy2(input_path, output_path)
            for arquivo_tmp in candidatos:
                if os.path.exists(arquivo_tmp):
                    os.remove(arquivo_tmp)
            return False, tamanho_original, tamanho_original

        os.replace(melhor_saida, output_path)
        for arquivo_tmp in candidatos:
            if arquivo_tmp != melhor_saida and os.path.exists(arquivo_tmp):
                os.remove(arquivo_tmp)
        return True, tamanho_original, tamanho_compactado

    def _tarefa_compactar_lote(self, destino):
        try:
            arquivos_reduzidos = 0
            total_reducao_bytes = 0
            for pdf_file in self._arquivos_em_processamento():
                nome_base = os.path.basename(pdf_file)
                output_path = os.path.join(destino, f"compactado_{nome_base}")
                compactou, original_bytes, final_bytes = self._tarefa_compactar_arquivo(pdf_file, output_path)
                if compactou:
                    arquivos_reduzidos += 1
                    total_reducao_bytes += (original_bytes - final_bytes)

            if arquivos_reduzidos > 0:
                reducao_mb = total_reducao_bytes / (1024 * 1024)
                mensagem = f"Compactação finalizada! {arquivos_reduzidos} arquivo(s) reduzidos ({reducao_mb:.2f} MB no total)."
            else:
                mensagem = "Compactação concluída sem ganhos de tamanho. Os arquivos originais foram preservados."

            self.after(0, lambda: self.finalizar_processo(mensagem))
        except Exception as e:
            self.after(0, lambda mensagem=str(e): self.finalizar_erro("Erro na compactação", mensagem))

    def abrir_ajuda(self):
        help_win = ctk.CTkToplevel(self)
        help_win.title("Como Funciona - iLoveCaioPDF")
        help_win.geometry("500x600")
        help_win.transient(self)

        texto = """COMO USAR

1. Adicionar
Arraste PDFs, Word ou imagens, ou use “Selecionar Arquivos”.
Use “Limpar fila” para remover todos de uma vez.

2. Unir PDFs
Adicione 2 ou mais PDFs e/ou imagens e clique em “Unir”.
As imagens viram páginas de PDF na ordem da fila.
Use os botões de mover para organizar a ordem correta dos arquivos

3. Dividir PDF
Adicione apenas 1 PDF
- Tudo: Cria um arquivo para cada página
- Intervalo: Extrai páginas específicas (Ex: 1-5, 8, 11-13)
- Lote: Divide o PDF a cada X páginas

4. Converter
Adicione arquivos Word (.doc ou .docx) e clique em “Converter”

5. Converter imagens
Deixe apenas imagens na fila e clique em “Converter imagens”.
Cada arquivo vira um PDF separado. Nomes repetidos recebem um número.
Formatos: JPG, JPEG, PNG, BMP, WEBP e TIFF.

6. Compactar
Adicione PDFs e clique em “Compactar”

Desenvolvido por:
Caio Pedro Neto Xavier
"""
        textbox = ctk.CTkTextbox(help_win, width=460, height=560, font=ctk.CTkFont(size=14))
        textbox.pack(padx=20, pady=20)
        textbox.insert("0.0", texto)
        textbox.configure(state="disabled")

if __name__ == "__main__":
    app = ILoveCaioPDF()
    app.mainloop()
