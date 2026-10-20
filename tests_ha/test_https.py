"""Real local TLS transport through HA's shared sessions, with no committed key material."""

import ssl
from datetime import UTC, datetime

import pytest
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from custom_components.isapi_vision.api import CameraCertificateError
from custom_components.isapi_vision.client import make_client


@pytest.mark.enable_socket
@pytest.mark.parametrize("verify", [True, False])
async def test_shared_session_respects_certificate_setting(hass, aiohttp_server, tmp_path, verify):
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
    schemes = []

    async def device(request):
        schemes.append(request.scheme)
        return web.Response(
            text="<DeviceInfo><serialNumber>TEST-TLS</serialNumber></DeviceInfo>", content_type="application/xml"
        )

    app = web.Application()
    app.router.add_get("/ISAPI/System/deviceInfo", device)
    server = await aiohttp_server(app, ssl=context)
    client = make_client(
        hass,
        {
            "host": "127.0.0.1",
            "username": "synthetic-account",
            "password": "synthetic-password",
            "port": server.port,
            "use_ssl": True,
            "verify_ssl": verify,
            "channel": 1,
        },
    )
    if verify:
        with pytest.raises(CameraCertificateError):
            await client.device_info()
        assert schemes == []
    else:
        assert (await client.device_info())["serialNumber"] == "TEST-TLS"
        assert schemes == ["https"]
