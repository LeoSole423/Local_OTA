#!/usr/bin/env python3
import argparse
import os
import socket
import sys
import time
import subprocess
from typing import Optional, Tuple

DEFAULT_PORT = 3232
CHUNK_SIZE = 4096
SERVICE_TYPE = "_arduino._tcp.local."


def ensure_zeroconf():
    try:
        from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo
        return Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo
    except Exception:
        try:
            print("[INFO] Instalando dependencia 'zeroconf'...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "zeroconf"])  # noqa: S603,S607
            from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo
            return Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo
        except Exception as e:
            print(f"[WARN] No se pudo instalar/importar 'zeroconf': {e}")
            return None


def human_size(num_bytes: int) -> str:
    units = ['B','KB','MB','GB']
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024.0


def discover_esp32(timeout_s: float = 3.0) -> Optional[Tuple[str, int]]:
    z = ensure_zeroconf()
    if not z:
        return None
    Zeroconf, ServiceBrowser, ServiceStateChange, ServiceInfo = z

    found = {}

    class _Listener:
        def add_service(self, zeroconf, service_type, name):
            try:
                info = zeroconf.get_service_info(service_type, name, timeout=int(timeout_s*1000))
                if not info:
                    return
                # Prefer IPv4
                ip = None
                if info.addresses:
                    for addr in info.addresses:
                        if len(addr) == 4:
                            ip = socket.inet_ntoa(addr)
                            break
                    if not ip:
                        # fallback first address
                        ip = socket.inet_ntoa(info.addresses[0][:4])
                if not ip:
                    return
                props = {k.decode(): (v.decode() if isinstance(v, (bytes, bytearray)) else str(v)) for k, v in (info.properties or {}).items()}
                found[name] = (ip, info.port, props)
            except Exception:
                pass

        # Keep interface compatible though unused
        def remove_service(self, zeroconf, service_type, name):
            pass
        def update_service(self, zeroconf, service_type, name):
            pass

    zeroconf = Zeroconf()
    listener = _Listener()
    browser = ServiceBrowser(zeroconf, SERVICE_TYPE, listener=listener)

    # Esperar a que lleguen anuncios
    time.sleep(timeout_s)

    try:
        zeroconf.close()
    except Exception:
        pass

    if not found:
        return None

    # Preferir servicios con board=esp32
    preferred = None
    for name, (ip, port, props) in found.items():
        if props.get("board") == "esp32":
            preferred = (ip, port)
            break
    if preferred:
        return preferred

    # Tomar el primero
    name, (ip, port, _props) = next(iter(found.items()))
    return ip, port


def send_file(ip: str, port: int, file_path: str, retries: int = 5, retry_delay: float = 1.0) -> int:
    if not os.path.isfile(file_path):
        print(f"[ERROR] Archivo no encontrado: {file_path}", file=sys.stderr)
        return 2

    file_size = os.path.getsize(file_path)
    print(f"[INFO] Enviando '{file_path}' ({human_size(file_size)}) a {ip}:{port}")

    attempt = 0
    sock = None
    while attempt <= retries:
        try:
            sock = socket.create_connection((ip, port), timeout=10)
            break
        except Exception as e:
            if attempt == retries:
                print(f"[ERROR] No se pudo conectar a {ip}:{port} tras {retries+1} intentos: {e}", file=sys.stderr)
                return 3
            print(f"[WARN] Conexión fallida (intento {attempt+1}/{retries+1}): {e}. Reintentando en {retry_delay}s...")
            time.sleep(retry_delay)
            attempt += 1

    sent = 0
    start = time.time()
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                sock.sendall(chunk)
                sent += len(chunk)
                pct = (sent / file_size * 100.0) if file_size > 0 else 100.0
                sys.stdout.write(f"\r[INFO] Progreso: {pct:6.2f}% ({human_size(sent)}/{human_size(file_size)})")
                sys.stdout.flush()
        sys.stdout.write("\n")
        elapsed = max(time.time() - start, 1e-3)
        rate = sent / elapsed
        print(f"[OK] Envío completado: {human_size(sent)} en {elapsed:.2f}s ({human_size(rate)}/s)")
        print("[INFO] La ESP32 debería reiniciarse si la OTA fue exitosa.")
        return 0
    except KeyboardInterrupt:
        print("\n[ABORT] Cancelado por el usuario.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\n[ERROR] Falló el envío: {e}", file=sys.stderr)
        return 4
    finally:
        try:
            if sock:
                sock.shutdown(socket.SHUT_WR)
                sock.close()
        except Exception:
            pass


def guess_default_bin() -> str:
    # Por defecto, use el nombre de proyecto 'OTA' configurado en CMakeLists.txt
    # ESP-IDF produce build/<project>.bin
    candidate = os.path.join('build', 'OTA.bin')
    return candidate


def main():
    parser = argparse.ArgumentParser(description='Enviar firmware a ESP32 por OTA TCP (sin URL).')
    parser.add_argument('--ip', help='IP de la ESP32 (si no se indica, se intenta descubrir por mDNS)')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Puerto TCP del servidor OTA (por defecto {DEFAULT_PORT})')
    parser.add_argument('--file', default=guess_default_bin(), help='Ruta al .bin (por defecto build/OTA.bin)')
    parser.add_argument('--retries', type=int, default=5, help='Reintentos de conexión (por defecto 5)')
    parser.add_argument('--retry-delay', type=float, default=1.0, help='Segundos entre reintentos (por defecto 1.0)')
    parser.add_argument('--discovery-timeout', type=float, default=3.0, help='Tiempo de descubrimiento mDNS en segundos (por defecto 3.0)')

    args = parser.parse_args()

    ip = args.ip
    port = args.port

    if not ip:
        print("[INFO] Buscando ESP32 por mDNS (_arduino._tcp)...")
        discovered = discover_esp32(timeout_s=args.discovery_timeout)
        if discovered:
            ip, discovered_port = discovered
            if discovered_port:
                port = discovered_port
            print(f"[OK] Encontrado dispositivo en {ip}:{port}")
        else:
            print("[ERROR] No se encontró ningún dispositivo por mDNS. Indica --ip manualmente.", file=sys.stderr)
            sys.exit(5)

    sys.exit(send_file(ip, port, args.file, retries=args.retries, retry_delay=args.retry_delay))


if __name__ == '__main__':
    main()
