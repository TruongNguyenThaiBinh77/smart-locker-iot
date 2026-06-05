import http.server
import socketserver
import json
import threading

PORT = 8081

class MockHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if "/cabinets/config/" in self.path:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            # Response mock theo yêu cầu của USER
            response = {
              "cabinetId": "5157c039-64e6-40c2-9823-e56faf015c75",
              "cabinetCode": "cab-mock-1",
              "locationId": "148d9afc-9397-4b3b-9d39-0beeebde2c72",
              "mqttTopicPrefix": "cabinet/cab-mock-1",
              "heartbeatInterval": 60,
              "openDoorTimeout": 5,
              "ledIntensity": 80,
              "volumeLevel": 70,
              "isSynced": False, # Trigger auto-setup
              "lastSyncedAt": None,
              "mqttBrokerHost": "localhost", # Test local mqtt if available
              "mqttBrokerPort": 1883,
              "mqttUsername": "test_user",
              "mqttPassword": "test_password",
              "totalRows": 2,
              "totalColumns": 2, # Small layout for fast testing
              "isActive": True
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    with socketserver.TCPServer(("", PORT), MockHandler) as httpd:
        print(f"Mock Backend API running at http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()
