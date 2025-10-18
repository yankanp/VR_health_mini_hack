# server.py  --- simple HTTPS static server for WebXR
import http.server, ssl, socketserver, os

PORT = 8000
DIRECTORY = "."

os.chdir(DIRECTORY)
httpd = socketserver.TCPServer(("0.0.0.0", PORT), http.server.SimpleHTTPRequestHandler)

# 1️⃣ generate local certs once (mkcert localhost 192.168.x.x)
certfile = "csc.pem"
keyfile  = "csc-key.pem"

httpd.socket = ssl.wrap_socket(httpd.socket,
                               keyfile=keyfile,
                               certfile=certfile,
                               server_side=True)

print(f"✅ Serving HTTPS on 0.0.0.0:{PORT}")
httpd.serve_forever()
