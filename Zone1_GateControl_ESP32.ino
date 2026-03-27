#include "esp_camera.h"
#include <WiFi.h>
#include <ESP32Servo.h>
#include <WebServer.h>
#include "esp_http_server.h"

// ================= CẤU HÌNH WIFI =================
const char *ssid = "anh toan ky su mang";
const char *password = "1234567890";

// ================= CẤU HÌNH SERVO =================
Servo myServo;
int servoPin = 13;

// Logic Servo với Keep-Alive
enum ServoState { CLOSED, OPENING };
ServoState servoState = CLOSED;
unsigned long servoOpenUntil = 0;
unsigned long lastKeepAlive = 0;
const unsigned long SERVO_OPEN_TIME = 10000; // Tăng lên 10 giây
const unsigned long KEEP_ALIVE_TIMEOUT = 2000; // 2 giây không có tín hiệu -> đóng

// ================= SERVER =================
WebServer server(80);
httpd_handle_t stream_httpd = NULL;

// ================= PIN DEFINITIONS (AI-THINKER) =================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM       5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// ================= STREAM HANDLER =================
static esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t *_jpg_buf = NULL;
  char part_buf[64];

  res = httpd_resp_set_type(req, "multipart/x-mixed-replace; boundary=frame");
  if (res != ESP_OK) return res;

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      res = ESP_FAIL;
    } else {
      if (fb->format != PIXFORMAT_JPEG) {
        bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
        esp_camera_fb_return(fb);
        fb = NULL;
        if (!jpeg_converted) {
          Serial.println("JPEG compression failed");
          res = ESP_FAIL;
        }
      } else {
        _jpg_buf_len = fb->len;
        _jpg_buf = fb->buf;
      }
    }
    if (res == ESP_OK) {
      size_t hlen = snprintf(part_buf, 64, "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", _jpg_buf_len);
      res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, "\r\n--frame\r\n", 11);
    }
    if (fb) {
      esp_camera_fb_return(fb);
      fb = NULL;
      _jpg_buf = NULL;
    } else if (_jpg_buf) {
      free(_jpg_buf);
      _jpg_buf = NULL;
    }
    if (res != ESP_OK) break;
  }
  return res;
}

void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 81;
  config.ctrl_port = 32768;

  httpd_uri_t stream_uri = {
    .uri       = "/stream",
    .method    = HTTP_GET,
    .handler   = stream_handler,
    .user_ctx  = NULL
  };

  if (httpd_start(&stream_httpd, &config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("✅ Camera Stream Ready! Port 81");
  }
}

// ================= HELPER FUNCTIONS =================
void setServoOpen() {
  myServo.write(90);
  servoState = OPENING;
  servoOpenUntil = millis() + SERVO_OPEN_TIME;
  lastKeepAlive = millis();
  Serial.println(">>> SERVO: OPEN (90°)");
}

void setServoClosed() {
  myServo.write(0);
  servoState = CLOSED;
  Serial.println(">>> SERVO: CLOSED (0°)");
}

// ================= SETUP =================
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  Serial.println();
  Serial.println("╔════════════════════════════════════════╗");
  Serial.println("║  ESP32-CAM GATE CONTROL - IMPROVED V2  ║");
  Serial.println("╚════════════════════════════════════════╝");

  // 1. Camera Config
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 15;  // Giảm chất lượng để tăng tốc độ
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 18;
    config.fb_count = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera init failed: 0x%x\n", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  s->set_framesize(s, FRAMESIZE_VGA);

  // 2. WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  int wifi_attempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifi_attempts < 20) {
    delay(500);
    Serial.print(".");
    wifi_attempts++;
  }
  
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("\n❌ WiFi connection failed!");
    Serial.println("Restarting in 5 seconds...");
    delay(5000);
    ESP.restart();
  }
  
  Serial.println("");
  Serial.print("✅ WiFi connected: ");
  Serial.println(WiFi.localIP());
  WiFi.setSleep(false);

  // 3. Servo
  ESP32PWM::allocateTimer(3);
  myServo.setPeriodHertz(50);
  myServo.attach(servoPin, 500, 2400);
  setServoClosed();  // Mặc định đóng
  Serial.println("✅ Servo ready on GPIO 13");

  // 4. Web Server Routes
  server.on("/", []() {
    String html = "<html><body><h1>ESP32 Gate Control</h1>";
    html += "<p>Status: " + String(servoState == OPENING ? "OPEN" : "CLOSED") + "</p>";
    html += "<p><a href='/vi_pham'>CLOSE GATE</a></p>";
    html += "<p><a href='/dat_chuan'>OPEN GATE</a></p>";
    html += "</body></html>";
    server.send(200, "text/html", html);
  });

  // VI PHẠM -> Đóng cửa
  server.on("/vi_pham", []() {
    Serial.println(">>> CMD: VI PHAM -> CLOSE GATE");
    setServoClosed();
    server.send(200, "text/plain", "CLOSED");
  });

  // ĐẠT CHUẨN -> Mở cửa
  server.on("/dat_chuan", []() {
    Serial.println(">>> CMD: DAT CHUAN -> OPEN GATE");
    setServoOpen();
    server.send(200, "text/plain", "OPENED");
  });

  // KEEP ALIVE -> Giữ cửa mở (gọi liên tục từ Python)
  server.on("/keep_alive", []() {
    if (servoState == OPENING) {
      lastKeepAlive = millis();
      servoOpenUntil = millis() + SERVO_OPEN_TIME;
      Serial.println(">>> CMD: KEEP ALIVE (cửa vẫn mở)");
    }
    server.send(200, "text/plain", "KEEP_ALIVE_OK");
  });

  // STATUS CHECK
  server.on("/status", []() {
    String status = servoState == OPENING ? "OPEN" : "CLOSED";
    server.send(200, "text/plain", status);
  });

  server.begin();
  startCameraServer();
  
  Serial.println("╔════════════════════════════════════════╗");
  Serial.printf("║ Stream: http://%s:81/stream\n", WiFi.localIP().toString().c_str());
  Serial.printf("║ Control: http://%s\n", WiFi.localIP().toString().c_str());
  Serial.println("╚════════════════════════════════════════╝");
}

// ================= LOOP =================
void loop() {
  server.handleClient();

  // AUTO CLOSE logic (cải tiến)
  if (servoState == OPENING) {
    unsigned long now = millis();
    
    // Kiểm tra keep-alive timeout
    if (now - lastKeepAlive > KEEP_ALIVE_TIMEOUT) {
      // Không còn tín hiệu từ Python -> Đóng cửa
      if (now >= servoOpenUntil) {
        setServoClosed();
        Serial.println(">>> AUTO: Timeout -> CLOSE");
      }
    }
  }

  // Watchdog: Nếu mất WiFi -> restart
  static unsigned long lastWifiCheck = 0;
  if (millis() - lastWifiCheck > 10000) {  // Check mỗi 10s
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("⚠️ WiFi lost! Restarting...");
      delay(1000);
      ESP.restart();
    }
    lastWifiCheck = millis();
  }
}