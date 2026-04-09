import sys
import io
import json
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QTextEdit, 
                             QListWidget, QInputDialog, QGridLayout, 
                             QFrame, QScrollArea, QMessageBox, QStackedWidget,
                             QButtonGroup, QSizePolicy, QLineEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- MÃ MÀU THEME NOTION ---
N_BG = "#FFFFFF"           
N_SIDEBAR = "#F7F6F3"      
N_TEXT = "#37352F"         
N_MUTED = "#787774"        
N_BORDER = "#E9E9E7"       
N_HOVER = "#EFEEDF"        
N_PRIMARY = "#2F2F2F"      
N_GREEN_BG = "#E1F3EA"     
N_GREEN_BD = "#0F7B6C"     
N_RED_BG = "#FDEBEC"       
N_RED_BD = "#E03E3E"       

# --- CORE LOGIC ---
SCOPES = ['https://www.googleapis.com/auth/drive.file']

class DriveManager:
    def __init__(self, root_name="TN"):
        self.creds = None
        self.authenticate()
        self.service = build('drive', 'v3', credentials=self.creds)
        self.root_id = self.get_or_create_folder(root_name)

    def authenticate(self):
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                self.creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(self.creds.to_json())

    def get_or_create_folder(self, name, parent_id=None):
        query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id: query += f" and '{parent_id}' in parents"
        res = self.service.files().list(q=query, spaces='drive').execute().get('files', [])
        if not res:
            meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder'}
            if parent_id: meta['parents'] = [parent_id]
            return self.service.files().create(body=meta, fields='id').execute().get('id')
        return res[0].get('id')

    def list_items(self, parent_id, mime_type=None):
        query = f"'{parent_id}' in parents and trashed=false"
        if mime_type: query += f" and mimeType='{mime_type}'"
        return self.service.files().list(q=query, spaces='drive', fields='files(id, name)').execute().get('files', [])

    def download_json(self, file_id):
        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done: _, done = downloader.next_chunk()
        return json.loads(fh.getvalue().decode('utf-8'))

    def upload_json(self, name, data, parent_id, file_id=None):
        if name.endswith('.json'): name = name[:-5]
        
        meta = {'name': f"{name}.json"}
        media = MediaIoBaseUpload(io.BytesIO(json.dumps(data, ensure_ascii=False).encode('utf-8')), mimetype='application/json')
        if file_id:
            self.service.files().update(fileId=file_id, body=meta, media_body=media).execute()
        else:
            meta['parents'] = [parent_id]
            self.service.files().create(body=meta, media_body=media).execute()

    def delete_file(self, file_id):
        self.service.files().delete(fileId=file_id).execute()

def parse_format(text):
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    qs = []
    for i in range(0, len(lines), 6):
        try:
            qs.append({"q": lines[i], "o": lines[i+1:i+5], "a": lines[i+5][-1].upper()})
        except: break
    return qs

def convert_to_text(questions):
    res = []
    for q in questions:
        res.append(q['q']); res.extend(q['o']); res.append(f"Đáp án: {q['a']}")
    return "\n".join(res)

class Worker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func, self.args, self.kwargs = func, args, kwargs
    def run(self):
        try:
            res = self.func(*self.args, **self.kwargs)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))

# --- UI COMPONENTS ---
class NotionButton(QPushButton):
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
        if primary:
            self.setStyleSheet(f"QPushButton {{ background-color: {N_PRIMARY}; color: {N_BG}; border: 1px solid {N_PRIMARY}; border-style: solid; border-radius: 4px; font-weight: bold; padding: 10px 15px; outline: none; }} QPushButton:hover {{ background-color: #454545; border-color: #454545; }}")
        else:
            self.setStyleSheet(f"QPushButton {{ background-color: {N_BG}; color: {N_TEXT}; border: 1px solid {N_BORDER}; border-style: solid; border-radius: 4px; font-weight: bold; padding: 10px 15px; outline: none; }} QPushButton:hover {{ background-color: {N_HOVER}; }}")

