
import cv2
from ultralytics import YOLO
import os
import datetime
import time
import threading
import requests
import numpy as np
from urllib.request import urlopen

# ================== 1. CẤU HÌNH ==================

MODEL_PATH = r"E:\moi nhat\best (2).pt"

# Cấu hình ESP32
ESP32_IP_ADDRESS = "192.168.10.8"
ESP32_BASE_URL = f"http://{ESP32_IP_ADDRESS}"
VIDEO_STREAM_URL = f"{ESP32_BASE_URL}:81/stream"
URL_VI_PHAM = f"{ESP32_BASE_URL}/vi_pham"
URL_DAT_CHUAN = f"{ESP32_BASE_URL}/dat_chuan"


TELEGRAM_TOKEN = "7627363741:AAEueX-zyLXybrzQhjBi77cWdbsgk4GGE0I"
TELEGRAM_CHAT_ID = "-5003916204" 
CAMERA_NAME = "CỔNG RA VÀO (Camera 1)"


OUTPUT_DIR = "E:/Luu Anh"
SOUND_FILE = "warning_beep.mp3"
COOLDOWN_SECONDS = 15  

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# ================== 2. KHỞI TẠO ==================

print("========================================")
print("  HỆ THỐNG GIÁM SÁT (MŨ - ÁO - GĂNG - GIÀY)")
print(f"  TELEGRAM COOLDOWN: {COOLDOWN_SECONDS}s")
print("========================================")

try:
    model = YOLO(MODEL_PATH)
    print("✅ Model loaded successfully")
except Exception as e:
    print(f"❌ Lỗi tải model: {e}")
    exit()

last_telegram_time = 0      
last_esp32_cmd_time = 0     
lock = threading.Lock()

def phat_am_thanh():
    def _run():
        try:
            from playsound import playsound
            playsound(SOUND_FILE, block=False)
        except:
           
            import winsound
            winsound.Beep(2000, 500)
    threading.Thread(target=_run, daemon=True).start()

def gui_lenh_esp32(url, mo_ta):
    global last_esp32_cmd_time
    curr = time.time()
    
    if curr - last_esp32_cmd_time < 1.0:
        return

    last_esp32_cmd_time = curr 

    def _send():
        try:
            requests.get(url, timeout=2)
        except Exception as e:
            print(f"⚠️ Lỗi ESP32 ({mo_ta}): {e}")
            
    threading.Thread(target=_send, daemon=True).start()

def gui_telegram(message, image_frame):
    """Gửi Telegram trên luồng riêng"""
    def _run(img_copy):
        try:
            print(f"🚀 [TELEGRAM] Đang gửi cảnh báo...")
            url_msg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data_msg = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
            requests.post(url_msg, data=data_msg, timeout=5)
            url_photo = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            _, img_encoded = cv2.imencode('.jpg', img_copy, [cv2.IMWRITE_JPEG_QUALITY, 80])
            files = {'photo': ('violation.jpg', img_encoded.tobytes())}
            data_photo = {"chat_id": TELEGRAM_CHAT_ID}
            requests.post(url_photo, data=data_photo, files=files, timeout=10)
            
            print("✅ [TELEGRAM] Gửi thành công!")
        except Exception as e:
            print(f"⚠️ Lỗi gửi Telegram: {e}")
    
    threading.Thread(target=_run, args=(image_frame.copy(),), daemon=True).start()

class VideoStreamReader:
    def __init__(self, url):
        self.url = url
        self.frame = None
        self.stopped = False
        
    def start(self):
        print(f"🔄 Đang kết nối camera: {self.url}")
        threading.Thread(target=self.update, daemon=True).start()
        start = time.time()
        while self.frame is None:
            if time.time() - start > 10:
                print("❌ Timeout: Không thấy Camera ESP32. Kiểm tra IP!")
                return False
            time.sleep(0.1)
        print("✅ Đã kết nối Camera!\n")
        return True
    
    def update(self):
        stream = None
        bytes_data = b''
        while not self.stopped:
            try:
                if stream is None:
                    stream = urlopen(self.url, timeout=5)
                bytes_data += stream.read(4096)
                a = bytes_data.find(b'\xff\xd8')
                b = bytes_data.find(b'\xff\xd9')
                if a != -1 and b != -1:
                    jpg = bytes_data[a:b+2]
                    bytes_data = bytes_data[b+2:]
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        with lock: self.frame = frame
            except:
                stream = None
                time.sleep(1)

    def read(self):
        with lock:
            return self.frame.copy() if self.frame is not None else None
    
    def stop(self):
        self.stopped = True

def is_inside(obj_box, person_box, tolerance=40):
    ox1, oy1, ox2, oy2 = obj_box
    px1, py1, px2, py2 = person_box
    px1 -= tolerance; py1 -= tolerance; px2 += tolerance; py2 += tolerance
    cx = (ox1 + ox2) / 2; cy = (oy1 + oy2) / 2
    return (px1 < cx < px2) and (py1 < cy < py2)

# ================== 3. CHƯƠNG TRÌNH CHÍNH ==================

stream = VideoStreamReader(VIDEO_STREAM_URL)
if not stream.start():
    exit()

