import os
import sys

# --- SOLUSI ERROR DLL: MATIKAN GPU SEBELUM IMPORT APAPUN ---
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["QT_API"] = "pyqt5"

import cv2
import numpy as np
import torch
import time
import queue
import math
from datetime import date, datetime
import requests

# PyQt5 Imports
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, \
    QLabel, QGridLayout, QScrollArea, QSizePolicy, QMessageBox, \
    QPushButton, QVBoxLayout, QTabWidget, QHBoxLayout, QTableWidget, QTableWidgetItem, QDateEdit, QHeaderView, QDialog
from PyQt5.QtGui import QPixmap, QIcon, QImage, QPalette
from PyQt5.QtSql import QSqlDatabase, QSqlQuery
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QEvent, QObject, QDateTime
from PyQt5 import QtCore

# YOLO Import
from ultralytics import YOLO

# --- SETUP JALUR (PATH) DRIVE C ---
# Folder foto langsung ke folder public Laravel agar muncul di web
output_folder = r'C:\laragon\www\webmonitoring\public\foto'
# File database di dalam folder database Laravel
database_path = r'C:\laragon\www\webmonitoring\database\logging.db'

# --- SETUP MODEL ---
try:
    model = YOLO('best.pt')
    model.to('cpu') 
except Exception as e:
    print(f"Model custom tidak ditemukan, menggunakan yolo11n standar. Error: {e}")
    model = YOLO('yolo11n.pt')
    model.to('cpu')

if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# --- SETUP KAMERA DINAMIS ---
def read_ip_cameras(file_path):
    ip_cameras = []
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip():
                    ip_cameras.append(line.strip())
    else:
        print(f"File {file_path} tidak ditemukan, menggunakan default webcam.")
        ip_cameras.append("0")
    return ip_cameras

file_path = "ipcamera.txt"
array_ip_cameras = read_ip_cameras(file_path)
NUM_CAMERAS = len(array_ip_cameras)

frame_queues = [queue.Queue(maxsize=30) for _ in range(NUM_CAMERAS)]
display_queues = [queue.Queue(maxsize=30) for _ in range(NUM_CAMERAS)]

