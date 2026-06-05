#include <SoftwareSerial.h>

// ─── RS485 Pins ───
const int SSerialRX        = 6;
const int SSerialTX        = 9;
const int SSerialTxControl = 7;
const int RS485_BAUD       = 9600;

SoftwareSerial RS485Serial(SSerialRX, SSerialTX);

// ─── Slave Config ───
#define SLAVE_ID 2  // Cần thay đổi ID duy nhất cho mỗi Arduino trên cùng bus

// ─── Pin Mapping ───
const int LOCK_PINS[]     = {2,  4,  5};
const int MAGNETIC_PINS[] = {11, 12, A0};
const int NUM_SLOTS       = sizeof(LOCK_PINS) / sizeof(LOCK_PINS[0]);
// Số lượng slot thực tế đang gắn hardware (để in log ALIVE chính xác)
const int ACTIVE_SLOTS    = NUM_SLOTS;
// HW-578 is Active Low but user wants default LOW (Low Level Trigger usually means ON when LOW)
// If USER says "High hút vào low là đẩy ra fix lại vì hiện tại đang bị ngược giờ default đang là high"
// then RELAY_ON = HIGH, RELAY_OFF = LOW.
#define RELAY_ON  HIGH
#define RELAY_OFF LOW

// ─── Timers ───
unsigned long lastHeartbeat      = 0;
const unsigned long HEARTBEAT_INTERVAL = 60000; // 1 phút 1 lần như yêu cầu
// ─── Buffer nhận lệnh ───
char cmdBuffer[32];
int  cmdIndex = 0;

// ─── Magnetic sensor state tracking ───
bool     doorClosed[6];           // true = cửa đóng (sensor LOW)
bool     prevDoorClosed[6];       // trạng thái trước đó (để detect edge)
unsigned long lastDebounce[6];    // timestamp debounce
const unsigned long DEBOUNCE_MS = 200;

// ─── Sensor polling interval ───
unsigned long lastSensorPoll = 0;
const unsigned long SENSOR_POLL_MS = 100;

// ═══════════════════════════════════════════════
//  SETUP
// ═══════════════════════════════════════════════

void setup() {
  // RS485 direction control
  pinMode(SSerialTxControl, OUTPUT);
  digitalWrite(SSerialTxControl, LOW); // Chế độ NHẬN
  // Khởi tạo lock pins (OUTPUT) và magnetic pins (INPUT_PULLUP)
  for (int i = 0; i < NUM_SLOTS; i++) {
    pinMode(LOCK_PINS[i], OUTPUT);
    digitalWrite(LOCK_PINS[i], RELAY_OFF);
    pinMode(MAGNETIC_PINS[i], INPUT_PULLUP);

    // Đọc trạng thái ban đầu
    doorClosed[i]     = (digitalRead(MAGNETIC_PINS[i]) == LOW);
    prevDoorClosed[i] = doorClosed[i];
    lastDebounce[i]   = 0;
  }

  RS485Serial.begin(RS485_BAUD);
  Serial.begin(9600); // Debug qua USB Serial Monitor
  Serial.println(F("AISL Locker Controller v2.1 (Simplified)"));
  Serial.print(F("Slots: "));
  Serial.println(NUM_SLOTS);

  // In trạng thái ban đầu
  for (int i = 0; i < NUM_SLOTS; i++) {
    Serial.print(F("  Slot "));
    Serial.print(i);
    Serial.print(F(": lock=pin"));
    Serial.print(F(" door="));
    Serial.println(doorClosed[i] ? F("CLOSED") : F("OPEN"));
  }

}

// ═══════════════════════════════════════════════
//  MAIN LOOP
// ═══════════════════════════════════════════════

