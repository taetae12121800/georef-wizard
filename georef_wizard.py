"""
GeoRef Wizard
=============
Step-by-step georeferencing tool.
Combines PDF control point picking, TIFF extraction, and georeferencing.

Requirements:
    pip install pymupdf Pillow rasterio numpy

Steps:
    1. Load PDF
    2. Pick Control Points
    3. Extract TIFFs
    4. Georeference
    5. Results
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
try:
    import fitz
except ImportError:
    import pymupdf as fitz
from PIL import Image, ImageTk
import os

# ── Constants ─────────────────────────────────────────────────────────────────
BG          = "#0F1117"
SURFACE     = "#1A1D27"
SURFACE2    = "#22263A"
ACCENT      = "#4E9EFF"
ACCENT2     = "#7B61FF"
SUCCESS     = "#3DDC84"
WARNING     = "#FFB347"
DANGER      = "#FF5C5C"
TEXT        = "#E8EAF0"
TEXT_DIM    = "#6B7280"
BORDER      = "#2D3148"
THUMB_W     = 130
THUMB_H     = 170

STEPS = [
    ("1", "Load PDF",           "Open your map PDF"),
    ("2", "Control Points",     "Click points on each sheet"),
    ("3", "Extract TIFFs",      "Convert pages to images"),
    ("4", "Georeference",       "Warp images to real world"),
    ("5", "Results",            "Review and export"),
]


# ── Wizard Shell ──────────────────────────────────────────────────────────────
class GeoRefWizard:
    def __init__(self, root):
        self.root         = root
        self.root.title("GeoRef Wizard")
        self.root.configure(bg=BG)
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        self.current_step = 0
        self.step_frames  = []

        # ── Shared state passed between steps ─────────────────────────────────
        self.pdf_doc        = None       # fitz document
        self.pdf_path       = ""         # full path to PDF
        self.pdf_name       = ""         # filename without extension
        self.selected_pages = []         # list of page numbers (1-based) to process
        self.control_points = []         # all CPs across all pages
        self.tiff_paths     = {}         # page_num → raw tiff path
        self.georef_paths   = {}         # page_num → georeferenced tiff path
        self.rms_scores     = {}         # page_num → rms float

        self._build_ui()
        self._show_step(0)

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=SURFACE, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="⬡  GeoRef Wizard",
                 bg=SURFACE, fg=TEXT,
                 font=("Courier New", 15, "bold")).pack(side="left", padx=24, pady=16)

        self.header_subtitle = tk.Label(header, text="",
                                         bg=SURFACE, fg=TEXT_DIM,
                                         font=("Courier New", 10))
        self.header_subtitle.pack(side="left", padx=8, pady=16)

        # ── Step indicator bar ────────────────────────────────────────────────
        self._build_step_bar()

        # ── Body ──────────────────────────────────────────────────────────────
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)

        # Left sidebar — step list
        self._build_sidebar()

        # Main content area
        self.content_area = tk.Frame(self.body, bg=BG)
        self.content_area.pack(side="left", fill="both", expand=True)

        # Build placeholder frames for each step
        self._build_step_placeholders()

        # ── Footer / navigation ───────────────────────────────────────────────
        self._build_footer()

    def _build_step_bar(self):
        """Horizontal progress strip under the header."""
        bar = tk.Frame(self.root, bg=SURFACE2, height=48)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bg=SURFACE2)
        inner.pack(expand=True, fill="both")

        self.step_bar_labels = []

        for i, (num, title, _) in enumerate(STEPS):
            cell = tk.Frame(inner, bg=SURFACE2)
            cell.pack(side="left", expand=True, fill="both")

            # Connector line (not before first)
            if i > 0:
                tk.Frame(cell, bg=BORDER, height=2).pack(
                    side="left", fill="x", expand=True, pady=22)

            # Circle + label
            bubble_frame = tk.Frame(cell, bg=SURFACE2)
            bubble_frame.pack(side="left", padx=4)

            bubble = tk.Label(bubble_frame, text=num,
                              bg=BORDER, fg=TEXT_DIM,
                              font=("Courier New", 9, "bold"),
                              width=3, height=1,
                              relief="flat")
            bubble.pack()

            lbl = tk.Label(bubble_frame, text=title,
                           bg=SURFACE2, fg=TEXT_DIM,
                           font=("Courier New", 8))
            lbl.pack()

            # Connector line (not after last)
            if i < len(STEPS) - 1:
                tk.Frame(cell, bg=BORDER, height=2).pack(
                    side="left", fill="x", expand=True, pady=22)

            self.step_bar_labels.append((bubble, lbl))

    def _build_sidebar(self):
        """Left panel showing all steps with status icons."""
        sidebar = tk.Frame(self.body, bg=SURFACE, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="STEPS",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 9, "bold")).pack(
                     anchor="w", padx=20, pady=(20, 8))

        self.sidebar_items = []

        for i, (num, title, subtitle) in enumerate(STEPS):
            btn = tk.Frame(sidebar, bg=SURFACE, cursor="hand2")
            btn.pack(fill="x", padx=12, pady=2)

            # Status dot
            dot = tk.Label(btn, text="○",
                           bg=SURFACE, fg=TEXT_DIM,
                           font=("Courier New", 12))
            dot.pack(side="left", padx=(8, 6), pady=8)

            # Text
            text_frame = tk.Frame(btn, bg=SURFACE)
            text_frame.pack(side="left", fill="x", expand=True)

            title_lbl = tk.Label(text_frame, text=f"{num}. {title}",
                                  bg=SURFACE, fg=TEXT_DIM,
                                  font=("Courier New", 9, "bold"),
                                  anchor="w")
            title_lbl.pack(anchor="w")

            sub_lbl = tk.Label(text_frame, text=subtitle,
                                bg=SURFACE, fg=TEXT_DIM,
                                font=("Courier New", 7),
                                anchor="w")
            sub_lbl.pack(anchor="w")

            # Click to jump (only to completed or current)
            idx = i
            for w in (btn, dot, title_lbl, sub_lbl, text_frame):
                w.bind("<Button-1>", lambda e, s=idx: self._try_jump(s))

            self.sidebar_items.append((btn, dot, title_lbl, sub_lbl))

        # Divider
        tk.Frame(sidebar, bg=BORDER, height=1).pack(
            fill="x", padx=12, pady=16)

        # Info box
        self.info_box = tk.Label(sidebar,
                                  text="Open a PDF to begin.",
                                  bg=SURFACE2, fg=TEXT_DIM,
                                  font=("Courier New", 8),
                                  wraplength=180, justify="left",
                                  padx=12, pady=10)
        self.info_box.pack(fill="x", padx=12, pady=4)

    def _build_step_placeholders(self):
        self.step_frames = []

        # Step 1 — real implementation
        self.step_frames.append(self._build_step1())

        # Step 2 — real CP picker
        self.step_frames.append(self._build_step2())

        # Step 3 — real TIFF extractor
        self.step_frames.append(self._build_step3())

        # Step 4 — real georeferencer
        self.step_frames.append(self._build_step4())

        # Step 5 — real results screen
        self.step_frames.append(self._build_step5())

    # ── Step 1 — Load PDF ─────────────────────────────────────────────────────
    def _build_step1(self):
        frame = tk.Frame(self.content_area, bg=BG)

        # Heading
        head = tk.Frame(frame, bg=BG)
        head.pack(fill="x", padx=40, pady=(40, 8))
        tk.Label(head, text="Step 1  —  Load PDF",
                 bg=BG, fg=TEXT,
                 font=("Courier New", 18, "bold")).pack(anchor="w")
        tk.Label(head, text="Open your map PDF and select the sheets you want to georeference",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 10)).pack(anchor="w", pady=(4,0))
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=40, pady=16)

        # Body — two columns
        body = tk.Frame(frame, bg=BG)
        body.pack(fill="both", expand=True, padx=40, pady=(0, 40))

        # Left — open button + file info
        left = tk.Frame(body, bg=BG, width=280)
        left.pack(side="left", fill="y", padx=(0, 20))
        left.pack_propagate(False)

        open_btn = tk.Button(left,
                             text="📂   Open PDF",
                             command=self._step1_open_pdf,
                             bg=ACCENT, fg=BG,
                             font=("Courier New", 11, "bold"),
                             relief="flat", pady=12, padx=20,
                             cursor="hand2")
        open_btn.pack(fill="x", pady=(0, 16))
        open_btn.bind("<Enter>", lambda e: open_btn.config(bg=ACCENT2))
        open_btn.bind("<Leave>", lambda e: open_btn.config(bg=ACCENT))

        # File info card
        self.s1_info_card = tk.Frame(left, bg=SURFACE, pady=16, padx=16)
        self.s1_info_card.pack(fill="x")

        tk.Label(self.s1_info_card, text="NO FILE LOADED",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 9, "bold")).pack(anchor="w")

        self.s1_filename_lbl = tk.Label(self.s1_info_card, text="—",
                                         bg=SURFACE, fg=TEXT,
                                         font=("Courier New", 10),
                                         wraplength=230, justify="left")
        self.s1_filename_lbl.pack(anchor="w", pady=(4,0))

        self.s1_pages_lbl = tk.Label(self.s1_info_card, text="",
                                      bg=SURFACE, fg=TEXT_DIM,
                                      font=("Courier New", 9))
        self.s1_pages_lbl.pack(anchor="w", pady=(4,0))

        tk.Frame(self.s1_info_card, bg=BORDER, height=1).pack(fill="x", pady=12)

        tk.Label(self.s1_info_card, text="SELECTED PAGES",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w")

        self.s1_selected_lbl = tk.Label(self.s1_info_card, text="None selected",
                                         bg=SURFACE, fg=TEXT_DIM,
                                         font=("Courier New", 9),
                                         wraplength=230, justify="left")
        self.s1_selected_lbl.pack(anchor="w", pady=(4,0))

        # Select all / none buttons
        sel_row = tk.Frame(left, bg=BG)
        sel_row.pack(fill="x", pady=(12,0))

        self._small_btn(sel_row, "Select All",
                        self._step1_select_all, SURFACE2).pack(side="left", padx=(0,6))
        self._small_btn(sel_row, "Clear All",
                        self._step1_clear_all, SURFACE2).pack(side="left")

        # Right — scrollable thumbnail grid
        right = tk.Frame(body, bg=SURFACE)
        right.pack(side="left", fill="both", expand=True)

        # Empty state
        self.s1_empty = tk.Frame(right, bg=SURFACE)
        self.s1_empty.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(self.s1_empty,
                 text="📄",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 36)).pack()
        tk.Label(self.s1_empty,
                 text="Open a PDF to see\npage thumbnails here",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 10),
                 justify="center").pack(pady=8)

        # Thumbnail canvas
        self.s1_thumb_canvas = tk.Canvas(right, bg=SURFACE,
                                          highlightthickness=0)
        self.s1_thumb_sb = tk.Scrollbar(right, orient="horizontal",
                                         command=self.s1_thumb_canvas.xview)
        self.s1_thumb_canvas.configure(xscrollcommand=self.s1_thumb_sb.set)

        self.s1_thumb_inner = tk.Frame(self.s1_thumb_canvas, bg=SURFACE)
        self.s1_thumb_canvas.create_window((0,0), window=self.s1_thumb_inner,
                                            anchor="nw")
        self.s1_thumb_inner.bind("<Configure>",
            lambda e: self.s1_thumb_canvas.configure(
                scrollregion=self.s1_thumb_canvas.bbox("all")))

        # Mousewheel scrolls horizontally on thumb canvas
        def _hscroll(event):
            self.s1_thumb_canvas.xview_scroll(int(-1*(event.delta/120)), "units")
        self.s1_thumb_canvas.bind("<MouseWheel>", _hscroll)
        self.s1_thumb_inner.bind("<MouseWheel>", _hscroll)

        # State for step 1
        self._s1_thumb_images  = []
        self._s1_page_vars     = []   # BooleanVar per page
        self._s1_thumb_frames  = []   # frame widgets for highlight

        return frame

    # ── Step 1 Actions ────────────────────────────────────────────────────────
    def _step1_open_pdf(self):
        path = filedialog.askopenfilename(
            title="Select PDF Map",
            filetypes=[("PDF files", "*.pdf")]
        )
        if not path:
            return

        self.pdf_path  = path
        self.pdf_doc   = fitz.open(path)
        self.pdf_name  = os.path.splitext(os.path.basename(path))[0]

        total = len(self.pdf_doc)
        self.s1_filename_lbl.config(text=os.path.basename(path))
        self.s1_pages_lbl.config(text=f"{total} pages total")

        # Hide empty state, show canvas
        self.s1_empty.place_forget()
        self.s1_thumb_canvas.pack(fill="both", expand=True, padx=8, pady=(8,0))
        self.s1_thumb_sb.pack(fill="x", padx=8, pady=(0,8))

        self._step1_build_thumbs()
        self._step1_update_selection_label()

    def _step1_build_thumbs(self):
        # Clear old
        for w in self.s1_thumb_inner.winfo_children():
            w.destroy()
        self._s1_thumb_images.clear()
        self._s1_page_vars.clear()
        self._s1_thumb_frames.clear()

        for i in range(len(self.pdf_doc)):
            page = self.pdf_doc[i]
            mat  = fitz.Matrix(0.25, 0.25)
            pix  = page.get_pixmap(matrix=mat)
            img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img.thumbnail((THUMB_W, THUMB_H))
            tk_img = ImageTk.PhotoImage(img)
            self._s1_thumb_images.append(tk_img)

            var = tk.BooleanVar(value=False)
            self._s1_page_vars.append(var)

            # Card
            card = tk.Frame(self.s1_thumb_inner, bg=SURFACE2,
                            padx=6, pady=6, cursor="hand2")
            card.pack(side="left", padx=8, pady=12)
            self._s1_thumb_frames.append(card)

            # Checkbox
            cb = tk.Checkbutton(card, variable=var,
                                bg=SURFACE2, activebackground=SURFACE2,
                                selectcolor=BG,
                                command=lambda i=i: self._step1_toggle(i))
            cb.pack(anchor="e")

            # Thumbnail image
            img_lbl = tk.Label(card, image=tk_img, bg=SURFACE2,
                               cursor="hand2")
            img_lbl.pack()

            # Page label
            tk.Label(card, text=f"Page {i+1}",
                     bg=SURFACE2, fg=TEXT_DIM,
                     font=("Courier New", 8)).pack(pady=(4,0))

            # Click anywhere on card to toggle
            pg = i
            for w in (card, img_lbl):
                w.bind("<Button-1>", lambda e, p=pg: self._step1_toggle(p))
            # Mousewheel passthrough
            for w in (card, img_lbl, cb):
                w.bind("<MouseWheel>",
                       lambda e: self.s1_thumb_canvas.xview_scroll(
                           int(-1*(e.delta/120)), "units"))

    def _step1_toggle(self, idx):
        var = self._s1_page_vars[idx]
        var.set(not var.get())
        card = self._s1_thumb_frames[idx]
        if var.get():
            card.config(bg=ACCENT, padx=6, pady=6)
            for w in card.winfo_children():
                if isinstance(w, tk.Label):
                    w.config(bg=ACCENT)
        else:
            card.config(bg=SURFACE2)
            for w in card.winfo_children():
                if isinstance(w, tk.Label):
                    w.config(bg=SURFACE2)
        self._step1_update_selection_label()

    def _step1_select_all(self):
        for i in range(len(self._s1_page_vars)):
            self._s1_page_vars[i].set(True)
            self._step1_highlight_card(i, True)
        self._step1_update_selection_label()

    def _step1_clear_all(self):
        for i in range(len(self._s1_page_vars)):
            self._s1_page_vars[i].set(False)
            self._step1_highlight_card(i, False)
        self._step1_update_selection_label()

    def _step1_highlight_card(self, idx, selected):
        card = self._s1_thumb_frames[idx]
        color = ACCENT if selected else SURFACE2
        card.config(bg=color)
        for w in card.winfo_children():
            if isinstance(w, tk.Label):
                w.config(bg=color)

    def _step1_update_selection_label(self):
        selected = [i+1 for i, v in enumerate(self._s1_page_vars) if v.get()]
        if selected:
            pages_str = ", ".join(str(p) for p in selected)
            self.s1_selected_lbl.config(
                text=f"Pages: {pages_str}",
                fg=SUCCESS
            )
        else:
            self.s1_selected_lbl.config(text="None selected", fg=TEXT_DIM)
        self.selected_pages = selected

    # ── Step 2 — Control Point Picker ────────────────────────────────────────
    def _build_step2(self):
        frame = tk.Frame(self.content_area, bg=BG)

        # ── Top bar ───────────────────────────────────────────────────────────
        topbar = tk.Frame(frame, bg=SURFACE, height=44)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="Step 2  —  Control Points",
                 bg=SURFACE, fg=TEXT,
                 font=("Courier New", 11, "bold")).pack(side="left", padx=16, pady=10)

        tk.Label(topbar, text="Ctrl+Scroll = Zoom   |   Scroll = Pan",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 8)).pack(side="left", padx=16)

        # Page counter (right side of topbar)
        self.s2_page_lbl = tk.Label(topbar, text="",
                                     bg=SURFACE, fg=ACCENT,
                                     font=("Courier New", 9, "bold"))
        self.s2_page_lbl.pack(side="right", padx=16)

        self.s2_pts_lbl = tk.Label(topbar, text="",
                                    bg=SURFACE, fg=TEXT_DIM,
                                    font=("Courier New", 8))
        self.s2_pts_lbl.pack(side="right", padx=8)

        # ── Body: sidebar | canvas | right panel ──────────────────────────────
        body = tk.Frame(frame, bg=BG)
        body.pack(fill="both", expand=True)

        # ── Page thumbnail sidebar ─────────────────────────────────────────────
        sb_outer = tk.Frame(body, bg=SURFACE, width=110)
        sb_outer.pack(side="left", fill="y")
        sb_outer.pack_propagate(False)

        tk.Label(sb_outer, text="Pages", bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(pady=(8,4))

        self.s2_sb_canvas = tk.Canvas(sb_outer, bg=SURFACE,
                                       highlightthickness=0, width=100)
        sb_vscroll = tk.Scrollbar(sb_outer, orient="vertical",
                                   command=self.s2_sb_canvas.yview)
        self.s2_sb_canvas.configure(yscrollcommand=sb_vscroll.set)
        sb_vscroll.pack(side="right", fill="y")
        self.s2_sb_canvas.pack(fill="both", expand=True)

        self.s2_sb_frame = tk.Frame(self.s2_sb_canvas, bg=SURFACE)
        self.s2_sb_canvas.create_window((0,0), window=self.s2_sb_frame, anchor="nw")
        self.s2_sb_frame.bind("<Configure>",
            lambda e: self.s2_sb_canvas.configure(
                scrollregion=self.s2_sb_canvas.bbox("all")))

        def _sb_wheel(e):
            self.s2_sb_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        self.s2_sb_canvas.bind("<MouseWheel>", _sb_wheel)
        self.s2_sb_frame.bind("<MouseWheel>", _sb_wheel)

        # ── Main canvas ────────────────────────────────────────────────────────
        canvas_wrap = tk.Frame(body, bg=BG)
        canvas_wrap.pack(side="left", fill="both", expand=True)

        self.s2_canvas = tk.Canvas(canvas_wrap, bg="#0A0A0F",
                                    cursor="crosshair", highlightthickness=0)
        self.s2_canvas.pack(fill="both", expand=True)

        h_sb = tk.Scrollbar(canvas_wrap, orient="horizontal",
                             command=self.s2_canvas.xview)
        h_sb.pack(fill="x")
        v_sb = tk.Scrollbar(body, orient="vertical",
                             command=self.s2_canvas.yview)
        v_sb.pack(side="left", fill="y")
        self.s2_canvas.configure(xscrollcommand=h_sb.set,
                                  yscrollcommand=v_sb.set)

        self.s2_canvas.bind("<Button-1>",   self._s2_on_click)
        self.s2_canvas.bind("<MouseWheel>", self._s2_on_mousewheel)

        # ── Right panel ────────────────────────────────────────────────────────
        rp = tk.Frame(body, bg=SURFACE, width=260)
        rp.pack(side="right", fill="y")
        rp.pack_propagate(False)

        tk.Label(rp, text="Control Points",
                 bg=SURFACE, fg=TEXT,
                 font=("Courier New", 11, "bold")).pack(pady=(14,2), padx=14, anchor="w")

        tk.Label(rp, text="Click map → paste ArcGIS coords",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 7)).pack(padx=14, anchor="w", pady=(0,10))

        # Coord input (hidden until click)
        self.s2_input_frame = tk.Frame(rp, bg=SURFACE)
        self.s2_input_frame.pack(fill="x", padx=12)

        tk.Label(self.s2_input_frame,
                 text="📍 Paste ArcGIS Pro coordinates:",
                 bg=SURFACE, fg=WARNING,
                 font=("Courier New", 8, "bold"),
                 wraplength=210).pack(anchor="w", pady=(0,4))

        tk.Label(self.s2_input_frame,
                 text="e.g.  6,741,550.11E 1,920,906.42N ftUS",
                 bg=SURFACE, fg="#444",
                 font=("Courier New", 7)).pack(anchor="w", pady=(0,6))

        self.s2_coord_entry = tk.Entry(self.s2_input_frame,
                                        bg=SURFACE2, fg=TEXT,
                                        insertbackground=TEXT,
                                        font=("Courier New", 9),
                                        relief="flat", bd=6)
        self.s2_coord_entry.pack(fill="x", pady=(0,4))
        self.s2_coord_entry.bind("<KeyRelease>", self._s2_preview_coords)

        self.s2_preview_lbl = tk.Label(self.s2_input_frame, text="",
                                        bg=SURFACE, fg=SUCCESS,
                                        font=("Courier New", 8),
                                        wraplength=210)
        self.s2_preview_lbl.pack(anchor="w", pady=(0,8))

        save_btn = tk.Button(self.s2_input_frame,
                             text="✅  Save Point",
                             command=self._s2_save_point,
                             bg=SUCCESS, fg=BG,
                             font=("Courier New", 9, "bold"),
                             relief="flat", pady=6, cursor="hand2")
        save_btn.pack(fill="x")
        self.s2_input_frame.pack_forget()

        tk.Frame(rp, bg=BORDER, height=1).pack(fill="x", padx=12, pady=10)

        # Page summary
        self.s2_summary_lbl = tk.Label(rp, text="",
                                        bg=SURFACE, fg=TEXT_DIM,
                                        font=("Courier New", 7),
                                        wraplength=220, justify="left")
        self.s2_summary_lbl.pack(padx=14, anchor="w", pady=(0,6))

        tk.Label(rp, text="POINTS — THIS PAGE",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 7, "bold")).pack(padx=14, anchor="w")

        list_wrap = tk.Frame(rp, bg=SURFACE)
        list_wrap.pack(fill="both", expand=True, padx=8, pady=4)

        self.s2_listbox = tk.Listbox(list_wrap,
                                      bg=SURFACE2, fg=TEXT,
                                      selectbackground=ACCENT,
                                      font=("Courier New", 7),
                                      relief="flat", bd=0)
        self.s2_listbox.pack(side="left", fill="both", expand=True)

        list_sb = tk.Scrollbar(list_wrap, command=self.s2_listbox.yview)
        list_sb.pack(side="right", fill="y")
        self.s2_listbox.configure(yscrollcommand=list_sb.set)

        rm_btn = tk.Button(rp, text="❌  Remove Selected",
                           command=self._s2_remove_selected,
                           bg=DANGER, fg=TEXT,
                           font=("Courier New", 8, "bold"),
                           relief="flat", pady=5, cursor="hand2")
        rm_btn.pack(fill="x", padx=12, pady=(4,2))

        clr_btn = tk.Button(rp, text="🗑  Clear This Page",
                            command=self._s2_clear_page,
                            bg=SURFACE2, fg=TEXT_DIM,
                            font=("Courier New", 8),
                            relief="flat", pady=4, cursor="hand2")
        clr_btn.pack(fill="x", padx=12, pady=(0,12))

        # Status bar at bottom of step
        self.s2_status = tk.Label(frame, text="Select a page from the sidebar to begin.",
                                   bg=SURFACE2, fg=TEXT_DIM,
                                   font=("Courier New", 8),
                                   anchor="w", pady=4, padx=12)
        self.s2_status.pack(fill="x")

        # Step 2 internal state
        self._s2_current_page  = None   # 1-based page number
        self._s2_zoom          = 1.5
        self._s2_tk_image      = None
        self._s2_pending_pixel = None
        self._s2_thumb_images  = []
        self._s2_thumb_labels  = []     # (label, frame) per selected page
        self._s2_page_heights  = {}     # page_num → height in pts

        return frame

    def _s2_enter(self):
        """Called when wizard arrives at Step 2 — refresh sidebar from selected_pages."""
        self._s2_build_sidebar()
        if self.selected_pages:
            self._s2_load_page(self.selected_pages[0])

    def _s2_build_sidebar(self):
        for w in self.s2_sb_frame.winfo_children():
            w.destroy()
        self._s2_thumb_images.clear()
        self._s2_thumb_labels.clear()

        for pg in self.selected_pages:
            page = self.pdf_doc[pg - 1]
            mat  = fitz.Matrix(0.15, 0.15)
            pix  = page.get_pixmap(matrix=mat)
            img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img.thumbnail((82, 110))
            tk_img = ImageTk.PhotoImage(img)
            self._s2_thumb_images.append(tk_img)

            cell = tk.Frame(self.s2_sb_frame, bg=SURFACE, pady=4, cursor="hand2")
            cell.pack(fill="x", padx=4)

            lbl = tk.Label(cell, image=tk_img, bg=SURFACE,
                           relief="flat", bd=2, cursor="hand2")
            lbl.pack()

            num_lbl = tk.Label(cell, text=f"Pg {pg}",
                               bg=SURFACE, fg=TEXT_DIM,
                               font=("Courier New", 7))
            num_lbl.pack()

            # Points badge
            badge = tk.Label(cell, text="",
                             bg=SURFACE, fg=SUCCESS,
                             font=("Courier New", 7))
            badge.pack()

            for w in (cell, lbl, num_lbl):
                w.bind("<Button-1>", lambda e, p=pg: self._s2_load_page(p))
                w.bind("<MouseWheel>",
                       lambda e: self.s2_sb_canvas.yview_scroll(
                           int(-1*(e.delta/120)), "units"))

            self._s2_thumb_labels.append((lbl, cell, badge, pg))

    def _s2_highlight_sidebar(self):
        for lbl, cell, badge, pg in self._s2_thumb_labels:
            pts = len(self._s2_points_for_page(pg))
            badge.config(text=f"{pts} pt{'s' if pts!=1 else ''}" if pts else "")
            if pg == self._s2_current_page:
                lbl.config(bg=ACCENT, bd=3)
                cell.config(bg=SURFACE2)
            else:
                lbl.config(bg=SURFACE, bd=2)
                cell.config(bg=SURFACE)

    def _s2_load_page(self, page_num):
        self._s2_current_page = page_num
        self._s2_pending_pixel = None
        self.s2_input_frame.pack_forget()
        self._s2_render()
        self._s2_highlight_sidebar()
        self._s2_refresh_list()

    def _s2_render(self):
        if not self.pdf_doc or self._s2_current_page is None:
            return
        page = self.pdf_doc[self._s2_current_page - 1]
        mat  = fitz.Matrix(self._s2_zoom, self._s2_zoom)
        pix  = page.get_pixmap(matrix=mat)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        self._s2_tk_image = ImageTk.PhotoImage(img)
        self.s2_canvas.delete("all")
        self.s2_canvas.create_image(0, 0, anchor="nw", image=self._s2_tk_image)
        self.s2_canvas.configure(scrollregion=(0, 0, pix.width, pix.height))

        self._s2_page_heights[self._s2_current_page] = page.rect.height

        total = len(self.selected_pages)
        idx   = self.selected_pages.index(self._s2_current_page) + 1
        self.s2_page_lbl.config(
            text=f"Page {self._s2_current_page}  ({idx}/{total} selected)")

        self._s2_redraw_points()
        self._s2_refresh_list()

    # ── Mousewheel / Zoom ──────────────────────────────────────────────────────
    def _s2_on_mousewheel(self, event):
        if event.state & 0x0004:
            self._s2_zoom_at_cursor(event)
        else:
            self.s2_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    ZOOM_STEPS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0]

    def _s2_zoom_at_cursor(self, event):
        cx = self.s2_canvas.canvasx(event.x)
        cy = self.s2_canvas.canvasy(event.y)
        old = self._s2_zoom

        idx = min(range(len(self.ZOOM_STEPS)),
                  key=lambda i: abs(self.ZOOM_STEPS[i] - self._s2_zoom))
        if event.delta > 0:
            new_idx = min(idx + 1, len(self.ZOOM_STEPS) - 1)
        else:
            new_idx = max(idx - 1, 0)

        self._s2_zoom = self.ZOOM_STEPS[new_idx]
        if self._s2_zoom == old:
            return

        self._s2_render()

        scale  = self._s2_zoom / old
        x_frac = (cx * scale - event.x) / self.s2_canvas.winfo_width()
        y_frac = (cy * scale - event.y) / self.s2_canvas.winfo_height()
        self.s2_canvas.xview_moveto(max(0, x_frac))
        self.s2_canvas.yview_moveto(max(0, y_frac))

    # ── Click & Save ───────────────────────────────────────────────────────────
    def _s2_on_click(self, event):
        if not self.pdf_doc or self._s2_current_page is None:
            messagebox.showinfo("No Page", "Select a page from the sidebar first.")
            return

        cx = self.s2_canvas.canvasx(event.x)
        cy = self.s2_canvas.canvasy(event.y)
        self._s2_pending_pixel = (cx, cy)

        r = 6
        self.s2_canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    fill=WARNING, outline="white",
                                    width=2, tags="pending")
        self.s2_canvas.create_text(cx+10, cy-10, text="?",
                                    fill=WARNING,
                                    font=("Courier New", 9, "bold"),
                                    tags="pending")

        self.s2_input_frame.pack(fill="x", padx=12)
        self.s2_coord_entry.delete(0, "end")
        self.s2_preview_lbl.config(text="")
        self.s2_coord_entry.focus()

        px = cx / self._s2_zoom
        py = cy / self._s2_zoom
        self.s2_status.config(
            text=f"Pixel ({px:.1f}, {py:.1f}) on page {self._s2_current_page} — paste coordinates →"
        )

    def _s2_parse_coords(self, raw):
        import re
        tokens = re.findall(r"[\d,]+\.?\d*[NSEWnsew]", raw.upper())
        if len(tokens) < 2:
            raise ValueError("Need two coordinate values.")
        result = {}
        for token in tokens:
            d   = token[-1]
            num = float(token[:-1].replace(",", ""))
            if d in ("W","S") and num > 0:
                num = -num
            if d in ("E","W"):
                result["x"] = num
            else:
                result["y"] = num
        if "x" not in result or "y" not in result:
            raise ValueError("Need Easting (E/W) and Northing (N/S).")
        return result["x"], result["y"]

    def _s2_preview_coords(self, event=None):
        raw = self.s2_coord_entry.get()
        if not raw.strip():
            self.s2_preview_lbl.config(text="")
            return
        try:
            x, y = self._s2_parse_coords(raw)
            self.s2_preview_lbl.config(
                text=f"X: {x:,.2f}   Y: {y:,.2f}", fg=SUCCESS)
        except ValueError:
            self.s2_preview_lbl.config(text="⚠ keep typing...", fg=WARNING)

    def _s2_save_point(self):
        if not self._s2_pending_pixel:
            return
        try:
            rx, ry = self._s2_parse_coords(self.s2_coord_entry.get())
        except ValueError:
            messagebox.showerror("Invalid Coordinates",
                                  "Could not parse.\n\n"
                                  "Expected: 6,741,550.11E 1,920,906.42N ftUS")
            return

        cx, cy = self._s2_pending_pixel
        px = round(cx / self._s2_zoom, 2)
        py = round(cy / self._s2_zoom, 2)

        page_pts = self._s2_points_for_page(self._s2_current_page)
        pt_id    = len(page_pts) + 1

        self.control_points.append({
            "id": pt_id, "pixel_x": px, "pixel_y": py,
            "real_x": rx, "real_y": ry,
            "page": self._s2_current_page
        })

        self.s2_canvas.delete("pending")
        self._s2_draw_marker(cx, cy, pt_id)
        self.s2_input_frame.pack_forget()
        self._s2_pending_pixel = None
        self._s2_refresh_list()
        self._s2_highlight_sidebar()
        self.s2_status.config(
            text=f"✅ Point #{pt_id} saved on page {self._s2_current_page}.  "
                 f"Total: {len(self.control_points)} across all pages."
        )

    def _s2_draw_marker(self, cx, cy, label):
        r = 6
        self.s2_canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                    fill=DANGER, outline="white", width=2)
        self.s2_canvas.create_text(cx, cy, text=str(label),
                                    fill=TEXT, font=("Courier New", 7, "bold"))

    def _s2_redraw_points(self):
        for pt in self._s2_points_for_page(self._s2_current_page):
            self._s2_draw_marker(
                pt["pixel_x"] * self._s2_zoom,
                pt["pixel_y"] * self._s2_zoom,
                pt["id"]
            )

    def _s2_points_for_page(self, page_num):
        return [p for p in self.control_points if p["page"] == page_num]

    def _s2_refresh_list(self):
        self.s2_listbox.delete(0, "end")
        pts = self._s2_points_for_page(self._s2_current_page) if self._s2_current_page else []
        for pt in pts:
            self.s2_listbox.insert(
                "end",
                f"#{pt['id']:02d}  ({pt['real_x']:,.0f}, {pt['real_y']:,.0f})"
            )

        # Summary across all pages
        pages_with = {}
        for pt in self.control_points:
            pages_with.setdefault(pt["page"], 0)
            pages_with[pt["page"]] += 1

        if pages_with:
            parts = [f"Pg{pg}:{cnt}" for pg, cnt in sorted(pages_with.items())]
            self.s2_summary_lbl.config(
                text="Points: " + "  ".join(parts), fg=SUCCESS)
        else:
            self.s2_summary_lbl.config(text="No points yet.", fg=TEXT_DIM)

        cur_count = len(pts)
        self.s2_pts_lbl.config(
            text=f"{cur_count} point{'s' if cur_count!=1 else ''} on this page")

    def _s2_remove_selected(self):
        sel = self.s2_listbox.curselection()
        if not sel:
            return
        pts = self._s2_points_for_page(self._s2_current_page)
        self.control_points.remove(pts[sel[0]])
        for i, pt in enumerate(self._s2_points_for_page(self._s2_current_page)):
            pt["id"] = i + 1
        self._s2_render()

    def _s2_clear_page(self):
        pts = self._s2_points_for_page(self._s2_current_page)
        if not pts:
            return
        if messagebox.askyesno("Clear Page",
                                f"Remove all {len(pts)} points from page {self._s2_current_page}?"):
            self.control_points = [p for p in self.control_points
                                   if p["page"] != self._s2_current_page]
            self.s2_canvas.delete("pending")
            self.s2_input_frame.pack_forget()
            self._s2_render()
            self._s2_highlight_sidebar()

    # ── Step 3 — Extract TIFFs ────────────────────────────────────────────────
    def _build_step3(self):
        frame = tk.Frame(self.content_area, bg=BG)

        # ── Heading ───────────────────────────────────────────────────────────
        head = tk.Frame(frame, bg=BG)
        head.pack(fill="x", padx=40, pady=(32, 8))
        tk.Label(head, text="Step 3  —  Extract TIFFs",
                 bg=BG, fg=TEXT,
                 font=("Courier New", 18, "bold")).pack(anchor="w")
        tk.Label(head,
                 text="Convert your selected PDF pages to TIFF images ready for georeferencing",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 10)).pack(anchor="w", pady=(4, 0))
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=40, pady=14)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(frame, bg=BG)
        body.pack(fill="both", expand=True, padx=40, pady=(0, 20))

        # ── Left — settings + controls ────────────────────────────────────────
        left = tk.Frame(body, bg=BG, width=300)
        left.pack(side="left", fill="y", padx=(0, 20))
        left.pack_propagate(False)

        # Output folder picker
        tk.Label(left, text="OUTPUT FOLDER",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(0, 4))

        folder_row = tk.Frame(left, bg=BG)
        folder_row.pack(fill="x", pady=(0, 12))

        self.s3_folder_lbl = tk.Label(folder_row,
                                       text="No folder selected",
                                       bg=SURFACE, fg=TEXT_DIM,
                                       font=("Courier New", 8),
                                       anchor="w", padx=8, pady=6,
                                       wraplength=190)
        self.s3_folder_lbl.pack(side="left", fill="x", expand=True)

        self._small_btn(folder_row, "Browse",
                        self._s3_pick_folder, ACCENT).pack(side="right", padx=(6, 0))

        # DPI setting
        tk.Label(left, text="RESOLUTION (DPI)",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(4, 4))

        dpi_row = tk.Frame(left, bg=BG)
        dpi_row.pack(fill="x", pady=(0, 16))

        self.s3_dpi_var = tk.StringVar(value="150")
        for dpi, label in [("96","96 — draft"), ("150","150 — recommended"), ("300","300 — high res")]:
            rb = tk.Radiobutton(dpi_row, text=label,
                                variable=self.s3_dpi_var, value=dpi,
                                bg=BG, fg=TEXT_DIM,
                                selectcolor=BG, activebackground=BG,
                                font=("Courier New", 8))
            rb.pack(anchor="w")

        # Pages to extract summary
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))
        tk.Label(left, text="PAGES TO EXTRACT",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(0, 6))

        self.s3_pages_summary = tk.Label(left, text="",
                                          bg=BG, fg=TEXT,
                                          font=("Courier New", 9),
                                          wraplength=260, justify="left")
        self.s3_pages_summary.pack(anchor="w", pady=(0, 16))

        # Extract button
        self.s3_extract_btn = tk.Button(left,
                                         text="⚙  Extract TIFFs",
                                         command=self._s3_run_extraction,
                                         bg=ACCENT, fg=BG,
                                         font=("Courier New", 11, "bold"),
                                         relief="flat", pady=12,
                                         cursor="hand2")
        self.s3_extract_btn.pack(fill="x")
        self.s3_extract_btn.bind("<Enter>",
            lambda e: self.s3_extract_btn.config(bg=ACCENT2))
        self.s3_extract_btn.bind("<Leave>",
            lambda e: self.s3_extract_btn.config(bg=ACCENT))

        # Progress bar
        self.s3_progress_var = tk.DoubleVar(value=0)
        self.s3_progress = ttk.Progressbar(left,
                                            variable=self.s3_progress_var,
                                            maximum=100,
                                            length=260)
        self.s3_progress.pack(fill="x", pady=(10, 4))

        self.s3_progress_lbl = tk.Label(left, text="",
                                         bg=BG, fg=TEXT_DIM,
                                         font=("Courier New", 8))
        self.s3_progress_lbl.pack(anchor="w")

        # ── Right — results log ───────────────────────────────────────────────
        right = tk.Frame(body, bg=SURFACE)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="EXTRACTION LOG",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", padx=14, pady=(12, 4))

        log_wrap = tk.Frame(right, bg=SURFACE)
        log_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.s3_log = tk.Text(log_wrap,
                               bg=SURFACE2, fg=TEXT,
                               font=("Courier New", 9),
                               relief="flat", bd=0,
                               state="disabled",
                               wrap="word")
        log_sb = tk.Scrollbar(log_wrap, command=self.s3_log.yview)
        self.s3_log.configure(yscrollcommand=log_sb.set)
        log_sb.pack(side="right", fill="y")
        self.s3_log.pack(fill="both", expand=True)

        # Tag styles for log
        self.s3_log.tag_configure("ok",      foreground=SUCCESS)
        self.s3_log.tag_configure("warn",    foreground=WARNING)
        self.s3_log.tag_configure("error",   foreground=DANGER)
        self.s3_log.tag_configure("dim",     foreground=TEXT_DIM)
        self.s3_log.tag_configure("heading", foreground=ACCENT,
                                              font=("Courier New", 9, "bold"))

        # Internal state
        self._s3_output_folder = ""

        return frame

    def _s3_enter(self):
        """Called when wizard arrives at Step 3."""
        pages = self.selected_pages
        self.s3_pages_summary.config(
            text=f"Pages: {', '.join(str(p) for p in pages)}\n"
                 f"({len(pages)} page{'s' if len(pages)!=1 else ''} total)"
        )
        self._s3_log_write(
            f"Ready to extract {len(pages)} page(s) from:\n{self.pdf_name}.pdf\n\n"
            "Pick an output folder then click Extract TIFFs.",
            tag="dim"
        )

    def _s3_pick_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder for TIFFs")
        if folder:
            self._s3_output_folder = folder
            short = os.path.basename(folder) or folder
            self.s3_folder_lbl.config(text=short, fg=TEXT)

    def _s3_log_write(self, text, tag=""):
        self.s3_log.configure(state="normal")
        self.s3_log.insert("end", text + "\n", tag)
        self.s3_log.see("end")
        self.s3_log.configure(state="disabled")

    def _s3_log_clear(self):
        self.s3_log.configure(state="normal")
        self.s3_log.delete("1.0", "end")
        self.s3_log.configure(state="disabled")

    def _s3_run_extraction(self):
        if not self._s3_output_folder:
            messagebox.showwarning("No Folder", "Please select an output folder first.")
            return

        os.makedirs(self._s3_output_folder, exist_ok=True)
        dpi    = int(self.s3_dpi_var.get())
        scale  = dpi / 72.0
        pages  = self.selected_pages
        total  = len(pages)

        self._s3_log_clear()
        self._s3_log_write(
            f"Extracting {total} page(s) at {dpi} DPI...\n", tag="heading")

        self.s3_extract_btn.config(state="disabled", text="Extracting...")
        self.tiff_paths = {}
        errors = 0

        for i, pg in enumerate(pages):
            pct = int((i / total) * 100)
            self.s3_progress_var.set(pct)
            self.s3_progress_lbl.config(text=f"Page {pg}  ({i+1}/{total})")
            self.root.update_idletasks()

            try:
                page    = self.pdf_doc[pg - 1]
                mat     = fitz.Matrix(scale, scale)
                pix     = page.get_pixmap(matrix=mat)
                img     = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                outname = f"{self.pdf_name}_page_{pg}_raw.tif"
                outpath = os.path.join(self._s3_output_folder, outname)
                img.save(outpath, format="TIFF")
                self.tiff_paths[pg] = outpath
                self._s3_log_write(
                    f"  ✓  Page {pg}  →  {outname}  "
                    f"({pix.width}x{pix.height}px)", tag="ok")

            except Exception as e:
                errors += 1
                self._s3_log_write(f"  ✗  Page {pg}  ERROR: {e}", tag="error")

        self.s3_progress_var.set(100)
        self.s3_progress_lbl.config(text="Done")

        if errors == 0:
            self._s3_log_write(
                f"\n✅  All {total} TIFFs saved to:\n{self._s3_output_folder}",
                tag="ok")
            self.s3_extract_btn.config(
                bg=SUCCESS, fg=BG,
                text="✓  Extraction Complete — click Next to continue")
        else:
            self._s3_log_write(
                f"\n⚠  {errors} error(s) — check log above.", tag="warn")
            self.s3_extract_btn.config(
                state="normal", text="⚙  Retry Extraction", bg=WARNING, fg=BG)

    # ── Step 4 — Georeference ─────────────────────────────────────────────────
    def _build_step4(self):
        frame = tk.Frame(self.content_area, bg=BG)

        # ── Heading ───────────────────────────────────────────────────────────
        head = tk.Frame(frame, bg=BG)
        head.pack(fill="x", padx=40, pady=(32, 8))
        tk.Label(head, text="Step 4  —  Georeference",
                 bg=BG, fg=TEXT,
                 font=("Courier New", 18, "bold")).pack(anchor="w")
        tk.Label(head,
                 text="Warp each TIFF using your control points and save georeferenced GeoTIFFs",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 10)).pack(anchor="w", pady=(4, 0))
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=40, pady=14)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(frame, bg=BG)
        body.pack(fill="both", expand=True, padx=40, pady=(0, 20))

        # ── Left — settings + controls ────────────────────────────────────────
        left = tk.Frame(body, bg=BG, width=300)
        left.pack(side="left", fill="y", padx=(0, 20))
        left.pack_propagate(False)

        # Coordinate system
        tk.Label(left, text="COORDINATE SYSTEM (EPSG)",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(0, 4))

        epsg_row = tk.Frame(left, bg=BG)
        epsg_row.pack(fill="x", pady=(0, 4))

        self.s4_epsg_entry = tk.Entry(epsg_row,
                                       bg=SURFACE, fg=TEXT,
                                       insertbackground=TEXT,
                                       font=("Courier New", 10),
                                       relief="flat", bd=6, width=12)
        self.s4_epsg_entry.insert(0, "102642")
        self.s4_epsg_entry.pack(side="left")

        tk.Label(epsg_row, text="  NAD83 StatePlane CA II",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 7)).pack(side="left")

        tk.Label(left,
                 text="Common: 4326=WGS84  3857=WebMercator\n"
                      "102642=CA StatePlane II (US ft)",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 7),
                 justify="left").pack(anchor="w", pady=(2, 14))

        # Transformation
        tk.Label(left, text="TRANSFORMATION",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(0, 4))

        self.s4_transform_var = tk.StringVar(value="polynomial1")
        for val, label in [
            ("polynomial1", "Polynomial 1  (3+ pts, recommended)"),
            ("polynomial2", "Polynomial 2  (6+ pts)"),
            ("thin_plate_spline", "Thin Plate Spline  (many pts)"),
        ]:
            tk.Radiobutton(left, text=label,
                           variable=self.s4_transform_var, value=val,
                           bg=BG, fg=TEXT_DIM,
                           selectcolor=BG, activebackground=BG,
                           font=("Courier New", 8)).pack(anchor="w")

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", pady=14)

        # Summary
        self.s4_summary_lbl = tk.Label(left, text="",
                                        bg=BG, fg=TEXT,
                                        font=("Courier New", 8),
                                        wraplength=260, justify="left")
        self.s4_summary_lbl.pack(anchor="w", pady=(0, 14))

        # Run button
        self.s4_run_btn = tk.Button(left,
                                     text="⚙  Run Georeferencing",
                                     command=self._s4_run,
                                     bg=ACCENT, fg=BG,
                                     font=("Courier New", 11, "bold"),
                                     relief="flat", pady=12,
                                     cursor="hand2")
        self.s4_run_btn.pack(fill="x")
        self.s4_run_btn.bind("<Enter>",
            lambda e: self.s4_run_btn.config(bg=ACCENT2))
        self.s4_run_btn.bind("<Leave>",
            lambda e: self.s4_run_btn.config(bg=ACCENT))

        # Progress
        self.s4_progress_var = tk.DoubleVar(value=0)
        self.s4_progress = ttk.Progressbar(left,
                                            variable=self.s4_progress_var,
                                            maximum=100, length=260)
        self.s4_progress.pack(fill="x", pady=(10, 4))

        self.s4_progress_lbl = tk.Label(left, text="",
                                         bg=BG, fg=TEXT_DIM,
                                         font=("Courier New", 8))
        self.s4_progress_lbl.pack(anchor="w")

        # ── Right — log ───────────────────────────────────────────────────────
        right = tk.Frame(body, bg=SURFACE)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="GEOREFERENCING LOG",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(
                     anchor="w", padx=14, pady=(12, 4))

        log_wrap = tk.Frame(right, bg=SURFACE)
        log_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.s4_log = tk.Text(log_wrap,
                               bg=SURFACE2, fg=TEXT,
                               font=("Courier New", 9),
                               relief="flat", bd=0,
                               state="disabled", wrap="word")
        log_sb = tk.Scrollbar(log_wrap, command=self.s4_log.yview)
        self.s4_log.configure(yscrollcommand=log_sb.set)
        log_sb.pack(side="right", fill="y")
        self.s4_log.pack(fill="both", expand=True)

        self.s4_log.tag_configure("ok",      foreground=SUCCESS)
        self.s4_log.tag_configure("warn",    foreground=WARNING)
        self.s4_log.tag_configure("error",   foreground=DANGER)
        self.s4_log.tag_configure("dim",     foreground=TEXT_DIM)
        self.s4_log.tag_configure("heading", foreground=ACCENT,
                                              font=("Courier New", 9, "bold"))

        return frame

    def _s4_enter(self):
        pages = self.selected_pages
        self.s4_summary_lbl.config(
            text=f"{len(pages)} page(s) ready\n"
                 f"Pages: {', '.join(str(p) for p in pages)}"
        )
        self._s4_log_clear()
        self._s4_log_write(
            f"Ready to georeference {len(pages)} page(s).\n"
            "Confirm settings then click Run Georeferencing.", tag="dim")

    def _s4_log_write(self, text, tag=""):
        self.s4_log.configure(state="normal")
        self.s4_log.insert("end", text + "\n", tag)
        self.s4_log.see("end")
        self.s4_log.configure(state="disabled")

    def _s4_log_clear(self):
        self.s4_log.configure(state="normal")
        self.s4_log.delete("1.0", "end")
        self.s4_log.configure(state="disabled")

    def _s4_run(self):
        try:
            import numpy as np
            from PIL import Image as PILImage
        except ImportError as e:
            messagebox.showerror("Missing Library", f"Install numpy:\n  pip install numpy\n\n{e}")
            return

        # Prefer GDAL (via ArcGIS Pro Python), fall back to numpy
        georef_fn = None
        try:
            from osgeo import gdal, osr
            georef_fn = self._s4_georeference_gdal
            self._s4_log_write("Engine: GDAL (full pixel warp)", tag="dim")
        except ImportError:
            try:
                import rasterio
                import numpy as np
                georef_fn = self._s4_georeference_numpy
                self._s4_log_write(
                    "Engine: numpy affine (GDAL not found — switch to ArcGIS Pro interpreter for best results)",
                    tag="warn")
            except ImportError as e:
                messagebox.showerror(
                    "Missing Library",
                    "Install rasterio and numpy:\n\n"
                    "  pip install rasterio numpy\n\n"
                    f"{e}"
                )
                return

        epsg  = self.s4_epsg_entry.get().strip()
        pages = self.selected_pages
        total = len(pages)

        self._s4_log_clear()
        self._s4_log_write(
            f"Georeferencing {total} page(s)  |  EPSG:{epsg}\n", tag="heading")

        self.s4_run_btn.config(state="disabled", text="Processing...")
        self.georef_paths = {}
        self.rms_scores   = {}
        errors = 0

        for i, pg in enumerate(pages):
            pct = int((i / total) * 100)
            self.s4_progress_var.set(pct)
            self.s4_progress_lbl.config(text=f"Page {pg}  ({i+1}/{total})")
            self.root.update_idletasks()

            tiff_path = self.tiff_paths.get(pg)
            if not tiff_path:
                self._s4_log_write(f"  ✗  Page {pg}  — no TIFF found", tag="error")
                errors += 1
                continue

            pts = [p for p in self.control_points if p["page"] == pg]
            if len(pts) < 3:
                self._s4_log_write(
                    f"  ✗  Page {pg}  — only {len(pts)} control point(s)", tag="error")
                errors += 1
                continue

            try:
                out_path, rms = georef_fn(tiff_path, pts, epsg, pg)
                self.georef_paths[pg] = out_path
                self.rms_scores[pg]   = rms

                rms_tag  = "warn" if rms > 2.0 else "ok"
                rms_flag = "⚠  HIGH RMS" if rms > 2.0 else "✓"
                self._s4_log_write(
                    f"  {rms_flag}  Page {pg}  RMS: {rms:.4f}  →  "
                    f"{os.path.basename(out_path)}", tag=rms_tag)

            except Exception as e:
                self._s4_log_write(f"  ✗  Page {pg}  ERROR: {e}", tag="error")
                errors += 1

        self.s4_progress_var.set(100)

        if errors == 0:
            high_rms = [pg for pg, r in self.rms_scores.items() if r > 2.0]
            if high_rms:
                self._s4_log_write(
                    f"\n⚠  Done — {len(high_rms)} page(s) have high RMS. "
                    "Review in Step 5.", tag="warn")
                self.s4_run_btn.config(
                    state="normal",
                    text="✓  Done — click Next to review results",
                    bg=WARNING, fg=BG)
            else:
                self._s4_log_write(
                    f"\n✅  All {total} GeoTIFFs complete!", tag="ok")
                self.s4_run_btn.config(
                    text="✓  Complete — click Next to see results",
                    bg=SUCCESS, fg=BG)
            self.s4_progress_lbl.config(text="Complete")
        else:
            self._s4_log_write(
                f"\n⚠  {errors} page(s) failed — check log.", tag="warn")
            self.s4_run_btn.config(
                state="normal", text="⚙  Retry", bg=DANGER, fg=TEXT)

    def _s4_georeference_gdal(self, tiff_path, pts, epsg, page_num):
        """
        Full GDAL warp — sets GCPs on a copy then warps pixels into place.
        Produces a properly rectified GeoTIFF matching ArcGIS Pro quality.
        """
        from osgeo import gdal, osr

        gdal.UseExceptions()

        # Build spatial reference
        srs = osr.SpatialReference()
        if epsg.isdigit():
            srs.ImportFromEPSG(int(epsg))
        else:
            srs.SetFromUserInput(epsg)
        wkt = srs.ExportToWkt()

        # Build GCPs: gdal.GCP(map_x, map_y, map_z, pixel_x, pixel_y)
        gcps = [
            gdal.GCP(pt["real_x"], pt["real_y"], 0,
                     pt["pixel_x"], pt["pixel_y"])
            for pt in pts
        ]

        # Step 1 — write GCPs into a temp copy of the raw TIFF
        gcp_path = tiff_path.replace("_raw.tif", "_gcp_temp.tif")
        src_ds   = gdal.Open(tiff_path)
        driver   = gdal.GetDriverByName("GTiff")
        gcp_ds   = driver.CreateCopy(gcp_path, src_ds)
        gcp_ds.SetGCPs(gcps, wkt)
        gcp_ds.FlushCache()
        gcp_ds = None
        src_ds = None

        # Step 2 — warp using the chosen transformation type
        out_path   = tiff_path.replace("_raw.tif", "_georef.tif")
        transform  = self.s4_transform_var.get()
        use_tps    = (transform == "thin_plate_spline")
        poly_order = {"polynomial1": 1, "polynomial2": 2}.get(transform, 1)

        warp_opts = gdal.WarpOptions(
            format="GTiff",
            dstSRS=wkt,
            tps=use_tps,
            polynomialOrder=None if use_tps else poly_order,
            resampleAlg=gdal.GRA_Bilinear,
            transformerOptions=["SRC_METHOD=GCP_POLYNOMIAL"]
        )
        result = gdal.Warp(out_path, gcp_path, options=warp_opts)
        result.FlushCache()
        result = None

        # Clean up temp file
        try:
            os.remove(gcp_path)
        except Exception:
            pass

        rms = self._s4_calc_rms_gdal(pts, epsg)
        return out_path, rms

    def _s4_calc_rms_gdal(self, pts, epsg):
        """
        True RMS in map units — reprojects each pixel coord to map coords
        using a fitted polynomial and compares to the real CP coords.
        """
        import math
        import numpy as np

        A = np.array([[p["pixel_x"], p["pixel_y"], 1] for p in pts], dtype=float)
        X = np.array([p["real_x"] for p in pts], dtype=float)
        Y = np.array([p["real_y"] for p in pts], dtype=float)

        cx, _, _, _ = np.linalg.lstsq(A, X, rcond=None)
        cy, _, _, _ = np.linalg.lstsq(A, Y, rcond=None)

        errors = []
        for p in pts:
            pred_x = cx[0]*p["pixel_x"] + cx[1]*p["pixel_y"] + cx[2]
            pred_y = cy[0]*p["pixel_x"] + cy[1]*p["pixel_y"] + cy[2]
            errors.append(math.sqrt(
                (pred_x - p["real_x"])**2 + (pred_y - p["real_y"])**2))

        return round(math.sqrt(sum(e**2 for e in errors) / len(errors)), 4)

    def _s4_georeference_numpy(self, tiff_path, pts, epsg, page_num):
        """
        Fallback: numpy affine least-squares + rasterio write.
        No pixel resampling — stamps coordinates onto the image.
        Works but less accurate than GDAL warp.
        """
        import numpy as np
        import rasterio
        from rasterio.transform import Affine
        from rasterio.crs import CRS

        A = np.array([[p["pixel_x"], p["pixel_y"], 1] for p in pts], dtype=float)
        X = np.array([p["real_x"] for p in pts], dtype=float)
        Y = np.array([p["real_y"] for p in pts], dtype=float)

        coeff_x, _, _, _ = np.linalg.lstsq(A, X, rcond=None)
        coeff_y, _, _, _ = np.linalg.lstsq(A, Y, rcond=None)

        a, b, c = coeff_x
        d, e, f = coeff_y

        transform = Affine(a, b, c, d, e, f)
        crs = CRS.from_epsg(int(epsg)) if epsg.isdigit() else CRS.from_user_input(epsg)
        out_path = tiff_path.replace("_raw.tif", "_georef.tif")

        with rasterio.open(tiff_path) as src:
            profile = src.profile.copy()
            profile.update(crs=crs, transform=transform, driver="GTiff")
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(src.read())

        rms = self._s4_calc_rms_gdal(pts, epsg)
        return out_path, rms

    # ── Step 5 — Results ──────────────────────────────────────────────────────
    def _build_step5(self):
        frame = tk.Frame(self.content_area, bg=BG)

        # ── Heading ───────────────────────────────────────────────────────────
        head = tk.Frame(frame, bg=BG)
        head.pack(fill="x", padx=40, pady=(32, 8))

        tk.Label(head, text="Step 5  —  Results",
                 bg=BG, fg=TEXT,
                 font=("Courier New", 18, "bold")).pack(anchor="w")
        tk.Label(head,
                 text="Review your georeferenced outputs and load them into ArcGIS Pro",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 10)).pack(anchor="w", pady=(4, 0))
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", padx=40, pady=14)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(frame, bg=BG)
        body.pack(fill="both", expand=True, padx=40, pady=(0, 20))

        # ── Left — summary stats + actions ────────────────────────────────────
        left = tk.Frame(body, bg=BG, width=300)
        left.pack(side="left", fill="y", padx=(0, 20))
        left.pack_propagate(False)

        # Banner — success or warning
        self.s5_banner = tk.Label(left, text="",
                                   bg=SURFACE2, fg=TEXT,
                                   font=("Courier New", 10, "bold"),
                                   wraplength=270, justify="center",
                                   pady=14, padx=12)
        self.s5_banner.pack(fill="x", pady=(0, 16))

        # Stats cards row
        stats_row = tk.Frame(left, bg=BG)
        stats_row.pack(fill="x", pady=(0, 16))

        self.s5_stat_total  = self._s5_stat_card(stats_row, "PAGES",    "—")
        self.s5_stat_ok     = self._s5_stat_card(stats_row, "OK",       "—", SUCCESS)
        self.s5_stat_warn   = self._s5_stat_card(stats_row, "REVIEW",   "—", WARNING)
        self.s5_stat_total.pack(side="left", expand=True, fill="x", padx=(0,4))
        self.s5_stat_ok.pack(side="left",    expand=True, fill="x", padx=4)
        self.s5_stat_warn.pack(side="left",  expand=True, fill="x", padx=(4,0))

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", pady=(0, 14))

        # Output folder
        tk.Label(left, text="OUTPUT FOLDER",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(0, 4))

        self.s5_folder_lbl = tk.Label(left, text="—",
                                       bg=SURFACE, fg=TEXT_DIM,
                                       font=("Courier New", 8),
                                       wraplength=270, justify="left",
                                       anchor="w", padx=10, pady=8)
        self.s5_folder_lbl.pack(fill="x", pady=(0, 10))

        # Action buttons
        open_btn = tk.Button(left,
                             text="📂  Open Output Folder",
                             command=self._s5_open_folder,
                             bg=ACCENT, fg=BG,
                             font=("Courier New", 10, "bold"),
                             relief="flat", pady=10, cursor="hand2")
        open_btn.pack(fill="x", pady=(0, 6))
        open_btn.bind("<Enter>", lambda e: open_btn.config(bg=ACCENT2))
        open_btn.bind("<Leave>", lambda e: open_btn.config(bg=ACCENT))

        restart_btn = tk.Button(left,
                                text="↺  Start New Session",
                                command=self._s5_restart,
                                bg=SURFACE2, fg=TEXT_DIM,
                                font=("Courier New", 9),
                                relief="flat", pady=8, cursor="hand2")
        restart_btn.pack(fill="x", pady=(0, 6))
        restart_btn.bind("<Enter>", lambda e: restart_btn.config(fg=TEXT))
        restart_btn.bind("<Leave>", lambda e: restart_btn.config(fg=TEXT_DIM))

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", pady=14)

        # ArcGIS Pro instructions
        tk.Label(left, text="LOAD INTO ARCGIS PRO",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(anchor="w", pady=(0, 6))

        for step in [
            "1.  Open ArcGIS Pro",
            "2.  Map tab → Add Data",
            "3.  Browse to output folder",
            "4.  Select *_georef.tif files",
            "5.  They'll snap to correct location"
        ]:
            tk.Label(left, text=step,
                     bg=BG, fg=TEXT_DIM,
                     font=("Courier New", 8),
                     anchor="w").pack(anchor="w", pady=1)

        # ── Right — per-page results table ────────────────────────────────────
        right = tk.Frame(body, bg=SURFACE)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="PER-PAGE RESULTS",
                 bg=SURFACE, fg=TEXT_DIM,
                 font=("Courier New", 8, "bold")).pack(
                     anchor="w", padx=14, pady=(12, 4))

        # Scrollable results list
        results_wrap = tk.Frame(right, bg=SURFACE)
        results_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.s5_results_canvas = tk.Canvas(results_wrap, bg=SURFACE,
                                            highlightthickness=0)
        results_sb = tk.Scrollbar(results_wrap, orient="vertical",
                                   command=self.s5_results_canvas.yview)
        self.s5_results_canvas.configure(yscrollcommand=results_sb.set)
        results_sb.pack(side="right", fill="y")
        self.s5_results_canvas.pack(fill="both", expand=True)

        self.s5_results_frame = tk.Frame(self.s5_results_canvas, bg=SURFACE)
        self.s5_results_canvas.create_window(
            (0, 0), window=self.s5_results_frame, anchor="nw")
        self.s5_results_frame.bind("<Configure>",
            lambda e: self.s5_results_canvas.configure(
                scrollregion=self.s5_results_canvas.bbox("all")))

        def _wheel(e):
            self.s5_results_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        self.s5_results_canvas.bind("<MouseWheel>", _wheel)
        self.s5_results_frame.bind("<MouseWheel>", _wheel)

        return frame

    def _s5_stat_card(self, parent, label, value, color=TEXT):
        """Small stat card widget, returns the value label for updating."""
        card = tk.Frame(parent, bg=SURFACE2, padx=8, pady=8)
        tk.Label(card, text=label,
                 bg=SURFACE2, fg=TEXT_DIM,
                 font=("Courier New", 7, "bold")).pack()
        val_lbl = tk.Label(card, text=value,
                            bg=SURFACE2, fg=color,
                            font=("Courier New", 14, "bold"))
        val_lbl.pack()
        return card

    def _s5_enter(self):
        """Populate results when Step 5 is shown."""
        # Clear old results
        for w in self.s5_results_frame.winfo_children():
            w.destroy()

        pages   = self.selected_pages
        total   = len(pages)
        ok      = sum(1 for pg in pages
                      if self.rms_scores.get(pg, 99) <= 2.0)
        warn    = total - ok

        # Update stat cards
        for card in [self.s5_stat_total, self.s5_stat_ok, self.s5_stat_warn]:
            for w in card.winfo_children():
                if isinstance(w, tk.Label) and w.cget("font") == "Courier New 14 bold":
                    pass
        # Simpler — just rebuild the value labels
        self._s5_update_stat(self.s5_stat_total, str(total), TEXT)
        self._s5_update_stat(self.s5_stat_ok,    str(ok),    SUCCESS)
        self._s5_update_stat(self.s5_stat_warn,  str(warn),  WARNING if warn else TEXT_DIM)

        # Banner
        if warn == 0:
            self.s5_banner.config(
                text=f"✅  All {total} page(s) georeferenced successfully",
                bg=SUCCESS, fg=BG)
        else:
            self.s5_banner.config(
                text=f"⚠  {warn} page(s) have high RMS — consider re-picking control points",
                bg=WARNING, fg=BG)

        # Output folder
        folder = os.path.dirname(
            next(iter(self.georef_paths.values()), ""))
        self.s5_folder_lbl.config(text=folder or "—", fg=TEXT)

        # Per-page rows
        for pg in pages:
            rms       = self.rms_scores.get(pg)
            out_path  = self.georef_paths.get(pg)
            has_georef = out_path and os.path.exists(out_path)

            row = tk.Frame(self.s5_results_frame, bg=SURFACE2,
                           pady=10, padx=14)
            row.pack(fill="x", padx=8, pady=4)

            # Status icon
            if not has_georef:
                icon, icon_color = "✗", DANGER
            elif rms is not None and rms > 2.0:
                icon, icon_color = "⚠", WARNING
            else:
                icon, icon_color = "✓", SUCCESS

            tk.Label(row, text=icon,
                     bg=SURFACE2, fg=icon_color,
                     font=("Courier New", 14, "bold")).pack(side="left", padx=(0,12))

            # Info
            info = tk.Frame(row, bg=SURFACE2)
            info.pack(side="left", fill="x", expand=True)

            tk.Label(info, text=f"Page {pg}",
                     bg=SURFACE2, fg=TEXT,
                     font=("Courier New", 10, "bold")).pack(anchor="w")

            fname = os.path.basename(out_path) if out_path else "Not generated"
            tk.Label(info, text=fname,
                     bg=SURFACE2, fg=TEXT_DIM,
                     font=("Courier New", 8)).pack(anchor="w")

            # RMS badge
            if rms is not None:
                rms_color = WARNING if rms > 2.0 else SUCCESS
                rms_frame = tk.Frame(row, bg=SURFACE, padx=10, pady=6)
                rms_frame.pack(side="right")
                tk.Label(rms_frame, text="RMS",
                         bg=SURFACE, fg=TEXT_DIM,
                         font=("Courier New", 7)).pack()
                tk.Label(rms_frame, text=f"{rms:.2f}",
                         bg=SURFACE, fg=rms_color,
                         font=("Courier New", 11, "bold")).pack()
                if rms > 2.0:
                    tk.Label(rms_frame, text="re-check CPs",
                             bg=SURFACE, fg=WARNING,
                             font=("Courier New", 6)).pack()

            # Mousewheel passthrough
            for w in (row, info):
                w.bind("<MouseWheel>",
                       lambda e: self.s5_results_canvas.yview_scroll(
                           int(-1*(e.delta/120)), "units"))

    def _s5_update_stat(self, card, value, color):
        """Update the value label inside a stat card."""
        children = card.winfo_children()
        if len(children) >= 2:
            children[1].config(text=value, fg=color)

    def _s5_open_folder(self):
        folder = os.path.dirname(next(iter(self.georef_paths.values()), ""))
        if folder and os.path.exists(folder):
            import subprocess
            subprocess.Popen(f'explorer "{folder}"')
        else:
            messagebox.showwarning("Folder Not Found",
                                   "Could not locate the output folder.")

    def _s5_restart(self):
        if messagebox.askyesno("Start New Session",
                                "This will clear all current work.\nAre you sure?"):
            self.pdf_doc        = None
            self.pdf_path       = ""
            self.pdf_name       = ""
            self.selected_pages = []
            self.control_points = []
            self.tiff_paths     = {}
            self.georef_paths   = {}
            self.rms_scores     = {}
            self._show_step(0)

    def _build_footer(self):
        """Navigation buttons at bottom."""
        footer = tk.Frame(self.root, bg=SURFACE, height=64)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # Progress text
        self.progress_label = tk.Label(footer, text="",
                                        bg=SURFACE, fg=TEXT_DIM,
                                        font=("Courier New", 9))
        self.progress_label.pack(side="left", padx=24)

        # Buttons
        btn_frame = tk.Frame(footer, bg=SURFACE)
        btn_frame.pack(side="right", padx=24)

        self.back_btn = self._nav_btn(btn_frame, "◀  Back",
                                       self.go_back, color=SURFACE2)
        self.back_btn.pack(side="left", padx=8, pady=12)

        self.next_btn = self._nav_btn(btn_frame, "Next  ▶",
                                       self.go_next, color=ACCENT)
        self.next_btn.pack(side="left", pady=12)

    def _nav_btn(self, parent, text, command, color=ACCENT):
        btn = tk.Button(parent, text=text, command=command,
                        bg=color, fg=TEXT,
                        font=("Courier New", 10, "bold"),
                        relief="flat", padx=20, pady=8,
                        cursor="hand2", activebackground=ACCENT2,
                        activeforeground=TEXT)
        btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT2))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))
        return btn

    # ── Navigation ────────────────────────────────────────────────────────────
    def _show_step(self, idx):
        """Show the frame for step idx, hide all others."""
        self.current_step = idx

        for i, frame in enumerate(self.step_frames):
            frame.pack_forget()
        self.step_frames[idx].pack(fill="both", expand=True)

        # Step entry hooks
        if idx == 1:
            self._s2_enter()
        if idx == 2:
            self._s3_enter()
        if idx == 3:
            self._s4_enter()
        if idx == 4:
            self._s5_enter()

        self._update_step_bar()
        self._update_sidebar()
        self._update_footer()

    def _update_step_bar(self):
        for i, (bubble, lbl) in enumerate(self.step_bar_labels):
            if i < self.current_step:
                bubble.config(bg=SUCCESS, fg=BG, text="✓")
                lbl.config(fg=SUCCESS)
            elif i == self.current_step:
                bubble.config(bg=ACCENT, fg=BG,
                               text=STEPS[i][0])
                lbl.config(fg=ACCENT)
            else:
                bubble.config(bg=BORDER, fg=TEXT_DIM,
                               text=STEPS[i][0])
                lbl.config(fg=TEXT_DIM)

    def _update_sidebar(self):
        infos = [
            "Open a PDF map to begin.",
            "Click on the map to drop control points.\nPaste ArcGIS Pro coordinates for each one.",
            "Only pages with control points will be extracted.",
            "Each page is warped using your control points.",
            "Review RMS scores and open your output folder.",
        ]
        for i, (btn, dot, title_lbl, sub_lbl) in enumerate(self.sidebar_items):
            if i < self.current_step:
                dot.config(fg=SUCCESS, text="✓")
                title_lbl.config(fg=SUCCESS)
                sub_lbl.config(fg=SUCCESS)
                btn.config(bg=SURFACE)
            elif i == self.current_step:
                dot.config(fg=ACCENT, text="●")
                title_lbl.config(fg=ACCENT)
                sub_lbl.config(fg=TEXT_DIM)
                btn.config(bg=SURFACE2)
            else:
                dot.config(fg=TEXT_DIM, text="○")
                title_lbl.config(fg=TEXT_DIM)
                sub_lbl.config(fg=TEXT_DIM)
                btn.config(bg=SURFACE)

        self.info_box.config(text=infos[self.current_step])
        self.header_subtitle.config(text=f"Step {self.current_step+1} of {len(STEPS)}")

    def _update_footer(self):
        num, title, _ = STEPS[self.current_step]
        self.progress_label.config(
            text=f"Step {num} of {len(STEPS)}  —  {title}"
        )
        # Hide back on first step
        self.back_btn.config(state="normal" if self.current_step > 0 else "disabled",
                              bg=SURFACE2 if self.current_step > 0 else BORDER)
        # Change label on last step
        if self.current_step == len(STEPS) - 1:
            self.next_btn.config(text="Finish  ✓", bg=SUCCESS)
        else:
            self.next_btn.config(text="Next  ▶", bg=ACCENT)

    def _try_jump(self, idx):
        """Allow jumping back to any previous step."""
        if idx <= self.current_step:
            self._show_step(idx)

    def _small_btn(self, parent, text, command, color=SURFACE2):
        btn = tk.Button(parent, text=text, command=command,
                        bg=color, fg=TEXT_DIM,
                        font=("Courier New", 8),
                        relief="flat", padx=10, pady=4,
                        cursor="hand2")
        btn.bind("<Enter>", lambda e: btn.config(fg=TEXT))
        btn.bind("<Leave>", lambda e: btn.config(fg=TEXT_DIM))
        return btn

    def go_next(self):
        # ── Step 1 validation ─────────────────────────────────────────────────
        if self.current_step == 0:
            if not self.pdf_doc:
                messagebox.showwarning("No PDF", "Please open a PDF first.")
                return
            if not self.selected_pages:
                messagebox.showwarning("No Pages",
                                       "Please select at least one page to continue.")
                return

        # ── Step 2 validation ─────────────────────────────────────────────────
        if self.current_step == 1:
            missing = []
            for pg in self.selected_pages:
                pts = [p for p in self.control_points if p["page"] == pg]
                if len(pts) < 3:
                    missing.append(f"Page {pg}: {len(pts)} point(s)")
            if missing:
                messagebox.showwarning(
                    "Not Enough Points",
                    "Each page needs at least 3 control points.\n\n"
                    + "\n".join(missing)
                )
                return

        # ── Step 3 validation ─────────────────────────────────────────────────
        if self.current_step == 2:
            if not self.tiff_paths:
                messagebox.showwarning("No TIFFs",
                                       "Please extract TIFFs before continuing.")
                return
            missing = [pg for pg in self.selected_pages if pg not in self.tiff_paths]
            if missing:
                messagebox.showwarning("Missing TIFFs",
                                       f"These pages failed to extract:\n"
                                       f"{', '.join(f'Page {p}' for p in missing)}\n\n"
                                       f"Please retry extraction.")
                return

        # ── Step 4 validation ─────────────────────────────────────────────────
        if self.current_step == 3:
            if not self.georef_paths:
                messagebox.showwarning("Not Georeferenced",
                                       "Please run georeferencing before continuing.")
                return

        if self.current_step < len(STEPS) - 1:
            self._show_step(self.current_step + 1)
        else:
            self._finish()

    def go_back(self):
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _finish(self):
        messagebox.showinfo(
            "Session Complete",
            f"✅  {len(self.georef_paths)} GeoTIFF(s) saved.\n\n"
            "Drag them into ArcGIS Pro or use\n"
            "Map tab → Add Data to load them."
        )


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app  = GeoRefWizard(root)
    root.mainloop()