class ImageViewer(QDialog):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle("Bukti Pelanggaran")
        layout = QVBoxLayout()
        foto_full_path = os.path.join(output_folder, image_path)
        label = QLabel()
        pixmap = QPixmap(foto_full_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(800, 600, Qt.KeepAspectRatio)
            label.setPixmap(pixmap)
        else:
            label.setText(f"Gambar tidak ditemukan")
        layout.addWidget(label)
        self.setLayout(layout)

class CaptureIpCameraFramesWorker(QThread):
    def __init__(self, url, frame_queue) -> None:
        super(CaptureIpCameraFramesWorker, self).__init__()
        self.frame_queue = frame_queue
        self.url = url
        self.__thread_active = True

    def run(self) -> None:
        video_source = int(self.url) if self.url.isdigit() else self.url
        cap = cv2.VideoCapture(video_source)
        while self.__thread_active:
            ret, frame = cap.read()
            if ret:
                if not self.frame_queue.full():
                    self.frame_queue.put(frame)
            else:
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(video_source)
        cap.release()

    def stop(self) -> None:
        self.__thread_active = False

class DisplayIpCameraFramesWorker(QThread):
    ImageUpdated = pyqtSignal(QImage)
    def __init__(self, frame_queue) -> None:
        super(DisplayIpCameraFramesWorker, self).__init__()
        self.frame_queue = frame_queue
        self.__thread_active = True

    def run(self) -> None:
        while self.__thread_active:
            try:
                frame = self.frame_queue.get(timeout=1)
                cv_rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = cv_rgb_image.shape
                qt_image = QImage(cv_rgb_image.data, w, h, w * ch, QImage.Format_RGB888)
                self.ImageUpdated.emit(qt_image)
            except: continue

    def stop(self) -> None:
        self.__thread_active = False

class InferenceFramesWorker(QThread):
    warningSignal = pyqtSignal(int, str, str) 
    result_ready = pyqtSignal(str, str, str, str)

    def __init__(self, input_queues, output_queues) -> None:
        super(InferenceFramesWorker, self).__init__()
        self.input_queues = input_queues
        self.output_queues = output_queues
        self.num_cams = len(input_queues)
        self.last_capture_times = [0] * self.num_cams
        self.__thread_active = True

    def run(self) -> None:
        curr = 0
        while self.__thread_active:
            if not self.input_queues[curr].empty():
                frame = self.input_queues[curr].get()
                results = model.predict(frame, conf=0.5, verbose=False, device='cpu') 
                result = results[0]
                annotated_frame = result.plot() 
                
                if not self.output_queues[curr].full():
                    self.output_queues[curr].put(annotated_frame)
                
                if (time.time() - self.last_capture_times[curr] >= 30):
                    boxes = result.boxes
                    v_type = None
                    for box in boxes:
                        cls = int(box.cls[0])
                        if cls == 1: v_type = "no-helmet"
                        elif cls == 2: v_type = "no-vest"
                        
                        if v_type:
                            ts = time.strftime("%m%d%H%M%S")
                            tgl = time.strftime("%Y-%m-%d")
                            wkt = datetime.now().strftime("%H:%M:%S")
                            loc = f"Camera {curr + 1}"
                            fname = f'{v_type}_{loc.replace(" ", "")}_{ts}.jpg'
                            fpath = os.path.join(output_folder, fname)
                            cv2.imwrite(fpath, annotated_frame)
                            self.result_ready.emit(tgl, wkt, loc, fname)
                            self.warningSignal.emit(curr + 1, v_type, fname)
                            self.last_capture_times[curr] = time.time()
                            break 

            curr = (curr + 1) % self.num_cams
            if all(q.empty() for q in self.input_queues):
                time.sleep(0.01)

    def stop(self) -> None:
        self.__thread_active = False

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super(MainWindow, self).__init__()
        self.camera_labels = []
        self.scroll_areas = []
        self.camera_states = []
        self.camera_stats_labels = []
        self.camera_stats_values = [0] * NUM_CAMERAS

        self.init_ui_elements()
        self.setup_threads()
        self.initUI()

    def init_ui_elements(self):
        self.btn_1 = QPushButton('Live Monitor')
        self.btn_2 = QPushButton('Logging / Data')
        self.btn_1.clicked.connect(lambda: self.right_widget.setCurrentIndex(0))
        self.btn_2.clicked.connect(lambda: self.right_widget.setCurrentIndex(1))

        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(['Tanggal', 'Waktu', 'Lokasi', 'Bukti'])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_widget.cellClicked.connect(self.show_image_table)

        self.stats_layout = QVBoxLayout()
        self.total_label = QLabel("Total Pelanggaran : 0")
        self.stats_layout.addWidget(self.total_label)

        for i in range(NUM_CAMERAS):
            lbl = QLabel("Menunggu Kamera...")
            lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            lbl.setScaledContents(True)
            lbl.installEventFilter(self)
            lbl.setObjectName(f"Camera_{i}")
            self.camera_labels.append(lbl)

            scr = QScrollArea()
            scr.setWidgetResizable(True)
            scr.setWidget(lbl)
            self.scroll_areas.append(scr)
            self.camera_states.append("Normal")

            s_lbl = QLabel(f"Camera {i+1} : 0")
            self.camera_stats_labels.append(s_lbl)
            self.stats_layout.addWidget(s_lbl)

    def setup_threads(self):
        self.inference_worker = InferenceFramesWorker(frame_queues, display_queues)
        self.inference_worker.warningSignal.connect(self.showWarningGeneric)
        self.inference_worker.result_ready.connect(self.insert_data)
        self.inference_worker.start()

        self.cap_workers = []
        self.disp_workers = []
        for i in range(NUM_CAMERAS):
            cw = CaptureIpCameraFramesWorker(array_ip_cameras[i], frame_queues[i])
            cw.start()
            self.cap_workers.append(cw)

            dw = DisplayIpCameraFramesWorker(display_queues[i])
            dw.ImageUpdated.connect(lambda img, idx=i: self.camera_labels[idx].setPixmap(QPixmap.fromImage(img)))
            dw.start()
            self.disp_workers.append(dw)

    def initUI(self) -> None:
        left_w = QWidget()
        l_lay = QVBoxLayout(); l_lay.addWidget(self.btn_1); l_lay.addWidget(self.btn_2); l_lay.addStretch()
        left_w.setLayout(l_lay)
        self.right_widget = QTabWidget()
        self.right_widget.addTab(self.ui1(), ''); self.right_widget.addTab(self.ui2(), '')
        self.right_widget.setStyleSheet("QTabBar::tab { width: 0; height: 0; }")
        main_lay = QHBoxLayout(); main_lay.addWidget(left_w, 1); main_lay.addWidget(self.right_widget, 5)
        c_widget = QWidget(); c_widget.setLayout(main_lay); self.setCentralWidget(c_widget)
        self.setWindowTitle("PPE Monitoring System - YOLO11 Drive C Mode"); self.resize(1280, 720)

    def ui1(self):
        w = QWidget(); lay = QGridLayout(); cols = math.ceil(math.sqrt(NUM_CAMERAS))
        for i, s in enumerate(self.scroll_areas): lay.addWidget(s, i // cols, i % cols)
        w.setLayout(lay); return w

    def ui2(self):
        w = QWidget(); lay = QVBoxLayout(); h_lay = QHBoxLayout()
        self.d_start = QDateEdit(calendarPopup=True); self.d_end = QDateEdit(calendarPopup=True)
        self.d_start.setDate(date.today().replace(day=1)); self.d_end.setDate(date.today())
        btn_f = QPushButton("Filter Data"); btn_f.clicked.connect(self.updatetable)
        h_lay.addWidget(QLabel("Dari:")); h_lay.addWidget(self.d_start); h_lay.addWidget(QLabel("Sampai:")); h_lay.addWidget(self.d_end); h_lay.addWidget(btn_f)
        lay.addLayout(h_lay); lay.addLayout(self.stats_layout); lay.addWidget(self.table_widget); w.setLayout(lay)
        self.updatetable(); return w

    def insert_data(self, tgl, wkt, loc, bukti):
        q = QSqlQuery()
        q.prepare("INSERT INTO data (Tanggal, Waktu, Lokasi, Bukti) VALUES (?, ?, ?, ?)")
        for val in [tgl, wkt, loc, bukti]: q.addBindValue(val)
        if q.exec_(): self.updatetable()

    def updatetable(self):
        self.table_widget.setRowCount(0); t_start = self.d_start.date().toString("yyyy-MM-dd"); t_end = self.d_end.date().toString("yyyy-MM-dd")
        q = QSqlQuery(); q.prepare("SELECT Tanggal, Waktu, Lokasi, Bukti FROM data WHERE Tanggal BETWEEN ? AND ?")
        q.addBindValue(t_start); q.addBindValue(t_end)
        row = 0; counts = [0] * NUM_CAMERAS
        if q.exec_():
            while q.next():
                self.table_widget.insertRow(row)
                for i in range(4): self.table_widget.setItem(row, i, QTableWidgetItem(str(q.value(i))))
                try:
                    c_idx = int(q.value(2).replace("Camera ", "")) - 1
                    if 0 <= c_idx < NUM_CAMERAS: counts[c_idx] += 1
                except: pass
                row += 1
        self.total_label.setText(f"Total Pelanggaran : {sum(counts)}")
        for i in range(NUM_CAMERAS): self.camera_stats_labels[i].setText(f"Camera {i+1} : {counts[i]}")

    def show_image_table(self, r, c):
        if c == 3: ImageViewer(self.table_widget.item(r, c).text()).exec_()

    def showWarningGeneric(self, cam_id, v_type, img_p):
        d = QDialog(self); d.setWindowTitle(f"⚠️ PELANGGARAN KAMERA {cam_id}"); l = QVBoxLayout()
        img_l = QLabel(); pix = QPixmap(os.path.join(output_folder, img_p)).scaled(400, 300, Qt.KeepAspectRatio); img_l.setPixmap(pix)
        txt = "TANPA HELM" if v_type == "tanpahelm" else "TANPA VEST"
        msg = QLabel(f"TERDETEKSI {txt}!"); msg.setStyleSheet("color: red; font-size: 20px; font-weight: bold;")
        l.addWidget(img_l); l.addWidget(msg); d.setLayout(l); d.show()

    def eventFilter(self, source, event):
        if event.type() == QEvent.MouseButtonDblClick and "Camera_" in source.objectName():
            idx = int(source.objectName().split("_")[1])
            if self.camera_states[idx] == "Normal":
                for i, s in enumerate(self.scroll_areas): 
                    if i != idx: s.hide()
                self.camera_states[idx] = "Maximized"
            else:
                for s in self.scroll_areas: s.show()
                self.camera_states[idx] = "Normal"
            return True
        return super().eventFilter(source, event)

    def closeEvent(self, event):
        self.inference_worker.stop()
        for w in self.cap_workers + self.disp_workers: w.stop()
        event.accept()

def main():
    db = QSqlDatabase.addDatabase('QSQLITE')
    db.setDatabaseName(database_path)
    if not db.open(): return
    q = QSqlQuery()
    q.exec_("CREATE TABLE IF NOT EXISTS data (id INTEGER PRIMARY KEY AUTOINCREMENT, Tanggal TEXT, Waktu TEXT, Lokasi TEXT, Bukti TEXT)")
    app = QApplication(sys.argv); window = MainWindow(); window.show(); sys.exit(app.exec_())

if __name__ == '__main__':
    main()