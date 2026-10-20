"""Real local TLS transport through HA's shared sessions, with no committed key material."""

import asyncio
import ssl
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from custom_components.isapi_vision.api import CameraCertificateError
from custom_components.isapi_vision.client import make_client


@pytest.mark.enable_socket
@pytest.mark.parametrize("verify", [True, False])
async def test_shared_session_respects_certificate_setting(hass, tmp_path, verify):
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-camera.invalid")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2020, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2120, 1, 1, tzinfo=UTC))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("test-camera.invalid")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "certificate.pem", tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    key_path.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    tls_versions = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/ISAPI/System/deviceInfo"
            tls_versions.append(self.connection.version())
            payload = b"<DeviceInfo><serialNumber>TEST-TLS</serialNumber></DeviceInfo>"
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    # Isolate the test server from HA's event loop. A client's intentional certificate
    # rejection is handled by the server's socket accept path, not as an HA background error.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    client = make_client(
        hass,
        {
            "host": "127.0.0.1",
            "username": "synthetic-account",
            "password": "synthetic-password",
            "port": server.server_port,
            "use_ssl": True,
            "verify_ssl": verify,
            "channel": 1,
        },
    )
    try:
        if verify:
            with pytest.raises(CameraCertificateError):
                await client.device_info()
            assert tls_versions == []
        else:
            assert (await client.device_info())["serialNumber"] == "TEST-TLS"
            assert len(tls_versions) == 1 and tls_versions[0].startswith("TLS")
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
