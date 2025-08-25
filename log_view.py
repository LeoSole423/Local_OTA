#!/usr/bin/env python3
import argparse
import socket
import sys
import time
import subprocess
from typing import Optional, Tuple

DEFAULT_PORT = 3333
SERVICE_TYPE = "_arduino._tcp.local."  # reutilizamos el anuncio OTA para obtener la IP


def ensure_zeroconf():
    try:
        from zeroconf import Zeroconf, ServiceBrowser
        return Zeroconf, ServiceBrowser
    except Exception:
        try:
            print("[INFO] Instalando dependencia 'zeroconf'...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "zeroconf"])  # noqa: S603,S607
            from zeroconf import Zeroconf, ServiceBrowser
            return Zeroconf, ServiceBrowser
        except Exception as e:
            print(f"[WARN] No se pudo instalar/importar 'zeroconf': {e}")
            return None


def discover_ip(timeout_s: float = 3.0) -> Optional[str]:
    z = ensure_zeroconf()
    if not z:
        return None
    Zeroconf, ServiceBrowser = z

    found_ip: Optional[str] = None

    class _Listener:
        def add_service(self, zeroconf, service_type, name):
            nonlocal found_ip
            try:
                info = zeroconf.get_service_info(service_type, name, timeout=int(timeout_s*1000))
                if not info:
                    return
                # Preferir IPv4
                ip = None
                if info.addresses:
                    for addr in info.addresses:
                        if len(addr) == 4:
                            ip = socket.inet_ntoa(addr)
                            break
                    if not ip:
                        ip = socket.inet_ntoa(info.addresses[0][:4])
                if ip and not found_ip:
                    found_ip = ip
            except Exception:
                pass

        def remove_service(self, zeroconf, service_type, name):
            pass

        def update_service(self, zeroconf, service_type, name):
            pass

    zeroconf = Zeroconf()
    listener = _Listener()
    browser = ServiceBrowser(zeroconf, SERVICE_TYPE, listener=listener)

    # Esperar anuncios
    time.sleep(timeout_s)

    try:
        zeroconf.close()
    except Exception:
        pass

    return found_ip


def stream_logs(ip: str, port: int):
    print(f"[INFO] Conectando a {ip}:{port} (CTRL+C para salir)")
    try:
        with socket.create_connection((ip, port), timeout=10) as sock:
            sock.settimeout(5)
            buffer = b""
            while True:
                try:
                    data = sock.recv(4096)
                    if not data:
                        print("\n[WARN] Conexión cerrada por el remoto.")
                        break
                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        try:
                            print(line.decode(errors="ignore"))
                        except Exception:
                            # fallback si hay caracteres no imprimibles
                            print(repr(line))
                except socket.timeout:
                    continue
    except KeyboardInterrupt:
        print("\n[ABORT] Cancelado por el usuario.")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar o leer: {e}", file=sys.stderr)
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Ver logs de ESP32 por TCP")
    parser.add_argument('--ip', help='IP de la ESP32 (si no se indica, se intenta descubrir por mDNS)')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help=f'Puerto de logs (por defecto {DEFAULT_PORT})')
    parser.add_argument('--discovery-timeout', type=float, default=3.0, help='Tiempo de descubrimiento mDNS en segundos (por defecto 3.0)')
    args = parser.parse_args()

    ip = args.ip
    if not ip:
        print("[INFO] Buscando ESP32 por mDNS (_arduino._tcp)...")
        ip = discover_ip(timeout_s=args.discovery_timeout)
        if not ip:
            print("[ERROR] No se encontró ningún dispositivo por mDNS. Indica --ip manualmente.", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] Encontrado dispositivo en {ip}")

    stream_logs(ip, args.port)


if __name__ == '__main__':
    main()
