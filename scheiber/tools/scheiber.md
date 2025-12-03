



## filter out all noisy canids
```
python3 analyser.py -i can1 --canid-map can_names.csv --filter 0E602380~1FFFFFFF --filter 02040580~1FFFFFFF --filter 02040588~1FFFFFFF --filter 02060580~1FFFFFFF --filter 02060588~1FFFFFFF --filter 0E642380~1FFFFFFF --filter 0E642380~1FFFFFFF --filter 0E662380~1FFFFFFF --filter 02040B88~1FFFFFFF --filter 02060B88~1FFFFFFF --filter 0E622380~1FFFFFFF
```

candump equivalent:
```
candump can1 | grep -v -E "0E602380|02040580|02040588|02060580|02060588|0E642380|0E662380|02040B88|02060B88"
```
filter out all Low-Prio Bloc9 messages: 00000600~1FFFFF00


# Bloc 9 experiments

The Bloc9 has a Dip-Switch to set an ID.

When the ID on the Bloc 9 is set as 0001 using the DIP-Switches, the actual ID is 1000 in binary aka 8.

We found that ID in a message from that Bloc 9 at Bit 4 to Bit 7 in the 32Bit CAN ID (Bit 1 being the least siginificant bit).

## Only messages with CAN-ID 021A06C0 - X27 ID:8  (1000) ??

### Sequence
- Turn everything off
- Records with
  `python3 analyser.py -i can1 --canid-map can_names.csv --filter 021A06C0:1FFFFFFF`
- Turn on after the other on S1 - S6

### Result
```
|  Δt(ms) |  CAN ID  | Name              | Len | Data
--------------------------------------------------------------------------------
|   703.9 | 021A06C0 | X27 ID:8  (1000)  |   8 | 00 00 01 01 00 00 01 01
|         |          |                   |     |                   ^^ ^^ 
|         |          |                20:40:29 | 00 00 01 01 00 00 00 00
|         |          |                20:40:30 | 00 00 00 00 00 00 00 00
|         |          |                20:40:35 | 00 00 01 01 00 00 00 00
|         |          |                20:40:35 | 00 00 01 01 00 00 01 01
```

### Conclusions
- the sender id 021A06C0 does not correspond to the Bloc 9, just to S5 & S6 of that Bloc 9
- there are 2 bits that change per state change of one output


## Filter for all CAN IDs with the ID 8 (binary 1000) at bit 3 to 7 in the CAN-ID

### ID Filter:
```
   02        1A       06       C0  
00000010  00011010 00000110 11000000
                             ^^^^
Mask:                             
00010000  00000000 00000000 01111000
   10        00       00       78
```

Command:
```
python3 analyser.py -i can1 --canid-map can_names.csv --filter 021A06C0:10000078
```

## Result
```
|  Δt(ms) |  CAN ID  | Name              | Len | Data
--------------------------------------------------------------------------------
|   998.2 | 000006C0 |                   |   5 | 08 11 00 A8 22            #<= Repeats on a regular basis
|  1001.1 | 00001FC0 |                   |   5 | 08 0B 00 43 F4            #<= Repeats on a regular basis
|   301.1 | 021606C0 |                   |   8 | 00 00 00 00 00 00 00 00
|   400.9 | 021806C0 |                   |   8 | 00 00 00 00 00 00 00 00
|   300.4 | 021A06C0 | X27 ID:8  (1000)  |   8 | 00 00 01 01 00 00 01 01
```

### Conclusion, we identified messages for all six switches PLUS DIMMER!
```
|  Δt(ms) |  CAN ID  | Name                  | Len | Data
--------------------------------------------------------------------------------
|   998.1 | 000006C0 | X27 ID:8 ??? LowPrio  |   5 | 08 11 00 A8 22
|         |          |                       |     | 
|  1000.7 | 00001FC0 | X27 ID:8 ??? LowPrio  |   5 | 08 0B 00 43 F4
|         |          |                       |     | 
|  5611.9 | 021606C0 | X27 ID:8 S1 & S2      |   8 | 00 00 00 00 00 00 00 00
|         |          |                       |     |                   ^^ ^^ 
|  5400.8 | 021806C0 | X27 ID:8 S3 & S4      |   8 | 00 00 00 00 00 00 00 00
|         |          |                       |     |                   ^^ ^^ 
|   109.7 | 021A06C0 | X27 ID:8 S5 & S6      |   8 | 53 00 11 01 00 00 01 01
|         |          |                       |     |             ^^    ^^ 
```
First four bytes are for control of lower light and the second four for control of higher light.

## X28 ID 9

```
python3 analyser.py -i can1 --canid-map can_names.csv --filter 021A06C8:10000078
```

```
|  Δt(ms) |  CAN ID  | Name                  | Len | Data
--------------------------------------------------------------------------------
|   997.0 | 000006C8 |                       |   5 | 08 11 00 E5 DA
|         |          |                       |     | 
|   399.7 | 021606C8 |                       |   8 | 00 00 00 00 00 00 00 00
|         |          |                       |     |                   ^^ ^^ 
|   301.0 | 021806C8 |                       |   8 | 00 00 00 00 00 00 00 00
|         |          |                       |     |                   ^^ ^^ 
|   299.8 | 021A06C8 | X28 ID:9  (1001) ??   |   8 | 00 00 00 00 00 00 00 00
|         |          |                       |     |                   ^^ ^^
```


candump can1 without all the noise and without the low-prio Bloc9-messages ():
```
candump can1 | grep -v -E "0E602380|02040580|02040588|02060580|02060588|0E642380|0E662380|02040B88|02060B88|000006[0-9A-Fa-f]{2}"

```