void loop() {
  static unsigned long lastCharTime = 0;
  
  while (RS485Serial.available()) {
    char c = RS485Serial.read();
    unsigned long now = millis();
    
    // Nếu quá lâu không có ký tự mới (200ms) -> Coi như lệnh cũ đã hết, reset buffer
    if (cmdIndex > 0 && (now - lastCharTime > 200)) {
       cmdIndex = 0;
    }
    lastCharTime = now;

    if (c == '\n' || c == '\r') {
      if (cmdIndex > 0) {
        cmdBuffer[cmdIndex] = '\0';
        processCommand(cmdBuffer);
        cmdIndex = 0;
      }
    } else if (cmdIndex < (int)sizeof(cmdBuffer) - 1) {
      // Chỉ nhận các ký tự in được hoặc ký tự đặc biệt hợp lệ, bỏ qua rác đầu chuỗi
      if (cmdIndex == 0 && isspace(c)) continue; 
      cmdBuffer[cmdIndex++] = c;
    }
  }

  // ─── 2. Đọc lệnh từ USB Serial (Manual Debug) ───
  while (Serial.available()) {
    char c = Serial.read();
    
    // Manual RS485 Test: Nếu gõ '!' thì gửi chuỗi test ra RS485
    if (c == '!') {
      Serial.println(F(">>> Sending TEST to RS485..."));
      digitalWrite(SSerialTxControl, HIGH);
      delay(5);
      RS485Serial.println(F("{\"event\":\"TEST_FROM_INO\"}"));
      RS485Serial.flush();
      delay(20);
      digitalWrite(SSerialTxControl, LOW);
    }

    if (c == '\n' || c == '\r') {
      if (cmdIndex > 0) {
        cmdBuffer[cmdIndex] = '\0';
        processCommand(cmdBuffer);
        cmdIndex = 0;
      }
    } else if (cmdIndex < (int)sizeof(cmdBuffer) - 1) {
      cmdBuffer[cmdIndex++] = c;
    }
  }

  // ─── 2. Poll magnetic sensors (mỗi SENSOR_POLL_MS) ───
  unsigned long now = millis();
  if (now - lastSensorPoll >= SENSOR_POLL_MS) {
    lastSensorPoll = now;
    pollMagneticSensors(now);
  }
}

// ═══════════════════════════════════════════════
//  MAGNETIC SENSOR POLLING
// ═══════════════════════════════════════════════

void pollMagneticSensors(unsigned long now) {
  for (int i = 0; i < NUM_SLOTS; i++) {
    bool currentState = (digitalRead(MAGNETIC_PINS[i]) == LOW); // LOW = đóng

    // Nếu trạng thái thay đổi → reset debounce timer
    if (currentState != prevDoorClosed[i]) {
      lastDebounce[i] = now;
      prevDoorClosed[i] = currentState;
    }

    // Nếu trạng thái ổn định qua debounce
    if ((now - lastDebounce[i]) >= DEBOUNCE_MS) {
      // Detect edge: cửa vừa ĐÓNG (false → true)
      if (currentState && !doorClosed[i]) {
        // Thêm delay nhỏ để chắc chắn nam châm đã hít cứng
        delay(100);
        if (digitalRead(MAGNETIC_PINS[i]) == LOW) {
           doorClosed[i] = true;
           Serial.print(F("Door CLOSED: slot "));
           Serial.println(i);
           sendDoorEvent(i, "DOOR_CLOSED");
        }
      }
      // Detect edge: cửa vừa MỞ (true → false)
      else if (!currentState && doorClosed[i]) {
        // Thêm delay nhỏ để chắc chắn cửa đã bung ra hẳn
        delay(100);
        if (digitalRead(MAGNETIC_PINS[i]) == HIGH) {
           doorClosed[i] = false;
           Serial.print(F("Door OPENED: slot "));
           Serial.println(i);
           sendDoorEvent(i, "DOOR_OPENED");
        }
      }
    }
  }

  // 4. Định kỳ gửi heartbeat (ALIVE) để RPi biết Arduino vẫn đang hoạt động
  if (millis() - lastHeartbeat >= HEARTBEAT_INTERVAL) {
    lastHeartbeat = millis();
    
    // In trạng thái tất cả Magnetic sensors ra USB Serial
    Serial.println(F("--- MAGNETIC STATUS ---"));
    for (int i = 0; i < NUM_SLOTS; i++) {
       Serial.print(F("Slot "));
       Serial.print(i);
       Serial.print(F(" (GPIO "));
       Serial.print(MAGNETIC_PINS[i]);
       Serial.print(F("): "));
       
       if (i >= ACTIVE_SLOTS) {
          Serial.println(F("OFFLINE (Not Connect)"));
       } else {
          Serial.println(doorClosed[i] ? F("CLOSED (LOW)") : F("OPEN (HIGH)"));
       }
    }
    Serial.println(F("-----------------------"));

    // USB Serial Debug
    Serial.println(F("{\"event\":\"ALIVE\"}"));
    Serial.flush(); // CỰC KỲ QUAN TRỌNG: Đợi gửi xong USB để không gây ngắt nhiễu cho SoftwareSerial
    
    // RS485 Serial (Cần bật chân control)
    digitalWrite(SSerialTxControl, HIGH);
    delay(5);
    
    char heartbeatJson[64];
    snprintf(heartbeatJson, sizeof(heartbeatJson), "{\"slave\":%d,\"event\":\"ALIVE\"}", SLAVE_ID);
    
    // noInterrupts();
    RS485Serial.println(heartbeatJson);
    interrupts();
    
    RS485Serial.flush(); // Dọn buffer nhận/echo
    
    // Tính toán delay động (~1.1ms mỗi ký tự ở 9600 baud)
    int txDelay = (strlen(heartbeatJson) + 2) * 1.1; 
    delay(txDelay + 2); 
    
    digitalWrite(SSerialTxControl, LOW);
  }
}

