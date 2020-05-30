''' c header/data parser '''
import linecache
import re
import struct
import json

import clang.cindex
from clang.cindex import CursorKind


class ParsedStruct(dict):
    ''' struct data wrapper '''
    def __init__(self, parsed_struct):
        self.parsed_struct = parsed_struct
        super(ParsedStruct, self).__init__()

    def __setattr__(self, name, value):
        if name == "parsed_struct":
            return dict.__setattr__(self, name, value)
        if 'field' in self.parsed_struct:
            if name in self.parsed_struct['field']:
                self.parsed_struct['field'][name]['value'] = value
            else:
                raise TypeError("no value in \"{}\"".format(name))
        return True

    def __getattribute__(self, name):
        if name == "prints":
            return dict.__getattribute__(self, name)
        if name == "pack":
            return dict.__getattribute__(self, name)
        if name == "parsed_struct":
            return dict.__getattribute__(self, name)
        if name == "get_parsed":
            return dict.__getattribute__(self, name)
        if name == "__value":
            if 'value' in self.parsed_struct:
                return self.parsed_struct['value']
            raise TypeError("no value in \"{}\"".format(name))

        if 'field' in self.parsed_struct:
            if name in self.parsed_struct['field']:
                if 'value' in self.parsed_struct['field'][name]:
                    return self.parsed_struct['field'][name]['value']
                return ParsedStruct(self.parsed_struct['field'][name])
        raise TypeError("no entry named \"{}\"".format(name))

    def __str__(self):
        __fl = []
        if 'field' in self.parsed_struct:
            for field_name in self.parsed_struct['field_order']:
                field = self.parsed_struct['field'][field_name]
                __fs = "{{ name: \"{}\", type: \"{}\"".format(field['name'], field['type'])
                __fv = field.get('value', None)
                if __fv is not None:
                    __fs = __fs +  ", value: \"{}\"".format(__fv)
                __fs = __fs + " }"
                __fl.append(__fs)
        __type = self.parsed_struct['type']
        __name = self.parsed_struct['name']
        __value = self.parsed_struct.get('value', None)
        return_string = "{{ name: \"{}\", type:\"{}\"".format(__name, __type)
        if len(__fl) > 0:
            return_string = return_string +" , fields: {}".format(", ".join(__fl))
        if __value is not None:
            return_string = return_string + ", value: \"{}\"".format(__value)
        return_string = return_string + " }"
        return return_string


    def prints(self):
        ''' prints structure and values '''
        def print_type(__type, indent):
            __string = "\t" * indent
            __list = []
            if 'name' in __type:
                __list.append(__type['name'])
            if 'type' in __type:
                __list.append(__type['type'])
            __string += "({})".format(" -- ".join(__list))
            if 'value' in __type:
                __string += "v: \"{}\"".format(__type['value'])
            print(__string)
            if "field_order" in __type:
                for field in __type['field_order']:
                    print_type(__type['field'][field], indent + 1)

        print_type(self.parsed_struct, 0)

    def get_parsed(self):
        ''' return the parsed struct '''
        return self.parsed_struct

    def pack(self, endian="<"):
        ''' return a packed bytestring of the struct '''
        def recursive_pack(entry, data):
            if 'field_order' in entry:
                for field_name in entry['field_order']:
                    recursive_pack(entry['field'][field_name], data)
            if 'struct' in entry:
                __struct = entry['struct']
                if 'array_length' in entry:
                    for i in range(0, entry['array_length']):
                        packed = struct.pack("{}{}".format(endian, __struct['symbol']), entry['value'][i] )
                        data.extend(packed)
                else:
                    packed = struct.pack("{}{}".format(endian, __struct['symbol']), entry['value'] )
                    data.extend(packed)
        __data = bytearray()
        recursive_pack(self.parsed_struct, __data)
        return __data


