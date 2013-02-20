import socket

def gom_key_payload(remote_ip, params):
    return "Login,0,%s,%s,%s" % (params['uno'], remote_ip, params['uip'])

def gom_stream_key(remote_ip, payload):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((remote_ip, 63800))
    s.send(payload + "\n")
    data = s.recv(1024)
    s.close()
    return data[data.rfind(",")+1:-1]

