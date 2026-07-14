/*
 * LIPLAB 촉각(타도마) 얼굴 모형 — Arduino Uno 펌웨어
 * ------------------------------------------------------------------
 * 웹(브라우저, Web Serial)이 문장을 음소로 분석해 아래 형식의 값을
 * 한 줄씩 보내면, 아두이노는 판단 없이 그대로 액추에이터로 재현한다.
 *
 * 시리얼 입력 형식(한 줄 = 한 음소, 9600 baud):
 *     J,L,V,A,D\n
 *       J = 턱 각도 (0~20)          → 턱서보(D9)
 *       L = 입술    (0=평순 / 1=원순) → 입술서보(D10)  (0°→0, 1→40°)
 *       V = 진동    (0=무성 / 1=유성) → 진동모터(D5)
 *       A = 기류    (0=none / 1=plosive(파열) / 2=fricative(마찰)) → 팬(D6)
 *       D = 지속시간 (ms)
 *     예) 파열 유성 'ㅂ' + 100ms:  4,0,1,1,100
 *     특수: "0,0,0,0,0" 을 보내면 전부 정지(휴지)한다.
 *
 * 배선 (외부 5V 전원 사용, ※ 외부전원 GND ↔ 아두이노 GND 반드시 공통 연결):
 *     턱서보  : 빨강→5V(외부+), 검정→GND(외부-), 노랑(신호)→D9
 *     입술서보: 빨강→5V(외부+), 검정→GND(외부-), 노랑(신호)→D10
 *     진동모터: D5 →[220Ω]→ 2N2222 베이스,  컬렉터→모터(+), 모터(-)→GND(외부-),
 *               이미터→GND(외부-),  모터 양단에 1N4007 병렬(띠=모터+ 방향, 역기전력 보호)
 *     팬      : D6 →[220Ω]→ 2N2222 베이스,  컬렉터→팬(+),  팬(-)→GND(외부-),
 *               이미터→GND(외부-),   팬 양단에 1N4007 병렬(역방향)
 *     2N2222 핀(평면을 정면으로): 왼쪽부터 E(이미터) - B(베이스) - C(컬렉터)
 */

#include <Servo.h>

const int PIN_JAW  = 9;    // 턱서보 신호
const int PIN_LIP  = 10;   // 입술서보 신호
const int PIN_VIB  = 5;    // 진동모터 트랜지스터 베이스(저항 경유)
const int PIN_FAN  = 6;    // 팬 트랜지스터 베이스(저항 경유, PWM)

const int LIP_FLAT  = 0;   // 평순 각도
const int LIP_ROUND = 40;  // 원순 각도

const int FAN_PLOSIVE = 255;  // 파열: 짧고 강하게
const int FAN_FRIC    = 150;  // 마찰: 약하게 지속
const int PLOSIVE_MS  = 70;   // 파열 버스트 길이(ms)

Servo servoJaw, servoLip;

void rest() {
  servoJaw.write(0);
  servoLip.write(LIP_FLAT);
  digitalWrite(PIN_VIB, LOW);
  analogWrite(PIN_FAN, 0);
}

void setup() {
  Serial.begin(9600);
  servoJaw.attach(PIN_JAW);
  servoLip.attach(PIN_LIP);
  pinMode(PIN_VIB, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  rest();
}

// 한 음소 재현: 값을 반영하고 지속시간만큼 유지
void playPhoneme(int jaw, int lip, int vib, int air, long dur) {
  jaw = constrain(jaw, 0, 20);
  servoJaw.write(jaw);
  servoLip.write(lip ? LIP_ROUND : LIP_FLAT);
  digitalWrite(PIN_VIB, vib ? HIGH : LOW);

  if (air == 1) {                 // 파열음: 짧고 강한 버스트 후 정지
    analogWrite(PIN_FAN, FAN_PLOSIVE);
    long burst = min(dur, (long)PLOSIVE_MS);
    delay(burst);
    analogWrite(PIN_FAN, 0);
    if (dur > burst) delay(dur - burst);
  } else if (air == 2) {          // 마찰음: 약하게 지속
    analogWrite(PIN_FAN, FAN_FRIC);
    delay(dur);
    analogWrite(PIN_FAN, 0);
  } else {                        // 기류 없음(모음·비음)
    analogWrite(PIN_FAN, 0);
    delay(dur);
  }
}

void loop() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  // "J,L,V,A,D" 파싱
  int vals[5] = {0, 0, 0, 0, 0};
  int idx = 0, from = 0;
  for (int i = 0; i <= line.length() && idx < 5; i++) {
    if (i == line.length() || line.charAt(i) == ',') {
      vals[idx++] = line.substring(from, i).toInt();
      from = i + 1;
    }
  }

  // 전부 0 → 휴지(정지)
  if (vals[0] == 0 && vals[1] == 0 && vals[2] == 0 && vals[3] == 0 && vals[4] == 0) {
    rest();
    return;
  }

  playPhoneme(vals[0], vals[1], vals[2], vals[3], (long)vals[4]);
  Serial.println("ok");   // 웹이 다음 음소를 보내는 흐름제어용(선택)
}