class OptionButton(QPushButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFlat(True) 
        self.current_state = "normal"
        self.update_ui()

    def set_state(self, state):
        self.current_state = state
        self.update_ui()

    def update_ui(self):
        base = "border-style: solid; border-radius: 6px; font-size: 16px; text-align: left; padding: 15px; outline: none; "
        if self.current_state == "correct":
            self.setStyleSheet(f"QPushButton {{ {base} background-color: {N_GREEN_BG}; border: 2px solid {N_GREEN_BD}; color: {N_GREEN_BD}; font-weight: bold; }}")
        elif self.current_state == "incorrect":
            self.setStyleSheet(f"QPushButton {{ {base} background-color: {N_RED_BG}; border: 2px solid {N_RED_BD}; color: {N_RED_BD}; font-weight: bold; }}")
        else:
            self.setStyleSheet(f"QPushButton {{ {base} background-color: {N_BG}; border: 1px solid {N_BORDER}; color: {N_TEXT}; font-weight: normal; }} QPushButton:hover {{ background-color: {N_HOVER}; border: 1px solid #D9D9D7; }} QPushButton:checked {{ background-color: #F2F1EE; border: 2px solid {N_PRIMARY}; font-weight: bold; }} QPushButton:disabled {{ color: {N_MUTED}; background-color: {N_BG}; border: 1px solid {N_BORDER}; }}")

class AccordionButton(QPushButton):
    def __init__(self, text, color):
        super().__init__(text)
        self.setCheckable(True); self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFlat(True)
        self.setStyleSheet(f"QPushButton {{ background-color: {N_BG}; border: 1px solid {color}; border-style: solid; border-radius: 6px; color: {color}; font-size: 16px; text-align: left; padding: 15px; font-weight: bold; outline: none; }} QPushButton:hover {{ background-color: {N_HOVER}; }} QPushButton:checked {{ background-color: {color}; color: white; }}")

# --- MAIN APP ---
class TN_Master(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TN - Trắc Nghiệm Thông Minh")
        self.resize(1300, 850)
        self.setStyleSheet(f"QMainWindow {{ background-color: {N_BG}; }} QWidget {{ color: {N_TEXT}; font-family: 'Segoe UI', Arial; }}")
        
        self.drive = DriveManager()
        self.current_folder_id = None
        self.current_exam_id = None 
        
        self.quiz_data = []
        self.quiz_index = 0
        self.quiz_mode = "test"
        self.user_answers = {}        
        self.flagged_qs = set()       
        self.practice_clicked = {}    

        self.confirm_callback = None
        self.view_before_confirm = 0

        self.init_ui()
        self.load_folders_bg()

    def init_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        layout = QHBoxLayout(central); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        
        # --- SIDEBAR ---
        sidebar = QFrame(); sidebar.setFixedWidth(260)
        sidebar.setStyleSheet(f"background-color: {N_SIDEBAR}; border-right: 1px solid {N_BORDER};")
        side_lyt = QVBoxLayout(sidebar)
        
        logo = QLabel("TN Workspace"); logo.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {N_TEXT}; margin: 15px 0; border: none;")
        self.folder_list = QListWidget()
        self.folder_list.setStyleSheet(f"QListWidget {{ background: transparent; border: none; font-size: 14px; outline: none; }} QListWidget::item {{ padding: 10px; border-radius: 4px; margin-bottom: 2px; }} QListWidget::item:hover {{ background-color: {N_HOVER}; }} QListWidget::item:selected {{ background-color: #EBEBEA; font-weight: bold; color: {N_TEXT}; }}")
        self.folder_list.itemClicked.connect(self.on_folder_select)
        
        lbl_db = QLabel("THƯ MỤC"); lbl_db.setStyleSheet(f"color: {N_MUTED}; font-weight: bold; font-size: 12px; border: none;")
        side_lyt.addWidget(logo); side_lyt.addWidget(lbl_db); side_lyt.addWidget(self.folder_list)
        
        h_folder_btn_lyt = QHBoxLayout()
        self.btn_new_f = NotionButton("+ Thư mục mới")
        self.btn_new_f.clicked.connect(self.toggle_folder_input)
        
        self.btn_del_f = QPushButton("Xóa")
        self.btn_del_f.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del_f.setFlat(True)
        self.btn_del_f.setStyleSheet(f"QPushButton {{ background-color: {N_BG}; color: {N_RED_BD}; border: 1px solid {N_BORDER}; border-style: solid; border-radius: 4px; font-weight: bold; padding: 10px; outline: none; }} QPushButton:hover {{ background-color: {N_RED_BG}; color: white; }}")
        self.btn_del_f.clicked.connect(self.delete_folder_confirm)
        self.btn_del_f.hide() 
        
        h_folder_btn_lyt.addWidget(self.btn_new_f)
        h_folder_btn_lyt.addWidget(self.btn_del_f)
        side_lyt.addLayout(h_folder_btn_lyt)
        
        self.folder_input_widget = QWidget(); fi_lyt = QVBoxLayout(self.folder_input_widget); fi_lyt.setContentsMargins(0,0,0,0)
        self.txt_folder_name = QLineEdit(); self.txt_folder_name.setPlaceholderText("Tên thư mục...")
        self.txt_folder_name.setStyleSheet(f"background: {N_BG}; border: 1px solid {N_BORDER}; border-radius: 4px; padding: 8px; outline: none;")
        h_fi_btn = QHBoxLayout()
        btn_fi_create = NotionButton("Tạo", primary=True); btn_fi_create.clicked.connect(self.create_folder_bg)
        btn_fi_cancel = NotionButton("Hủy"); btn_fi_cancel.clicked.connect(self.toggle_folder_input)
        h_fi_btn.addWidget(btn_fi_create); h_fi_btn.addWidget(btn_fi_cancel)
        fi_lyt.addWidget(self.txt_folder_name); fi_lyt.addLayout(h_fi_btn)
        side_lyt.addWidget(self.folder_input_widget); self.folder_input_widget.hide()
        
        # --- WORKSPACE MAIN ---
        workspace = QWidget()
        self.work_lyt = QVBoxLayout(workspace); self.work_lyt.setContentsMargins(40, 30, 40, 30)
        
        ctrl_header = QFrame()
        h_lyt = QHBoxLayout(ctrl_header); h_lyt.setContentsMargins(0,0,0,10)
        self.lbl_status = QLabel("Trạng thái: Sẵn sàng"); self.lbl_status.setStyleSheet(f"color: {N_MUTED}; font-weight: bold;")
        self.btn_create_exam = NotionButton("⚡ Tạo đề thi mới", primary=True)
        self.btn_create_exam.clicked.connect(self.show_import_view)
        h_lyt.addWidget(self.lbl_status); h_lyt.addStretch(); h_lyt.addWidget(self.btn_create_exam)
        
        self.view_stack = QStackedWidget()
        
        # VIEW 0: LIST EXAMS
        self.exam_list_scroll = QScrollArea(); self.exam_list_scroll.setWidgetResizable(True); self.exam_list_scroll.setStyleSheet("border: none; background: transparent;")
        self.exam_container = QWidget(); self.exam_lyt = QVBoxLayout(self.exam_container); self.exam_lyt.setAlignment(Qt.AlignmentFlag.AlignTop); self.exam_lyt.setSpacing(10)
        self.exam_list_scroll.setWidget(self.exam_container)
        
        # VIEW 1: IMPORT / EDIT
        self.import_widget = QWidget(); imp_lyt = QVBoxLayout(self.import_widget)
        self.imp_title = QTextEdit(); self.imp_title.setPlaceholderText("Tên đề thi..."); self.imp_title.setFixedHeight(40)
        self.imp_title.setStyleSheet(f"background-color: {N_BG}; border: 1px solid {N_BORDER}; border-radius: 4px; padding: 8px; outline: none; font-weight: bold;")
        self.imp_body = QTextEdit(); self.imp_body.setPlaceholderText("Dán nội dung trắc nghiệm format A,B,C,D...")
        self.imp_body.setStyleSheet(f"background-color: {N_BG}; border: 1px solid {N_BORDER}; border-radius: 4px; padding: 8px; outline: none;")
        
        self.btn_save_imp = NotionButton("Lưu lên Drive", primary=True); self.btn_save_imp.clicked.connect(self.process_import_bg)
        self.btn_cancel_imp = NotionButton("Hủy"); self.btn_cancel_imp.clicked.connect(lambda: self.switch_view(0))
        h_imp = QHBoxLayout(); h_imp.addWidget(self.btn_save_imp); h_imp.addWidget(self.btn_cancel_imp); h_imp.addStretch()
        imp_lyt.addWidget(self.imp_title); imp_lyt.addWidget(self.imp_body); imp_lyt.addLayout(h_imp)

        # VIEW 2: QUIZ SESSION
        self.quiz_widget = QWidget(); quiz_main_lyt = QHBoxLayout(self.quiz_widget); quiz_main_lyt.setContentsMargins(0,0,0,0)
        
        self.q_area = QFrame(); self.q_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        q_lyt = QVBoxLayout(self.q_area)
        
        q_toolbar = QHBoxLayout()
        self.btn_back = NotionButton("← Quay lại")
        self.btn_back.clicked.connect(self.exit_quiz_confirm)
        self.btn_flag = NotionButton("⚑ Đánh cờ")
        self.btn_flag.clicked.connect(self.toggle_flag)
        q_toolbar.addWidget(self.btn_back); q_toolbar.addStretch(); q_toolbar.addWidget(self.btn_flag)

        self.lbl_q_text = QLabel(); self.lbl_q_text.setWordWrap(True)
        self.lbl_q_text.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {N_TEXT}; margin: 20px 0;")
        
        self.quiz_group = QButtonGroup()
        self.quiz_group.buttonClicked.connect(self.handle_answer_selection)
        self.opts = []
        for i in range(4):
            btn = OptionButton()
            self.opts.append(btn); self.quiz_group.addButton(btn, i)
        
        self.q_footer = QHBoxLayout()
        self.btn_prev = NotionButton("Chuyển câu trước")
        self.btn_prev.clicked.connect(lambda: self.navigate_q(-1))
        self.btn_next = NotionButton("Chuyển câu sau")
        self.btn_next.clicked.connect(lambda: self.navigate_q(1))
        self.btn_submit_exam = NotionButton("Nộp bài hoàn thành", primary=True)
        self.btn_submit_exam.clicked.connect(self.submit_exam_confirm)
        
        self.lbl_feedback = QLabel(""); self.lbl_feedback.setStyleSheet(f"font-size: 16px; font-weight: bold; margin-left: 15px;")
        
        self.q_footer.addWidget(self.btn_prev); self.q_footer.addWidget(self.lbl_feedback); self.q_footer.addStretch()
        self.q_footer.addWidget(self.btn_next); self.q_footer.addWidget(self.btn_submit_exam)

        q_lyt.addLayout(q_toolbar); q_lyt.addWidget(self.lbl_q_text)
        for btn in self.opts: q_lyt.addWidget(btn)
        q_lyt.addLayout(self.q_footer)

        # --- BẢNG TIẾN ĐỘ ---
        # Đã mở rộng chiều rộng từ 280 -> 320px để hiển thị thoải mái 5 cột vuông vắn
        self.nav_area = QFrame(); self.nav_area.setFixedWidth(320) 
        self.nav_area.setStyleSheet(f"background-color: {N_SIDEBAR}; border-radius: 8px; border: 1px solid {N_BORDER}; margin-left: 20px;")
        nav_lyt = QVBoxLayout(self.nav_area)
        lbl_nav = QLabel("Tiến độ làm bài"); lbl_nav.setStyleSheet(f"color: {N_MUTED}; font-weight: bold; border: none; margin-bottom: 10px;")
        nav_lyt.addWidget(lbl_nav)
        
        scroll_nav = QScrollArea()
        scroll_nav.setWidgetResizable(True); scroll_nav.setStyleSheet("border: none; background: transparent;")
        
        self.nav_container = QWidget()
        self.nav_wrap_vbox = QVBoxLayout(self.nav_container)
        self.nav_wrap_vbox.setContentsMargins(0, 0, 0, 0)
        self.nav_wrap_vbox.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        self.nav_grid_widget = QWidget()
        self.nav_grid_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self.nav_grid = QGridLayout(self.nav_grid_widget)
        self.nav_grid.setSpacing(10)
        self.nav_grid.setContentsMargins(0, 0, 0, 0)
        
        self.nav_wrap_vbox.addWidget(self.nav_grid_widget)
        
        scroll_nav.setWidget(self.nav_container)
        nav_lyt.addWidget(scroll_nav)
        
        quiz_main_lyt.addWidget(self.q_area); quiz_main_lyt.addWidget(self.nav_area)

        # VIEW 3: RESULTS SCREEN
        self.res_widget = QWidget(); res_main_lyt = QVBoxLayout(self.res_widget)
        
        res_toolbar = QHBoxLayout()
        btn_res_back = NotionButton("← Quay lại danh sách", primary=True)
        btn_res_back.clicked.connect(lambda: self.switch_view(0))
        res_toolbar.addWidget(btn_res_back); res_toolbar.addStretch()
        
        self.res_scroll = QScrollArea()
        self.res_scroll.setWidgetResizable(True); self.res_scroll.setStyleSheet("border: none; background: transparent;")
        self.res_container = QWidget()
        self.res_lyt = QVBoxLayout(self.res_container)
        self.res_lyt.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.lbl_res_score = QLabel("0.0 / 10.0")
        self.lbl_res_score.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {N_TEXT};")
        self.lbl_res_count = QLabel("Số câu đúng: 0 / 0")
        self.lbl_res_count.setStyleSheet(f"font-size: 20px; color: {N_MUTED}; margin-bottom: 20px;")
        
        self.btn_toggle_wrong = AccordionButton("▼ Danh sách câu sai (0)", N_RED_BD)
        self.btn_toggle_wrong.clicked.connect(lambda: self.wrong_content.setVisible(self.btn_toggle_wrong.isChecked()))
        self.wrong_content = QFrame()
        self.wrong_lyt = QVBoxLayout(self.wrong_content)
        self.wrong_content.hide()

        self.btn_toggle_correct = AccordionButton("▼ Danh sách câu đúng (0)", N_GREEN_BD)
        self.btn_toggle_correct.clicked.connect(lambda: self.correct_content.setVisible(self.btn_toggle_correct.isChecked()))
        self.correct_content = QFrame()
        self.correct_lyt = QVBoxLayout(self.correct_content)
        self.correct_content.hide()

        self.res_lyt.addWidget(self.lbl_res_score); self.res_lyt.addWidget(self.lbl_res_count)
        self.res_lyt.addWidget(self.btn_toggle_wrong); self.res_lyt.addWidget(self.wrong_content)
        self.res_lyt.addWidget(self.btn_toggle_correct); self.res_lyt.addWidget(self.correct_content)
        
        self.res_scroll.setWidget(self.res_container)
        res_main_lyt.addLayout(res_toolbar); res_main_lyt.addWidget(self.res_scroll)

        # VIEW 4: MENU ĐỀ THI
        self.menu_widget = QWidget(); menu_lyt = QVBoxLayout(self.menu_widget); menu_lyt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_menu_title = QLabel("Tên đề"); self.lbl_menu_title.setStyleSheet("font-size: 28px; font-weight: bold; margin-bottom: 20px;"); self.lbl_menu_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_m_prac = NotionButton("BẮT ĐẦU LUYỆN TẬP", primary=True); btn_m_prac.clicked.connect(lambda: self.start_quiz_prep("practice"))
        btn_m_test = NotionButton("BẮT ĐẦU KIỂM TRA", primary=True); btn_m_test.clicked.connect(lambda: self.start_quiz_prep("test"))
        btn_m_edit = NotionButton("Sửa nội dung đề"); btn_m_edit.clicked.connect(self.prepare_edit)
        btn_m_del = NotionButton("Xóa đề thi"); btn_m_del.setStyleSheet(f"QPushButton {{ background-color: {N_BG}; color: {N_RED_BD}; border: 1px solid {N_BORDER}; border-style: solid; border-radius: 4px; font-weight: bold; padding: 10px 15px; outline: none; }} QPushButton:hover {{ background-color: {N_RED_BG}; }}")
        btn_m_del.clicked.connect(self.delete_exam_confirm)
        btn_m_back = NotionButton("Quay lại danh sách"); btn_m_back.clicked.connect(lambda: self.switch_view(0))
        
        for b in [self.lbl_menu_title, btn_m_prac, btn_m_test, btn_m_edit, btn_m_del, btn_m_back]:
            menu_lyt.addWidget(b); menu_lyt.addSpacing(5)

        # VIEW 5: CONFIRMATION
        self.confirm_widget = QWidget(); conf_lyt = QVBoxLayout(self.confirm_widget); conf_lyt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_conf_title = QLabel("Xác nhận"); self.lbl_conf_title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;"); self.lbl_conf_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_conf_msg = QLabel("Message"); self.lbl_conf_msg.setStyleSheet("font-size: 16px; margin-bottom: 30px;"); self.lbl_conf_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h_conf_btn = QHBoxLayout()
        self.btn_conf_yes = NotionButton("Đồng ý", primary=True); self.btn_conf_no = NotionButton("Hủy")
        self.btn_conf_no.clicked.connect(lambda: self.switch_view(self.view_before_confirm))
        h_conf_btn.addWidget(self.btn_conf_yes); h_conf_btn.addWidget(self.btn_conf_no)
        conf_lyt.addWidget(self.lbl_conf_title); conf_lyt.addWidget(self.lbl_conf_msg); conf_lyt.addLayout(h_conf_btn)

        for v in [self.exam_list_scroll, self.import_widget, self.quiz_widget, self.res_widget, self.menu_widget, self.confirm_widget]: 
            self.view_stack.addWidget(v)
        
        self.work_lyt.addWidget(ctrl_header); self.work_lyt.addWidget(self.view_stack)
        layout.addWidget(sidebar); layout.addWidget(workspace)

    # --- UI & VIEW MANAGER ---
    def switch_view(self, index):
        self.view_stack.setCurrentIndex(index)
        if index == 0:
            self.btn_create_exam.show()
        else:
            self.btn_create_exam.hide()

    def set_status(self, text, loading=False):
        self.lbl_status.setText(text)
        if "Lỗi" in text: self.lbl_status.setStyleSheet(f"color: {N_RED_BD}; font-weight: bold;")
        else: self.lbl_status.setStyleSheet(f"color: {N_MUTED}; font-weight: bold;")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor if loading else Qt.CursorShape.ArrowCursor)

    def show_confirm(self, title, msg, yes_txt, yes_action, is_red=False):
        self.view_before_confirm = self.view_stack.currentIndex()
        self.lbl_conf_title.setText(title); self.lbl_conf_msg.setText(msg); self.btn_conf_yes.setText(yes_txt)
        if is_red:
            self.btn_conf_yes.setStyleSheet(f"QPushButton {{ background-color: {N_RED_BG}; color: {N_RED_BD}; border: 1px solid {N_RED_BD}; border-style: solid; border-radius: 4px; font-weight: bold; padding: 10px 15px; outline: none; }} QPushButton:hover {{ background-color: #FAD7DA; }}")
        else:
            self.btn_conf_yes.setStyleSheet(f"QPushButton {{ background-color: {N_PRIMARY}; color: {N_BG}; border: 1px solid {N_PRIMARY}; border-style: solid; border-radius: 4px; font-weight: bold; padding: 10px 15px; outline: none; }} QPushButton:hover {{ background-color: #454545; }}")
        
        try: self.btn_conf_yes.clicked.disconnect()
        except: pass
        self.btn_conf_yes.clicked.connect(yes_action)
        self.switch_view(5)

    def handle_error(self, err):
        self.set_status(f"Lỗi hệ thống: {str(err)}")
        self.show_confirm("Lỗi kết nối", str(err), "Đã hiểu", lambda: self.switch_view(self.view_before_confirm))
        self.btn_conf_no.hide()

    def clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

    # --- FOLDER LOGIC ---
    def toggle_folder_input(self):
        if self.folder_input_widget.isVisible(): 
            self.folder_input_widget.hide(); self.btn_new_f.show()
            if self.current_folder_id: self.btn_del_f.show()
        else: 
            self.folder_input_widget.show(); self.btn_new_f.hide(); self.btn_del_f.hide(); self.txt_folder_name.clear()

    def load_folders_bg(self):
        self.set_status("Đang đồng bộ...", True)
        self.worker = Worker(self.drive.list_items, self.drive.root_id, "application/vnd.google-apps.folder")
        self.worker.finished.connect(self.on_folders_loaded)
        self.worker.error.connect(self.handle_error); self.worker.start()

    def on_folders_loaded(self, folders):
        self.folder_list.clear(); self.folders_data = folders
        for f in folders: self.folder_list.addItem(f['name'])
        self.set_status("Sẵn sàng")

    def create_folder_bg(self):
        name = self.txt_folder_name.text().strip()
        if name:
            self.set_status("Đang tạo...", True); self.toggle_folder_input()
            self.worker = Worker(self.drive.get_or_create_folder, name, self.drive.root_id)
            self.worker.finished.connect(lambda r: QTimer.singleShot(100, self.load_folders_bg))
            self.worker.error.connect(self.handle_error); self.worker.start()

    def on_folder_select(self, item):
        self.current_folder_id = next(f['id'] for f in self.folders_data if f['name'] == item.text())
        self.btn_del_f.show()
        self.refresh_exams_bg()

    def delete_folder_confirm(self):
        if not self.current_folder_id: return
        self.btn_conf_no.show()
        self.show_confirm("Xóa thư mục", "Bạn có chắc chắn muốn xóa thư mục này và TOÀN BỘ đề thi bên trong không?", "Xóa thư mục", self.do_delete_folder, True)

    def do_delete_folder(self):
        self.set_status("Đang xóa thư mục...", True)
        self.worker = Worker(self.drive.delete_file, self.current_folder_id)
        self.worker.finished.connect(self.on_folder_deleted)
        self.worker.error.connect(self.handle_error)
        self.worker.start()

    def on_folder_deleted(self, res):
        self.current_folder_id = None
        self.btn_del_f.hide()
        self.clear_layout(self.exam_lyt)
        self.switch_view(0)
        QTimer.singleShot(100, self.load_folders_bg)

    def refresh_exams_bg(self):
        self.set_status("Đang tải đề...", True)
        self.worker = Worker(self.drive.list_items, self.current_folder_id, "application/json")
        self.worker.finished.connect(self.on_exams_loaded)
        self.worker.error.connect(self.handle_error); self.worker.start()

    def on_exams_loaded(self, exams):
        self.clear_layout(self.exam_lyt)
            
        for ex in exams:
            display_name = ex['name']
            if display_name.endswith('.json'): display_name = display_name[:-5]
            
            btn = QPushButton(f"  📄  {display_name}")
            btn.setFlat(True); btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{ background-color: {N_BG}; border: 1px solid {N_BORDER}; border-radius: 6px; 
                               color: {N_TEXT}; font-size: 16px; font-weight: bold; text-align: left; padding: 20px; margin-bottom: 5px; outline: none; border-style: solid; }}
                QPushButton:hover {{ background-color: {N_HOVER}; }}
            """)
            btn.clicked.connect(lambda ch, e=ex: self.open_menu_view(e))
            self.exam_lyt.addWidget(btn)
        self.switch_view(0); self.set_status("Sẵn sàng")

    # --- IMPORT / EDIT LOGIC ---
    def show_import_view(self):
        if self.current_folder_id:
            self.current_exam_id = None
            self.imp_title.clear(); self.imp_body.clear()
            self.btn_save_imp.setText("Lưu lên Drive")
            self.btn_cancel_imp.setText("Hủy")
            self.switch_view(1)
        else:
            self.set_status("Lỗi: Vui lòng chọn thư mục bên trái trước")

    def process_import_bg(self):
        title, body = self.imp_title.toPlainText().strip(), self.imp_body.toPlainText().strip()
        qs = parse_format(body)
        if title and qs:
            self.set_status("Đang lưu...", True)
            self.worker = Worker(self.drive.upload_json, title, {"questions": qs}, self.current_folder_id, self.current_exam_id)
            self.worker.finished.connect(lambda r: QTimer.singleShot(100, self.refresh_exams_bg))
            self.worker.error.connect(self.handle_error); self.worker.start()

    # --- EXAM MENU ---
    def open_menu_view(self, exam_info):
        self.current_exam_id = exam_info['id']
        display_name = exam_info['name']
        if display_name.endswith('.json'): display_name = display_name[:-5]
        self.lbl_menu_title.setText(display_name)
        self.switch_view(4)

    def prepare_edit(self):
        self.set_status("Đang tải dữ liệu để sửa...", True)
        self.imp_title.setText(self.lbl_menu_title.text())
        self.btn_save_imp.setText("Lưu lại thay đổi")
        self.btn_cancel_imp.setText("Hủy thay đổi")
        self.worker = Worker(self.drive.download_json, self.current_exam_id)
        self.worker.finished.connect(self.on_edit_data_loaded)
        self.worker.error.connect(self.handle_error); self.worker.start()

    def on_edit_data_loaded(self, data):
        self.imp_body.setText(convert_to_text(data['questions']))
        self.switch_view(1); self.set_status("Sẵn sàng")

    def delete_exam_confirm(self):
        self.btn_conf_no.show()
        self.show_confirm("Xóa đề thi", "Bạn có chắc chắn muốn xóa vĩnh viễn đề này?", "Xóa", self.do_delete, True)

    def do_delete(self):
        self.set_status("Đang xóa...", True)
        self.worker = Worker(self.drive.delete_file, self.current_exam_id)
        self.worker.finished.connect(lambda r: QTimer.singleShot(100, self.refresh_exams_bg))
        self.worker.error.connect(self.handle_error); self.worker.start()

    def start_quiz_prep(self, mode):
        self.quiz_mode = mode
        self.set_status("Đang chuẩn bị đề...", True)
        self.worker = Worker(self.drive.download_json, self.current_exam_id)
        self.worker.finished.connect(self.start_quiz_session)
        self.worker.error.connect(self.handle_error); self.worker.start()

    # --- QUIZ ENGINE ---
    def start_quiz_session(self, data):
        self.quiz_data = data['questions']
        self.quiz_index = 0
        self.user_answers.clear(); self.flagged_qs.clear(); self.practice_clicked.clear()
        
        if self.quiz_mode == "practice":
            self.nav_area.hide(); self.btn_flag.hide()
            self.btn_prev.hide(); self.btn_next.hide(); self.btn_submit_exam.hide()
        else:
            self.nav_area.show(); self.btn_flag.show()
            self.btn_prev.show(); self.btn_next.show(); self.btn_submit_exam.show()
            
            self.clear_layout(self.nav_grid)
            self.nav_btns = []
            
            # --- TẠO CÁC Ô SỐ HÌNH VUÔNG ---
            for i in range(len(self.quiz_data)):
                btn = QPushButton(str(i + 1))
                btn.setFixedSize(40, 40)
                btn.setFlat(True) 
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda ch, idx=i: self.jump_to_q(idx))
                
                self.nav_grid.addWidget(btn, i // 5, i % 5)
                self.nav_btns.append(btn)
                
        self.switch_view(2)
        self.load_question()
        self.set_status("Chế độ: Luyện tập tuyến tính" if self.quiz_mode == "practice" else "Chế độ: Kiểm tra", False)

    def exit_quiz_confirm(self):
        self.btn_conf_no.show()
        self.show_confirm("Thoát làm bài", "Kết quả bài làm sẽ không được lưu. Bạn có chắc chắn muốn thoát?", "Đồng ý", lambda: self.switch_view(0))

    def load_question(self):
        q = self.quiz_data[self.quiz_index]
        self.lbl_q_text.setText(f"Câu {self.quiz_index + 1} / {len(self.quiz_data)}:\n\n{q['q']}")
        self.lbl_feedback.setText("")
        
        self.quiz_group.setExclusive(False)
        mapping = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
        
        for i, btn in enumerate(self.opts):
            btn.setText(q['o'][i])
            btn.set_state("normal") 
            btn.setEnabled(True) 
            
            if self.quiz_mode == "test":
                btn.setChecked(self.user_answers.get(self.quiz_index) == i)
            else:
                clicked_in_past = self.practice_clicked.get(self.quiz_index, set())
                if i in clicked_in_past:
                    is_correct = (mapping[i] == q['a'])
                    btn.set_state("correct" if is_correct else "incorrect")
                    if is_correct: 
                        self.lbl_feedback.setText("✓ Chính xác. Đang chuyển câu..."); self.lbl_feedback.setStyleSheet(f"color: {N_GREEN_BD}; margin-left: 15px;")
                        for b in self.opts: b.setEnabled(False) 
        
        self.quiz_group.setExclusive(True if self.quiz_mode == "test" else False)
        
        if self.quiz_mode == "test":
            self.btn_prev.setEnabled(self.quiz_index > 0); self.btn_next.setEnabled(self.quiz_index < len(self.quiz_data) - 1)
            is_flagged = self.quiz_index in self.flagged_qs
            self.btn_flag.setText("⚑ Bỏ cờ" if is_flagged else "⚑ Đánh cờ")
            self.btn_flag.setStyleSheet(f"background-color: {'#FFF3E0' if is_flagged else N_BG}; color: {'#E65100' if is_flagged else N_TEXT}; border: 1px solid {N_BORDER}; border-radius: 4px; padding: 10px 15px; font-weight: bold; outline: none; border-style: solid;")
            self.update_nav_ui()

    def handle_answer_selection(self, button):
        opt_index = self.opts.index(button)
        
        if self.quiz_mode == "test":
            self.user_answers[self.quiz_index] = opt_index
            self.update_nav_ui()
        else:
            q = self.quiz_data[self.quiz_index]
            mapping = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
            is_correct = (mapping[opt_index] == q['a'])
            
            if self.quiz_index not in self.user_answers:
                self.user_answers[self.quiz_index] = opt_index
            
            if self.quiz_index not in self.practice_clicked: self.practice_clicked[self.quiz_index] = set()
            self.practice_clicked[self.quiz_index].add(opt_index)
            
            button.set_state("correct" if is_correct else "incorrect")
            
            if is_correct:
                self.lbl_feedback.setText("✓ Chính xác. Đang chuyển câu..."); self.lbl_feedback.setStyleSheet(f"color: {N_GREEN_BD}; margin-left: 15px;")
                for b in self.opts: b.setEnabled(False)
                QTimer.singleShot(800, self.auto_next_practice)
            else:
                self.lbl_feedback.setText("✗ Sai rồi. Bạn hãy chọn lại."); self.lbl_feedback.setStyleSheet(f"color: {N_RED_BD}; margin-left: 15px;")

    def auto_next_practice(self):
        self.quiz_index += 1
        if self.quiz_index < len(self.quiz_data):
            self.load_question()
        else:
            self.do_submit_exam() 

    def toggle_flag(self):
        if self.quiz_index in self.flagged_qs: self.flagged_qs.remove(self.quiz_index)
        else: self.flagged_qs.add(self.quiz_index)
        self.load_question()

    def jump_to_q(self, idx):
        self.quiz_index = idx; self.load_question()

    def navigate_q(self, step):
        self.quiz_index += step; self.load_question()

    def update_nav_ui(self):
        for i, btn in enumerate(self.nav_btns):
            bg = "#EBEBEA" if i in self.user_answers else N_BG
            color = N_TEXT 
            border = f"2px solid #E65100;" if i in self.flagged_qs else (f"2px solid {N_PRIMARY};" if i == self.quiz_index else f"1px solid {N_BORDER};")
            
            style = "min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; border-radius: 4px; font-weight: bold; font-size: 14px; outline: none; border-style: solid; margin: 0px; padding: 0px;"
            btn.setStyleSheet(f"QPushButton {{ background-color: {bg}; border: {border}; color: {color}; {style} }} QPushButton:hover {{ background-color: {N_HOVER}; }}")

    # --- RESULTS SCREEN ---
    def submit_exam_confirm(self):
        if self.quiz_mode == "test":
            unanswered = len(self.quiz_data) - len(self.user_answers)
            if unanswered > 0:
                self.btn_conf_no.show()
                self.show_confirm("Nộp bài", f"Bạn còn {unanswered} câu chưa làm. Vẫn nộp bài?", "Nộp bài", self.do_submit_exam)
                return
        self.do_submit_exam()

    def do_submit_exam(self):
        self.clear_layout(self.wrong_lyt)
        self.clear_layout(self.correct_lyt)

        correct_count = 0
        wrong_count = 0
        mapping = {0: 'A', 1: 'B', 2: 'C', 3: 'D'}
        idx_mapping = {'A': 0, 'B': 1, 'C': 2, 'D': 3}

        for i, q in enumerate(self.quiz_data):
            ans_char = q['a']
            correct_opt_idx = idx_mapping[ans_char]
            correct_text = f"{ans_char}. {q['o'][correct_opt_idx]}"
            
            is_correct = False
            user_opt_idx = self.user_answers.get(i)
            
            if user_opt_idx is not None:
                user_char = mapping[user_opt_idx]
                user_text = f"{user_char}. {q['o'][user_opt_idx]}"
                is_correct = (user_char == ans_char)
            else:
                user_text = "Chưa trả lời"

            item_box = QFrame()
            item_box.setStyleSheet(f"background-color: {N_BG}; border: 1px solid {N_BORDER}; border-radius: 6px; margin-bottom: 10px;")
            item_lyt = QVBoxLayout(item_box); item_lyt.setContentsMargins(15,15,15,15)
            
            lbl_q = QLabel(f"Câu {i+1}: {q['q']}"); lbl_q.setWordWrap(True); lbl_q.setStyleSheet(f"font-weight: bold; font-size: 16px; border: none;")
            item_lyt.addWidget(lbl_q)

            if is_correct:
                correct_count += 1
                lbl_ans = QLabel(f"✓ Đáp án: {correct_text}")
                lbl_ans.setStyleSheet(f"color: {N_GREEN_BD}; font-weight: bold; border: none; margin-top: 5px;")
                item_lyt.addWidget(lbl_ans)
                self.correct_lyt.addWidget(item_box)
            else:
                wrong_count += 1
                lbl_user = QLabel(f"✗ Bạn chọn: {user_text}")
                lbl_user.setStyleSheet(f"color: {N_RED_BD}; font-weight: bold; border: none; margin-top: 5px;")
                lbl_correct = QLabel(f"→ Đáp án đúng: {correct_text}")
                lbl_correct.setStyleSheet(f"color: {N_GREEN_BD}; font-weight: bold; border: none; margin-top: 5px;")
                item_lyt.addWidget(lbl_user); item_lyt.addWidget(lbl_correct)
                self.wrong_lyt.addWidget(item_box)

        # Xử lý điểm thông minh (Bỏ .0 nếu là số nguyên)
        score_10 = (correct_count / len(self.quiz_data)) * 10
        if score_10.is_integer(): score_str = f"{int(score_10)}"
        else: score_str = f"{round(score_10, 2)}"
        
        self.lbl_res_score.setText(f"{score_str} / 10")
        self.lbl_res_count.setText(f"Số câu đúng: {correct_count} / {len(self.quiz_data)}")
        
        self.btn_toggle_wrong.setText(f"▼ Danh sách câu sai ({wrong_count})")
        self.btn_toggle_correct.setText(f"▼ Danh sách câu đúng ({correct_count})")
        
        self.btn_toggle_wrong.setChecked(False); self.wrong_content.hide()
        self.btn_toggle_correct.setChecked(False); self.correct_content.hide()

        self.switch_view(3)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TN_Master()
    window.show()
    sys.exit(app.exec())