# can analyser - inspired by cansniffer

## Sample usage:

```
python test.py -i can1 --canid-map can_names.csv --filter 021A06C0:1FF00000
```

## canid to name mapping

### RegEx expander template
```
$1;X?? ID:$2 LowPrio
$1;X?? ID:$2 S1 & S2
$1;X?? ID:$2 S3 & S4
$1;X?? ID:$2 S5 & S6
```

## Candump from hallway light on/off
  can1  0E622380   [8]  00 04 00 FF FF FF FF FF
  can1  00001808   [5]  08 0F 01 9A 90
  can1  00001C00   [5]  08 09 01 BD D3
  can1  00001A80   [5]  08 01 00 63 15
  can1  00001FC0   [5]  08 0B 00 43 F4
  can1  00001788   [5]  08 10 02 98 73
  can1  00000580   [5]  08 10 01 9C 18
  can1  00000B88   [5]  08 0F 00 FB 03
  can1  00000588   [5]  08 10 01 48 91
  can1  04001A80   [5]  01 53 E8 86 84
  can1  00002380   [5]  08 12 01 28 FC
  can1  04001A80   [5]  01 53 E8 86 04
  can1  021A06C0   [8]  00 00 00 00 00 00 00 00
  can1  00001808   [5]  08 0F 01 9A 90
  can1  0E622380   [8]  00 04 00 FF FF FF FF FF
  can1  00001C00   [5]  08 09 01 BD D3
  can1  00001A80   [5]  08 01 00 63 15
  can1  00001FC0   [5]  08 0B 00 43 F4
  can1  00001788   [5]  08 10 02 98 73
  can1  00000580   [5]  08 10 01 9C 18
  can1  00000B88   [5]  08 0F 00 FB 03
  can1  00000588   [5]  08 10 01 48 91
  can1  04001A80   [5]  01 53 E8 86 84
  can1  040806C0   [6]  01 53 E8 86 84 03
  can1  00002380   [5]  08 12 01 28 FC
  can1  00001808   [5]  08 0F 01 9A 90
  can1  0E622380   [8]  00 04 00 FF FF FF FF FF
  can1  04001A80   [5]  01 53 E8 86 04
  can1  00001C00   [5]  08 09 01 BD D3
  can1  021A06C0   [8]  0E 00 11 01 00 00 00 00
  can1  00001A80   [5]  08 01 00 63 15
  can1  00001FC0   [5]  08 0B 00 43 F4
  can1  00001788   [5]  08 10 02 98 73
  can1  00000580   [5]  08 10 01 9C 18
  can1  00000B88   [5]  08 0F 00 FB 03
  can1  00000588   [5]  08 10 01 48 91
  can1  00002380   [5]  08 12 01 28 FC
  can1  00001808   [5]  08 0F 01 9A 90
  can1  0E622380   [8]  00 04 00 FF FF FF FF FF
  can1  00001C00   [5]  08 09 01 BD D3
  can1  00001A80   [5]  08 01 00 63 15
  can1  00001FC0   [5]  08 0B 00 43 F4
  can1  00001788   [5]  08 10 02 98 73
  can1  00000580   [5]  08 10 01 9C 18