print("🚀 HỆ THỐNG ĐANG CHẠY... (Nhấn 'q' để thoát)")
frame_count = 0
fps_start = time.time()

try:
    while True:
        frame = stream.read()
        if frame is None:
            time.sleep(0.01)
            continue
            
        frame_count += 1
        curr_time = time.time() 
        
        if frame_count % 30 == 0:
            fps = 30 / (time.time() - fps_start)
            fps_start = time.time()

        results = model(frame, conf=0.35, verbose=False)
        boxes = results[0].boxes; names = results[0].names
        
        persons = []
        gear = {'helmet': [], 'vest': [], 'gloves': [], 'boots': []}
        missing_direct = {'no_helmet': [], 'no_vest': [], 'no_gloves': [], 'no_boots': []}
        
        for box in boxes:
            cls_id = int(box.cls[0]); name = names[cls_id]
            coords = box.xyxy[0].cpu().numpy()
            
            if name == 'Person': persons.append(coords)
            elif name == 'Safety Helmet': gear['helmet'].append(coords)
            elif name == 'Reflective Jacket': gear['vest'].append(coords)
            elif name == 'Gloves': gear['gloves'].append(coords)
            elif name == 'Boots': gear['boots'].append(coords)
            elif name == 'No Safety Helmet': missing_direct['no_helmet'].append(coords)
            elif name == 'No Reflective Jacket': missing_direct['no_vest'].append(coords)
            elif name == 'No Gloves': missing_direct['no_gloves'].append(coords)
            elif name == 'No Boots': missing_direct['no_boots'].append(coords)

        is_violation = False
        msg_list = set()
        people_safe_count = 0 
        people_violation_count = 0

        for cat, b_list in gear.items():
            for b in b_list:
                x1, y1, x2, y2 = map(int, b)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, cat[:2].upper(), (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        violation_map = {'no_helmet': "THIEU MU", 'no_vest': "THIEU AO", 'no_gloves': "THIEU GANG", 'no_boots': "THIEU GIAY"}
        for key, text in violation_map.items():
            for box in missing_direct[key]:
                is_violation = True; people_violation_count += 1
                msg_list.add(text)
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                cv2.putText(frame, text, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)

        for person in persons:
            check = {'MU': False, 'AO': False, 'GANG': False, 'GIAY': False}
            for h in gear['helmet']: 
                if is_inside(h, person): check['MU'] = True; break
            for v in gear['vest']:   
                if is_inside(v, person): check['AO'] = True; break
            for g in gear['gloves']: 
                if is_inside(g, person): check['GANG'] = True; break
            for b in gear['boots']:  
                if is_inside(b, person): check['GIAY'] = True; break
            
            errors = [k for k, v in check.items() if not v]
            x1, y1, x2, y2 = map(int, person)
            
            if errors:
                is_violation = True; people_violation_count += 1
                err_text = "THIEU: " + ",".join(errors)
                msg_list.add(err_text)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                cv2.putText(frame, err_text, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,255), 2)
            else:
                people_safe_count += 1
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                cv2.putText(frame, "OK", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

        total_people = len(persons)
        
        if is_violation:
            gui_lenh_esp32(URL_VI_PHAM, "VI PHAM -> DONG CUA")
            if curr_time - last_telegram_time > COOLDOWN_SECONDS:
                
                print(f"\n🚨 [ALARM] Phát hiện lỗi: {msg_list}")
                
                loi_nhan = ", ".join(msg_list)
                ts_str = datetime.datetime.now().strftime("%H:%M:%S")
                ts_file = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                msg = (f"⛔ TỪ CHỐI RA VÀO!\n"
                       f"📍 Tại: {CAMERA_NAME}\n"
                       f"👥 {people_violation_count} người vi phạm\n"
                       f"❌ Lỗi: {loi_nhan}\n"
                       f"⏰ Lúc: {ts_str}")
                
                gui_telegram(msg, frame)
                cv2.imwrite(f"{OUTPUT_DIR}/loi_{ts_file}.jpg", frame)
                phat_am_thanh()

                last_telegram_time = curr_time
        
        elif people_safe_count > 0:
            gui_lenh_esp32(URL_DAT_CHUAN, "AN TOAN -> MO CUA")
        status_text = ""
        status_color = (50, 50, 50)
        
        if is_violation:
            status_text = f"⛔ VI PHAM - CUA DONG"
            status_color = (0, 0, 255)
        elif people_safe_count > 0:
            status_text = f"✅ AN TOAN - CUA MO"
            status_color = (0, 255, 0)
        else:
            status_text = "DANG CHO QUET..."
        
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 60), status_color, -1)
        cv2.putText(frame, status_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        if is_violation:
            time_left = max(0, int(COOLDOWN_SECONDS - (curr_time - last_telegram_time)))
            if time_left > 0:
                cv2.putText(frame, f"Next Alert: {time_left}s", (frame.shape[1]-200, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            else:
                cv2.putText(frame, "SENDING...", (frame.shape[1]-200, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        cv2.imshow("SAFETY MONITOR - FIXED", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\n⏹️  Dừng chương trình...")
finally:
    stream.stop()
    cv2.destroyAllWindows()
    # Thử gửi lệnh tắt cuối cùng
    try: requests.get(URL_VI_PHAM, timeout=1); 
    except: pass