/*
 * LIPLAB 촉각(타도마) 얼굴 모형 — Arduino Uno 펌웨어
 * ------------------------------------------------------------------
 * 웹(브라우저, Web Serial)이 문장을 음소로 분석해 아래 형식의 값을
 * 한 줄씩 보내면, 아두이노는 판단 없이 그대로 액추에이터로 재현한다.
 *
 * 시리얼 입력 형식(9600 baud, 한 줄 단위):
 *   ① 움직임:  J,L,V,A,D\n
 *       J = 턱 각도 (0~20)          → 턱서보
 *       L = 입술    (0=평순 / 1=원순) → 입술서보  (0°→0, 1→40°)
 *       V = 진동    (0=무성 / 1=유성) → 진동모터
 *       A = 기류    (0=none / 1=plosive(파열) / 2=fricative(마찰)) → 팬
 *       D = 지속시간 (ms)
 *       예) 파열 유성 'ㅂ' + 100ms:  4,0,1,1,100
 *       특수: "0,0,0,0,0" → 전부 정지(휴지)
 *   ② 런타임 핀 설정:  SET,jaw,lip,vib,fan\n
 *       웹에서 부품별 핀을 보내면 재업로드 없이 즉시 그 핀으로 재설정한다.
 *       예) SET,9,10,5,6   (기본값)
 *
 * 배선 (외부 5V 전원, ※ 외부전원 GND ↔ 아두이노 GND 반드시 공통 연결):
 *   턱/입술 서보 : 빨강→5V(외부+), 검정→GND(외부-), 노랑(신호)→각 핀
 *   진동모터/팬  : 신호핀 →[220Ω]→ 2N2222 베이스, 컬렉터→부하(+), 부하(-)→GND(외부-),
 *                  이미터→GND(외부-), 부하 양단에 1N4007 병렬(역기전력 보호)
 *   2N2222 핀(평면 정면): 왼쪽부터 E(이미터) - B(베이스) - C(컬렉터)
 *   ※ 팬은 세기 조절(PWM)이 필요 → 3·5·6·11번 중 하나 (D9·D10은 Servo가 PWM을 점유)
 *   ※ D0·D1은 USB 통신용이라 사용 금지
 */

#include <Servo.h>

// 기본 핀 — 웹의 'SET' 명령으로 런타임에 바꿀 수 있다(재업로드 불필요).
int pinJaw = 9;    // 턱서보 신호
int pinLip = 10;   // 입술서보 신호
int pinVib = 5;    // 진동모터 트랜지스터 베이스(저항 경유)
int pinFan = 6;    // 팬 트랜지스터 베이스(저항 경유, PWM)

const int LIP_FLAT  = 0;   // 평순 각도
const int LIP_ROUND = 40;  // 원순 각도

const int FAN_PLOSIVE = 255;  // 파열: 짧고 강하게
const int FAN_FRIC    = 150;  // 마찰: 약하게 지속
const int PLOSIVE_MS  = 70;   // 파열 버스트 길이(ms)

Servo servoJaw, servoLip;

void rest() {
  servoJaw.write(0);
  servoLip.write(LIP_FLAT);
  digitalWrite(pinVib, LOW);
  analogWrite(pinFan, 0);
}

// 현재 핀 값으로 액추에이터를 (재)설정 — setup과 SET 명령에서 호출
void applyPins() {
  servoJaw.detach();
  servoLip.detach();
  servoJaw.attach(pinJaw);
  servoLip.attach(pinLip);
  pinMode(pinVib, OUTPUT);
  pinMode(pinFan, OUTPUT);
  rest();
}

void setup() {
  Serial.begin(9600);
  applyPins();
}

// 한 음소 재현: 값을 반영하고 지속시간만큼 유지
void playPhoneme(int jaw, int lip, int vib, int air, long dur) {
  jaw = constrain(jaw, 0, 20);
  servoJaw.write(jaw);
  servoLip.write(lip ? LIP_ROUND : LIP_FLAT);
  digitalWrite(pinVib, vib ? HIGH : LOW);

  if (air == 1) {                 // 파열음: 짧고 강한 버스트 후 정지
    analogWrite(pinFan, FAN_PLOSIVE);
    long burst = min(dur, (long)PLOSIVE_MS);
    delay(burst);
    analogWrite(pinFan, 0);
    if (dur > burst) delay(dur - burst);
  } else if (air == 2) {          // 마찰음: 약하게 지속
    analogWrite(pinFan, FAN_FRIC);
    delay(dur);
    analogWrite(pinFan, 0);
  } else {                        // 기류 없음(모음·비음)
    analogWrite(pinFan, 0);
    delay(dur);
  }
}

// "SET,jaw,lip,vib,fan" 파싱 → 런타임 핀 재설정
void handleSet(String line) {
  int firstComma = line.indexOf(',');
  if (firstComma < 0) return;
  int p[4]; int k = 0; int from = firstComma + 1;
  for (int i = from; i <= line.length() && k < 4; i++) {
    if (i == line.length() || line.charAt(i) == ',') {
      p[k++] = line.substring(from, i).toInt();
      from = i + 1;
    }
  }
  if (k < 4) return;
  // 안전 가드: 유효 핀(2~13)만 반영
  for (int j = 0; j < 4; j++) if (p[j] < 2 || p[j] > 13) return;
  pinJaw = p[0]; pinLip = p[1]; pinVib = p[2]; pinFan = p[3];
  applyPins();
  Serial.println("pins set");
}

void loop() {
  if (!Serial.available()) return;

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line.startsWith("SET")) {   // ② 런타임 핀 설정
    handleSet(line);
    return;
  }

  // ① 움직임: "J,L,V,A,D" 파싱
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
