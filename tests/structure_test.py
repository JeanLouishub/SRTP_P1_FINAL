import socket 
import os 
import argparse
import sys
import time 
import struct
import zlib
import copy

# Add src directory to path
src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
sys.path.insert(0, src_path)

from code_pack import *
from client import *
from server import *

#class PacketinfoWrong(Packetinfo):
#    
#    def __init__(self, ptype, window, seqnum, length=0, payload=b'', timestamp=0, rto=4000):
#        super().__init__(ptype, window, seqnum, length, payload, timestamp, rto)
#        
#    def encode_pack(self):
        #construction "header" sur 32 bits
#        header = (
#            (self.ptype << 30)| #bit shift de 30 vers la gauche pour avoir les 2 MSB a ptype 
#            (self.window << 24) | #bit shift de (32 - 2 - 6 = 24) 
#            (self.length << 11) | #bit shift de (32 - 2 - 6 - 12 = 13)
#            (self.seqnum)) #dernier 11 bits du header
#        
#        header_pack: bytes = struct.pack("!I",header) #!I pour network order unsigned int
#        timestamp_pack: bytes = struct.pack("!I",self.timestamp)
#        
#        CRC1 = zlib.crc32(header_pack + timestamp_pack) #checksum du header 
#        crc1_pack: bytes = struct.pack("!I",CRC1)
#        
#        packet: bytes = header_pack + timestamp_pack + crc1_pack
#        
#        if self.payload: #payload doit etre packed par utilisateur!
#            CRC2 = zlib.crc32(self.payload)
#            crc2_pack: bytes = struct.pack("!I",CRC2) #checksum du payload 
#            packet += self.payload + crc2_pack
#        
#        return packet

##########################################################
# tests code_pack 

def test_encode_decode():
    p = Packetinfo(1, 5, 10, payload=b"abc", timestamp=100)

    encoded = p.encode_pack()
    decoded = decode_pack(encoded)

    assert decoded.payload == b"abc",'encode_decode fail'

def test_decode_corrupCR():
    pheader = Packetinfo(1, 5, 10, payload=b"abc", timestamp=100)
    ppayload = copy.deepcopy(pheader)
    #CR1
    encoded = bytearray(pheader.encode_pack())
    encoded[0] ^= 0xFF  # corrompre le header
        
    decoded = decode_pack(bytes(encoded))
    assert decoded is None,'decode_corrupCR1 fail'
    #CR2
    encoded = bytearray(ppayload.encode_pack())
    encoded[-5] ^= 0xFF  # corrompre le payload 

    decoded = decode_pack(bytes(encoded))
    assert decoded is None,'decode_corrupCR2 fail'

def test_rto_decrement():
    p = Packetinfo(1, 1, 1, rto=1000)

    p.decremente_rto(500)
    assert p.rto == 500,'rto_decrement fail'

    p.decremente_rto(600)
    assert p.rto == 0,'rto_decrement ground 0 fail'

def test_retransmit():
    p = Packetinfo(1, 1, 1, rto=0)
    assert p.retransmit_pack() is True,'retransmit fail '

##########################################################
# tests protocol 

def test_encode_decode_valid_packet():
    packet = encode_pack(1, 5, 10, b"BARB35lesang", 1234)

    decoded = decode_pack(packet)

    assert decoded is not None,'encode_decode_valid_packet fail'
    assert decoded.ptype == 1,'encode_decode_valid_packet ptype fail'
    assert decoded.window == 5,'encode_decode_valid_packet window fail'
    assert decoded.seqnum == 10,'encode_decode_valid_packet seqnum fail'
    assert decoded.payload == b"BARB35lesang",'encode_decode_valid_packet payload fail'
    assert decoded.timestamp == 1234,'encode_decode_valid_packet timestamp fail'
    assert decoded.length == len(b"BARB35lesang"),'encode_decode_valid_packet length fail'

def test_invalid_ptype():
    packet = encode_pack(5, 5, 10, b"test")
    assert packet is None,'invalid ptype fail'

def test_invalid_seqnum():
    packet = encode_pack(1, 5, 2048, b"test")
    assert packet is None,'invalid seqnum fail'
    packet = encode_pack(1, 5, -1000, b"test")
    assert packet is None,'invalid negative seqnum fail'

def test_seqnum_limit():
    packet = encode_pack(1, 2, 2047, b"ok")
    decoded = decode_pack(packet)
    assert decoded.seqnum == 2047,'seqnum limit fail'

def test_payload_limit():
    payload = b"a" * 1025
    packet = encode_pack(1, 5, 1, payload)
    assert packet is None,'payload limit fail'

