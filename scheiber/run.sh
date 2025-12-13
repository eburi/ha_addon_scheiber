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
bashio::log.info "Running migrations..."
# Run migration scripts if they exist
cd /src
source .venv/bin/activate

if [ -d "migrate" ]; then
    # Create migration tracker file if it doesn't exist
    MIGRATION_TRACKER="${DATA_DIR}/.migrations_applied"
    touch "${MIGRATION_TRACKER}"
    
    # Find all migration scripts (sorted by filename)
    for migration in $(find migrate -type f \( -name "*.sh" -o -name "*.py" \) | sort); do
        migration_name=$(basename "$migration")
        
        # Check if migration has already been applied
        if grep -Fxq "${migration_name}" "${MIGRATION_TRACKER}"; then
            bashio::log.debug "Migration ${migration_name} already applied, skipping"
            continue
        fi
        
        bashio::log.info "Running migration: ${migration_name}"
        
        # Run migration based on file type
        if [[ "$migration" == *.py ]]; then
            # Python migration (with venv already activated)
            if python3 "$migration" --data-dir "${DATA_DIR}" --config-file "${CONFIG_FILE}"; then
                echo "${migration_name}" >> "${MIGRATION_TRACKER}"
                bashio::log.info "Migration ${migration_name} completed successfully"
            else
                bashio::log.error "Migration ${migration_name} failed!"
                exit 1
            fi
        elif [[ "$migration" == *.sh ]]; then
            # Shell migration
            if bash "$migration" "${DATA_DIR}" "${CONFIG_FILE}"; then
                echo "${migration_name}" >> "${MIGRATION_TRACKER}"
                bashio::log.info "Migration ${migration_name} completed successfully"
            else
                bashio::log.error "Migration ${migration_name} failed!"
                exit 1
            fi
        fi
    done
fi

bashio::log.info "---------------------------------------------------------------------------"
bashio::log.info "Starting actual bridge..."

# Check which version to run
if [ "${RUN_DEV_VERSION}" = "true" ]; then
    bashio::log.info "Running LEGACY mqtt_bridge.py (version 5.7.8 - archived)"
    exec python3 archive/mqtt_bridge.py \
         --mqtt-host "${MQTT_HOST}" \
         --mqtt-port "${MQTT_PORT}" \
         --mqtt-user "${MQTT_USER}" \
         --mqtt-password "${MQTT_PASSWORD}" \
         --mqtt-topic-prefix "${MQTT_TOPIC_PREFIX}" \
         --log-level "${LOG_LEVEL}" \
         --can-interface "${CAN_INTERFACE}" \
         --data-dir "${DATA_DIR}" \
         --config-file "${CONFIG_FILE}"
else
    bashio::log.info "Running can-mqtt-bridge (version 6.0.0)"
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
fi