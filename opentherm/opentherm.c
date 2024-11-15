#include <stdio.h>
#include <math.h>

#include <WiFi.h>
#include <WiFiClient.h>
#include <WebServer.h>
#include <ESPmDNS.h>

#include <OpenTherm.h>

unsigned long millis();
float crono_get_stp(int, int, int, int);
int day, h, m;
WebServer server(80);

//Master OpenTherm Shield pins configuration
const int OT_IN_PIN = 21;  //4 for ESP8266 (D2), 21 for ESP32
const int OT_OUT_PIN = 22; //5 for ESP8266 (D1), 22 for ESP32
OpenTherm ot(OT_IN_PIN, OT_OUT_PIN);


int chust = 0, // 0=off, 1=roomstp, 2=crono, 3=chwstp
  dhwust = 0; // 0=off, 1=dhwstp, 2=crono
int chuovrrd = 0,
  dhwuovrrd = 0;

float roomt=20., roomstp=20., chwstp=45., dhwstp=40.; // user values
int chon=0, dhwon=0;
float mchwstp, mdhwstp, mdhwt; // machine values
int mchon, mdhwon, flame, fault, faultg, faults;


class Thermostat {
 private:
  int8_t sign;
  float delta;
  int delay;
  int8_t state = -1;
  unsigned long lastswitch = -1;
 public:

  Thermostat(int usign, float udelta, int udelay) {
    if (usign >= 0)
      sign = 1;
    else
      sign = -1;
    delta = udelta >= 0. ? udelta : 0.;
    delay = udelay >= 0 ? udelay : 0;
  }

  int doswitch(float obs, float setp) {
    int8_t newstate;
    int now;

    if (state == -1) {
      state = (((obs > setp)*2 - 1)*sign + 1)/2;
      lastswitch = millis();
    } else {
      newstate = (abs(obs-setp) > delta)*(((obs > setp)*2 - 1)*sign + 1)/2;
      if (newstate != state) {
	now = millis();
	if ((now-lastswitch)/1000 > delay) {
	  lastswitch = now;
	  state = newstate;
	}
      }
    }
    return state;
  }
};
    
Thermostat ch_ts(-1, 0.5, 120);

void handleInterrupt() {
  ot.handleInterrupt();
}

void update_machine() {

  switch(chust) {
  case 0:
    chon = 0;
  case 1:
    chon = ch_ts.doswitch(roomt, roomstp);
    mchwstp = chwstp; // pid(roomt, ...)
  case 2:
    chon = ch_ts.doswitch(roomt, crono_get_stp(day, h, m, 0));
    mchwstp = chwstp; // pid(roomt, ...)
  case 3:
    chon = 1;
    mchwstp = chwstp;
  default:
    chon = 0;
  }
  switch(dhwust) {
  case 0:
    dhwon = 0;
  case 1:
    dhwon = 1;
    mdhwstp = dhwstp;
  case 2:
    dhwon = 1;
    mdhwstp = crono_get_stp(day, h, m, 1);
  default:
    dhwon = 0;
  }
}
    
void setup(void) {
  /*    pinMode(BUILTIN_LED, OUTPUT);
	digitalWrite(BUILTIN_LED, 0); */
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.println("");

  // Wait for connection
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Connected to ");
  Serial.println(ssid);
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  /* if (MDNS.begin("thermostat")) {
     Serial.println("MDNS responder started");
     } */

  server.on("/", handleRoot);
  server.on("/user/set", HTTP_POST, setuser);
  server.on("/user/get", HTTP_GET, getuser);
  server.on("/machine/get", HTTP_GET, getmachine);
  server.on("/chcron/set", HTTP_POST, setchcron);
  server.on("/chcron/get", HTTP_GET, getchcron);
  server.on("/dhwcron/set", HTTP_POST, setdhwcron);
  server.on("/dhwcron/get", HTTP_GET, getdhwcron);
  server.on("/test", []() {
      server.send(200, "text/plain", "this works as well");
    });

  server.onNotFound(handleNotFound);

  server.begin();
  Serial.println("HTTP server started");
  ot.begin(handleInterrupt);
}


void loop(void) {
  // here do opentherm communication
  // id 0 send chon dhwon, receive mchon, mdhwon, flame, fault
  // id 1 send mchwstp
  // id 56 send mdhwstp
  // id 26 receive mdhwt ? id 25 boiler flow water t ?
  // id 19 dhw flow rate ?

  server.handleClient();
  // handle timers here
}


