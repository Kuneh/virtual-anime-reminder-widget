import sys
import os
import time
import datetime
import json
import tempfile
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QTimeEdit, QFileDialog,
                            QTextEdit, QSystemTrayIcon, QMenu, QAction,
                            QDesktopWidget, QComboBox, QSlider, QGroupBox)
from PyQt5.QtCore import Qt, QTimer, QTime, QThread, pyqtSignal, QSize, QPoint
from PyQt5.QtGui import QIcon, QPixmap, QFont, QPainter, QMovie
import pygame
from gtts import gTTS
from pydub import AudioSegment
from pydub.effects import speedup

class AnimeVoicePlayer(QThread):
    finished = pyqtSignal()
    
    def __init__(self, text, voice_settings=None):
        super().__init__()
        self.text = text
        
        self.settings = {
            "language": "ja",
            "speed": 1.2,
            "pitch": 1.3,
            "add_words": True
        }
        
        if voice_settings:
            self.settings.update(voice_settings)
    
    def run(self):
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
            temp_file.close()
            
            processed_file = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
            processed_file.close()
            
            self._generate_speech_file(temp_file.name)
            self._process_audio(temp_file.name, processed_file.name)
            self._play_speech_file(processed_file.name)
            
            if os.path.exists(temp_file.name):
                os.remove(temp_file.name)
            if os.path.exists(processed_file.name):
                os.remove(processed_file.name)
                
            self.finished.emit()
        except Exception as e:
            print(f"Error in voice playback: {e}")
            self.finished.emit()
    
    def _add_anime_phrases(self, text):
        if not self.settings["add_words"]:
            return text
            
        if any(word in text.lower() for word in ["desu", "nya", "chan", "kun", "senpai"]):
            return text
            
        import random
        anime_endings = ["desu", "ne", "yo"]
        return text + " " + random.choice(anime_endings)
    
    def _generate_speech_file(self, filename):
        try:
            text = self._add_anime_phrases(self.text)
            
            tts = gTTS(text=text, lang=self.settings["language"], slow=False)
            tts.save(filename)
        except Exception as e:
            print(f"Error generating speech: {e}")
            raise
    
    def _process_audio(self, input_file, output_file):
        try:
            audio = AudioSegment.from_file(input_file)
            
            if self.settings["speed"] != 1.0:
                audio = speedup(audio, self.settings["speed"], 150)
            
            if self.settings["pitch"] != 1.0:
                try:
                    from pydub.effects import pitch_shift
                    semitones = (self.settings["pitch"] - 1.0) * 12
                    audio = pitch_shift(audio, semitones)
                except (ImportError, AttributeError):
                    print("Sox not available for pitch shifting, using alternative approach")
                    faster = self.settings["pitch"]
                    audio = audio._spawn(audio.raw_data, overrides={
                        "frame_rate": int(audio.frame_rate * faster)
                    })
                    audio = audio.set_frame_rate(44100)
            
            audio.export(output_file, format="wav")
        except Exception as e:
            print(f"Error processing audio: {e}")
            raise
    
    def _play_speech_file(self, filename):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            sound = pygame.mixer.Sound(filename)
            sound.play()
            
            while pygame.mixer.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"Error playing speech: {e}")
            raise

class ReminderThread(QThread):
    reminder_signal = pyqtSignal(str)
    
    def __init__(self, reminders):
        super().__init__()
        self.reminders = reminders
        self.running = True
        
    def run(self):
        while self.running:
            current_time = datetime.datetime.now().strftime("%H:%M")
            for reminder in self.reminders:
                if reminder["time"] == current_time and reminder["active"]:
                    self.reminder_signal.emit(reminder["text"])
                    reminder["active"] = False
            time.sleep(30)
            
    def stop(self):
        self.running = False

