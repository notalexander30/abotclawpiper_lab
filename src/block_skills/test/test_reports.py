import json
import struct
import zlib
from block_skills.capture import png_bytes
from block_skills.reports import write_report


def test_screenshot_encoder_is_a_real_png():
    data = png_bytes(2, 1, bytes([255, 0, 0, 0, 255, 0]))
    assert data[:8] == b'\x89PNG\r\n\x1a\n'
    offset, image = 8, b''
    while offset < len(data):
        length = struct.unpack('!I', data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]
        payload = data[offset+8:offset+8+length]
        crc = struct.unpack('!I', data[offset+8+length:offset+12+length])[0]
        assert crc == zlib.crc32(kind+payload) & 0xffffffff
        if kind == b'IDAT':
            image += payload
        offset += length+12
    assert zlib.decompress(image) == b'\0\xff\0\0\0\xff\0'


def test_report_is_persisted_atomically(tmp_path):
    path = tmp_path/'task'/'result.json'
    write_report(path, {'success': True, 'verified': True, 'already_complete': False})
    assert json.loads(path.read_text())['verified']
    assert not path.with_suffix('.tmp').exists()
