'''
Python 2 binary-string helpers for the PDF parser.

File bytes are kept as Latin-1 text so indexing, slicing, and concatenation
behave as they did when str and bytes were the same type. Call the helpers
below instead of hashlib, zlib, and struct so those stdlib functions can keep
returning bytes for other libraries.
'''

import binascii
import hashlib
import struct
import zlib

_struct_pack = struct.pack
_struct_unpack = struct.unpack
_zlib_compress = zlib.compress
_zlib_decompress = zlib.decompress


class Latin1File(object):
    '''Binary file whose reads are Latin-1 text, matching Python 2 str.'''

    def __init__(self, fp):
        self.fp = fp

    def read(self, n=-1):
        data = self.fp.read() if n is None or n < 0 else self.fp.read(n)
        if isinstance(data, bytes):
            return data.decode('latin-1')
        return data

    def readline(self, *args):
        data = self.fp.readline(*args)
        if isinstance(data, bytes):
            return data.decode('latin-1')
        return data

    def readlines(self, *args):
        return [line.decode('latin-1') if isinstance(line, bytes) else line
                for line in self.fp.readlines(*args)]

    def seek(self, *args):
        return self.fp.seek(*args)

    def tell(self):
        return self.fp.tell()

    def close(self):
        return self.fp.close()

    def __iter__(self):
        for line in self.fp:
            yield line.decode('latin-1') if isinstance(line, bytes) else line

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def to_bytes(data):
    if isinstance(data, str):
        return data.encode('latin-1')
    if isinstance(data, bytearray):
        return bytes(data)
    return data


def to_str(data):
    if isinstance(data, (bytes, bytearray)):
        return bytes(data).decode('latin-1')
    return data


def hexlify(data):
    '''Python 2 ``str.encode('hex')``: lowercase hex digits.'''
    return binascii.hexlify(to_bytes(data)).decode('ascii')


def unhexlify(data):
    '''Python 2 ``str.decode('hex')``: raw bytes as Latin-1 text.'''
    if isinstance(data, str):
        data = data.encode('ascii')
    return to_str(binascii.unhexlify(data))


class _Hash(object):
    def __init__(self, name, data=b'', usedforsecurity=True):
        self._h = hashlib.new(name, usedforsecurity=usedforsecurity)
        if data:
            self.update(data)

    def update(self, data):
        self._h.update(to_bytes(data))
        return self

    def digest(self):
        return to_str(self._h.digest())

    def hexdigest(self):
        return self._h.hexdigest()

    def copy(self):
        clone = _Hash(self._h.name)
        clone._h = self._h.copy()
        return clone


def md5(data=b'', *, usedforsecurity=True):
    return _Hash('md5', data, usedforsecurity)


def sha1(data=b'', *, usedforsecurity=True):
    return _Hash('sha1', data, usedforsecurity)


def sha256(data=b'', *, usedforsecurity=True):
    return _Hash('sha256', data, usedforsecurity)


def pack(fmt, *args):
    converted = []
    for arg in args:
        if isinstance(arg, str):
            converted.append(to_bytes(arg))
        else:
            converted.append(arg)
    return to_str(_struct_pack(fmt, *converted))


def unpack(fmt, data):
    return _struct_unpack(fmt, to_bytes(data))


def decompress(data, *args, **kwargs):
    return to_str(_zlib_decompress(to_bytes(data), *args, **kwargs))


def compress(data, *args, **kwargs):
    return to_str(_zlib_compress(to_bytes(data), *args, **kwargs))


def install():
    '''Patch struct and zlib for a process that still treats PDF bytes as text.

    Used by pdf2txt.py. The main analyzer calls the helpers directly so other
    libraries keep the normal bytes-returning stdlib functions.
    '''
    if not getattr(struct.pack, '_py3compat', False):
        struct.pack = pack
        struct.unpack = unpack
        pack._py3compat = True
        unpack._py3compat = True
    if not getattr(zlib.decompress, '_py3compat', False):
        zlib.decompress = decompress
        zlib.compress = compress
        decompress._py3compat = True
        compress._py3compat = True