class DataParser(dict):
    ''' Parses data according to struct definitions '''
    def __init__(self, definitions, endian='<'):
        self.endian = endian
        self.struct_builtins = [['c', 'char', 1],
                                ['b', 'signed char', 1],
                                ['B', 'unsigned char', 1],
                                ['?', '_Bool', 1],
                                ['h', 'short', 2],
                                ['H', 'unsigned short', 2],
                                ['i', 'int', 4],
                                ['I', 'unsigned int', 4],
                                ['l', 'long', 4],
                                ['L', 'unsigned long', 4],
                                ['q', 'long long', 8],
                                ['Q', 'unsigned long long', 8],
                                ['f', 'float', 4],
                                ['d', 'double', 8]]

        self.definitions = {}
        for builtin in self.struct_builtins:
            self.definitions[builtin[1]] = {
                'name': builtin[1],
                'type': builtin[1],
                'struct': {
                    'symbol': builtin[0],
                    'byte_size': builtin[2],
                    }}
        self.definitions.update(definitions)
        super(DataParser, self).__init__()

    def parse(self, parse_type, data):
        ''' parse data as parsed_type '''
        splits = parse_type.split(":__:")
        if len(splits) == 2:
            parse_type = splits[0]
        if parse_type in self.definitions:
            definition = self.definitions[parse_type]
        if not definition:
            raise TypeError("type {} not defined".format(parse_type))

        parsed_struct = {}
        if len(splits) == 2:
            parsed_struct['array_length'] = int(splits[1])

        def parse_definition(definition, parsed_struct, passed_name, parent, data, offset):
            parsed_struct['name'] = passed_name
            if 'type' not in definition:
                parsed_struct['type'] = definition['name']
            else:
                parsed_struct['type'] = definition['type']

            if 'extensions' in definition:
                parsed_struct['extensions'] = definition['extensions']
            if 'array_length' in definition:
                parsed_struct['array_length'] = definition['array_length']

            if 'is_type' in definition:
                new_definition = self.definitions[definition['type']]
                if 'extensions' in definition:
                    parsed_struct['extensions'] = definition['extensions']
                if 'array_length' in definition:
                    parsed_struct['array_length'] = definition['array_length']
                offset = parse_definition(new_definition, parsed_struct, passed_name, parent, data, offset)
                return offset
            if 'fields' in definition:
                for field in definition['fields']:
                    if 'field' not in parsed_struct:
                        parsed_struct['field'] = {}
                    if 'field_order' not in parsed_struct:
                        parsed_struct['field_order'] = []
                    parsed_struct['field_order'].append(field['name'])
                    nps = parsed_struct['field'][field['name']] = {}
                    if 'array_length' in field:
                        nps['array_length'] = field['array_length']
                    if 'extensions' in field:
                        nps['extensions'] = field['extensions']
                    if 'variable_sized_array' in field:
                        nps['variable_sized_array'] = field['variable_sized_array']
                    offset = parse_definition(self.definitions[field['type']], nps, field['name'], parsed_struct, data, offset)
                return offset

            if 'struct' in definition:
                parsed_struct['struct'] = definition['struct']
                if 'extensions' in parsed_struct:
                    if 'array_length_reference' in parsed_struct['extensions']:
                        arl = parsed_struct['extensions']['array_length_reference']
                        parsed_struct['array_length'] = parent['field'][arl]['value']
                if 'array_length' in parsed_struct:
                    __value_list = list()
                    for i in range(0, parsed_struct['array_length']):
                        __value_list.append(struct.unpack_from("{}{}".format(self.endian, definition['struct']['symbol']), data, offset+ i * definition['struct']['byte_size'])[0])
                    parsed_struct['value'] = __value_list
                    return offset + definition['struct']['byte_size'] * parsed_struct['array_length']
                parsed_struct['value'] =  struct.unpack_from("{}{}".format(self.endian, definition['struct']['symbol']), data, offset)[0]
                return offset + definition['struct']['byte_size']
            return offset

        parse_definition(definition, parsed_struct, parse_type, None, data, 0)
        return ParsedStruct(parsed_struct)


class HeaderParser:
    ''' parse c style headers '''
    def __init__(self, headers, clang_library_file="/lib/llvm-8/lib/libclang.so.1", clang_args=['-x', 'c', '-std=c++11', '-D__CODE_GENERATOR__']):
        clang.cindex.Config.set_library_file(clang_library_file)
        self.types = {}
        index = clang.cindex.Index.create()
        translation_unit = index.parse(headers, clang_args)
        self.__traverse__(translation_unit.cursor, None, self.types)


    def __traverse__(self, cursor, current_type, types):
        if cursor.kind in [CursorKind.TRANSLATION_UNIT]:
            pass
        else:
            if cursor.kind == CursorKind.STRUCT_DECL:
                if types.has_key(cursor.type.spelling):
                    current_type = None
                else:
                    current_type = {
                        'name': cursor.type.spelling,
                        'fields': [],
                        }
                    types[cursor.type.spelling] = current_type
            elif cursor.kind == CursorKind.TYPEDEF_DECL:
                if hasattr(cursor, 'is_definition'):
                    if cursor.is_definition():
                        if not types.has_key(cursor.type.spelling):
                            current_type = {
                                'name': cursor.type.spelling,
                                'type': cursor.underlying_typedef_type.spelling,
                                'is_type': True,
                                'fields': [],
                                }
                            types[cursor.type.spelling] = current_type
            elif cursor.kind == CursorKind.FIELD_DECL:
                if current_type is not None:
                    array_type = cursor.type.get_array_element_type().spelling
                    __field = {
                        'name': cursor.spelling,
                        'type': cursor.type.spelling,
                        }

                    # there has to be a better way...
                    line = linecache.getline(cursor.location.file.name, cursor.location.line)
                    match = re.match(r'.*DataParser=({.*}).*', line)
                    if match:
                        __field['extensions'] = json.loads(match.group(1))
                    if array_type != "":
                        size = cursor.type.get_size()
                        __field['type'] = array_type
                        if size > 0:
                            __field['array_length'] = size
                        else:
                            __field['variable_size_array'] = True
                    current_type['fields'].append(__field)
            else:
                pass
        for child_node in cursor.get_children():
            self.__traverse__(child_node, current_type, types)

    def get_definitions(self):
        ''' return parsed types '''
        return self.types
