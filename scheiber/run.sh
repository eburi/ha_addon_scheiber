#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "---------------------------------------------------------------------------"
bashio::log.info "Starting scheiber CAN 2 MQTT Bridge..."

# Read config values using bashio
CAN_IFACE=$(bashio::config 'can_interface')
MQTT_HOST=$(bashio::config 'mqtt_host')
MQTT_PORT=$(bashio::config 'mqtt_port')
MQTT_USER=$(bashio::config 'mqtt_user')
MQTT_PASSWORD=$(bashio::config 'mqtt_password')
MQTT_TOPIC_PREFIX=$(bashio::config 'mqtt_topic_prefix')
LOG_LEVEL=$(bashio::config 'log_level')
DATA_DIR=$(bashio::config 'data_dir')
CONFIG_FILE=$(bashio::config 'config_file')
RUN_DEV_VERSION=$(bashio::config 'run_dev_version')

bashio::log.info "---------------------------------------------------------------------------"
bashio::log.info "Configuration Values:"
bashio::log.info "Using CAN interface: ${CAN_IFACE}"
bashio::log.info "MQTT user: ${MQTT_USER}"
bashio::log.info "MQTT host: ${MQTT_HOST}:${MQTT_PORT}"
bashio::log.info "MQTT topic prefix: ${MQTT_TOPIC_PREFIX}"
bashio::log.info "Log level: ${LOG_LEVEL}"
bashio::log.info "Data directory: ${DATA_DIR}"   
bashio::log.info "Configuration File: ${CONFIG_FILE}"
bashio::log.info "Dev version: ${RUN_DEV_VERSION}"

# Export variables for use in the python script
export CAN_INTERFACE="${CAN_IFACE}"
export MQTT_HOST="${MQTT_HOST}"
export MQTT_PORT="${MQTT_PORT}"
export MQTT_TOPIC_PREFIX="${MQTT_TOPIC_PREFIX}"
export MQTT_USER="${MQTT_USER}"
export MQTT_PASSWORD="${MQTT_PASSWORD}"
export LOG_LEVEL="${LOG_LEVEL}"
export LOG_LEVEL="${LOG_LEVEL}"
export DATA_DIR="${DATA_DIR}"
export CONFIG_FILE="${CONFIG_FILE}"

bashio::log.info "---------------------------------------------------------------------------"
bashio::log.info "Setting up CAN interface..."
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

bashio::log.info "---------------------------------------------------------------------------"
bashio::log.info "Starting actual bridge..."
# Start scheiber mqtt bridge
cd /src
source .venv/bin/activate

# Check which version to run
if [ "${RUN_DEV_VERSION}" = "true" ]; then
    bashio::log.info "Running PREVIEW can-mqtt-bridge (version 5.4.0-preview)"
    exec python3 can-mqtt-bridge \
         --can-interface "${CAN_INTERFACE}" \
         --mqtt-host "${MQTT_HOST}" \
         --mqtt-port "${MQTT_PORT}" \
         --mqtt-user "${MQTT_USER}" \
         --mqtt-password "${MQTT_PASSWORD}" \
         --mqtt-topic-prefix "${MQTT_TOPIC_PREFIX}" \
         --log-level "${LOG_LEVEL}" \
         --config "${CONFIG_FILE}" \
         --data-dir "${DATA_DIR}"
else
    bashio::log.info "Running OLD mqtt_bridge.py (version 5.3.6)"
    exec python3 mqtt_bridge.py \
         --mqtt-host "${MQTT_HOST}" \
         --mqtt-port "${MQTT_PORT}" \
         --mqtt-user "${MQTT_USER}" \
         --mqtt-password "${MQTT_PASSWORD}" \
         --mqtt-topic-prefix "${MQTT_TOPIC_PREFIX}" \
         --log-level "${LOG_LEVEL}" \
         --can-interface "${CAN_INTERFACE}" \
         --data-dir "${DATA_DIR}" \
         --config-file "${CONFIG_FILE}"
fi