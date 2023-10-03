"""JSON Serialization Utilities."""
import base64
import datetime
import decimal
from decimal import Decimal
import json as stdjson
import uuid
from typing import Any, Callable, TypeVar


try:
    from django.utils.functional import Promise as DjangoPromise
except ImportError:  # pragma: no cover
    class DjangoPromise:
        """Dummy object."""

try:
    import json
    _json_extra_kwargs = {}

    class _DecodeError(Exception):
        pass
except ImportError:                 # pragma: no cover
    import simplejson as json
    from simplejson.decoder import JSONDecodeError as _DecodeError
    _json_extra_kwargs = {
        'use_decimal': False,
        'namedtuple_as_object': False,
    }


_encoder_cls = type(json._default_encoder)
_default_encoder = None   # ... set to JSONEncoder below.


class JSONEncoder(_encoder_cls):
    """Kombu custom json encoder."""

    def default(self, o,
                dates=(datetime.datetime, datetime.date),
                times=(datetime.time,),
                textual=(decimal.Decimal, uuid.UUID, DjangoPromise),
                isinstance=isinstance,
                datetime=datetime.datetime,
                text_t=str):
        reducer = getattr(o, '__json__', None)
        if reducer is not None:
            return reducer()
        else:
            if isinstance(o, dates):
                if not isinstance(o, datetime):
                    o = datetime(o.year, o.month, o.day, 0, 0, 0, 0)
                r = o.isoformat()
                if r.endswith("+00:00"):
                    r = r[:-6] + "Z"
                return r
            elif isinstance(o, times):
                return o.isoformat()
            elif isinstance(o, textual):
                return text_t(o)
            return super().default(o)


_default_encoder = JSONEncoder


def dumps(s, _dumps=json.dumps, cls=None, default_kwargs=None, **kwargs):
    """Serialize object to json string."""
    if not default_kwargs:
        default_kwargs = _json_extra_kwargs
    return _dumps(s, cls=cls or _default_encoder,
                  **dict(default_kwargs, **kwargs))


def object_hook(o: dict):
    """Hook function to perform custom deserialization."""
    if o.keys() == {"__type__", "__value__"}:
        decoder = _decoders.get(o["__type__"])
        if decoder:
            return decoder(o["__value__"])
        else:
            raise ValueError("Unsupported type", type, o)
    else:
        return o


def loads(s, _loads=json.loads, decode_bytes=True, object_hook=object_hook):
    """Deserialize json from string."""
    # None of the json implementations supports decoding from
    # a buffer/memoryview, or even reading from a stream
    #    (load is just loads(fp.read()))
    # but this is Python, we love copying strings, preferably many times
    # over.  Note that pickle does support buffer/memoryview
    # </rant>
    if isinstance(s, memoryview):
        s = s.tobytes().decode("utf-8")
    elif isinstance(s, bytearray):
        s = s.decode("utf-8")
    elif decode_bytes and isinstance(s, bytes):
        s = s.decode("utf-8")

    return _loads(s, object_hook=object_hook)


DecoderT = EncoderT = Callable[[Any], Any]
T = TypeVar("T")
EncodedT = TypeVar("EncodedT")


def register_type(
    t: type[T],
    marker: str,
    encoder: Callable[[T], EncodedT],
    decoder: Callable[[EncodedT], T],
):
    """Add support for serializing/deserializing native python type."""
    _encoders[t] = (marker, encoder)
    _decoders[marker] = decoder


_encoders: dict[type, tuple[str, EncoderT]] = {}
_decoders: dict[str, DecoderT] = {
    "bytes": lambda o: o.encode("utf-8"),
    "base64": lambda o: base64.b64decode(o.encode("utf-8")),
}

# NOTE: datetime should be registered before date,
# because datetime is also instance of date.
register_type(datetime, "datetime", datetime.datetime.isoformat, datetime.datetime.fromisoformat)
register_type(
    datetime.date,
    "date",
    lambda o: o.isoformat(),
    lambda o: datetime.datetime.fromisoformat(o).date(),
)
register_type(datetime.time, "time", lambda o: o.isoformat(), datetime.time.fromisoformat)
register_type(Decimal, "decimal", str, Decimal)
register_type(
    uuid.UUID,
    "uuid",
    lambda o: {"hex": o.hex},
    lambda o: uuid.UUID(**o),
)
