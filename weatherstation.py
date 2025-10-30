from flask import Flask, request, jsonify
from datetime import datetime
import pytz
import os
import json
import paho.mqtt.client as mqtt
import requests
import dns.resolver

# MQTT settings
MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_USER = "MQTT_USER"
MQTT_PASSWORD = "MQTT_PASSWORD"
MQTT_PREFIX = "MQTT_PREFIX"
DEVICE_ID = "weather_station"
DEVICE_NAME = "Weather Station"
DEVICE_MANUFACTURER = "VEVOR"
DEVICE_MODEL = "7-in-1 Weather Station"
TIMEZONE = "Europe/Berlin"
UNITS = "metric"
WU_FORWARD = "true"
WU_USERNAME = "WU_USERNAME"
WU_PASSWORD = "WU_PASSWORD"

app = Flask(__name__)

mqtt_client = mqtt.Client()
if MQTT_USER:
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
mqtt_client.connect(MQTT_HOST, MQTT_PORT, 60)
mqtt_client.loop_start()

def f_to_c(f): return round((float(f) - 32) * 5.0 / 9.0, 1)
def inhg_to_hpa(inhg): return round(float(inhg) * 33.8639, 1)
def mph_to_kmh(mph): return round(float(mph) * 1.60934, 1)
def inch_to_mm(inch): return round(float(inch) * 25.4, 1)

def safe_get(key): return request.args.get(key, None)

@app.route('/weatherstation/updateweatherstation.php')
def update():
    attributes = {
        "Barometric Pressure": {
            "value": (
                inhg_to_hpa(safe_get("baromin")) if UNITS == "metric" else round(float(safe_get("baromin")), 1)
            ) if safe_get("baromin") else None,
            "unit": "hPa" if UNITS == "metric" else "inHg",
            "device_class": "atmospheric_pressure",
        },
        "Temperature": {
            "value": (
                f_to_c(safe_get("tempf")) if UNITS == "metric" else round(float(safe_get("tempf")), 1)
            ) if safe_get("tempf") else None,
            "unit": "°C" if UNITS == "metric" else "°F",
            "device_class": "temperature",
        },
        "Humidity": {"value": safe_get("humidity"), "unit": "%", "device_class": "humidity"},
        "Dew Point": {
            "value": (
                f_to_c(safe_get("dewptf")) if UNITS == "metric" else round(float(safe_get("dewptf")), 1)
            ) if safe_get("dewptf") else None,
            "unit": "°C" if UNITS == "metric" else "°F",
            "device_class": "temperature",
        },
        "Rainfall": {
            "value": (
                inch_to_mm(safe_get("rainin")) if UNITS == "metric" else round(float(safe_get("rainin")), 2)
            ) if safe_get("rainin") else None,
            "unit": "mm" if UNITS == "metric" else "in",
            "device_class": "precipitation",
        },
        "Daily Rainfall": {
            "value": (
                inch_to_mm(safe_get("dailyrainin")) if UNITS == "metric" else round(float(safe_get("dailyrainin")), 2)
            ) if safe_get("dailyrainin") else None,
            "unit": "mm" if UNITS == "metric" else "in",
            "device_class": "precipitation",
        },
        "Wind Direction": {"value": safe_get("winddir"), "unit": "°", "device_class": None},
        "Wind Speed": {
            "value": (
                mph_to_kmh(safe_get("windspeedmph")) if UNITS == "metric" else round(float(safe_get("windspeedmph")), 1)
            ) if safe_get("windspeedmph") else None,
            "unit": "km/h" if UNITS == "metric" else "mph",
            "device_class": "wind_speed",
        },
        "Wind Gust Speed": {
            "value": (
                mph_to_kmh(safe_get("windgustmph")) if UNITS == "metric" else round(float(safe_get("windgustmph")), 1)
            ) if safe_get("windgustmph") else None,
            "unit": "km/h" if UNITS == "metric" else "mph",
            "device_class": "wind_speed",
        },
        "UV Index": {"value": safe_get("UV"), "unit": "index", "device_class": None},
        "Solar Radiation": {"value": safe_get("solarRadiation"), "unit": "W/m²", "device_class": "irradiance"},
    }

    dateutc = safe_get('dateutc')
    local_time = ""
    if dateutc:
        try:
            dt = datetime.strptime(dateutc, "%Y-%m-%d %H:%M:%S")
            dt = pytz.utc.localize(dt).astimezone(pytz.timezone(TIMEZONE))
            local_time = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            local_time = dateutc  # fallback

    # Publish each sensor to MQTT using HA auto-discovery
    for name, data in attributes.items():
        if data["value"] is None:
            continue
        sensor_id = name.lower().replace(" ", "_")
        base = f"{MQTT_PREFIX}/sensor/{DEVICE_ID}_{sensor_id}"
        state_topic = f"{base}/state"
        attr_topic = f"{base}/attributes"
        config_topic = f"{base}/config"
        config_payload = {
            "name": f"{DEVICE_NAME} {name}",
            "state_topic": state_topic,
            "unit_of_measurement": data["unit"],
            "device_class": data["device_class"],
            "unique_id": f"{DEVICE_ID}_{sensor_id}",
            "json_attributes_topic": attr_topic,
            "device": {
                "identifiers": [DEVICE_ID],
                "name": DEVICE_NAME,
                "manufacturer": DEVICE_MANUFACTURER,
                "model": DEVICE_MODEL,
            },
        }
        mqtt_client.publish(config_topic, json.dumps(config_payload), retain=True)
        mqtt_client.publish(state_topic, str(data["value"]), retain=True)
        mqtt_client.publish(attr_topic, json.dumps({"measured_on": local_time}), retain=True)

    if WU_FORWARD:
        params = request.args.to_dict(flat=True)
        if WU_USERNAME:
            params["ID"] = WU_USERNAME
        if WU_PASSWORD:
            params["PASSWORD"] = WU_PASSWORD
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ["8.8.8.8", "8.8.4.4"]
            wu_ip = resolver.resolve("rtupdate.wunderground.com")[0].to_text()
            url = f"http://{wu_ip}/weatherstation/updateweatherstation.php"
            headers = {"Host": "rtupdate.wunderground.com"}
            requests.get(url, params=params, headers=headers, timeout=5)
        except Exception as e:
            print(f"Failed to forward to Weather Underground: {e}")

    return "success", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