def test_zero_payload():
    packet = encode_pack(1, 3, 1, b"", 42)
    decoded = decode_pack(packet)

    assert decoded.length == 0,'zero payload length fail'
    assert decoded.payload == b'','zero payload content fail'

def test_window_bounds():
    packet = encode_pack(1, 63, 5, b"ok")
    decoded = decode_pack(packet)
    assert decoded.window == 63,'window upper bound fail'

def test_invalid_window():
    packet = encode_pack(1, 64, 5, b"ok")
    assert packet is None,'invalid window fail'
    packet = encode_pack(1, -5, 5, b"ok")
    assert packet is None,'invalid window neg fail'

def test_truncated_payload():
    payload = b"hello"
    packet = encode_pack(1, 55, 1, payload)
    truncated = packet[:-6]
    decoded = decode_pack(truncated)
    assert decoded is None,'test_truncated_payload fail'

##########################################################
# tests client

def test_packet_not_received():
    window = Window(5, "tmp.bin")
    p0 = Packetinfo(1,5,0,payload=b"abc")
    p2 = Packetinfo(1,5,2,payload=b"def")

    window.add_packet(p0)
    assert window.base_seqnum == 1,'test_packet_not_received fail'

    window.add_packet(p2)
    assert window.base_seqnum == 1,'test_packet_not_received base_seqnum fail'
    assert 2 in window.packets,'test_packet_not_received sr fail'

    window.file.close()
    os.remove("tmp.bin")

def test_packet_out_of_order():
    window = Window(5, "tmp.bin")

    p1 = Packetinfo(1,5,1,payload=b"abc")
    result = window.add_packet(p1)

    assert result is True,'test_packet_out_of_order fail'
    assert 1 in window.packets,'test_packet_out_of_order sr fail'

    window.file.close()
    os.remove("tmp.bin")

def test_packet_outside_window():
    window = Window(1, "tmp.bin")

    p1 = Packetinfo(1,5,0,payload=b"a")
    p2 = Packetinfo(1,5,2,payload=b"b")

    window.add_packet(p1)
    assert window.base_seqnum == 1,'test_packet_outside_window fail'

    result = window.add_packet(p2)
    assert result is False,'test_packet_outside_window fail'

    window.file.close()
    os.remove("tmp.bin")

def test_empty_payload_end_transfer():
    window = Window(5,"tmp.bin")
    p = Packetinfo(1,5,0,payload=b"")

    window.add_packet(p)

    assert window.file_written is True,'test_empty_payload_end_transfer fail'
    assert window.base_seqnum == 1,'test_empty_payload_end_transfer base_seqnum fail'
    assert len(window.packets) == 0,'test_empty_payload_end_transfer packets fail'
    window.file.close()
    os.remove("tmp.bin")


def test_corrupted_packet():
    packet = encode_pack(1,5,0,b"abc")

    corrupted = bytearray(packet)
    corrupted[3] ^= 0xFF

    decoded = decode_pack(bytes(corrupted))

    assert decoded is None,'test_corrupted_packet fail'


def test_truncated_packet():
    packet = encode_pack(1,5,0,b"abc")
    truncated = packet[:-8]
    decoded = decode_pack(truncated)
    assert decoded is None,'test_truncated_packet fail'

##########################################################
# tests server 


def test_split_data(): # à faire sur les packet type 3 quand implémenter
    data = b"a"*3000
    result = split_data(data)

    assert len(result) == 3,'test_split_data fail'
    assert len(result[0].payload) == 1024,'test_split_data part 1 fail'
    assert len(result[1].payload) == 1024,'test_split_data part 2 fail'
    assert len(result[2].payload) == 952,'test_split_data part 3 fail'
    #assert len(result[3].payload) == 0,'test_split_data part 4 fail'

def test_latency_computation():
    t1 = compute_timestamp()
    time.sleep(0.1)
    t2 = compute_timestamp()
    diff = abs(t2-t1)

    assert diff > 0,'test_latency_computation fail'

if __name__ == "__main__":
    test_encode_decode()
    test_decode_corrupCR()
    test_rto_decrement()
    test_retransmit()
    test_encode_decode_valid_packet()
    test_invalid_ptype()
    test_invalid_seqnum()
    test_seqnum_limit()
    test_payload_limit()
    test_zero_payload()
    test_window_bounds()
    test_invalid_window()
    test_truncated_payload()
    test_packet_not_received()
    test_packet_out_of_order()
    test_packet_outside_window()
    test_empty_payload_end_transfer()
    test_corrupted_packet()
    test_truncated_packet()
    test_split_data()
    test_latency_computation()