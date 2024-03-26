import socket

data = (
    b"\x02"  # STX
    b"\xfe"  # ID
    b"\x84\x87"  # Call to dispatching, Type 0x84 grpup 0x87
    b"\x9c\x00"  # Length: 156 , total data is 159 correct?
    b"\x00\x00"  # Destination address
    b"\x00"  # Destination port
    b"\x01\x00"  # Source address
    b"\x00"  # Source port
    b"\x1b\x0f\x00"  # This is length of structure but correct is 141 and only 2. But 141 is forbidden ans is replaced with
    ## Correct unescaped: \x8d\x00 = 141
    b"\x02"  # structure version
    b"@\xa4\x94\xdd\x96\xce\x1b\x1b\xb7\x19Ad\xd5jo\x80\xa4"  # Guid. What is it for? Reveresed byte order?  Not same as docs.
    b"0000000000000001\x00"  # station ID
    b"#\x82\x08p\x10cCx\x00\x00"  # ID of SIM-card, Imsi, not iccid: '23820870106343780000'
    b"\x03Y\x07s g\x06Q"  # ID of modem, ''0359077320670651''
    b"\x00"  # Protocol 0 = ELGAS2
    b"\x01\x00"  # address1, ushort = 16 bit? little endian?
    b"\x00"  # address2 uchar = 8 bit?
    b"\x1f"  # gprs signal strength = 31
    b"\x06\x00\x00\x00"  # number of gprs connections, ulong = 6, little endian
    b"\x9e+b-"  # Time of last gprs connection
    b"\x00\x00\x00\x00"  # number of gprs errors
    b"\x00\x00\x00\x00"  # time of last gprs error
    b"\x01\x00\x00\x00"  # number of resets
    b"\x91\xca\xaf,"  # time of last reset
    b"\x98\x00\x00\x00"  # number of tcp data (packets or bytes?)
    b"\x00\x00\x00\x00"  # number of all data, what is this?
    ## version 2 data
    b",@\x8c\x8c"  # serial number of device? how to parse?
    b"\nGJK"  # ip address ?  10.71.74.75
    b"\x1d*b-"  # time of last module error
    b"\x01"  # last modem error
    b"z\xfe"  # modem battery capacity  How to parse?
    b"\xcd\x01"  # modem battery voltage, how to parse?
    # What is the rest?
    b"01.000\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"  # Firmware
    b"}"  # LRC
    b"C"  # Checksum
    b"+"  # DRC
    b"\r"  # ETX
)


with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.connect(("localhost", 8649))
    sock.sendall(data)
    response = sock.recv(1024)
    print(f"Received: {response!r}")
    response = sock.recv(1024)
    print(f"Received: {response!r}")
