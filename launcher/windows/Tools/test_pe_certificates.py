import struct
import tempfile
import unittest
from pathlib import Path

from pe_certificates import validate


class CertificateTableTests(unittest.TestCase):
    def test_valid_unsigned_and_signed_headers_are_preserved(self):
        for offset, size in ((0, 0), (512, 16)):
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "module.dll"
                data = self.image(offset, size)
                path.write_bytes(data)
                validate(path)
                self.assertEqual(path.read_bytes(), data)

    def test_truncated_or_unaligned_certificate_tables_are_refused(self):
        for offset, size in ((528, 16), (513, 8), (512, 0)):
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "module.dll"
                path.write_bytes(self.image(offset, size))
                with self.assertRaisesRegex(ValueError, "certificate table"):
                    validate(path)

    @staticmethod
    def image(offset, size):
        data = bytearray(528)
        data[:2] = b"MZ"
        struct.pack_into("<I", data, 60, 128)
        data[128:132] = b"PE\0\0"
        struct.pack_into("<H", data, 152, 0x20b)
        struct.pack_into("<II", data, 152 + 112 + 32, offset, size)
        return data
