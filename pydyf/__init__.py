"""
A low-level PDF generator.

"""

import sys
import zlib
from codecs import BOM_UTF16_BE

VERSION = __version__ = '0.0.3'


def _to_bytes(item):
    """Convert item to bytes."""
    if isinstance(item, bytes):
        return item
    elif isinstance(item, Object):
        return item.data
    elif isinstance(item, float):
        if item.is_integer():
            return f'{int(item):d}'.encode('ascii')
        else:
            return f'{item:f}'.encode('ascii')
    elif isinstance(item, int):
        return f'{item:d}'.encode('ascii')
    return str(item).encode('ascii')


class Object:
    """Base class for PDF objects."""
    def __init__(self):
        #: Number of the object.
        self.number = None
        #: Position in the PDF of the object.
        self.offset = 0
        #: Version number of the object, non-negative.
        self.generation = 0
        #: Indicate if an object is used (``'n'``), or has been deleted
        #: and therefore is free (``'f'``).
        self.free = 'n'

    @property
    def indirect(self):
        """Indirect representation of an object."""
        return b'\n'.join((
            str(self.number).encode('ascii') + b' ' +
            str(self.generation).encode('ascii') + b' obj',
            self.data,
            b'endobj',
        ))

    @property
    def reference(self):
        """Object identifier."""
        return (
            str(self.number).encode('ascii') + b' ' +
            str(self.generation).encode('ascii') + b' R')

    @property
    def data(self):
        """Data contained in the object. Shall be defined in each subclass."""
        raise NotImplementedError()


class Dictionary(Object, dict):
    """PDF Dictionary object.

    Inherits from :class:`Object` and Python :obj:`dict`.

    """
    def __init__(self, values=None):
        Object.__init__(self)
        dict.__init__(self, values or {})

    @property
    def data(self):
        result = [b'<<']
        for key, value in self.items():
            result.append(b'/' + _to_bytes(key) + b' ' + _to_bytes(value))
        result.append(b'>>')
        return b'\n'.join(result)


