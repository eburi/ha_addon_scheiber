# Home Assistant Add-on: scheiber

**Interface with scheiber components over CAN-bus and MQTT**

**Experimental!!**



# Data structure in MQTT for Home Assistant integration. 

## Topics

For the bus:
<prefix>/scheiber - json with state of the bus like load, as messages per minute, number of unique sender_ids, number of known sender_ids, list of unique sender_ids, list of known sender_ids, updated when it changes



For the device:
<prefix>/scheiber/<device-type>/<bus-id> - Information about this device in json (name, properties and more that we find later when analyzing more can messages)
<prefix>/scheiber/<device-type>/<bus-id>/config - json with configuration information for Home Assistant MQTT Auto Discovery to have the "switches", wich are dimmable, exposed as light components of the device.
See:
-  https://www.home-assistant.io/integrations/light.mqtt/
- https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery

<prefix>/scheiber/<device-type>/<bus_id>/<property_id>/state - current value as output from format_template

E.g:
homeassistant/scheiber/bloc9/10/s1/state => 1/0