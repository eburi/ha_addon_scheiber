# Home Assistant Add-on: CAN RAW Gateway  
**Yacht Devices RAW Text Protocol (Appendix E Compatible)**

This Home Assistant add-on exposes a Linux SocketCAN interface (e.g. `can0`) as a
**Yacht Devices–compatible RAW text TCP feed**, fully bi-directional, using the
format defined in **Appendix E** of the Yacht Devices YDEN-02 / YDNU-02 protocol
documentation.

👉 Protocol spec (RAW text mode):  
**https://www.yachtd.com/downloads/ydnu02.pdf**  
(See *Appendix E — Text Format of NMEA 2000 Messages*)

This allows Home Assistant OS to emulate the RAW output mode of Yacht Devices’
CAN/NMEA2000 bridges (such as YDEN-02), enabling integrations with SignalK,
NMEA2000 tools, or custom software that expect the YD RAW TCP interface.

---

## ✨ Features

### ✔ Exact Yacht Devices RAW Text Output
Every CAN frame is broadcast to all TCP clients in the RAW text format:

```
hh:mm:ss.sss R <CAN_ID> <DATA...>
```

- Timestamp in UTC with millisecond resolution  
- `R` indicates **Received** from CAN  
- CAN ID in 8-digit uppercase hex  
- Data bytes in two-digit uppercase hex  

Example:
```
12:30:15.482 R 19F51323 01 02 03 04
```

### ✔ Bi-directional (TCP → CAN → TCP)
TCP clients may send RAW lines:

```
19F51323 01 02 03 04
```

The add-on will:

1. Parse the frame  
2. Send it to the CAN bus  
3. Echo back as a **Transmitted** frame:
   ```
   hh:mm:ss.sss T 19F51323 01 02 03 04
   ```
4. Rebroadcast it to all other connected TCP clients  

### ✔ Timestamp & Direction Field (per Appendix E)
- Frames originating from CAN: `R`
- Frames originating from TCP clients: `T`  
- Timestamps follow the exact formatting rules in the spec

### ✔ Multi-client Support
Any number of TCP clients may connect.  
All receive the CAN feed and see each other’s transmissions.

### ✔ Works on Home Assistant OS
- Uses `host_network: true`  
- Accesses SocketCAN without needing `/dev/can0`  
- Requires only Home Assistant’s standard base images

---

## 📡 How It Works

```
     CAN Bus  ←→  SocketCAN (can0)
                    ↓
         CAN RAW Gateway Add-on
                    ↓
         TCP Server at <host>:<port>
         (default 0.0.0.0:2598)
                    ↓
     Clients (SignalK, tools, etc.)
```

The add-on behaves like a Yacht Devices RAW bridge, meaning SignalK or any
software expecting the YD RAW protocol can connect without modification.

---

## 🔧 Installation

1. Create a GitHub repository for this add-on, e.g.:

   ```
   https://github.com/<your_username>/ha-addon-can-raw
   ```

2. Add the repository to Home Assistant:
   - **Settings → Add-ons → Add-on Store**
   - Top-right menu → **Repositories**
   - Enter your repository URL

3. Install **CAN RAW Gateway** from the list

4. Start the add-on

5. Configure your client (e.g., SignalK) to connect to:

   ```
   Host: homeassistant.local
   Port: 2598
   ```

---

## ⚙️ Configuration Options

Inside the add-on UI:

```yaml
can_interface: can0
listen_host: 0.0.0.0
listen_port: 2598
log_level: info
```

### Parameters

| Option          | Description                               | Default |
|-----------------|-------------------------------------------|---------|
| `can_interface` | SocketCAN interface name                  | `can0`  |
| `listen_host`   | TCP bind address                          | `0.0.0.0` |
| `listen_port`   | TCP port for RAW server                   | `2598`  |
| `log_level`     | Logging verbosity                         | `info`  |

---

## 🔌 Client Examples

### Connect using netcat
```
nc homeassistant.local 2598
```

### Sample output
```
12:41:23.105 R 09F805FD FF 00 00 00
12:41:23.421 R 19F51323 01 02 03 04
```

### Transmit a frame back to the CAN bus
```
19F51323 01 02 03 04
```

Add-on will echo:
```
12:41:30.882 T 19F51323 01 02 03 04
```

---

## 🛠 Notes

- The add-on **does not** perform fast-packet reassembly  
- Frames larger than 8 bytes appear as raw CAN fragments  
- Future versions may add optional fast-packet support

---

## 📄 Protocol Reference

Yacht Devices — NMEA 2000® Gateway YDEN-02 / YDNU-02 Manual  
**https://www.yachtd.com/downloads/ydnu02.pdf**  
See **Appendix E — Text Format of NMEA 2000 Messages**

---

## 🏁 Summary

This add-on turns your Home Assistant OS host into a **fully compatible Yacht
Devices RAW NMEA2000 TCP bridge**, enabling powerful integrations with SignalK
or custom marine software.


