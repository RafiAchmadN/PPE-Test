# import the require packages.
import cv2
import pafy
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, \
    QLabel, QGridLayout, QScrollArea, QSizePolicy, QMessageBox, \
    QPushButton, QVBoxLayout, QTabWidget, QHBoxLayout, QTableWidget, QTableWidgetItem, QDateEdit, QHeaderView, QDialog
from PyQt5.QtGui import QPixmap, QIcon, QImage, QPalette, QPixmap
from PyQt5.QtSql import QSqlDatabase, QSqlQuery
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QEvent, QObject, QDateTime
from PyQt5 import QtCore
from datetime import date, datetime
import requests
import sys
import numpy as np
import torch
import time
import os
import queue
import ultralytics

# Add device='cpu' to the arguments
model = torch.hub.load(r'yolov5', 'custom', path='yolov5/runs/train/exp/weights/best.pt', source='local', device='cpu')
model.conf = 0.7
model.line_thickness = 1
q1 = queue.Queue(maxsize=30)
q2 = queue.Queue(maxsize=30)
q3 = queue.Queue(maxsize=30)
q4 = queue.Queue(maxsize=30)
d1 = queue.Queue(maxsize=30)
d2 = queue.Queue(maxsize=30)
d3 = queue.Queue(maxsize=30)
d4 = queue.Queue(maxsize=30)
# capture photo
output_folder = 'foto'  # Folder tujuan penyimpanan foto


# setup
# Membaca isi file dan menyimpannya ke dalam array
def read_ip_cameras(file_path):
    ip_cameras = []
    with open(file_path, 'r') as file:
        for line in file:
            ip_cameras.append(line.strip())
    return ip_cameras


# Contoh pemanggilan fungsi dengan file "ipcamera.txt"
file_path = "ipcamera.txt"
array_ip_cameras = read_ip_cameras(file_path)


# Output array_ip_cameras berisi URL kamera
# print(array_ip_cameras[0])
# print(array_ip_cameras[1])
# print(array_ip_cameras[2])
# print(array_ip_cameras[3])

class ImageViewer(QDialog):
    def __init__(self, image_path):
        super().__init__()
        self.setWindowTitle("Bukti")
        self.setWindowIcon(QIcon(QPixmap("logo.png")))
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        label = QLabel()
        pixmap = QPixmap(foto_path)
        label.setPixmap(pixmap)

        layout.addWidget(label)
        self.setLayout(layout)
class CaptureIpCameraFramesWorker(QThread):

    def __init__(self, url, frame_queue) -> None:
        super(CaptureIpCameraFramesWorker, self).__init__()
        # Declare and initialize instance variables.
        self.frame_queue = frame_queue
        self.url = url
        self.__thread_active = True
        self.fps = 0
        self.__thread_pause = False
        self.response = requests.get(self.url, stream=True)

    def run(self) -> None:
        # Initialize flag for connection status
        connected = False

        while self.__thread_active:
            if not self.__thread_pause:
                try:
                    self.response = requests.get(self.url, stream=True)
                    # Capture video from a network stream.
                    # cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                    # Get default video FPS.
                    # self.fps = cap.get(cv2.CAP_PROP_FPS)

                    if self.response.status_code == 200:
                        connected = True

                    if connected:
                        arr = np.asarray(bytearray(self.response.content), dtype=np.uint8)
                        frame = cv2.imdecode(arr, -1)
                        if not self.frame_queue.full():
                            self.frame_queue.put(frame)

                except Exception as e:
                    # Handle any exceptions that may occur during capture (e.g., camera disconnection)
                    connected = False

                if not connected:
                    # Camera is disconnected, sleep for a while before attempting to reconnect
                    # cv2.VideoCapture(self.url).release()
                    # self.fps = 0
                    cv2.waitKey(300000)  # Sleep for 1 second before retrying
            else:
                cv2.waitKey(100)  # Sleep for 100 milliseconds when paused

        # When everything done, release the video capture object.
        #cap.release()
        # Tells the thread's event loop to exit with return code 0 (success).
        self.quit()

    def stop(self) -> None:
        self.__thread_active = False

    def pause(self) -> None:
        self.__thread_pause = True

    def unpause(self) -> None:
        self.__thread_pause = False