class CharacterWidget(QWidget):
    clicked_signal = pyqtSignal()
    
    def __init__(self, image_path=None):
        super().__init__()
        self.setWindowTitle("Anime Character")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        self.setMinimumSize(200, 200)
        
        self.image_path = image_path
        self.pixmap = None
        self.movie = None
        self.update_image(image_path)
        
        self.speech_text = ""
        self.show_speech = False
        self.speech_timer = QTimer()
        self.speech_timer.timeout.connect(self.hide_speech)
        
        self.drag_position = None
        
        self.reposition()
    
    def update_image(self, image_path):
        self.image_path = image_path
        
        if image_path and os.path.exists(image_path):
            if image_path.lower().endswith('.gif'):
                self.movie = QMovie(image_path)
                self.movie.setScaledSize(QSize(200, 200))
                self.movie.start()
                self.pixmap = None
            else:
                self.pixmap = QPixmap(image_path)
                self.movie = None
            self.setFixedSize(200, 200)
            self.update()
    
    def show_message(self, text):
        self.speech_text = text
        self.show_speech = True
        self.update()
        self.speech_timer.start(5000)
    
    def hide_speech(self):
        self.show_speech = False
        self.update()
        self.speech_timer.stop()
    
    def reposition(self):
        desktop = QDesktopWidget().availableGeometry()
        self.move(desktop.width() - self.width() - 20, 
                desktop.height() - self.height() - 20)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        if self.movie and self.movie.isValid():
            current_frame = self.movie.currentPixmap()
            painter.drawPixmap(0, 0, current_frame)
        elif self.pixmap and not self.pixmap.isNull():
            painter.drawPixmap(0, 0, self.pixmap.scaled(
                200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        if self.show_speech and self.speech_text:
            bubble_width = max(200, len(self.speech_text) * 8)
            bubble_height = 60
            
            bubble_x = (self.width() - bubble_width) // 2
            bubble_y = -bubble_height
            
            painter.setPen(Qt.black)
            painter.setBrush(Qt.white)
            painter.drawRoundedRect(bubble_x, bubble_y, bubble_width, bubble_height, 10, 10)
            
            points = [
                QPoint(self.width() // 2, 0),
                QPoint(self.width() // 2 - 10, -10),
                QPoint(self.width() // 2 + 10, -10)
            ]
            painter.drawPolygon(points)
            
            painter.setPen(Qt.black)
            painter.setFont(QFont('Arial', 10))
            painter.drawText(bubble_x + 10, bubble_y + 10, 
                          bubble_width - 20, bubble_height - 20,
                          Qt.AlignCenter | Qt.TextWordWrap, self.speech_text)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            
            self.clicked_signal.emit()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

class AnimeReminderWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anime Reminder Assistant")
        self.setWindowFlags(Qt.Window)
        
        pygame.init()
        
        self.image_path = ""
        self.reminders = []
        
        self.voice_settings = {
            "language": "ja",
            "speed": 1.2,
            "pitch": 1.3,
            "add_words": True
        }
        
        self.settings_file = "anime_reminder_settings.json"
        self.load_settings()
        
        self.character_widget = CharacterWidget(self.image_path)
        self.character_widget.clicked_signal.connect(self.show)
        self.character_widget.show()
        
        self.init_ui()
        
        self.reminder_thread = ReminderThread(self.reminders)
        self.reminder_thread.reminder_signal.connect(self.show_reminder)
        self.reminder_thread.start()
        
        self.setup_tray()
        
    def init_ui(self):
        main_layout = QVBoxLayout()
        
        self.character_label = QLabel("No character selected")
        self.character_label.setAlignment(Qt.AlignCenter)
        self.character_label.setMinimumSize(200, 200)
        self.character_label.setStyleSheet("background-color: #f0f0f0; border-radius: 10px;")
        
        if self.image_path and os.path.exists(self.image_path):
            pixmap = QPixmap(self.image_path)
            self.character_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        self.select_image_btn = QPushButton("Select Character Image")
        self.select_image_btn.clicked.connect(self.select_image)
        
        voice_group = QGroupBox("Voice Settings")
        voice_layout = QVBoxLayout()
        
        lang_layout = QHBoxLayout()
        lang_label = QLabel("Voice Language:")
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Japanese", "English", "Korean", "Chinese"])
        index = 0
        if self.voice_settings["language"] == "en":
            index = 1
        elif self.voice_settings["language"] == "ko":
            index = 2
        elif self.voice_settings["language"] == "zh-CN":
            index = 3
        self.lang_combo.setCurrentIndex(index)
        self.lang_combo.currentIndexChanged.connect(self.update_voice_settings)
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.lang_combo)
        
        speed_layout = QHBoxLayout()
        speed_label = QLabel("Speed:")
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(80)
        self.speed_slider.setMaximum(150)
        self.speed_slider.setValue(int(self.voice_settings["speed"] * 100))
        self.speed_slider.valueChanged.connect(self.update_voice_settings)
        speed_layout.addWidget(speed_label)
        speed_layout.addWidget(self.speed_slider)
        
        pitch_layout = QHBoxLayout()
        pitch_label = QLabel("Pitch:")
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setMinimum(80)
        self.pitch_slider.setMaximum(150)
        self.pitch_slider.setValue(int(self.voice_settings["pitch"] * 100))
        self.pitch_slider.valueChanged.connect(self.update_voice_settings)
        pitch_layout.addWidget(pitch_label)
        pitch_layout.addWidget(self.pitch_slider)
        
        add_words_layout = QHBoxLayout()
        add_words_label = QLabel("Add Anime Words:")
        self.add_words_checkbox = QComboBox()
        self.add_words_checkbox.addItems(["Yes", "No"])
        self.add_words_checkbox.setCurrentIndex(0 if self.voice_settings["add_words"] else 1)
        self.add_words_checkbox.currentIndexChanged.connect(self.update_voice_settings)
        add_words_layout.addWidget(add_words_label)
        add_words_layout.addWidget(self.add_words_checkbox)
        
        voice_layout.addLayout(lang_layout)
        voice_layout.addLayout(speed_layout)
        voice_layout.addLayout(pitch_layout)
        voice_layout.addLayout(add_words_layout)
        voice_group.setLayout(voice_layout)
        
        self.text_label = QLabel("Reminder Message:")
        self.text_edit = QTextEdit()
        self.text_edit.setMaximumHeight(100)
        
        time_layout = QHBoxLayout()
        self.time_label = QLabel("Reminder Time:")
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime.currentTime())
        time_layout.addWidget(self.time_label)
        time_layout.addWidget(self.time_edit)
        
        self.add_reminder_btn = QPushButton("Add Reminder")
        self.add_reminder_btn.clicked.connect(self.add_reminder)
        
        self.test_voice_btn = QPushButton("Test Anime Voice")
        self.test_voice_btn.clicked.connect(self.test_voice)
        
        self.reminders_label = QLabel("Your Reminders:")
        self.reminders_display = QTextEdit()
        self.reminders_display.setReadOnly(True)
        self.update_reminders_display()
        
        self.exit_btn = QPushButton("Hide to Tray")
        self.exit_btn.clicked.connect(self.hide)
        
        main_layout.addWidget(self.character_label)
        main_layout.addWidget(self.select_image_btn)
        main_layout.addWidget(voice_group)
        main_layout.addWidget(self.text_label)
        main_layout.addWidget(self.text_edit)
        main_layout.addLayout(time_layout)
        main_layout.addWidget(self.add_reminder_btn)
        main_layout.addWidget(self.test_voice_btn)
        main_layout.addWidget(self.reminders_label)
        main_layout.addWidget(self.reminders_display)
        main_layout.addWidget(self.exit_btn)
        
        self.setLayout(main_layout)
        
        self.setStyleSheet("""
            QWidget {
                background-color: #f8f5ff;
                color: #333;
                font-family: 'Arial';
                font-size: 12px;
            }
            QLabel {
                font-weight: bold;
                color: #6a0dad;
            }
            QPushButton {
                background-color: #d9b3ff;
                border: 1px solid #c180ff;
                border-radius: 5px;
                padding: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c180ff;
            }
            QTextEdit {
                border: 1px solid #d9b3ff;
                border-radius: 5px;
            }
            QTimeEdit, QComboBox {
                border: 1px solid #d9b3ff;
                border-radius: 5px;
                padding: 5px;
            }
            QGroupBox {
                border: 1px solid #d9b3ff;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                color: #6a0dad;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #c180ff;
                height: 8px;
                background: #f0f0f0;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #d9b3ff;
                border: 1px solid #c180ff;
                width: 18px;
                margin: -2px 0;
                border-radius: 5px;
            }
        """)
        
        self.setFixedSize(350, 750)
    
    def update_voice_settings(self):
        lang_map = ["ja", "en", "ko", "zh-CN"]
        self.voice_settings["language"] = lang_map[self.lang_combo.currentIndex()]
        
        self.voice_settings["speed"] = self.speed_slider.value() / 100.0
        self.voice_settings["pitch"] = self.pitch_slider.value() / 100.0
        
        self.voice_settings["add_words"] = (self.add_words_checkbox.currentIndex() == 0)
        
        self.save_settings()
    
    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        if self.image_path and os.path.exists(self.image_path):
            self.tray_icon.setIcon(QIcon(self.image_path))
        else:
            self.tray_icon.setIcon(QIcon.fromTheme("appointment-soon"))
        
        tray_menu = QMenu()
        show_action = QAction("Show", self)
        quit_action = QAction("Exit", self)
        show_character_action = QAction("Show Character", self)
        hide_character_action = QAction("Hide Character", self)
        
        show_action.triggered.connect(self.show)
        quit_action.triggered.connect(self.quit_app)
        show_character_action.triggered.connect(self.show_character)
        hide_character_action.triggered.connect(self.hide_character)
        
        tray_menu.addAction(show_action)
        tray_menu.addAction(show_character_action)
        tray_menu.addAction(hide_character_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()
        
    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
    
    def show_character(self):
        self.character_widget.show()
        
    def hide_character(self):
        self.character_widget.hide()
    
    def select_image(self):
        file_dialog = QFileDialog()
        image_path, _ = file_dialog.getOpenFileName(
            self, "Select Character Image", "", "Image Files (*.png *.jpg *.jpeg *.gif)"
        )
        
        if image_path:
            self.image_path = image_path
            pixmap = QPixmap(image_path)
            self.character_label.setPixmap(pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
            self.character_widget.update_image(image_path)
            
            self.tray_icon.setIcon(QIcon(image_path))
            
            self.save_settings()
    
    def add_reminder(self):
        reminder_text = self.text_edit.toPlainText().strip()
        if not reminder_text:
            return
        
        reminder_time = self.time_edit.time().toString("HH:mm")
        
        reminder = {
            "text": reminder_text,
            "time": reminder_time,
            "active": True
        }
        
        self.reminders.append(reminder)
        self.update_reminders_display()
        self.save_settings()
        
        self.text_edit.clear()
    
    def update_reminders_display(self):
        self.reminders_display.clear()
        for i, reminder in enumerate(self.reminders):
            status = "Active" if reminder["active"] else "Done"
            self.reminders_display.append(f"{i+1}. {reminder['time']} - {reminder['text']} ({status})")
    
    def test_voice(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            text = "Hello! I'm your anime reminder assistant, desu!"
        
        if hasattr(self, 'voice_player') and self.voice_player.isRunning():
            return
            
        self.voice_player = AnimeVoicePlayer(text, self.voice_settings)
        self.voice_player.start()
        
        self.character_widget.show_message(text)
    
    def show_reminder(self, text):
        self.tray_icon.showMessage("Anime Reminder", text, QSystemTrayIcon.Information, 5000)
        
        self.character_widget.show()
        
        self.character_widget.show_message(text)
        
        if hasattr(self, 'voice_player') and self.voice_player.isRunning():
            return
            
        self.voice_player = AnimeVoicePlayer(text, self.voice_settings)
        self.voice_player.start()
        
        self.update_reminders_display()
        self.save_settings()
    
    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    self.image_path = settings.get("image_path", "")
                    self.reminders = settings.get("reminders", [])
                    
                    if "voice_settings" in settings:
                        self.voice_settings.update(settings["voice_settings"])
            except:
                pass
    
    def save_settings(self):
        settings = {
            "image_path": self.image_path,
            "reminders": self.reminders,
            "voice_settings": self.voice_settings
        }
        
        with open(self.settings_file, 'w') as f:
            json.dump(settings, f)
    
    def quit_app(self):
        if hasattr(self, 'reminder_thread'):
            self.reminder_thread.stop()
            self.reminder_thread.wait()
        
        self.character_widget.hide()
        
        self.save_settings()
        
        pygame.quit()
        
        QApplication.quit()
    
    def closeEvent(self, event):
        event.ignore()
        self.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = AnimeReminderWidget()
    sys.exit(app.exec_())