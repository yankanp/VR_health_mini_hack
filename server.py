# server.py — Capture Oculus screencast when VR user presses trigger, analyze with Gemini
import ssl, json, base64, time, threading, os, io, asyncio, requests
from PIL import ImageGrab
import http.server, socketserver, websockets

# ========== CONFIG ==========
PORT = 8000                    # HTTPS for Quest
WS_PORT = 8001                 # WebSocket for realtime control
API_KEY = ""  # 🔑 Replace with your Gemini API key
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
SAVE_DIR = "captures"
CAPTURE_REGION = None          # (x1, y1, x2, y2) for your cast window
os.makedirs(SAVE_DIR, exist_ok=True)
# ============================

clients = set()
latest_reply = "(waiting...)"

# --- Gemini helper ---
def analyze_image(b64img):
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": ("You are a human biology expert. Analyze the specific anatomical region highlighted by the VR user in this image. Provide a concise explanation of its relevance in human anatomy in one sentence."
)},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64img}},
                ]
            }
        ]
    }
    r = requests.post(
        GEMINI_URL + f"?key={API_KEY}",
        json=payload,
        headers={"Content-Type": "application/json"},
    )
    if r.status_code != 200:
        print("❌ Gemini API error:", r.text)
        return "(error)"
    response = r.json()
    return (
        response.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "(no response)")
    )

# --- Screenshot + Gemini pipeline ---
def take_screenshot_and_analyze():
    global latest_reply
    try:
        img = ImageGrab.grab(bbox=CAPTURE_REGION)
        if img.mode != "RGB":
            img = img.convert("RGB")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64img = base64.b64encode(buf.getvalue()).decode("utf-8")

        ts = time.strftime("%Y%m%d_%H%M%S")
        img_path = os.path.join(SAVE_DIR, f"capture_{ts}.jpg")
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(b64img))
        print(f"📸 Saved {img_path}")

        reply = analyze_image(b64img)
        latest_reply = reply
        print(f"🤖 Gemini: {reply}")
        return reply
    except Exception as e:
        print("❌ Error during capture:", e)
        return "(error)"

# --- WebSocket server ---
async def ws_handler(websocket):
    clients.add(websocket)
    await websocket.send(latest_reply)
    try:
        async for message in websocket:
            # Expecting message: "capture"
            if message.strip().lower() == "capture":
                print("🎮 Trigger received from Quest — capturing...")
                reply = take_screenshot_and_analyze()
                await broadcast(reply)
    finally:
        clients.remove(websocket)

async def broadcast(msg):
    if not clients:
        return
    await asyncio.gather(*[ws.send(msg) for ws in clients if ws.open])

async def ws_handler(websocket):
    clients.add(websocket)
    await websocket.send(latest_reply)
    try:
        async for message in websocket:
            if message.strip().lower() == "capture":
                print("🎮 Trigger capture (full view)")
                reply = take_screenshot_and_analyze()
                await broadcast(reply)
            elif message.strip().lower() == "capture_region":
                print("✏️ Region draw capture — cropping central area")
                reply = capture_and_analyze_region()
                await broadcast(reply)
    finally:
        clients.remove(websocket)

def capture_and_analyze_region():
    """Capture a zoomed central portion of the screen (simulating drawn region)"""
    global latest_reply
    try:
        img = ImageGrab.grab(bbox=CAPTURE_REGION)
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        crop_size = int(min(w, h) * 0.4)  # 40% center crop
        left = (w - crop_size) // 2
        top = (h - crop_size) // 2
        cropped = img.crop((left, top, left + crop_size, top + crop_size))
        buf = io.BytesIO()
        cropped.save(buf, format="JPEG", quality=85)
        b64img = base64.b64encode(buf.getvalue()).decode("utf-8")

        ts = time.strftime("%Y%m%d_%H%M%S")
        img_path = os.path.join(SAVE_DIR, f"region_{ts}.jpg")
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(b64img))
        print(f"🖊️ Saved region {img_path}")

        reply = analyze_image(b64img)
        latest_reply = f"{reply}"
        print(f"🤖 Gemini (region): {reply}")
        return latest_reply
    except Exception as e:
        print("❌ Error during region capture:", e)
        return "(error)"


# --- HTTPS static file server ---
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        return

def start_http():
    httpd = socketserver.TCPServer(("0.0.0.0", PORT), Handler)
    httpd.socket = ssl.wrap_socket(
        httpd.socket,
        keyfile="hotspot-key.pem",
        certfile="hotspot.pem",
        server_side=True,
    )
    print(f"✅ Serving HTTPS on port {PORT}")
    httpd.serve_forever()

# --- Startup ---
threading.Thread(target=start_http, daemon=True).start()

print("🌐 Starting WebSocket server (wss://)")

async def main():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile="hotspot.pem", keyfile="hotspot-key.pem")

    async with websockets.serve(ws_handler, "0.0.0.0", WS_PORT, ssl=ssl_context):
        print(f"✅ WebSocket server running on wss://0.0.0.0:{WS_PORT}")
        await asyncio.Future()  # run forever

asyncio.run(main())
