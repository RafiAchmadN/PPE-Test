import cv2
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, \
    QLabel, QGridLayout, QScrollArea, QSizePolicy, QMessageBox, \
    QPushButton, QVBoxLayout, QTabWidget, QHBoxLayout, QTableWidget, QTableWidgetItem, QDateEdit, QHeaderView, QDialog
from PyQt5.QtGui import QPixmap, QIcon, QImage, QPalette
from PyQt5.QtSql import QSqlDatabase, QSqlQuery
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QEvent, QObject, QDateTime
from PyQt5 import QtCore
from datetime import date, datetime
import requests
import sys
import numpy as np
import time
import os
import queue
import math

# --- UPGRADE: Import Ultralytics untuk YOLO11 ---
from ultralytics import YOLO

# --- SETUP MODEL ---
# Ganti path ini dengan model YOLO11 custom Anda (misal: 'best.pt' hasil training YOLO11)
# Jika belum ada custom, gunakan 'yolo11n.pt' (tapi class ID mungkin beda dengan model v5 lama Anda)
try:
    model = YOLO('best.pt')  # Pastikan file best.pt format YOLO11 ada
except:
    print("Model custom tidak ditemukan, menggunakan yolo11n standar.")
    model = YOLO('yolo11n.pt') 

# Konfigurasi Model
# model.conf = 0.5  # Di YOLO11 conf diatur saat predict/inference

output_folder = 'foto'
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
        print(f"File {file_path} tidak ditemukan!")
    return ip_cameras

file_path = "ipcamera.txt"
array_ip_cameras = read_ip_cameras(file_path)
NUM_CAMERAS = len(array_ip_cameras) # Jumlah kamera otomatis mengikuti isi file

# Membuat Queue secara dinamis sesuai jumlah kamera
frame_queues = [queue.Queue(maxsize=30) for _ in range(NUM_CAMERAS)]
display_queues = [queue.Queue(maxsize=30) for _ in range(NUM_CAMERAS)]

class ImageViewer(QDialog):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle("Bukti")
        self.setWindowIcon(QIcon(QPixmap("logo.png")))
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        label = QLabel()
        pixmap = QPixmap(foto_path)
        if not pixmap.isNull():
             # Scale gambar agar tidak terlalu besar di layar
            pixmap = pixmap.scaled(800, 600, Qt.KeepAspectRatio)
            label.setPixmap(pixmap)
        else:
            label.setText("Gambar tidak ditemukan")
        layout.addWidget(label)
        self.setLayout(layout)

class CaptureIpCameraFramesWorker(QThread):
    def __init__(self, url, frame_queue) -> None:
        super(CaptureIpCameraFramesWorker, self).__init__()
        self.frame_queue = frame_queue
        self.url = url
        self.__thread_active = True
        self.__thread_pause = False

    def run(self) -> None:
        # Support input berupa index kamera (0, 1) atau URL stream
        video_source = self.url
        if self.url.isdigit():
            video_source = int(self.url)

        cap = cv2.VideoCapture(video_source)
        
        while self.__thread_active:
            if not self.__thread_pause:
                ret, frame = cap.read()
                if ret:
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                else:
                    # Jika video file habis atau koneksi putus
                    cap.release()
                    time.sleep(1) # Tunggu sebentar sebelum reconnect
                    cap = cv2.VideoCapture(video_source)
            else:
                time.sleep(0.1)
        
        cap.release()
        self.quit()

    def stop(self) -> None:
        self.__thread_active = False

    def pause(self) -> None:
        self.__thread_pause = True

    def unpause(self) -> None:
        self.__thread_pause = False