setuser() {
  int val;
  float fval;
  // find a way to distinguish missing/error from 0
  for (uint8_t i = 0; i < server.args(); i++) {
    if (server.argName(i) == "chust") {
      val = server.arg(i).toInt();
      if (val >= 0 && val <= 3) chust = val;
    } else if (server.argName(i) == "dhwust") {
      val = server.arg(i).toInt();
      if (val >= 0 && val <= 2) dhwust = val;
    } else if (server.argName(i) == "roomstp") {
      fval = server.arg(i).toFloat();
      if (fval >= 10. && fval <= 40.) roomstp = val;
    } else if (server.argName(i) == "chwstp") {
      fval = server.arg(i).toFloat();
      if (fval >= 30. && fval <= 45.) chwstp = val;
    } else if (server.argName(i) == "dhwstp") {
      fval = server.arg(i).toFloat();
      if (fval >= 30. && fval <= 60.) dhwstp = val;
    }
  }
  server.send(200, "text/plain", "OK");
}

getuser() {
  String rep="{";
  rep.concat("chust:"+chust);
  rep.concat(",dhwust:"+dhwust);
  rep.concat(",roomt:"+roomt);
  rep.concat(",roomstp:"+roomstp);
  rep.concat(",chwstp:"+chwstp);
  rep.concat(",dhwstp:"+dhwstp);
  rep.concat(",mchwstp:"+mchwstp);
  rep.concat(",mdhwstp:"+mdhwstp);
  rep.concat(",chon:"+chon);
  rep.concat(",dhwon:"+dhwon+"}");
  server.send(200, "text/json", rep);
}

getmachine() {
  String rep="{";
  rep.concat("mchwstp:"+mchwstp);
  rep.concat(",mdhwstp:"+mdhwstp);
  rep.concat(",mdhwt:"+mdhwt);
  rep.concat(",mchon:"+mchon);
  rep.concat(",mdhwon:"+mdhwon);
  rep.concat(",flame:"+flame);
  rep.concat(",fault:"+fault);
  rep.concat(",faultg:"+faultg);
  rep.concat(",faults:"+faults+"}");
  server.send(200, "text/json", rep);
}

getdhwcron() {
  return getchron(0);
}
getchcron() {
  return getchron(1);
}

getchron(int typ) {
  uint8_t nprog;
  String prog;

  for (nprog = 0; nprog < NPROG; nprog++)
    if (progbuff[typ][nprog].stpentry >= NSTP) break;
  prog.concat("{nprog:"+nprog+",prog:[")
  for (uint8_t j = 0; j < nprog; j++) {
    prog.concat("{day:\"")
    for (uint8_t i = 0; i < 7; i++)
      prog.concat(progbuff[typ][j].day[i]);
    prog.concat("\",starth:"+progbuff[typ][j].starth);
    prog.concat(",stoph:"+progbuff[typ][j].stoph);
    prog.concat(",startm:"+progbuff[typ][j].startm);
    prog.concat(",stopm:"+progbuff[typ][j].stopm+"}");
    if (j < nprog-1) prog.concat(",");
  }
  prog.concat("]}");
  server.send(200, "text/json", prog);
}

setdhwcron() {
  return setchron(0);
}
setchcron() {
  return setchron(1);
}

setchron(int typ) {
  // use checkbox d1=1,d3=1...
  String prog;
  uint8_t nprog = server.arg("nprog").toInt();
  // check arguments
  if (nprog < 0 || nprog > NPROG) {
      server.send(400, "text/plain", "Bad Request");
      return 1;
  }
  for (uint8_t j = 0; j < nprog; j++) {
    prog = server.arg("prog"+String(j)); // "%01d%c%c%c%c%c%c%c%02d%02d%02d%02d"
    if (prog.length() != 16) {
      server.send(400, "text/plain", "Bad Request");
      return 1;
    }
  }
  // set crono
  crono_set_default(0, typ);
  for (uint8_t j = 0; j < nprog; j++) {
    prog = server.arg("prog"+String(j)); // "%01d%c%c%c%c%c%c%c%02d%02d%02d%02d"
    progbuff[typ][j].stpentry = prog.substring(0, 1).toInt();
    for (uint8_t i = 0; i < 7; i++)
      progbuff[typ][j].day[i] = prog.substring(i+1, i+2).toInt();
    progbuff[typ][j].starth = prog.substring(8, 10).toInt();
    progbuff[typ][j].startm = prog.substring(10, 12).toInt();
    progbuff[typ][j].stoph = prog.substring(12, 14).toInt();
    progbuff[typ][j].stopm = prog.substring(14, 16).toInt();
    crono_apply(progbuff[typ][j], typ);
  }
  for (uint8_t j = nprog; j < nprog; j++) {
    progbuff[typ][j].stpentry = 255;
  }
  server.send(200, "text/plain", "OK");
}
