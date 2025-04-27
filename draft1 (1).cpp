#include <SoftwareSerial.h>
#include <HCSR04.h>

UltraSonicDistanceSensor Sensor(13, 12, 400);
int _timeout;
String _buffer;
//String number = "+63";
SoftwareSerial sim(10, 11);
float prevdist = 0;

void setup() {
    Serial.begin(9600);
    _buffer.reserve(50);
    Serial.println("System Started...");
    sim.begin(9600);
    delay(10000);
}

String _readSerial() {
    _timeout = 0;
    while (!sim.available() && _timeout < 12000) {
        delay(13);
        _timeout++;
    }
    if (sim.available()) {
        return sim.readString();
    }
}

void ShowSerialData() {
    while (sim.available() != 0)
        Serial.write(sim.read());
    delay(5000);
}

void initializeGSM() {
    sim.println("AT");
    delay(1000);

    sim.println("AT+CPIN?");
    delay(1000);

    sim.println("AT+CREG?");
    delay(1000);

    sim.println("AT+CGATT?");
    delay(1000);

    sim.println("AT+CIPSHUT");
    delay(1000);

    sim.println("AT+CIPSTATUS");
    delay(2000);

    sim.println("AT+CIPMUX=0");
    delay(2000);

    ShowSerialData();

    sim.println("AT+CSTT=\"internet\"");
    delay(2000);

    ShowSerialData();

    sim.println("AT+CIICR");
    delay(3000);

    ShowSerialData();

    sim.println("AT+CIFSR");
    delay(2000);

    ShowSerialData();

    sim.println("AT+CIPSPRT=0");
    delay(3000);

    ShowSerialData();
}

void connectToServer() {
    sim.println("AT+CIPSTART=\"TCP\",\"api.thingspeak.com\",\"80\"");
    delay(6000);

    ShowSerialData();
}

void sendDataToServer(float distIn) {
    sim.println("AT+CIPSEND");
    delay(4000);

    ShowSerialData();

//    Serial.println("GET https://api.thingspeak.com/" + String(distIn));

//    sim.println("GET https://api.thingspeak.com/" + String(distIn));
    delay(4000);

    ShowSerialData();

    sim.println((char)26); // sending
    delay(5000);
    sim.println();

    ShowSerialData();
    
    sim.println("AT+CIPSHUT");
    delay(100)
    ShowSerialData();

    Serial.println("Data Uploaded!");
    delay(1000);
}

void sendSMS(String message) {
    sim.println("AT+CMGF=1");
    delay(200);
    sim.print("AT+CSMP=17,167,0,0 \r");
    delay(300);
    sim.println("AT+CMGS=\"" + number + "\"\r");
    delay(200);
    sim.println(message);
    delay(100);
    sim.println((char)26);
    delay(200);
    _buffer = _readSerial();
    Serial.println("\nMessage Sent!\n")
}

void tminSMS(String message, float tmin)
{
    sim.println("AT+CMGF=1");
    delay(200);
    sim.print("AT+CSMP=17,167,0,0 \r");
    delay(300);
    sim.println("AT+CMGS=\"" + number + "\"\r");
    delay(200);
    sim.print(message);
    sim.print(tmin);
    sim.println(" minutes.");
    sim.println((char)26);
    delay(200);
    _buffer = _readSerial();
    Serial.println("\nMessage Sent!\n");
}

void handleFloodLevel(float distIn) {
    //Declarations of flood levels
    int nptatv = 26;
    int wlevel = 37;
    int clevel = 45;
    int nptlv = 13;
    int klevel = 19;
    int hklevel = 10;
    int alevel = 8;

    //Handle different flood levels
    if (distIn >= nptatv) {
        if (distIn >= clevel) {
            sendSMS("The Flood has now reached 3'9'' (Chest height) in area 2 and is no longer passable to all types of vehicle.");
        } else if (distIn >= wlevel && distIn < clevel) {
            sendSMS("The Flood has now reached 3'1'' (Waist height) in area 2 and is no longer passable to all types of vehicle.");
        } else {
            sendSMS("The Flood has now reached 2'4'' (Leg height or Car Tire height) in area 2 and is no longer passable to all types of vehicle.");
        }
    } else if (distIn >= nptlv) {
        if (distIn >= klevel) {
            sendSMS("The Flood has now reached 1'7'' (Knee Height) in area 2 and no longer passable to light vehicles.");
        } else {
            sendSMS("The Flood has now reached 1'1'' (Shin height or car half-tire height) in area 2 and is no longer passable for light vehicles.");
        }
    } else if (distIn >= hklevel) {
        sendSMS("The Flood has now reached 10 in. (Half-Knee Height) in area 2 and is passable to all types of vehicles.");
    } else if (distIn >= alevel && distIn < hklevel) {
        sendSMS("The Flood has now reached 8 in. (Ankle Height) in area 2 and is passable to all types of vehicles.");
    }
}

void loop() {
    float dist = Sensor.measureDistanceCm();
    float floodLvl = 182.88 - dist;
    float distIn = floodLvl / 2.54;

    int regt = (prevdist - distIn)/10;
    int tmin = (distIn)/regt;

    Serial.println(dist);
    Serial.println(floodLvl);
    Serial.println(distIn);
    Serial.println(regt);
    Serial.println(tmin);

    if (sim.available())

        Serial.write(sim.read());
    

    if (tmin > 0 && distIn > 0)
    {

        initializeGSM();
        connectToServer();
        sendDataToServer(distIn);
        handleFloodLevel(distIn);
        delay(10000);
        tminSMS("The approximated time for the flood to recede is: ",tmin);
    }
    else
    {
        initializeGSM();
        connectToServer();
        sendDataToServer(distIn);
        handleFloodLevel(distIn);
    }

    prevdist = distIn;
    Serial.println("Prevdist recorded: " + String(prevdist));
    Serial.println("loop concluded");
    delay(600000);
}