class DisplayIpCameraFramesWorker(QThread):
    # Signal emitted when a new image or a new frame is ready.
    ImageUpdated = pyqtSignal(QImage)

    def __init__(self, frame_queue) -> None:
        super(DisplayIpCameraFramesWorker, self).__init__()
        # Declare and initialize instance variables.
        self.frame_queue = frame_queue
        self.__thread_active = True
        self.fps = 0
        self.__thread_pause = False

    def run(self) -> None:
        while self.__thread_active:
            try:
                # Get a frame from the queue.
                frame = self.frame_queue.get(timeout=1)
                # Get the frame height, width, and channels.
                height, width, channels = frame.shape
                # Calculate the number of bytes per line.
                bytes_per_line = width * channels
                # Convert image from BGR (cv2 default color format) to RGB (Qt default color format).
                cv_rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                # Convert the image to Qt format.
                qt_rgb_image = QImage(cv_rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
                # Scale the image.
                # qt_rgb_image_scaled = qt_rgb_image.scaled(1280, 720, Qt.KeepAspectRatio)  # 720p
                # Emit this signal to notify that a new image or frame is available.
                self.ImageUpdated.emit(qt_rgb_image)
            except queue.Empty:
                pass

    def stop(self) -> None:
        self.__thread_active = False

    def pause(self) -> None:
        self.__thread_pause = True

    def unpause(self) -> None:
        self.__thread_pause = False


class InferenceFramesWorker(QThread):
    warningSignalhelm1 = pyqtSignal(str)
    warningSignalvest1 = pyqtSignal(str)
    warningSignalhelm2 = pyqtSignal(str)
    warningSignalvest2 = pyqtSignal(str)
    warningSignalhelm3 = pyqtSignal(str)
    warningSignalvest3 = pyqtSignal(str)
    warningSignalhelm4 = pyqtSignal(str)
    warningSignalvest4 = pyqtSignal(str)
    result_ready = pyqtSignal(str, str, str, str)

    def __init__(self, q1, q2, q3, q4, d1, d2, d3, d4) -> None:
        super(InferenceFramesWorker, self).__init__()
        # Declare and initialize instance variables.
        self.q1 = q1
        self.q2 = q2
        self.q3 = q3
        self.q4 = q4
        self.d1 = d1
        self.d2 = d2
        self.d3 = d3
        self.d4 = d4

        self.current_time1 = time.time()
        self.current_time2 = time.time()
        self.current_time3 = time.time()
        self.current_time4 = time.time()
        self.current_time5 = time.time()
        self.last_time = 0
        self.tanggal = ""
        self.waktu = ""
        self.bukti = ""

        self.__thread_active = True
        self.fps = 0
        self.__thread_pause = False

    def run(self) -> None:
        current_queue = self.q1  # Start with q1
        current_warningSignalhelm = self.warningSignalhelm1
        current_warningSignalvest = self.warningSignalvest1
        getcurrent_time = self.current_time1
        lokasi = "Camera 1"
        while self.__thread_active:
            self.last_time = time.time()
            if not self.q1.empty() or not self.q2.empty() or not self.q3.empty() or not self.q4.empty():
                if not current_queue.empty():
                    frame = current_queue.get()
                    # resized_img = cv2.cuda.resize(frame, (640, 480),interpolation=cv2.INTER_CUBIC)
                    if frame is None:
                        print("Error: Could not read frame. Check your camera connection or video path.")
                        return
                    resized_img = cv2.resize(frame, (640, 480))
                    results = model(resized_img)
                    cv_img = np.squeeze(results.render())
                    coor = results.xyxy[0]
                    rows = len(coor)
                    i = 0
                    if (self.last_time - getcurrent_time >= 30):
                        while i < rows:
                            check = coor[i][5].item()
                            if check == 1:
                                timestr = time.strftime("%m%d%H%M%S")
                                self.tanggal = time.strftime("%Y-%m-%d")
                                self.waktu = datetime.now().strftime("%H:%M:%S")
                                filename = f'tanpahelm_{timestr}.jpg'  # Nama file foto dengan format 'foto_counter.jpg'
                                file_path = os.path.join(output_folder, filename)
                                cv2.imwrite(file_path, np.squeeze(results.render()))
                                # print(f"Foto {filename} diambil dan disimpan!")
                                self.bukti = filename
                                self.result_ready.emit(self.tanggal, self.waktu, lokasi, self.bukti)
                                current_warningSignalhelm.emit(self.bukti)
                                # print("Foto tanpa helm Terdeteksi")
                                if (lokasi == "Camera 1"):
                                    self.current_time1 = time.time()
                                elif (lokasi == "Camera 2"):
                                    self.current_time2 = time.time()
                                elif (lokasi == "Camera 3"):
                                    self.current_time3 = time.time()
                                else:
                                    self.current_time4 = time.time()
                            elif check == 2:
                                timestr = time.strftime("%m%d%H%M%S")
                                self.tanggal = time.strftime("%Y-%m-%d")
                                self.waktu = datetime.now().strftime("%H:%M:%S")
                                filename = f'tanpavest_{timestr}.jpg'  # Nama file foto dengan format 'foto_counter.jpg'
                                file_path = os.path.join(output_folder, filename)
                                cv2.imwrite(file_path, np.squeeze(results.render()))
                                # print(f"Foto {filename} diambil dan disimpan!")
                                self.bukti = filename
                                self.result_ready.emit(self.tanggal, self.waktu, lokasi, self.bukti)
                                current_warningSignalvest.emit(self.bukti)
                                # print("Foto tanpa vest Terdeteksi")
                                if (lokasi == "Camera 1"):
                                    self.current_time1 = time.time()
                                elif (lokasi == "Camera 2"):
                                    self.current_time2 = time.time()
                                elif (lokasi == "Camera 3"):
                                    self.current_time3 = time.time()
                                else:
                                    self.current_time4 = time.time()
                            else:
                                pass
                            i = i + 1
                    if current_queue is self.q1:
                        self.d1.put(cv_img)
                        current_queue = self.q2  # Toggle to q2
                        current_warningSignalhelm = self.warningSignalhelm2
                        current_warningSignalvest = self.warningSignalvest2
                        lokasi = "Camera 2"
                        getcurrent_time = self.current_time2
                    elif current_queue is self.q2:
                        self.d2.put(cv_img)
                        current_queue = self.q3  # Toggle to q3
                        current_warningSignalhelm = self.warningSignalhelm3
                        current_warningSignalvest = self.warningSignalvest3
                        lokasi = "Camera 3"
                        getcurrent_time = self.current_time3
                    elif current_queue is self.q3:
                        self.d3.put(cv_img)
                        current_queue = self.q4  # Toggle to q4
                        current_warningSignalhelm = self.warningSignalhelm4
                        current_warningSignalvest = self.warningSignalvest4
                        lokasi = "Camera 4"
                        getcurrent_time = self.current_time4
                    else:
                        self.d4.put(cv_img)
                        current_queue = self.q1  # Toggle back to q1
                        current_warningSignalhelm = self.warningSignalhelm1
                        current_warningSignalvest = self.warningSignalvest1
                        lokasi = "Camera 1"
                        getcurrent_time = self.current_time1

                else:
                    # If the current queue is empty, continue to the next queue
                    if current_queue is self.q1:
                        current_queue = self.q2
                        current_warningSignalhelm = self.warningSignalhelm2
                        current_warningSignalvest = self.warningSignalvest2
                        lokasi = "Camera 2"
                        getcurrent_time = self.current_time2
                    elif current_queue is self.q2:
                        current_queue = self.q3
                        current_warningSignalhelm = self.warningSignalhelm3
                        current_warningSignalvest = self.warningSignalvest3
                        lokasi = "Camera 3"
                        getcurrent_time = self.current_time3
                    elif current_queue is self.q3:
                        current_queue = self.q4
                        current_warningSignalhelm = self.warningSignalhelm4
                        current_warningSignalvest = self.warningSignalvest4
                        lokasi = "Camera 4"
                        getcurrent_time = self.current_time4
                    else:
                        current_queue = self.q1
                        current_warningSignalhelm = self.warningSignalhelm1
                        current_warningSignalvest = self.warningSignalvest1
                        lokasi = "Camera 1"
                        getcurrent_time = self.current_time1

    def stop(self) -> None:
        self.__thread_active = False

    def pause(self) -> None:
        self.__thread_pause = True

    def unpause(self) -> None:
        self.__thread_pause = False


class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super(MainWindow, self).__init__()

        # add all widgets
        self.btn_1 = QPushButton('Camera 1-4', self)
        self.btn_2 = QPushButton('Logging', self)

        self.btn_1.setObjectName('left_button')
        self.btn_2.setObjectName('left_button')

        self.btn_1.clicked.connect(self.button1)
        self.btn_2.clicked.connect(self.button2)

        self.btn_ui2_1 = QPushButton('Enter', self)
        self.btn_ui2_1.clicked.connect(self.updatetable)

        self.showText = QLabel("Total Pelanggaran")
        self.value1 = 0
        self.value2 = 0
        self.value3 = 0
        self.value4 = 0
        self.showcam1 = QLabel("Camera 1 : " + str(self.value1))
        self.showcam2 = QLabel("Camera 2 : " + str(self.value2))
        self.showcam3 = QLabel("Camera 3 : " + str(self.value3))
        self.showcam4 = QLabel("Camera 4 : " + str(self.value4))

        self.dateeditstart = QDateEdit(calendarPopup=True)
        self.dateeditend = QDateEdit(calendarPopup=True)
        # Table instance
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(4)
        self.table_widget.setHorizontalHeaderLabels(['Tanggal', 'Waktu', 'Lokasi', 'Bukti'])
        self.table_widget.setColumnWidth(0, 200)  # Kolom Tanggal
        self.table_widget.setColumnWidth(1, 140)  # Kolom Waktu
        self.table_widget.setColumnWidth(2, 300)  # Kolom Lokasi
        self.table_widget.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)  # Kolom Bukti
        # rtsp://<Username>:<Password>@<IP Address>:<Port>/cam/realmonitor?channel=1&subtype=0
        # self.url_1 = "rtsp://admin:YJVCAK@192.168.1.2:554/Streaming/Channels/102"
        self.url_1 = array_ip_cameras[0]
        self.url_2 = array_ip_cameras[1]
        self.url_3 = array_ip_cameras[2]
        self.url_4 = array_ip_cameras[3]
        self.camname1 = "Camera 1"
        self.camname2 = "Camera 2"
        self.camname3 = "Camera 3"
        self.camname4 = "Camera 4"
        # Dictionary to keep the state of a camera. The camera state will be: Normal or Maximized.
        self.list_of_cameras_state = {}

        # Create an instance of a QLabel class to show camera 1.
        self.camera_1 = QLabel()
        self.camera_1.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.camera_1.setScaledContents(True)
        self.camera_1.installEventFilter(self)
        self.camera_1.setObjectName("Camera_1")
        self.list_of_cameras_state["Camera_1"] = "Normal"

        # Create an instance of a QScrollArea class to scroll camera 1 image.
        self.QScrollArea_1 = QScrollArea()
        self.QScrollArea_1.setBackgroundRole(QPalette.Dark)
        self.QScrollArea_1.setWidgetResizable(True)
        self.QScrollArea_1.setWidget(self.camera_1)

        # Create an instance of a QLabel class to show camera 2.
        self.camera_2 = QLabel()
        self.camera_2.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.camera_2.setScaledContents(True)
        self.camera_2.installEventFilter(self)
        self.camera_2.setObjectName("Camera_2")
        self.list_of_cameras_state["Camera_2"] = "Normal"

        # Create an instance of a QScrollArea class to scroll camera 2 image.
        self.QScrollArea_2 = QScrollArea()
        self.QScrollArea_2.setBackgroundRole(QPalette.Dark)
        self.QScrollArea_2.setWidgetResizable(True)
        self.QScrollArea_2.setWidget(self.camera_2)

        # Create an instance of a QLabel class to show camera 3.
        self.camera_3 = QLabel()
        self.camera_3.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.camera_3.setScaledContents(True)
        self.camera_3.installEventFilter(self)
        self.camera_3.setObjectName("Camera_3")
        self.list_of_cameras_state["Camera_3"] = "Normal"

        # Create an instance of a QScrollArea class to scroll camera 3 image.
        self.QScrollArea_3 = QScrollArea()
        self.QScrollArea_3.setBackgroundRole(QPalette.Dark)
        self.QScrollArea_3.setWidgetResizable(True)
        self.QScrollArea_3.setWidget(self.camera_3)

        # Create an instance of a QLabel class to show camera 4.
        self.camera_4 = QLabel()
        self.camera_4.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.camera_4.setScaledContents(True)
        self.camera_4.installEventFilter(self)
        self.camera_4.setObjectName("Camera_4")
        self.list_of_cameras_state["Camera_4"] = "Normal"

        # Create an instance of a QScrollArea class to scroll camera 4 image.
        self.QScrollArea_4 = QScrollArea()
        self.QScrollArea_4.setBackgroundRole(QPalette.Dark)
        self.QScrollArea_4.setWidgetResizable(True)
        self.QScrollArea_4.setWidget(self.camera_4)

        # add tabs
        self.tab1 = self.ui1()
        self.tab2 = self.ui2()
        # Set the UI elements for this Widget class.
        self.initUI()

        self.InferenceFramesWorker_1 = InferenceFramesWorker(q1, q2, q3, q4, d1, d2, d3, d4)
        self.InferenceFramesWorker_1.warningSignalhelm1.connect(self.showWarninghelm1)
        self.InferenceFramesWorker_1.warningSignalvest1.connect(self.showWarningvest1)
        self.InferenceFramesWorker_1.warningSignalhelm2.connect(self.showWarninghelm2)
        self.InferenceFramesWorker_1.warningSignalvest2.connect(self.showWarningvest2)
        self.InferenceFramesWorker_1.warningSignalhelm3.connect(self.showWarninghelm3)
        self.InferenceFramesWorker_1.warningSignalvest3.connect(self.showWarningvest3)
        self.InferenceFramesWorker_1.warningSignalhelm4.connect(self.showWarninghelm4)
        self.InferenceFramesWorker_1.warningSignalvest4.connect(self.showWarningvest4)
        self.InferenceFramesWorker_1.result_ready.connect(self.insert_data)

        # Create an instance of CaptureIpCameraFramesWorker.
        self.CaptureIpCameraFramesWorker_1 = CaptureIpCameraFramesWorker(self.url_1, q1)
        self.DisplayIpCameraFramesWorker_1 = DisplayIpCameraFramesWorker(d1)
        self.DisplayIpCameraFramesWorker_1.ImageUpdated.connect(lambda image: self.ShowCamera1(image))

        # Create an instance of CaptureIpCameraFramesWorker.
        self.CaptureIpCameraFramesWorker_2 = CaptureIpCameraFramesWorker(self.url_2, q2)
        self.DisplayIpCameraFramesWorker_2 = DisplayIpCameraFramesWorker(d2)
        self.DisplayIpCameraFramesWorker_2.ImageUpdated.connect(lambda image: self.ShowCamera2(image))

        # Create an instance of CaptureIpCameraFramesWorker.
        self.CaptureIpCameraFramesWorker_3 = CaptureIpCameraFramesWorker(self.url_3, q3)
        self.DisplayIpCameraFramesWorker_3 = DisplayIpCameraFramesWorker(d3)
        self.DisplayIpCameraFramesWorker_3.ImageUpdated.connect(lambda image: self.ShowCamera3(image))

        # Create an instance of CaptureIpCameraFramesWorker.
        self.CaptureIpCameraFramesWorker_4 = CaptureIpCameraFramesWorker(self.url_4, q4)
        self.DisplayIpCameraFramesWorker_4 = DisplayIpCameraFramesWorker(d4)
        self.DisplayIpCameraFramesWorker_4.ImageUpdated.connect(lambda image: self.ShowCamera4(image))

        # Start the thread getIpCameraFrameWorker_1.
        self.CaptureIpCameraFramesWorker_1.start()

        # Start the thread getIpCameraFrameWorker_2.
        self.CaptureIpCameraFramesWorker_2.start()

        # Start the thread getIpCameraFrameWorker_3.
        self.CaptureIpCameraFramesWorker_3.start()

        # Start the thread getIpCameraFrameWorker_4.
        self.CaptureIpCameraFramesWorker_4.start()

        # Start the thread InferenceFramesWorker_1.
        self.InferenceFramesWorker_1.start()

        # Start the thread DisplayIpCameraFrameWorker_1.
        self.DisplayIpCameraFramesWorker_1.start()

        # Start the thread DisplayIpCameraFrameWorker_2.
        self.DisplayIpCameraFramesWorker_2.start()

        # Start the thread DisplayIpCameraFrameWorker_3.
        self.DisplayIpCameraFramesWorker_3.start()

        # Start the thread DisplayIpCameraFrameWorker_4.
        self.DisplayIpCameraFramesWorker_4.start()

    def button1(self):
        self.right_widget.setCurrentIndex(0)

    def button2(self):
        self.right_widget.setCurrentIndex(1)

    def initUI(self) -> None:
        left_layout = QVBoxLayout()
        left_layout.addWidget(self.btn_1)
        left_layout.addWidget(self.btn_2)
        left_layout.addStretch(100)
        left_layout.setSpacing(20)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        self.right_widget = QTabWidget()
        self.right_widget.tabBar().setObjectName("mainTab")

        self.right_widget.addTab(self.tab1, '')
        self.right_widget.addTab(self.tab2, '')

        self.right_widget.setCurrentIndex(0)
        self.right_widget.setStyleSheet('''QTabBar::tab{width: 0; height: 0; margin: 0; padding: 0; border: none;}''')

        main_layout = QHBoxLayout()
        main_layout.addWidget(left_widget)
        main_layout.addWidget(self.right_widget)
        main_layout.setStretch(0, 1)
        main_layout.setStretch(1, 100)
        main_widget = QWidget()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        self.setMinimumSize(800, 600)
        self.showMaximized()
        self.setWindowIcon(QIcon(QPixmap("logo.png")))
        # Set window title.
        self.setWindowTitle("IP Camera System")

    def ui1(self) -> None:
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self.QScrollArea_1, 0, 0)
        grid_layout.addWidget(self.QScrollArea_2, 0, 1)
        grid_layout.addWidget(self.QScrollArea_3, 1, 0)
        grid_layout.addWidget(self.QScrollArea_4, 1, 1)
        self.main = QWidget()
        self.main.setLayout(grid_layout)
        return self.main

    def ui2(self) -> None:
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self.QScrollArea_5, 0, 0)
        grid_layout.addWidget(self.QScrollArea_6, 0, 1)
        grid_layout.addWidget(self.QScrollArea_7, 1, 0)
        grid_layout.addWidget(self.QScrollArea_8, 1, 1)
        self.main = QWidget()
        self.main.setLayout(grid_layout)
        return self.main

    def show_image(self, row, column):
        # Jika yang diklik adalah kolom Bukti (indeks kolom 3)
        if column == 3:
            image_path = self.table_widget.item(row, column).text()
            image_viewer = ImageViewer(image_path)
            image_viewer.exec_()

    def ui2(self):
        button_height = 60
        upper_layout = QHBoxLayout()
        selected_date = QtCore.QDateTime(2023, 7, 1, 0, 0)
        self.dateeditstart.setDateTime(selected_date)
        self.dateeditend.setDateTime(QDateTime.currentDateTime())
        self.dateeditstart.setFixedHeight(button_height)
        self.dateeditend.setFixedHeight(button_height)
        self.btn_ui2_1.setFixedHeight(button_height)
        upper_layout.addWidget(self.dateeditstart)
        upper_layout.addWidget(self.dateeditend)
        upper_layout.addWidget(self.btn_ui2_1)
        data = self.fetch_alldata()
        self.table_widget.setRowCount(len(data))
        for row, (tanggal, waktu, lokasi, bukti) in enumerate(data):
            itemtanggal = QTableWidgetItem(tanggal)
            itemwaktu = QTableWidgetItem(waktu)
            itemlokasi = QTableWidgetItem(lokasi)
            itemtanggal.setTextAlignment(Qt.AlignCenter)
            itemwaktu.setTextAlignment(Qt.AlignCenter)
            itemlokasi.setTextAlignment(Qt.AlignCenter)
            if lokasi == "Camera 1":
                self.value1 += 1
            if lokasi == "Camera 2":
                self.value2 += 1
            if lokasi == "Camera 3":
                self.value3 += 1
            if lokasi == "Camera 4":
                self.value4 += 1
            self.table_widget.setItem(row, 0, itemtanggal)
            self.table_widget.setItem(row, 1, itemwaktu)
            self.table_widget.setItem(row, 2, itemlokasi)
            self.table_widget.setItem(row, 3, QTableWidgetItem(bukti))
        self.table_widget.cellClicked.connect(self.show_image)
        self.showcam1.setText("Camera 1 : " + str(self.value1))
        self.showcam2.setText("Camera 2 : " + str(self.value2))
        self.showcam3.setText("Camera 3 : " + str(self.value3))
        self.showcam4.setText("Camera 4 : " + str(self.value4))
        main_layout = QVBoxLayout()
        main_layout.addLayout(upper_layout)
        main_layout.addWidget(self.showText)
        main_layout.addWidget(self.showcam1)
        main_layout.addWidget(self.showcam2)
        main_layout.addWidget(self.showcam3)
        main_layout.addWidget(self.showcam4)
        main_layout.addWidget(self.table_widget)
        main = QWidget()
        main.setLayout(main_layout)
        return main

    def updatetable(self):
        self.resettable()
        dtstart = self.dateeditstart.dateTime()
        dtend = self.dateeditend.dateTime()
        datestart = dtstart.toString(self.dateeditstart.displayFormat())
        dateend = dtend.toString(self.dateeditend.displayFormat())

        data = self.fetch_datainrange(datestart, dateend)
        self.table_widget.setRowCount(len(data))
        for row, (tanggal, waktu, lokasi, bukti) in enumerate(data):
            itemtanggal = QTableWidgetItem(tanggal)
            itemwaktu = QTableWidgetItem(waktu)
            itemlokasi = QTableWidgetItem(lokasi)
            itemtanggal.setTextAlignment(Qt.AlignCenter)
            itemwaktu.setTextAlignment(Qt.AlignCenter)
            itemlokasi.setTextAlignment(Qt.AlignCenter)
            if lokasi == "Camera 1":
                self.value1 += 1
            if lokasi == "Camera 2":
                self.value2 += 1
            if lokasi == "Camera 3":
                self.value3 += 1
            if lokasi == "Camera 4":
                self.value4 += 1
            self.table_widget.setItem(row, 0, itemtanggal)
            self.table_widget.setItem(row, 1, itemwaktu)
            self.table_widget.setItem(row, 2, itemlokasi)
            self.table_widget.setItem(row, 3, QTableWidgetItem(bukti))
        self.showcam1.setText("Camera 1 : " + str(self.value1))
        self.showcam2.setText("Camera 2 : " + str(self.value2))
        self.showcam3.setText("Camera 3 : " + str(self.value3))
        self.showcam4.setText("Camera 4 : " + str(self.value4))
        # print(datestart)
        # print(dateend)

    def resettable(self):
        self.table_widget.setRowCount(0)
        self.value1 = 0
        self.value2 = 0
        self.value3 = 0
        self.value4 = 0
        self.showcam1.setText("Camera 1 : " + str(self.value1))
        self.showcam2.setText("Camera 2 : " + str(self.value2))
        self.showcam3.setText("Camera 3 : " + str(self.value3))
        self.showcam4.setText("Camera 4 : " + str(self.value4))
        
    def update_ui_stats(self, lokasi):
        # Parsing nomor kamera dari string "Camera 1", "Camera 2", dst
        try:
            cam_num = int(lokasi.replace("Camera ", ""))
            idx = cam_num - 1
            
            if 0 <= idx < len(self.camera_stats_values):
                # Increment counter spesifik kamera
                self.camera_stats_values[idx] += 1
                self.camera_stats_labels[idx].setText(f"Camera {cam_num} : {self.camera_stats_values[idx]}")
                
                # Hitung Total Keseluruhan
                total_all = sum(self.camera_stats_values)
                self.total_label.setText(f"Total Pelanggaran : {total_all}")
        except Exception as e:
            print(f"Error update stats: {e}")

    def insert_data(self, tanggal, waktu, lokasi, bukti):
        query = QSqlQuery()
        query.prepare("INSERT INTO data (Tanggal, Waktu, Lokasi, Bukti) VALUES (?, ?, ?, ?)")
        query.addBindValue(tanggal)
        query.addBindValue(waktu)
        query.addBindValue(lokasi)
        query.addBindValue(bukti)
        
        if query.exec_():
            # UPDATE REAL-TIME: Langsung update angka di layar tanpa perlu reload database
            self.update_ui_stats(lokasi)

            # Jika sedang membuka tab data, masukkan juga baris baru ke tabel
            if self.right_widget.currentIndex() == 1:
                row = self.table_widget.rowCount()
                self.table_widget.insertRow(row)
                self.table_widget.setItem(row, 0, QTableWidgetItem(tanggal))
                self.table_widget.setItem(row, 1, QTableWidgetItem(waktu))
                self.table_widget.setItem(row, 2, QTableWidgetItem(lokasi))
                self.table_widget.setItem(row, 3, QTableWidgetItem(bukti))
        else:
            # print("Gagal memasukkan data:", query.lastError().text())
            return False

    def fetch_datainrange(self, tanggal_a, tanggal_b):
        tanggal_a = datetime.strptime(tanggal_a, "%d/%m/%Y").strftime("%Y-%m-%d")
        tanggal_b = datetime.strptime(tanggal_b, "%d/%m/%Y").strftime("%Y-%m-%d")
        query = QSqlQuery()
        query.prepare("SELECT * FROM data WHERE tanggal BETWEEN :tanggal_a AND :tanggal_b")
        query.bindValue(":tanggal_a", tanggal_a)
        query.bindValue(":tanggal_b", tanggal_b)

        data = []
        if query.exec_():
            while query.next():
                tanggal = query.value(1)
                waktu = query.value(2)
                lokasi = query.value(3)
                bukti = query.value(4)
                data.append((tanggal, waktu, lokasi, bukti))
        # else:
        #     print("Error executing query:", query.lastError().text())

        data_reversed = list(reversed(data))
        return data_reversed

    def fetch_alldata(self):
        query = QSqlQuery("SELECT * FROM data")
        data = []
        while query.next():
            tanggal = query.value(1)
            waktu = query.value(2)
            lokasi = query.value(3)
            bukti = query.value(4)
            data.append((tanggal, waktu, lokasi, bukti))

        data_reversed = list(reversed(data))

        return data_reversed

    @QtCore.pyqtSlot()
    def ShowCamera1(self, frame: QImage) -> None:
        self.camera_1.setPixmap(QPixmap.fromImage(frame))

    @QtCore.pyqtSlot()
    def ShowCamera2(self, frame: QImage) -> None:
        self.camera_2.setPixmap(QPixmap.fromImage(frame))

    @QtCore.pyqtSlot()
    def ShowCamera3(self, frame: QImage) -> None:
        self.camera_3.setPixmap(QPixmap.fromImage(frame))

    @QtCore.pyqtSlot()
    def ShowCamera4(self, frame: QImage) -> None:
        self.camera_4.setPixmap(QPixmap.fromImage(frame))

    # Override method for class MainWindow.
    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        """
        Method to capture the events for objects with an event filter installed.
        :param source: The object for whom an event took place.
        :param event: The event that took place.
        :return: True if event is handled.
        """
        #
        if event.type() == QtCore.QEvent.MouseButtonDblClick:
            if source.objectName() == 'Camera_1':
                #
                if self.list_of_cameras_state["Camera_1"] == "Normal":
                    self.QScrollArea_2.hide()
                    self.QScrollArea_3.hide()
                    self.QScrollArea_4.hide()
                    self.list_of_cameras_state["Camera_1"] = "Maximized"
                else:
                    self.QScrollArea_2.show()
                    self.QScrollArea_3.show()
                    self.QScrollArea_4.show()
                    self.list_of_cameras_state["Camera_1"] = "Normal"
            elif source.objectName() == 'Camera_2':
                #
                if self.list_of_cameras_state["Camera_2"] == "Normal":
                    self.QScrollArea_1.hide()
                    self.QScrollArea_3.hide()
                    self.QScrollArea_4.hide()
                    self.list_of_cameras_state["Camera_2"] = "Maximized"
                else:
                    self.QScrollArea_1.show()
                    self.QScrollArea_3.show()
                    self.QScrollArea_4.show()
                    self.list_of_cameras_state["Camera_2"] = "Normal"
            elif source.objectName() == 'Camera_3':
                #
                if self.list_of_cameras_state["Camera_3"] == "Normal":
                    self.QScrollArea_1.hide()
                    self.QScrollArea_2.hide()
                    self.QScrollArea_4.hide()
                    self.list_of_cameras_state["Camera_3"] = "Maximized"
                else:
                    self.QScrollArea_1.show()
                    self.QScrollArea_2.show()
                    self.QScrollArea_4.show()
                    self.list_of_cameras_state["Camera_3"] = "Normal"
            elif source.objectName() == 'Camera_4':
                #
                if self.list_of_cameras_state["Camera_4"] == "Normal":
                    self.QScrollArea_1.hide()
                    self.QScrollArea_2.hide()
                    self.QScrollArea_3.hide()
                    self.list_of_cameras_state["Camera_4"] = "Maximized"
                else:
                    self.QScrollArea_1.show()
                    self.QScrollArea_2.show()
                    self.QScrollArea_3.show()
                    self.list_of_cameras_state["Camera_4"] = "Normal"
            else:
                return super(MainWindow, self).eventFilter(source, event)
            return True
        else:
            return super(MainWindow, self).eventFilter(source, event)

    # Overwrite method closeEvent from class QMainWindow.
    def closeEvent(self, event) -> None:
        # If thread getIpCameraFrameWorker_1 is running, then exit it.
        if self.CaptureIpCameraFramesWorker_1.isRunning():
            self.CaptureIpCameraFramesWorker_1.quit()
        # If thread getIpCameraFrameWorker_2 is running, then exit it.
        if self.CaptureIpCameraFramesWorker_2.isRunning():
            self.CaptureIpCameraFramesWorker_2.quit()
        # If thread getIpCameraFrameWorker_3 is running, then exit it.
        if self.CaptureIpCameraFramesWorker_3.isRunning():
            self.CaptureIpCameraFramesWorker_3.quit()
        # If thread getIpCameraFrameWorker_4 is running, then exit it.
        if self.CaptureIpCameraFramesWorker_4.isRunning():
            self.CaptureIpCameraFramesWorker_4.quit()
        # If thread getIpCameraFrameWorker_1 is running, then exit it.
        if self.DisplayIpCameraFramesWorker_1.isRunning():
            self.DisplayIpCameraFramesWorker_1.quit()
        # If thread getIpCameraFrameWorker_2 is running, then exit it.
        if self.DisplayIpCameraFramesWorker_2.isRunning():
            self.DisplayIpCameraFramesWorker_2.quit()
        # If thread getIpCameraFrameWorker_3 is running, then exit it.
        if self.DisplayIpCameraFramesWorker_3.isRunning():
            self.DisplayIpCameraFramesWorker_3.quit()
        # If thread getIpCameraFrameWorker_4 is running, then exit it.
        if self.DisplayIpCameraFramesWorker_4.isRunning():
            self.DisplayIpCameraFramesWorker_4.quit()
        # If thread getIpCameraFrameWorker_4 is running, then exit it.
        if self.InferenceFramesWorker_1.isRunning():
            self.InferenceFramesWorker_1.quit()
        # Accept the event
        event.accept()

    def showWarninghelm1(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Helm pada Camera 1")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()

    def showWarningvest1(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Vest pada Camera 1")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()

    def showWarninghelm2(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Helm pada Camera 2")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()

    def showWarningvest2(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Vest pada Camera 2")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()

    def showWarninghelm3(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Helm pada Camera 3")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()

    def showWarningvest3(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Vest pada Camera 3")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()

    def showWarninghelm4(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Helm pada Camera 4")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()

    def showWarningvest4(self, image_path):
        msg = QDialog()
        msg.setWindowIcon(QIcon(QPixmap("logo.png")))
        msg.setWindowTitle("Bukti")
        layout = QVBoxLayout()
        foto_path = f"foto/{image_path}"
        # Menampilkan gambar
        label_image = QLabel()
        pixmap = QPixmap(foto_path)
        label_image.setPixmap(pixmap)
        # Menambahkan teks
        label_text = QLabel("Terdeteksi orang tidak memakai Vest pada Camera 4")
        label_text.setAlignment(Qt.AlignCenter)  # Mengatur alignment ke tengah
        label_text.setStyleSheet("font-size: 16px;")  # Mengatur ukuran huruf

        layout.addWidget(label_image)
        layout.addWidget(label_text)
        msg.setLayout(layout)
        msg.exec_()


def main() -> None:
    db = QSqlDatabase.addDatabase('QSQLITE')
    db.setDatabaseName('logging.db')
    if not db.open():
        print("Tidak dapat membuka koneksi database")
    # Create a QApplication object. It manages the GUI application's control flow and main settings.
    # It handles widget specific initialization, finalization.
    # For any GUI application using Qt, there is precisely one QApplication object
    app = QApplication(sys.argv)
    # Create an instance of the class MainWindow.
    window = MainWindow()
    # Show the window.
    window.show()
    # Start Qt event loop.
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()