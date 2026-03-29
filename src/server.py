from code_pack import decode_pack, encode_pack, Packetinfo

import socket 
import os 
import argparse
import sys
import time 
#constantes
MAX_PACKET_SIZE = 1040
MAX_PAYLOAD_LEN = 1024
MAX_SEQNUM_MOD = 2048
EPSILON_RTO = 10
def compute_timestamp():
    """retourne le timestamp actuel en ms sur 32 bits"""
    return int(time.time()*1000) % 4294967296

def parse_args():
    """parse les arguments précisés à l'exécution du server"""
    parser = argparse.ArgumentParser(description="Server")
    parser.add_argument("hostname")
    # par défault root="."
    parser.add_argument("--root",type= str, default=".")
    parser.add_argument("port", type=int)

    args = parser.parse_args()
    hostname = args.hostname
    port = args.port
    root = args.root

    return hostname,port,root


def server(hostname,port,root):
    sessions = {}  # {addr: Session}
    with socket.socket(family = socket.AF_INET6, type = socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.01)
        sock.bind((hostname, port))
        while True:
            #si après 1sec rien n'est arrivé, le serveur check les timeout des sessions et retransmet les paquets nécessaires
            try:
                packet_,addr_client = sock.recvfrom(MAX_PACKET_SIZE)
            except socket.timeout:
                #check timeout des paquets
                for addr, session in list(sessions.items()):
                    session.send_payloads()
                continue

            packet = decode_pack(packet_)
            if packet is None:
                continue
            """
            print("\nserver recieve : \n"
                f"ptype : {packet.ptype}\n" 
                f"window : {packet.window}\n" 
                f"seqnum : {packet.seqnum}\n" 
                f"payload_len : {packet.length}\n" 
                f"payload : {packet.payload}\n" 
                f"timestamp : {packet.timestamp}\n" 
                )
            """
            
            #data
            if(packet.ptype == 1):
                #nouvelle session
                if addr_client not in sessions:
                    
                    # envoi d'un ack de reception du packet
                    timestamp = compute_timestamp()
                    ack = encode_pack(
                        ptype=2,
                        seqnum=packet.seqnum+1,
                        window=0,
                        payload=b"",
                        timestamp=packet.timestamp
                    )
                    sock.sendto(ack, addr_client)
                    """
                    print("\nserver send : \n"
                        f"ptype : {2}\n" 
                        f"window : {0}\n" 
                        f"seqnum : {packet.seqnum+1}\n" 
                        f"payload_len : {0}\n" 
                        f"payload : {b""}\n" 
                        f"timestamp : {timestamp}\n" 
                        )
                    """
                    
                    sessions[addr_client] = Session(packet, root, sock, addr_client)
                    # envoi des paquets
                
            #ack
            if (packet.ptype == 2 or packet.ptype == 3):
                if addr_client in sessions:
                    # le packet est géré par la session correspondante
                    sessions[addr_client].receive(packet)
                    # si la session est terminée, on la supprime
                    if(sessions[addr_client].isdone()):
                        #envoi du packet de fin
                        if (not sessions[addr_client].last_is_sent):
                            timestamp = compute_timestamp()
                            packetinfo = Packetinfo(ptype = 1,window = 0, seqnum = packet.seqnum,  length = 0,payload = b"", timestamp = timestamp, rto = 2000)
                            sessions[addr_client].packets[packet.seqnum] = packetinfo
                            
                            end_transfer_pack = encode_pack(
                                ptype=1,
                                seqnum=packet.seqnum,
                                window=0,
                                payload=b"",
                                timestamp=timestamp
                                )
                            sock.sendto(end_transfer_pack, addr_client)
                            sessions[addr_client].last_is_sent = True
                            
                        else:
                            del sessions[addr_client]

            



    pass

