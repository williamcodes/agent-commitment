"""wire package. See SPEC.md."""

from wire.codec import (
    CodecError,
    decode,
    decode_stream,
    dump_text,
    encode,
    encode_stream,
    filter_sensor,
    merge,
    record_count,
)

__all__ = [
    "encode",
    "decode",
    "encode_stream",
    "decode_stream",
    "record_count",
    "dump_text",
    "filter_sensor",
    "merge",
    "CodecError",
]
