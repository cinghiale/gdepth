#!/usr/bin/env python

def buffer_to_int2(buffer):
    return ord(buffer[0]) << 8 | ord(buffer[1])

def buffer_to_int4(buffer):
    return ord(buffer[0]) << 24 | ord(buffer[1]) << 16 | ord(buffer[2]) << 8 | ord(buffer[3])

def find_markers(blob):
    maybe = False
    for ix, byte in enumerate(blob):
        if byte == '\xff':
            maybe = True
        elif byte == '\x00':
            maybe = False
        elif maybe:
            yield ord(byte), ix+1
            maybe = False

def decode_xmp(buffer):
    namespace = None
    packet = None
    for ix, byte in enumerate(buffer):
        if byte == '\x00':
            namespace = buffer[:ix]
            break
    packet = buffer[len(namespace)+1:]
    return namespace, packet

def decode_extended_xml_packet(buffer):
    guid = buffer[:32]
    length = buffer_to_int4(buffer[32:36])
    offset = buffer_to_int4(buffer[36:40])
    packet = buffer[40:]
    return guid, length, offset, packet

def find_app_markers(blob):
    for marker_type, position in find_markers(blob):
        if 0xe0 <= marker_type <= 0xef:
            length = buffer_to_int2(blob[position:position+2])
            yield marker_type - 0xe0, position+2, length-2

def find_xmp_markers(blob):
    for app_marker, position, length in find_app_markers(blob):
        if app_marker == 1:
            namespace, packet = decode_xmp(blob[position:position+length])
            if namespace == 'http://ns.adobe.com/xap/1.0/':
                yield 'standard', packet
            elif namespace == 'http://ns.adobe.com/xmp/extension/':
                yield 'extended', decode_extended_xml_packet(packet)

def xmp_sections(blob):
    standard = None
    extended = []
    for section_type, value in find_xmp_markers(blob):
        if section_type == 'standard':
            standard = value
        else:
            guid, length, offset, packet = value
            extended.append((offset, packet))

    if extended:
        extended.sort()
        extended = ''.join([ x[1] for x in extended ])
    else:
        extended = None

    return standard, extended

import xml.etree.ElementTree as ET
class FieldParser(object):
    def __call__(self, name, value):
        try:
            method = getattr(self, '_' + name.lower())
        except AttributeError:
            return value
        else:
            return method(value)

    def _float(self, value):
        return float(value)

    def _base64(self, value):
        return value.decode('base64')

class GDepthFieldParser(FieldParser):
    _near = FieldParser._float
    _far = FieldParser._float
    _imagewidth = FieldParser._float
    _imageheight = FieldParser._float
    _data = FieldParser._base64

class GImageFieldParser(FieldParser):
    _data = FieldParser._base64

class GFocusFieldParser(FieldParser):
    pass

class GoogleDepthmap(object):
    DEPTH_NS = '{http://ns.google.com/photos/1.0/depthmap/}'
    FOCUS_NS = '{http://ns.google.com/photos/1.0/focus/}'
    IMAGE_NS = '{http://ns.google.com/photos/1.0/image/}'
    RDF_NS = '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}'

    def __init__(self, *xmp):
        self.depth = {}
        self.focus = {}
        self.image = {}

        xmp = filter(None, xmp)
        root = ET.fromstring(self.merge_xmp(*xmp))
        for description in root.iter(self.RDF_NS + 'Description'):
            self.analyze_description(description)

    def merge_xmp(self, *xmp):
        return '<root>' + ''.join(xmp) + '</root>'


    def analyze_description(self, description):
        depth_parser = GDepthFieldParser()
        focus_parser = GFocusFieldParser()
        image_parser = GImageFieldParser()
        for key, value in description.attrib.items():
            if key.startswith(self.DEPTH_NS):
                name = key[len(self.DEPTH_NS):]
                self.depth[name] = depth_parser(name, value)
            elif key.startswith(self.FOCUS_NS):
                name = key[len(self.FOCUS_NS):]
                self.focus[name] = focus_parser(name, value)
            elif key.startswith(self.IMAGE_NS):
                name = key[len(self.IMAGE_NS):]
                self.image[name] = image_parser(name, value)

if __name__ == '__main__':
    import sys
    import optparse

    parser = optparse.OptionParser(usage="usage: %prog [options] image")
    parser.add_option(
        "-d", "--dump-depth", dest="dump_depth",
        action="store",
        help="dump the depthmap to FILE", metavar="FILE")
    parser.add_option(
        "-i", "--dump-image", dest="dump_image",
        action="store",
        help="dump the image field to FILE", metavar="FILE")

    (options, args) = parser.parse_args()
    if not args:
        parser.print_usage()
        sys.exit(1)

    def print_values(data):
        for key, value in sorted(data.items()):
            if key != 'Data':
                print '{:15}: {}'.format(key, value)
            else:
                print '{:15}: <{} bytes long>'.format(key, len(value))

    blob = file(args[0]).read()
    g = GoogleDepthmap(*xmp_sections(blob))
    print 'Depth Section'
    print '-------------'
    print_values(g.depth)
    print 'Image Section'
    print '-------------'
    print_values(g.image)
    print 'Focus Section'
    print '-------------'
    print_values(g.focus)

    if options.dump_depth:
        file(options.dump_depth, 'w').write(g.depth['Data'])
    if options.dump_image:
        file(options.dump_image, 'w').write(g.image['Data'])