class Stream(Object):
    """PDF Stream object.

    Inherits from :class:`Object`.

    """
    def __init__(self, stream=None, extra=None, compress=False):
        super().__init__()
        #: Python array of data composing stream.
        self.stream = stream or []
        #: Metadata containing at least the length of the Stream.
        self.extra = extra or {}
        #: Compress the stream data if set to ``True``. Default is ``False``.
        self.compress = compress

    def begin_text(self):
        """Begin a text object."""
        self.stream.append(b'BT')

    def clip(self, even_odd=False):
        """Modify current clipping path by intersecting it with current path.

        Use the nonzero winding number rule to determine which regions lie
        inside the clipping path by default.

        Use the even-odd rule if ``even_odd`` set to ``True``.

        """
        self.stream.append(b'W*' if even_odd else b'W')

    def close(self):
        """Close current subpath.

        Append a straight line segment from the current point to the starting
        point of the subpath.

        """
        self.stream.append(b'h')

    def color_space(self, space, stroke=False):
        """Set the nonstroking color space.

        If stroke is set to ``True``, set the stroking color space instead.

        """
        self.stream.append(
            b'/' + _to_bytes(space) + b' ' + (b'CS' if stroke else b'cs'))

    def curve_to(self, x1, y1, x2, y2, x3, y3):
        """Add cubic Bézier curve to current path.

        The curve shall extend from ``(x3, y3)`` using ``(x1, y1)`` and ``(x2,
        y2)`` as the Bézier control points.

        """
        self.stream.append(b' '.join((
            _to_bytes(x1), _to_bytes(y1),
            _to_bytes(x2), _to_bytes(y2),
            _to_bytes(x3), _to_bytes(y3), b'c')))

    def curve_start_to(self, x2, y2, x3, y3):
        """Add cubic Bézier curve to current path

        The curve shall extend to ``(x3, y3)`` using the current point and
        ``(x2, y2)`` as the Bézier control points.

        """
        self.stream.append(b' '.join((
            _to_bytes(x2), _to_bytes(y2),
            _to_bytes(x3), _to_bytes(y3), b'v')))

    def curve_end_to(self, x1, y1, x3, y3):
        """Add cubic Bézier curve to current path

        The curve shall extend to ``(x3, y3)`` using `(x1, y1)`` and ``(x3,
        y3)`` as the Bézier control points.

        """
        self.stream.append(b' '.join((
            _to_bytes(x1), _to_bytes(y1),
            _to_bytes(x3), _to_bytes(y3), b'y')))

    def draw_x_object(self, reference):
        """Draw object given by reference."""
        self.stream.append(b'/' + _to_bytes(reference) + b' Do')

    def end(self):
        """End path without filling or stroking."""
        self.stream.append(b'n')

    def end_text(self):
        """End text object."""
        self.stream.append(b'ET')

    def fill(self, even_odd=False):
        """Fill path using nonzero winding rule.

        Use even-odd rule if ``even_odd`` is set to ``True``.

        """
        self.stream.append(b'f*' if even_odd else b'f')

    def fill_and_stroke(self, even_odd=False):
        """Fill and stroke path usign nonzero winding rule.

        Use even-odd rule if ``even_odd`` is set to ``True``.

        """
        self.stream.append(b'B*' if even_odd else b'B')

    def fill_stroke_and_close(self, even_odd=False):
        """Fill, stroke and close path using nonzero winding rule.

        Use even-odd rule if ``even_odd`` is set to ``True``.

        """
        self.stream.append(b'b*' if even_odd else b'b')

    def line_to(self, x, y):
        """Add line from current point to point ``(x, y)``."""
        self.stream.append(b' '.join((_to_bytes(x), _to_bytes(y), b'l')))

    def move_to(self, x, y):
        """Begin new subpath by moving current point to ``(x, y)``."""
        self.stream.append(b' '.join((_to_bytes(x), _to_bytes(y), b'm')))

    def shading(self, name):
        """Paint shape and color shading using shading dictionary ``name``."""
        self.stream.append(b'/' + _to_bytes(name) + b' sh')

    def pop_state(self):
        """Restore graphic state."""
        self.stream.append(b'Q')

    def push_state(self):
        """Save graphic state."""
        self.stream.append(b'q')

    def rectangle(self, x, y, width, height):
        """Add rectangle to current path as complete subpath.

        ``(x, y)`` is the lower-left corner and width and height the
        dimensions.

        """
        self.stream.append(b' '.join((
            _to_bytes(x), _to_bytes(y),
            _to_bytes(width), _to_bytes(height), b're')))

    def set_color_rgb(self, r, g, b, stroke=False):
        """Set RGB color for nonstroking operations.

        Set RGB color for stroking operations instead if ``stroke`` is set to
        ``True``.

        """
        self.stream.append(b' '.join((
            _to_bytes(r), _to_bytes(g), _to_bytes(b),
            (b'RG' if stroke else b'rg'))))

    def set_color_special(self, name, stroke=False):
        """Set color for nonstroking operations.

        Set color for stroking operation if ``stroke`` is set to ``True``.

        """
        self.stream.append(
            b'/' + _to_bytes(name) + b' ' + (b'SCN' if stroke else b'scn'))

    def set_dash(self, dash_array, dash_phase):
        """Set dash line pattern.

        :param dash_array: Dash pattern.
        :type dash_array: :term:`iterable`
        :param dash_phase: Start of dash phase.
        :type dash_phase: :obj:`int`

        """
        self.stream.append(b' '.join((
            Array(dash_array).data, _to_bytes(dash_phase), b'd')))

    def set_font_size(self, font, size):
        """Set font name and size."""
        self.stream.append(
            b'/' + _to_bytes(font) + b' ' + _to_bytes(size) + b' Tf')

    def set_text_rendering(self, mode):
        """Set text rendering mode."""
        self.stream.append(_to_bytes(mode) + b' Tr')

    def set_line_cap(self, line_cap):
        """Set line cap style."""
        self.stream.append(_to_bytes(line_cap) + b' J')

    def set_line_join(self, line_join):
        """Set line join style."""
        self.stream.append(_to_bytes(line_join) + b' j')

    def set_line_width(self, width):
        """Set line width."""
        self.stream.append(_to_bytes(width) + b' w')

    def set_miter_limit(self, miter_limit):
        """Set miter limit."""
        self.stream.append(_to_bytes(miter_limit) + b' M')

    def set_state(self, state_name):
        """Set specified parameters in graphic state.

        :param state_name: Name of the graphic state.

        """
        self.stream.append(b'/' + _to_bytes(state_name) + b' gs')

    def show_text(self, text):
        """Show text."""
        self.stream.append(b'[' + _to_bytes(text) + b'] TJ')

    def stroke(self):
        """Stroke path."""
        self.stream.append(b'S')

    def stroke_and_close(self):
        """Stroke and close path."""
        self.stream.append(b's')

    def text_matrix(self, a, b, c, d, e, f):
        """Set text matrix and text line matrix.

        :param a: Top left number in the matrix.
        :type a: :obj:`int` or :obj:`float`
        :param b: Top middle number in the matrix.
        :type b: :obj:`int` or :obj:`float`
        :param c: Middle left number in the matrix.
        :type c: :obj:`int` or :obj:`float`
        :param d: Middle middle number in the matrix.
        :type d: :obj:`int` or :obj:`float`
        :param e: Bottom left number in the matrix.
        :type e: :obj:`int` or :obj:`float`
        :param f: Bottom middle number in the matrix.
        :type f: :obj:`int` or :obj:`float`

        """
        self.stream.append(b' '.join((
            _to_bytes(a), _to_bytes(b), _to_bytes(c),
            _to_bytes(d), _to_bytes(e), _to_bytes(f), b'Tm')))

    def transform(self, a, b, c, d, e, f):
        """Modify current transformation matrix.

        :param a: Top left number in the matrix.
        :type a: :obj:`int` or :obj:`float`
        :param b: Top middle number in the matrix.
        :type b: :obj:`int` or :obj:`float`
        :param c: Middle left number in the matrix.
        :type c: :obj:`int` or :obj:`float`
        :param d: Middle middle number in the matrix.
        :type d: :obj:`int` or :obj:`float`
        :param e: Bottom left number in the matrix.
        :type e: :obj:`int` or :obj:`float`
        :param f: Bottom middle number in the matrix.
        :type f: :obj:`int` or :obj:`float`

        """
        self.stream.append(b' '.join((
            _to_bytes(a), _to_bytes(b), _to_bytes(c),
            _to_bytes(d), _to_bytes(e), _to_bytes(f), b'cm')))

    @property
    def data(self):
        stream = b'\n'.join(_to_bytes(item) for item in self.stream)
        extra = Dictionary(self.extra.copy())
        if self.compress:
            extra['Filter'] = '/FlateDecode'
            compressobj = zlib.compressobj()
            stream = compressobj.compress(stream)
            stream += compressobj.flush()
        extra['Length'] = len(stream)
        return b'\n'.join((extra.data, b'stream', stream, b'endstream'))


