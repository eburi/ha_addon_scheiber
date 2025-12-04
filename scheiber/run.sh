#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting scheiber CAN 2 MQTT Gateway..."

# Read config values using bashio
CAN_IFACE=$(bashio::config 'can_interface')
MQTT_HOST=$(bashio::config 'mqtt_host')
MQTT_PORT=$(bashio::config 'mqtt_port')
MQTT_USER=$(bashio::config 'mqtt_user')
MQTT_PASSWORD=$(bashio::config 'mqtt_password')
MQTT_TOPIC_PREFIX=$(bashio::config 'mqtt_topic_prefix')
LOG_LEVEL=$(bashio::config 'log_level')

bashio::log.info "Using CAN interface: ${CAN_IFACE}"
bashio::log.info "MQTT user: ${MQTT_USER}"
bashio::log.info "MQTT host: ${MQTT_HOST}:${MQTT_PORT}"
bashio::log.info "MQTT topic prefix: ${MQTT_TOPIC_PREFIX}"
bashio::log.info "Log level: ${LOG_LEVEL}"   

# Export variables for use in the python script
export CAN_INTERFACE="${CAN_IFACE}"
export MQTT_HOST="${MQTT_HOST}"
export MQTT_PORT="${MQTT_PORT}"
export MQTT_TOPIC_PREFIX="${MQTT_TOPIC_PREFIX}"
export MQTT_USER="${MQTT_USER}"
export MQTT_PASSWORD="${MQTT_PASSWORD}"
export LOG_LEVEL="${LOG_LEVEL}"


## Setup
# Use the CAN_IFACE value and configure just that device
# Init can0
ip link set can0 down 2>/dev/null
ip link set can0 type can bitrate 250000 fd off restart-ms 100
ip link set can0 up
ifconfig can0 txqueuelen 10000

# Init can1
ip link set can1 down 2>/dev/null
ip link set can1 type can bitrate 250000 fd off restart-ms 100
ip link set can1 up
ifconfig can1 txqueuelen 10000

# Start scheiber mqtt bridge
cd /tools
source .venv/bin/activate
exec python3 mqtt_bridge.py --debug \
     --mqtt-host "${MQTT_HOST}" \
     --mqtt-port "${MQTT_PORT}" \
     --mqtt-user "${MQTT_USER}" \
     --mqtt-password "${MQTT_PASSWORD}" \
     --mqtt-topic-prefix "${MQTT_TOPIC_PREFIX}" \
     --can-interface "${CAN_INTERFACE}"
     --can-interface "${CAN_INTERFACE}"