class Session:

    def __init__(self, packet, root, sock, addr):
        #on extrait le chemin du fichier à envoyer à partir du payload de la requete http
        http_instruct = packet.payload.decode('ascii')
        path = http_instruct.split(" ")[1].lstrip("/")
        full_path = os.path.join(root, path)

        try: 
            with open(full_path, "rb") as f:
                self.data = f.read()
        except FileNotFoundError:
            self.data = b""        
        
        self.timeout = 2 #timeout de départ en s
        self.addr = addr
        self.sock = sock
        self.done = False #session terminée ?
        self.last_is_sent = False
        
        self.base_seqnum = 0 #seqnum du prochain paquet à envoyer
        self.window_size = packet.window # nombre de paquets que le client peut recevoir en même temps
        self.packets = split_data(self.data)
        self.last_send_check = 0
        
        self.rtt = []
        self.rtt_len = 4    
        
        self.send_payloads_init()

    def client_space(self,seqnum):
        return self.packets[seqnum].timestamp == None
    
    def send_payloads(self):
        now = compute_timestamp()
        
        if now - self.last_send_check < 5:
            return 
        self.last_send_check = now
        
        j = 0
        
        #envoi seulement packet dans la window
        for offset in range(self.window_size):
            
            seqnum = (self.base_seqnum + offset) % MAX_SEQNUM_MOD
            if seqnum not in self.packets:
                continue
            
            if j >= self.window_size:
                break
            
            #envoi des packets qui entrent dans la fenetre
            timestamp = compute_timestamp()
            if self.client_space(seqnum):
                self.packets[seqnum].timestamp = timestamp
                packet = encode_pack(
                    ptype=1,
                    seqnum=seqnum,
                    window=0,
                    payload=self.packets[seqnum].payload,
                    timestamp=timestamp
                )
                self.sock.sendto(packet, self.addr)
                j += 1
                continue
            
            if  timestamp - self.packets[seqnum].timestamp  > self.packets[seqnum].rto:
                self.packets[seqnum].timestamp = timestamp
                self.packets[seqnum].rto = min(self.packets[seqnum].rto * 2, 60000) # exponential backoff du rto, max 60s
                packet = encode_pack(
                    ptype=1,
                    seqnum=seqnum,
                    window=0,
                    payload=self.packets[seqnum].payload,
                    timestamp=timestamp
                )
                self.sock.sendto(packet, self.addr)
                """
                print("\nserver send : \n"
                    f"ptype : {1}\n" 
                    f"window : {0}\n" 
                    f"seqnum : {seqnum}\n" 
                    f"payload_len : {len(self.packets[seqnum].payload)}\n" 
                    f"payload : {self.packets[seqnum].payload}\n" 
                    f"timestamp : {timestamp}\n" 
                    )
                """
                j += 1

    def send_payloads_init(self):
        
        j = 0
        for offset in range(self.window_size):
            
            seqnum = (self.base_seqnum + offset) % MAX_SEQNUM_MOD
            
            if seqnum not in self.packets:
                continue

            if j >= self.window_size:
                break
            timestamp = compute_timestamp()
            
            self.packets[seqnum].timestamp = timestamp
            packet = encode_pack(
                ptype=1,
                seqnum=seqnum,
                window=0,
                payload=self.packets[seqnum].payload,
                timestamp=timestamp
            )
            self.sock.sendto(packet, self.addr)
            """
            print("\nserver send : \n"
                f"ptype : {1}\n" 
                f"window : {0}\n" 
                f"seqnum : {seqnum}\n" 
                f"payload_len : {len(self.packets[seqnum].payload)}\n" 
                f"payload : {self.packets[seqnum].payload}\n" 
                f"timestamp : {timestamp}\n" 
                )
            """
            j += 1

    def ack_is_valid(self, ack_seqnum):
        d = (ack_seqnum - self.base_seqnum) % MAX_SEQNUM_MOD
        return d <= self.window_size
    
    def receive(self, packet):
        """
        if not self.ack_is_valid(packet.seqnum):
            return
        """
        # Supprimer les payloads acquittés et avancer la fenêtre
    
        
        # nombre de paquets acquittés cumulativement
        acked_count = (packet.seqnum - self.base_seqnum) % MAX_SEQNUM_MOD

        
        # si ACK dupliqué (aucune avancée)
        if acked_count == 0:
            self.window_size = packet.window
            return

        # on ne supprime pas plus que la fenêtre courante
        if acked_count > self.window_size:
            return
        
        for k in range(acked_count):
            seq = (self.base_seqnum + k) % MAX_SEQNUM_MOD
            if seq in self.packets:
                del self.packets[seq]
                
        # update les rto des packet non recu

        self.base_seqnum = packet.seqnum
        self.window_size = packet.window
        
        
        if not self.isdone():
            self.send_payloads()
        else:
            self.done = True
        
            
    def isdone(self):
        """la session est terminée si tous les payloads ont été acquittés"""
        return len(self.packets) == 0  
    
     
def split_data(data):
    """divise les données en blocs de taille maximale MAX_PAYLOAD_LEN et retourne un dictionnaire {seqnum: packet}"""
    """le dernier bloc est un bloc de taille 0 pour signaler la fin du transfert"""
    packets = {}
    n = 0
    for i in range(0, len(data), MAX_PAYLOAD_LEN):
        #timestamp = compute_timestamp()
        packets[n] = Packetinfo(ptype = 1,window = 0, seqnum = n,  length = len(data[i:i + MAX_PAYLOAD_LEN]),payload = data[i:i + MAX_PAYLOAD_LEN], timestamp = None, rto = 2000)
        n = (n+1) % MAX_SEQNUM_MOD
        
    #bloc de fin de transfert
    #packets[n] = Packetinfo(ptype = 1,window = 0, seqnum = n,  length = 0,payload = b"", timestamp = None, rto = 2000)

    return packets

if __name__ == "__main__":
    hostname, port, root = parse_args()
    server(hostname, port, root)