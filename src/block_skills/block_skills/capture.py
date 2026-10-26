"""Capture only the Gazebo window via X11; no camera, perception or extra packages.

Run in a subprocess so an X11 window disappearing cannot terminate a ROS node.
"""
import argparse
import ctypes as C
from pathlib import Path
import struct
import zlib


class Attributes(C.Structure):
    _fields_ = [(n, t) for n, t in [
        ('x', C.c_int), ('y', C.c_int), ('width', C.c_int), ('height', C.c_int),
        ('border_width', C.c_int), ('depth', C.c_int), ('visual', C.c_void_p), ('root', C.c_ulong),
        ('window_class', C.c_int), ('bit_gravity', C.c_int), ('win_gravity', C.c_int),
        ('backing_store', C.c_int), ('backing_planes', C.c_ulong), ('backing_pixel', C.c_ulong),
        ('save_under', C.c_int), ('colormap', C.c_ulong), ('map_installed', C.c_int), ('map_state', C.c_int),
        ('all_event_masks', C.c_long), ('your_event_mask', C.c_long), ('do_not_propagate_mask', C.c_long),
        ('override_redirect', C.c_int), ('screen', C.c_void_p)]]


class ClassHint(C.Structure):
    _fields_ = [('res_name', C.c_void_p), ('res_class', C.c_void_p)]


class XImage(C.Structure):
    _fields_ = [('width', C.c_int), ('height', C.c_int), ('xoffset', C.c_int), ('format', C.c_int),
                ('data', C.c_void_p), ('byte_order', C.c_int), ('bitmap_unit', C.c_int),
                ('bitmap_bit_order', C.c_int), ('bitmap_pad', C.c_int), ('depth', C.c_int),
                ('bytes_per_line', C.c_int), ('bits_per_pixel', C.c_int),
                ('red_mask', C.c_ulong), ('green_mask', C.c_ulong), ('blue_mask', C.c_ulong)]


def png_bytes(width, height, rgb):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data) & 0xffffffff)
    rows = b''.join(b'\0'+rgb[y*width*3:(y+1)*width*3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 3)) + chunk(b'IEND', b''))


def capture(output=None):
    x = C.CDLL('libX11.so.6')
    signatures = {
        'XOpenDisplay': ([C.c_char_p], C.c_void_p),
        'XDefaultRootWindow': ([C.c_void_p], C.c_ulong),
        'XQueryTree': ([C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                        C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)], C.c_int),
        'XGetWindowAttributes': ([C.c_void_p, C.c_ulong, C.POINTER(Attributes)], C.c_int),
        'XGetClassHint': ([C.c_void_p, C.c_ulong, C.POINTER(ClassHint)], C.c_int),
        'XFetchName': ([C.c_void_p, C.c_ulong, C.POINTER(C.c_void_p)], C.c_int),
        'XGetImage': ([C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_ulong, C.c_int], C.POINTER(XImage)),
        'XDestroyImage': ([C.POINTER(XImage)], C.c_int),
        'XFree': ([C.c_void_p], C.c_int), 'XCloseDisplay': ([C.c_void_p], C.c_int),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(x, name)
        fn.argtypes, fn.restype = args, result
    display = x.XOpenDisplay(None)
    if not display:
        raise RuntimeError('Cannot open X11 display; follow the README GUI Docker launch and Xauthority setup.')
    try:
        pending, candidates, visited = [x.XDefaultRootWindow(display)], [], set()
        while pending and len(visited) < 20000:
            window = pending.pop()
            if window in visited:
                continue
            visited.add(window)
            attrs, hint, name = Attributes(), ClassHint(), C.c_void_p()
            if not x.XGetWindowAttributes(display, window, C.byref(attrs)):
                continue
            title, classes = b'', []
            if x.XFetchName(display, window, C.byref(name)) and name:
                title = C.string_at(name)
                x.XFree(name)
            if x.XGetClassHint(display, window, C.byref(hint)):
                for ptr in [hint.res_name, hint.res_class]:
                    if ptr:
                        classes.append(C.string_at(ptr).lower())
                        x.XFree(ptr)
            if title == b'Gazebo' and b'gazebo' in classes and attrs.map_state == 2 and attrs.width >= 500 and attrs.height >= 300:
                candidates.append((attrs.width*attrs.height, window, attrs.width, attrs.height))
            root, parent, count = C.c_ulong(), C.c_ulong(), C.c_uint()
            children = C.POINTER(C.c_ulong)()
            if x.XQueryTree(display, window, C.byref(root), C.byref(parent), C.byref(children), C.byref(count)):
                if children:
                    pending.extend(children[i] for i in range(count.value))
                    x.XFree(children)
        if not candidates:
            raise RuntimeError('A visible Gazebo window was not found; screenshot evidence requires GUI mode.')
        _, window, width, height = max(candidates)
        if output is None:
            return width, height
        ptr = x.XGetImage(display, window, 0, 0, width, height, C.c_ulong(-1).value, 2)
        if not ptr:
            raise RuntimeError('Gazebo screenshot capture failed.')
        try:
            frame = ptr.contents
            if (frame.bits_per_pixel, frame.byte_order, frame.red_mask, frame.green_mask, frame.blue_mask) != (32, 0, 0xff0000, 0xff00, 0xff):
                raise RuntimeError('Unsupported X11 pixel format for screenshot evidence.')
            raw = C.string_at(frame.data, frame.bytes_per_line*height)
            rgb = bytearray(width*height*3)
            for row in range(height):
                data = raw[row*frame.bytes_per_line:row*frame.bytes_per_line+width*4]
                start, end = row*width*3, (row+1)*width*3
                rgb[start:end:3], rgb[start+1:end:3], rgb[start+2:end:3] = data[2::4], data[1::4], data[0::4]
            Path(output).write_bytes(png_bytes(width, height, rgb))
        finally:
            x.XDestroyImage(ptr)
        return width, height
    finally:
        x.XCloseDisplay(display)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    args = parser.parse_args()
    print(capture(args.output))