class DisplayIpCameraFramesWorker(QThread):
    ImageUpdated = pyqtSignal(QImage)

    def __init__(self, frame_queue) -> None:
        super(DisplayIpCameraFramesWorker, self).__init__()
        self.frame_queue = frame_queue
        self.__thread_active = True
        self.__thread_pause = False

    def run(self) -> None:
        while self.__thread_active:
            try:
                frame = self.frame_queue.get(timeout=1)
                height, width, channels = frame.shape
                bytes_per_line = width * channels
                cv_rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                qt_rgb_image = QImage(cv_rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
                self.ImageUpdated.emit(qt_rgb_image)
            except queue.Empty:
                pass

    def stop(self) -> None:
        self.__thread_active = False

class InferenceFramesWorker(QThread):
    # Sinyal dinamis: (Camera Index, Tipe Pelanggaran, Path Gambar)
    warningSignal = pyqtSignal(int, str, str) 
    result_ready = pyqtSignal(str, str, str, str)

    def __init__(self, input_queues, output_queues) -> None:
        super(InferenceFramesWorker, self).__init__()
        self.input_queues = input_queues
        self.output_queues = output_queues
        self.num_cams = len(input_queues)
        
        # Tracking waktu terakhir foto diambil per kamera untuk mencegah spam
        self.last_capture_times = [0] * self.num_cams
        self.__thread_active = True

    def run(self) -> None:
        current_cam_idx = 0
        
        while self.__thread_active:
            # Round-robin processing: Cek kamera 1, lalu 2, lalu 3, dst.
            if not self.input_queues[current_cam_idx].empty():
                frame = self.input_queues[current_cam_idx].get()
                
                if frame is None:
                    continue

                # Resize untuk performa (opsional, YOLO11 cukup cepat)
                # resized_img = cv2.resize(frame, (640, 640)) 
                
                # --- INFERENCE YOLO11 ---
                # conf=0.5 setara dengan model.conf = 0.5 di kode lama
                results = model.predict(frame, conf=0.5, verbose=False) 
                result = results[0] # Ambil hasil pertama
                
                # Render bounding box ke frame
                annotated_frame = result.plot() 
                
                # Masukkan frame hasil deteksi ke queue display
                if not self.output_queues[current_cam_idx].full():
                    self.output_queues[current_cam_idx].put(annotated_frame)
                
                # --- LOGIC DETEKSI PELANGGARAN ---
                # Cek cooldown waktu (30 detik per kamera)
                if (time.time() - self.last_capture_times[current_cam_idx] >= 30):
                    boxes = result.boxes
                    violation_type = None
                    
                    for box in boxes:
                        cls_id = int(box.cls[0]) # ID Class
                        
                        # PERHATIAN: Sesuaikan ID ini dengan model training Anda
                        # Asumsi kode lama: 1 = No Helm, 2 = No Vest
                        if cls_id == 1: 
                            violation_type = "tanpahelm"
                        elif cls_id == 2:
                            violation_type = "tanpavest"
                        
                        if violation_type:
                            timestr = time.strftime("%m%d%H%M%S")
                            tanggal = time.strftime("%Y-%m-%d")
                            waktu = datetime.now().strftime("%H:%M:%S")
                            lokasi = f"Camera {current_cam_idx + 1}"
                            filename = f'{violation_type}_{lokasi.replace(" ", "")}_{timestr}.jpg'
                            file_path = os.path.join(output_folder, filename)
                            
                            # Simpan Bukti
                            cv2.imwrite(file_path, annotated_frame)
                            
                            # Emit Signal
                            self.result_ready.emit(tanggal, waktu, lokasi, filename)
                            self.warningSignal.emit(current_cam_idx + 1, violation_type, filename)
                            
                            # Update timer dan break loop box (satu foto cukup per frame)
                            self.last_capture_times[current_cam_idx] = time.time()
                            break 

            # Pindah ke antrian kamera berikutnya
            current_cam_idx = (current_cam_idx + 1) % self.num_cams
            
            # Sedikit sleep agar CPU tidak 100% jika queue kosong
            if all(q.empty() for q in self.input_queues):
                time.sleep(0.01)

    def stop(self) -> None:
        self.__thread_active = False

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super(MainWindow, self).__init__()

        # --- INIT UI COMPONENTS ---
        self.btn_1 = QPushButton('Live Monitor', self)
        self.btn_2 = QPushButton('Logging / Data', self)
        self.btn_1.clicked.connect(self.button1)
        self.btn_2.clicked.connect(self.button2)

        self.btn_ui2_1 = QPushButton('Filter', self)
        self.btn_ui2_1.clicked.connect(self.updatetable)

        self.dateeditstart = QDateEdit(calendarPopup=True)
        self.dateeditend = QDateEdit(calendarPopup=True)
        
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(['Tanggal', 'Waktu', 'Lokasi', 'Bukti'])
        self.table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        # Statistik Pelanggaran
        self.stats_layout = QVBoxLayout()
        self.total_label = QLabel("Total Pelanggaran")
        self.stats_layout.addWidget(self.total_label)
        
        self.camera_stats_labels = [] # List label statistik per kamera
        self.camera_stats_values = [] # List value counter per kamera

        # --- DYNAMIC CAMERA WIDGETS ---
        self.camera_labels = []       # List objek QLabel
        self.scroll_areas = []        # List objek QScrollArea
        self.camera_states = []       # Status Normal/Maximized

        for i in range(NUM_CAMERAS):
            # Label
            cam_lbl = QLabel()
            cam_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            cam_lbl.setScaledContents(True)
            cam_lbl.installEventFilter(self)
            cam_lbl.setObjectName(f"Camera_{i}") # ID untuk event filter
            self.camera_labels.append(cam_lbl)

            # Scroll Area
            scroll = QScrollArea()
            scroll.setBackgroundRole(QPalette.Dark)
            scroll.setWidgetResizable(True)
            scroll.setWidget(cam_lbl)
            self.scroll_areas.append(scroll)
            
            # State
            self.camera_states.append("Normal")

            # Stats Label
            stat_lbl = QLabel(f"Camera {i+1} : 0")
            self.camera_stats_labels.append(stat_lbl)
            self.camera_stats_values.append(0)
            self.stats_layout.addWidget(stat_lbl)

        # --- THREADS SETUP ---
        self.capture_workers = []
        self.display_workers = []

        # 1. Inference Worker (Satu worker handle semua kamera)
        self.inference_worker = InferenceFramesWorker(frame_queues, display_queues)
        self.inference_worker.warningSignal.connect(self.showWarningGeneric)
        self.inference_worker.result_ready.connect(self.insert_data)
        self.inference_worker.start()

        # 2. Capture & Display Workers (Per Kamera)
        for i in range(NUM_CAMERAS):
            # Capture
            url = array_ip_cameras[i]
            cap_worker = CaptureIpCameraFramesWorker(url, frame_queues[i])
            cap_worker.start()
            self.capture_workers.append(cap_worker)

            # Display
            disp_worker = DisplayIpCameraFramesWorker(display_queues[i])
            # Gunakan lambda dengan argumen default i=i untuk binding yang benar
            disp_worker.ImageUpdated.connect(lambda image, idx=i: self.update_camera_frame(image, idx))
            disp_worker.start()
            self.display_workers.append(disp_worker)

        # Tab Setup
        self.tab1 = self.ui1()
        self.tab2 = self.ui2()
        self.initUI()

    def update_camera_frame(self, image, index):
        if index < len(self.camera_labels):
            self.camera_labels[index].setPixmap(QPixmap.fromImage(image))

    def button1(self):
        self.right_widget.setCurrentIndex(0)

    def button2(self):
        self.right_widget.setCurrentIndex(1)

    def initUI(self) -> None:
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.btn_1)
        left_layout.addWidget(self.btn_2)
        left_layout.addStretch(100)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        self.right_widget = QTabWidget()
        self.right_widget.addTab(self.tab1, '')
        self.right_widget.addTab(self.tab2, '')
        self.right_widget.setStyleSheet('''QTabBar::tab{width: 0; height: 0; margin: 0; padding: 0; border: none;}''')

        main_layout = QHBoxLayout()
        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.right_widget)
        
        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        self.setMinimumSize(1024, 768)
        self.setWindowTitle("YOLO11 Multi-Camera System")

    def ui1(self) -> None:
        # Dynamic Grid Layout calculation
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # Hitung jumlah kolom dan baris optimal (seperti matrix)
        cols = math.ceil(math.sqrt(NUM_CAMERAS))
        
        for i, scroll_area in enumerate(self.scroll_areas):
            row = i // cols
            col = i % cols
            grid_layout.addWidget(scroll_area, row, col)
            
        self.main_tab1 = QWidget()
        self.main_tab1.setLayout(grid_layout)
        return self.main_tab1

    def ui2(self):
        upper_layout = QHBoxLayout()
        selected_date = QtCore.QDateTime(2023, 1, 1, 0, 0)
        self.dateeditstart.setDateTime(selected_date)
        self.dateeditend.setDateTime(QDateTime.currentDateTime())
        
        upper_layout.addWidget(self.dateeditstart)
        upper_layout.addWidget(self.dateeditend)
        upper_layout.addWidget(self.btn_ui2_1)

        main_layout = QVBoxLayout()
        main_layout.addLayout(upper_layout)
        
        # Masukkan layout statistik yang sudah dibuat di init
        container_stats = QWidget()
        container_stats.setLayout(self.stats_layout)
        main_layout.addWidget(container_stats)
        
        main_layout.addWidget(self.table_widget)
        
        self.table_widget.cellClicked.connect(self.show_image_table)
        
        main = QWidget()
        main.setLayout(main_layout)
        
        # Load data awal
        self.updatetable() 
        return main

    def show_image_table(self, row, column):
        if column == 3:
            image_path = self.table_widget.item(row, column).text()
            image_viewer = ImageViewer(image_path)
            image_viewer.exec_()

    def updatetable(self):
        self.reset_stats()
        dtstart = self.dateeditstart.dateTime().toString("yyyy-MM-dd")
        dtend = self.dateeditend.dateTime().toString("yyyy-MM-dd")

        data = self.fetch_datainrange(dtstart, dtend)
        self.populate_table(data)

    def reset_stats(self):
        self.table_widget.setRowCount(0)
        for i in range(NUM_CAMERAS):
            self.camera_stats_values[i] = 0
            self.camera_stats_labels[i].setText(f"Camera {i+1} : 0")

    def populate_table(self, data):
        self.table_widget.setRowCount(len(data))
        
        # Reset nilai sementara
        temp_counts = [0] * len(self.camera_stats_values)
        
        for row, (tanggal, waktu, lokasi, bukti) in enumerate(data):
            self.table_widget.setItem(row, 0, QTableWidgetItem(tanggal))
            self.table_widget.setItem(row, 1, QTableWidgetItem(waktu))
            self.table_widget.setItem(row, 2, QTableWidgetItem(lokasi))
            self.table_widget.setItem(row, 3, QTableWidgetItem(bukti))
            
            # Hitung statistik dari data yang di-load
            try:
                cam_num = int(lokasi.replace("Camera ", ""))
                if 0 < cam_num <= len(temp_counts):
                    temp_counts[cam_num - 1] += 1
            except:
                pass

        # Terapkan hasil hitungan ke UI
        self.camera_stats_values = temp_counts
        total_all = 0
        for i in range(len(self.camera_stats_values)):
            count = self.camera_stats_values[i]
            self.camera_stats_labels[i].setText(f"Camera {i+1} : {count}")
            total_all += count
            
        # Update Label Total
        self.total_label.setText(f"Total Pelanggaran : {total_all}")

    def insert_data(self, tanggal, waktu, lokasi, bukti):
        query = QSqlQuery()
        query.prepare("INSERT INTO data (Tanggal, Waktu, Lokasi, Bukti) VALUES (?, ?, ?, ?)")
        query.addBindValue(tanggal)
        query.addBindValue(waktu)
        query.addBindValue(lokasi)
        query.addBindValue(bukti)
        
        if query.exec_():
            # Refresh table jika sedang di tab logging (opsional)
            if self.right_widget.currentIndex() == 1:
                self.updatetable()

    def fetch_datainrange(self, tgl_a, tgl_b):
        query = QSqlQuery()
        query.prepare("SELECT * FROM data WHERE Tanggal BETWEEN :a AND :b")
        query.bindValue(":a", tgl_a)
        query.bindValue(":b", tgl_b)
        data = []
        if query.exec_():
            while query.next():
                data.append((query.value(1), query.value(2), query.value(3), query.value(4)))
        return list(reversed(data))

    # --- EVENT HANDLING DINAMIS ---
    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        if event.type() == QtCore.QEvent.MouseButtonDblClick:
            obj_name = source.objectName() # Format "Camera_X"
            if "Camera_" in obj_name:
                idx = int(obj_name.split("_")[1])
                
                # Logic Maximize/Minimize
                if self.camera_states[idx] == "Normal":
                    # Sembunyikan semua KECUALI yang diklik
                    for i, scroll in enumerate(self.scroll_areas):
                        if i != idx:
                            scroll.hide()
                    self.camera_states[idx] = "Maximized"
                else:
                    # Tampilkan semua
                    for scroll in self.scroll_areas:
                        scroll.show()
                    self.camera_states[idx] = "Normal"
                return True
        return super(MainWindow, self).eventFilter(source, event)

    def showWarningGeneric(self, cam_id, type_violation, image_path):
        # Dialog pop-up untuk peringatan
        # Note: Jika terlalu sering pop-up bisa mengganggu, pertimbangkan logging saja
        msg = QDialog(self)
        msg.setWindowTitle(f"Peringatan Camera {cam_id}")
        layout = QVBoxLayout()
        
        label_img = QLabel()
        pix = QPixmap(f"foto/{image_path}")
        if not pix.isNull():
             pix = pix.scaled(400, 300, Qt.KeepAspectRatio)
        label_img.setPixmap(pix)
        
        pesan = "Tidak memakai Helm" if type_violation == "tanpahelm" else "Tidak memakai Vest"
        label_txt = QLabel(f"Terdeteksi {pesan} pada Camera {cam_id}")
        label_txt.setStyleSheet("font-size: 16px; font-weight: bold; color: red;")
        
        layout.addWidget(label_img)
        layout.addWidget(label_txt)
        msg.setLayout(layout)
        msg.open() # Gunakan open() agar non-blocking (asynchronous) dibanding exec_()

    def closeEvent(self, event) -> None:
        # Stop semua thread
        self.inference_worker.stop()
        for w in self.capture_workers:
            w.stop()
        for w in self.display_workers:
            w.stop()
        event.accept()

def main() -> None:
    # 1. Inisialisasi Driver SQLITE
    db = QSqlDatabase.addDatabase('QSQLITE')
    db.setDatabaseName('logging.db') # Ini akan jadi nama file database Anda
    
    # 2. Buka Koneksi (Otomatis membuat file kosong jika belum ada)
    if not db.open():
        print("Error: Tidak dapat membuka/membuat file database")
        return

    # 3. [PENTING] Buat Tabel 'data' Secara Otomatis
    # Kita cek dulu apakah tabel sudah ada, jika belum kita buat.
    query = QSqlQuery()
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Tanggal TEXT,
        Waktu TEXT,
        Lokasi TEXT,
        Bukti TEXT
    )
    """
    
    if query.exec_(create_table_sql):
        print("Status Database: SUKSES (Tabel 'data' siap digunakan).")
    else:
        print(f"Status Database: ERROR ({query.lastError().text()})")

    # 4. Jalankan Aplikasi Utama
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()