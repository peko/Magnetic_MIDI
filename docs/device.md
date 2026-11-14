# CIDOO C80 — USB/HID

```

Bus 006 Device 010: ID 2e3c:c368  CIDOO C80
Negotiated speed: High Speed (480Mbps)
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0 [unknown]
  bDeviceSubClass         0 [unknown]
  bDeviceProtocol         0 
  bMaxPacketSize0        64
  idVendor           0x2e3c 
  idProduct          0xc368 CIDOO C80
  bcdDevice            2.00
  iManufacturer           0 
  iProduct                2 CIDOO C80
  iSerial                 0 
  bNumConfigurations      1
  Configuration Descriptor:
    bLength                 9
    bDescriptorType         2
    wTotalLength       0x005b
    bNumInterfaces          3
    bConfigurationValue     1
    iConfiguration          0 
    bmAttributes         0xa0
      (Bus Powered)
      Remote Wakeup
    MaxPower              500mA
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        0
      bAlternateSetting       0
      bNumEndpoints           1
      bInterfaceClass         3 Human Interface Device
      bInterfaceSubClass      1 Boot Interface Subclass
      bInterfaceProtocol      1 Keyboard
      iInterface              0 
        HID Device Descriptor:
          bLength                 9
          bDescriptorType        33
          bcdHID               1.10
          bCountryCode            0 Not supported
          bNumDescriptors         1
          bDescriptorType        34 Report
          wDescriptorLength      65
          Report Descriptors: 
            ** UNAVAILABLE **
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x82  EP 2 IN
        bmAttributes            3
          Transfer Type            Interrupt
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0008  1x 8 bytes
        bInterval               1
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        1
      bAlternateSetting       0
      bNumEndpoints           1
      bInterfaceClass         3 Human Interface Device
      bInterfaceSubClass      0 [unknown]
      bInterfaceProtocol      0 
      iInterface              0 
        HID Device Descriptor:
          bLength                 9
          bDescriptorType        33
          bcdHID               1.10
          bCountryCode            0 Not supported
          bNumDescriptors         1
          bDescriptorType        34 Report
          wDescriptorLength     143
          Report Descriptors: 
            ** UNAVAILABLE **
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x83  EP 3 IN
        bmAttributes            3
          Transfer Type            Interrupt
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0020  1x 32 bytes
        bInterval               1
    Interface Descriptor:
      bLength                 9
      bDescriptorType         4
      bInterfaceNumber        2
      bAlternateSetting       0
      bNumEndpoints           2
      bInterfaceClass         3 Human Interface Device
      bInterfaceSubClass      0 [unknown]
      bInterfaceProtocol      0 
      iInterface              0 
        HID Device Descriptor:
          bLength                 9
          bDescriptorType        33
          bcdHID               1.10
          bCountryCode            0 Not supported
          bNumDescriptors         1
          bDescriptorType        34 Report
          wDescriptorLength      32
          Report Descriptors: 
            ** UNAVAILABLE **
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x84  EP 4 IN
        bmAttributes            3
          Transfer Type            Interrupt
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0040  1x 64 bytes
        bInterval               1
      Endpoint Descriptor:
        bLength                 7
        bDescriptorType         5
        bEndpointAddress     0x05  EP 5 OUT
        bmAttributes            3
          Transfer Type            Interrupt
          Synch Type               None
          Usage Type               Data
        wMaxPacketSize     0x0040  1x 64 bytes
        bInterval               1
```

## hidraw4 report descriptor
```
DRIVER=hid-generic
HID_ID=0003:00002E3C:0000C368
HID_NAME=CIDOO C80
HID_PHYS=usb-0000:e6:00.3-1/input0
HID_UNIQ=
MODALIAS=hid:b0003g0001v00002E3Cp0000C368
00000000: 0501 0906 a101 0507 19e0 29e7 1500 2501  ..........)...%.
00000010: 7501 9508 8102 9501 7508 8101 9505 7501  u.......u.....u.
00000020: 0508 1901 2905 9102 9501 7503 9101 9506  ....).....u.....
00000030: 7508 1500 26ff 0005 0719 002a 9700 8100  u...&......*....
00000040: c0                                       .
```

## hidraw5 report descriptor
```
DRIVER=hid-generic
HID_ID=0003:00002E3C:0000C368
HID_NAME=CIDOO C80
HID_PHYS=usb-0000:e6:00.3-1/input1
HID_UNIQ=
MODALIAS=hid:b0003g0001v00002E3Cp0000C368
00000000: 0501 0902 a101 8502 0901 a100 0509 1901  ................
00000010: 2905 1500 2501 7501 9505 8102 7503 9501  )...%.u.....u...
00000020: 8101 0501 0930 0931 1601 8026 ff7f 7510  .....0.1...&..u.
00000030: 9502 8106 0938 1581 257f 7508 9501 8106  .....8..%.u.....
00000040: c0c0 050c 0901 a101 8503 1900 2a3c 0215  ............*<..
00000050: 0026 3c02 9501 7510 8100 c005 0109 80a1  .&<...u.........
00000060: 0185 0419 8129 8315 0025 0175 0195 0381  .....)...%.u....
00000070: 0295 0581 01c0 0501 0906 a101 8505 0507  ................
00000080: 7501 95a0 1500 2501 1900 299f 8102 c0    u.....%...)....
```

## hidraw7 report descriptor
```
DRIVER=hid-generic
HID_ID=0003:00002E3C:0000C368
HID_NAME=CIDOO C80
HID_PHYS=usb-0000:e6:00.3-1/input2
HID_UNIQ=
MODALIAS=hid:b0003g0001v00002E3Cp0000C368
00000000: 061b ff09 91a1 0185 0119 002a ff00 1500  ...........*....
00000010: 26ff 0075 0895 3f81 0219 0029 ff91 02c0  &..u..?....)....
```
