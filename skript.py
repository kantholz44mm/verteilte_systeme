#!/usr/bin/env python3
import socket
import time
import threading

# =========================
# 🔧 KONFIGURATION
# =========================

PROTOCOL = "udp"        # "udp" oder "tcp"

# Server
BIND_IP = "127.0.0.1"
BIND_PORT = 8090

# Client
TARGET_IP = "127.0.0.1"
TARGET_PORT = 8080

MESSAGE = "123456"
WAIT_FOR_REPLY = True

SEND_INTERVAL = 1.0     # Sekunden
SEND_COUNT = 10         # 0 = unendlich

TIMEOUT = 5.0

# =========================


# =========================
# 📊 STATISTIK
# =========================

rtt_values = []


def print_stats():
    if not rtt_values:
        print("Keine RTT Daten vorhanden.")
        return

    avg = sum(rtt_values) / len(rtt_values)
    min_rtt = min(rtt_values)
    max_rtt = max(rtt_values)

    print("\n===== RTT STATISTIK =====")
    print(f"Anzahl: {len(rtt_values)}")
    print(f"Durchschnitt: {avg:.3f} ms")
    print(f"Minimum:      {min_rtt:.3f} ms")
    print(f"Maximum:      {max_rtt:.3f} ms")
    print("=========================\n")


# =========================
# 🧵 SERVER
# =========================

def udp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((BIND_IP, BIND_PORT))
    print(f"[UDP SERVER] Lauscht auf {BIND_IP}:{BIND_PORT}")

    while True:
        data, addr = sock.recvfrom(65535)
        recv_time = time.perf_counter()

        text = data.decode("utf-8", errors="replace")
        print(f"[UDP SERVER] Von {addr}: {text}")
        print(f"[UDP SERVER] Zeit: {recv_time:.9f}")

        if WAIT_FOR_REPLY:
            sock.sendto(data, addr)


def tcp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((BIND_IP, BIND_PORT))
    sock.listen(5)
    print(f"[TCP SERVER] Lauscht auf {BIND_IP}:{BIND_PORT}")

    while True:
        conn, addr = sock.accept()
        recv_time = time.perf_counter()
        print(f"[TCP SERVER] Verbindung von {addr}")

        with conn:
            data = conn.recv(65535)
            text = data.decode("utf-8", errors="replace")

            print(f"[TCP SERVER] Empfangen: {text}")
            print(f"[TCP SERVER] Zeit: {recv_time:.9f}")

            if WAIT_FOR_REPLY:
                conn.sendall(data)


# =========================
# 🧵 CLIENT
# =========================

def udp_client():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT)

    count = 0

    while True:
        if SEND_COUNT != 0 and count >= SEND_COUNT:
            print("[UDP CLIENT] Fertig.")
            print_stats()
            break

        payload = MESSAGE.encode("utf-8")
        start = time.perf_counter()

        sock.sendto(payload, (TARGET_IP, TARGET_PORT))
        print(f"[UDP CLIENT] Gesendet ({count+1}): {MESSAGE}")

        if WAIT_FOR_REPLY:
            try:
                data, addr = sock.recvfrom(65535)
                end = time.perf_counter()
                rtt = (end - start) * 1000

                rtt_values.append(rtt)

                print(f"[UDP CLIENT] Antwort: {data.decode()}")
                print(f"[UDP CLIENT] RTT: {rtt:.3f} ms")

            except socket.timeout:
                print("[UDP CLIENT] Timeout")

        count += 1
        time.sleep(SEND_INTERVAL)


def tcp_client():
    count = 0

    while True:
        if SEND_COUNT != 0 and count >= SEND_COUNT:
            print("[TCP CLIENT] Fertig.")
            print_stats()
            break

        payload = MESSAGE.encode("utf-8")
        start = time.perf_counter()

        try:
            with socket.create_connection((TARGET_IP, TARGET_PORT), timeout=TIMEOUT) as sock:
                sock.sendall(payload)
                print(f"[TCP CLIENT] Gesendet ({count+1}): {MESSAGE}")

                if WAIT_FOR_REPLY:
                    data = sock.recv(65535)
                    end = time.perf_counter()
                    rtt = (end - start) * 1000

                    rtt_values.append(rtt)

                    print(f"[TCP CLIENT] Antwort: {data.decode()}")
                    print(f"[TCP CLIENT] RTT: {rtt:.3f} ms")

        except Exception as e:
            print(f"[TCP CLIENT] Fehler: {e}")

        count += 1
        time.sleep(SEND_INTERVAL)


# =========================
# 🚀 START
# =========================

if __name__ == "__main__":
    print("Starte Server + Client gleichzeitig...")
    print(f"PROTOCOL={PROTOCOL}, SEND_COUNT={SEND_COUNT}")

    if PROTOCOL == "udp":
        server_thread = threading.Thread(target=udp_server, daemon=True)
        client_thread = threading.Thread(target=udp_client, daemon=True)
    else:
        server_thread = threading.Thread(target=tcp_server, daemon=True)
        client_thread = threading.Thread(target=tcp_client, daemon=True)

    server_thread.start()
    client_thread.start()

    while True:
        time.sleep(1)