void sendDoorEvent(int slot, const char* eventName) {
  char jsonOut[64];
  snprintf(jsonOut, sizeof(jsonOut), "{\"slave\":%d,\"event\":\"%s\",\"slot\":%d}", SLAVE_ID, eventName, slot);

  // Gửi USB trước
  Serial.println(jsonOut);
  Serial.flush(); // Đợi USB dọn sạch interrupt

  // Bật chế độ TRUYỀN RS485
  digitalWrite(SSerialTxControl, HIGH);
  delay(5);

  // noInterrupts();
  RS485Serial.println(jsonOut);
  interrupts();
  
  RS485Serial.flush();
  
  // Tính toán delay động
  int txDelay = (strlen(jsonOut) + 2) * 1.1;
  delay(txDelay + 2); 
  
  digitalWrite(SSerialTxControl, LOW);
}

// ═══════════════════════════════════════════════
//  XỬ LÝ LỆNH (Format: S{id}:{cmd})
// ═══════════════════════════════════════════════

void processCommand(const char* rawCmd) {
  // Skip leading spaces or garbage
  const char* cmd = rawCmd;
  while(*cmd && isspace(*cmd)) cmd++;
  
  if (*cmd == '\0') return;

  // 1. Phải bắt đầu bằng 'S'
  if (cmd[0] != 'S') {
    return; // Bỏ qua im lặng vì đây có thể là phản hồi từ Slave khác trên bus
  }

  // 2. Tìm dấu ':' để tách SlaveID và Command
  char* colonPos = strchr(cmd, ':');
  if (colonPos == NULL) return;

  // 3. Kiểm tra Slave ID
  int targetId = atoi(&cmd[1]);
  if (targetId != SLAVE_ID) {
    // Không phải lệnh cho mình, bỏ qua im lặng
    return;
  }

  // Đúng là lệnh cho mình thì mới in log
  Serial.print(F("RX CMD: '"));
  Serial.print(cmd);
  Serial.println(F("'"));

  Serial.print(F("MATCHED SLAVE_ID: "));
  Serial.println(SLAVE_ID);

  // 4. Command thực tế nằm sau dấu ':'
  const char* realCmd = colonPos + 1;
  char action = realCmd[0];
  
  Serial.print(F("Action: "));
  Serial.println(action);

  if (strcmp(realCmd, "PING") == 0) {
    Serial.println(F("Ping received"));
    sendResponse(-1, -1, "OK", 0, false, "");
    return;
  }
  
  if (strlen(realCmd) < 2) return;

  int slot = atoi(&realCmd[1]);

  // Validate slot
  if (slot < 0 || slot >= NUM_SLOTS) {
    sendError(slot, "INVALID_SLOT");
    return;
  }

  int lockPin = LOCK_PINS[slot];

  if (action == 'T') {
    testSlot(slot, lockPin);
  } else if (action == 'O') {
    openSlot(slot, lockPin);
  } else if (action == 'C') {
    closeSlot(slot, lockPin);
  }
}

// ═══════════════════════════════════════════════
//  TEST SLOT: HIGH → delay → LOW → đo thời gian + đọc sensor
// ═══════════════════════════════════════════════

void testSlot(int slot, int lockPin) {
  Serial.print(F("Testing slot "));
  Serial.print(slot);
  
  unsigned long startMs = millis();
  
  // Mở lock
  digitalWrite(lockPin, RELAY_ON);
  delay(1000); // Chờ relay hít và lẫy khóa được rút vào
  
  // Đóng lock lại
  digitalWrite(lockPin, RELAY_OFF);
  delay(2000); // Tăng thời gian chờ (2000ms) để lò xo đẩy cửa bung ra hẳn

  unsigned long elapsed = millis() - startMs;
  bool isDoorClosed = (digitalRead(MAGNETIC_PINS[slot]) == LOW);

  // Không còn JAMMED/FAIL nữa, chỉ báo kết quả OK và trạng thái sensor hiện tại
  sendResponse(slot, lockPin, "OK", (int)elapsed, isDoorClosed, "");
}

// ═══════════════════════════════════════════════
//  OPEN SLOT: set lock HIGH
// ═══════════════════════════════════════════════