class String(Object):
    """PDF String object.

    Inherits from :class:`Object`.

    """
    def __init__(self, string=''):
        super().__init__()
        #: Unicode string.
        self.string = string

    @property
    def data(self):
        try:
            return b'(' + _to_bytes(self.string) + b')'
        except UnicodeEncodeError:
            encoded = BOM_UTF16_BE + str(self.string).encode('utf-16-be')
            return b'<' + encoded.hex().encode('ascii') + b'>'


class Array(Object, list):
    """PDF Array object.

    Inherits from :class:`Object` and Python :obj:`list`.

    """
    def __init__(self, array=None):
        Object.__init__(self)
        list.__init__(self, array or [])

    @property
    def data(self):
        result = [b'[']
        for child in self:
            result.append(_to_bytes(child))
        result.append(b']')
        return b' '.join(result)


class PDF:
    """PDF document."""
    def __init__(self):
        #: Python :obj:`list` containing the PDF’s objects.
        self.objects = []

        zero_object = Object()
        zero_object.generation = 65535
        zero_object.free = 'f'
        self.add_object(zero_object)

        #: PDF :class:`Dictionary` containing the PDF’s pages.
        self.pages = Dictionary({
            'Type': '/Pages',
            'Kids': Array([]),
            'Count': 0,
        })
        self.add_object(self.pages)

        #: PDF :class:`Dictionary` containing the PDF’s metadata.
        self.info = Dictionary({})
        self.add_object(self.info)

        #: PDF :class:`Dictionary` containing references to the other objects.
        self.catalog = Dictionary({
            'Type': '/Catalog',
            'Pages': self.pages.reference,
        })
        self.add_object(self.catalog)

        #: Current position in the PDF.
        self.current_position = 0
        #: Position of the cross reference table.
        self.xref_position = None

    def add_page(self, page):
        """Add page to the PDF.

        :param page: New page.
        :type page: :class:`Dictionary`

        """
        self.pages['Count'] += 1
        self.add_object(page)
        self.pages['Kids'].extend([page.number, 0, 'R'])

    def add_object(self, object_):
        """Add object to the PDF."""
        object_.number = len(self.objects)
        self.objects.append(object_)

    def write_line(self, content, output):
        """Write line to output.

        :param content: Content to write.
        :type content: :obj:`bytes`
        :param output: Output stream.
        :type output: :term:`file object`

        """
        self.current_position += len(content) + 1
        output.write(content + b'\n')

    def write_object(self, object_, output):
        """Write object to output."""
        for line in object_.data.split(b'\n'):
            self.write_line(line, output)

    def write_header(self, output):
        """Write PDF header to output."""
        self.write_line(b'%PDF-1.7', output)
        self.write_line(b'%\xf0\x9f\x96\xa4', output)

    def write_body(self, output):
        """Write all non-free PDF objects to output."""
        for object_ in self.objects:
            if object_.free == 'f':
                continue
            object_.offset = self.current_position
            self.write_line(object_.indirect, output)

    def write_cross_reference_table(self, output):
        """Write cross reference table to output."""
        self.xref_position = self.current_position
        self.write_line(b'xref', output)
        self.write_line(f'0 {len(self.objects)}'.encode('ascii'), output)
        for object_ in self.objects:
            self.write_line(
                (f'{object_.offset:010} {object_.generation:05} '
                 f'{object_.free} ').encode('ascii'), output
            )

    def write_trailer(self, output):
        """Write trailer to output."""
        self.write_line(b'trailer', output)
        self.write_object(Dictionary({
            'Size': len(self.objects),
            'Root': self.catalog.reference,
            'Info': self.info.reference,
        }), output)
        self.write_line(b'startxref', output)
        self.write_line(str(self.xref_position).encode('ascii'), output)
        self.write_line(b'%%EOF', output)

    def write(self, output=sys.stdout):
        """Write PDF to output.

        :param output: Output stream, :obj:`sys.stdout` by default.
        :type output: :term:`file object`

        """
        self.write_header(output)
        self.write_body(output)
        self.write_cross_reference_table(output)
        self.write_trailer(output)