void openSlot(int slot, int lockPin) {
  Serial.print(F("Opening slot "));
  Serial.print(slot);
  Serial.print(F(" lock=pin"));
  Serial.println(lockPin);

  unsigned long startMs = millis();

  // Kích mức RELAY_ON để mở khóa
  digitalWrite(lockPin, RELAY_ON);
  
  // Chờ 1000ms để lẫy khóa rút hẳn vào
  delay(1000);
  
  // Tự động ngắt điện (RELAY_OFF) để bảo vệ cuộn dây khóa
  digitalWrite(lockPin, RELAY_OFF);

  // Chờ thêm 2000ms để cơ cấu lò xo đẩy cánh cửa bật ra thực sự
  delay(2000);

  unsigned long elapsed = millis() - startMs;
  bool isDoorClosed = (digitalRead(MAGNETIC_PINS[slot]) == LOW);

  sendResponse(slot, lockPin, "OK", (int)elapsed, isDoorClosed, "");
}

// ═══════════════════════════════════════════════
//  CLOSE SLOT: set lock LOW
// ═══════════════════════════════════════════════

void closeSlot(int slot, int lockPin) {
  Serial.print(F("Closing slot "));
  Serial.print(slot);
  Serial.print(F(" lock=pin"));
  Serial.println(lockPin);

  unsigned long startMs = millis();

  digitalWrite(lockPin, RELAY_OFF);
  // Chờ 1000ms để user có hoặc cơ chế có thời gian phản hồi (với close không quá lâu nhưng cho an toàn)
  delay(1000);

  unsigned long elapsed = millis() - startMs;
  bool isDoorClosed = (digitalRead(MAGNETIC_PINS[slot]) == LOW);

  sendResponse(slot, lockPin, "OK", (int)elapsed, isDoorClosed, "");
}

// ═══════════════════════════════════════════════
//  GỬI RESPONSE QUA RS485
// ═══════════════════════════════════════════════

void sendResponse(int slot, int gpio, const char* result, int ms,
                  bool isDoorClosed, const char* error) {

  char jsonOut[128];

  // Fix logic: Đảm bảo luôn có dấu '}' đóng chuỗi JSON và có field "slave"
  if (slot == -1) {
    // PING response: Báo cáo số slot thật của phần cứng
    snprintf(jsonOut, sizeof(jsonOut),
      "{\"slave\":%d,\"slots\":%d,\"result\":\"%s\",\"ms\":%d}",
      SLAVE_ID, NUM_SLOTS, result, ms);
  } else if (strlen(error) > 0) {
    snprintf(jsonOut, sizeof(jsonOut),
      "{\"slave\":%d,\"slot\":%d,\"result\":\"%s\",\"gpio\":%d,\"ms\":%d,\"door\":%s,\"error\":\"%s\"}",
      SLAVE_ID, slot, result, gpio, ms, isDoorClosed ? "true" : "false", error);
  } else {
    snprintf(jsonOut, sizeof(jsonOut),
      "{\"slave\":%d,\"slot\":%d,\"result\":\"%s\",\"gpio\":%d,\"ms\":%d,\"door\":%s}",
      SLAVE_ID, slot, result, gpio, ms, isDoorClosed ? "true" : "false");
  }

  // 1. Gửi USB Debug
  Serial.print(F(">>> RS485 TX: "));
  Serial.println(jsonOut);
  Serial.flush(); 

  // 2. Chờ adapter USB-RS485 phía Pi chuyển TX→RX hoàn toàn
  // USB latency (~16ms) + auto-direction switchover (~4ms) + margin
  delay(50);

  // 3. Gửi RS485
  digitalWrite(SSerialTxControl, HIGH); // Bật chế độ TRUYỀN
  delay(10); // Chờ ổn định bus

  // SoftwareSerial::println là hàm đồng bộ (blocking), nó sẽ tự quản lý interrupt
  RS485Serial.println(jsonOut);
  RS485Serial.flush(); // Đợi truyền xong byte cuối (tùy phiên bản Arduino)
  
  // Tính toán delay nhỏ dựa trên baud rate để đảm bảo byte cuối ra khỏi chip hoàn toàn
  // 9600 baud ~ 1.04ms/char. Thêm biên an tử.
  int txDelay = (strlen(jsonOut) + 2) * 1.1;
  delay(txDelay + 2); 
  
  digitalWrite(SSerialTxControl, LOW); // Trở lại chế độ NHẬN
}

void sendError(int slot, const char* error) {
  sendResponse(slot, -1, "FAIL", 0, false, error);
}
