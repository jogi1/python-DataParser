#!/usr/bin/python3
import struct
import clang.cindex
from clang.cindex import CursorKind, TokenKind

class ParsedStruct(dict):
    def __init__(self, parsed_struct):
        self.parsed_struct = parsed_struct
        return

    def __getattribute__(self, name):
        if name == "prints":
            return dict.__getattribute__(self, name)
        if name == "parsed_struct":
            return dict.__getattribute__(self, name)
        if name == "get_parsed":
            return dict.__getattribute__(self, name)
        if name == "__value":
            if 'value' in self.parsed_struct:
                return self.parsed_struct['value']
            else:
                raise(TypeError("no value in \"{}\"".format(name)))

        if 'field' in self.parsed_struct:
            if name in self.parsed_struct['field']:
                if 'value' in self.parsed_struct['field'][name]:
                    return self.parsed_struct['field'][name]['value']
                else:
                    return ParsedStruct(self.parsed_struct['field'][name])
        raise(TypeError("no entry named \"{}\"".format(name)))

    def __str__(self):
        fl = []
        if 'field' in self.parsed_struct:
            for field_name in self.parsed_struct['field_order']:
                field = self.parsed_struct['field'][field_name]
                fs = "{{ name: \"{}\", type: \"{}\"".format(field['name'], field['type'])
                fv = field.get('value', None)
                if fv is not None:
                    fs = fs +  ", value: \"{}\"".format(fv)
                fs = fs + " }"
                fl.append(fs)
        name = self.parsed_struct['type']
        __type = self.parsed_struct['name']
        __value = self.parsed_struct.get('value', None)
        return_string =  "{{ name: \"{}\", type:\"{}\"".format(name, __type)
        if len(fl) > 0:
            return_string = return_string +" , fields: {}".format(", ".join(fl))
        if __value is not None:
            return_string = return_string + ", value: \"{}\"".format(__value)
        return_string = return_string + " }"
        return return_string


    def prints(self):
        def print_type(__type, indent):
            s = "\t" * indent;
            l = []
            if 'name' in __type:
                l.append(__type['name'])
            if 'type' in __type:
                l.append(__type['type'])
            s += "({})".format(" -- ".join(l))
            if 'value' in __type:
                s += "v: \"{}\"".format(__type['value'])
            print(s)
            if "field_order" in __type:
                for field in __type['field_order']:
                    print_type(__type['field'][field], indent + 1)

        print_type(self.parsed_struct, 0)
    def get_parsed(self):
        return self.parsed_struct


class DataParser(dict):
    def __init__(self, definitions, endian='<'):
        self.endian = endian
        self.definitions = {
            'long': {
                'name': 'long',
                'type': 'long',
                'struct': {
                    'symbol': 'l',
                    'byte_size': 4,
                    }
                },
            'unsigned long': {
                'name': 'unsigned long',
                'type': 'unsigned long',
                'struct': {
                    'symbol': 'L',
                    'byte_size': 4,
                    }
                },
            'float': {
                'name': 'float',
                'type': 'float',
                'struct': {
                    'symbol': 'f',
                    'byte_size': 4,
                    }
                },
            'char': {
                'name': 'char',
                'type': 'char',
                'struct': {
                    'symbol': 'c',
                    'byte_size': 1,
                    }
                }
            }
        self.definitions.update(definitions)

    def parse(self, parse_type, data):
        if parse_type in self.definitions:
            definition = self.definitions[parse_type]
        if not definition:
            raise TypeError("type {} not defined".format(parse_type))
        parsed_struct = {}

        def parse_definition(definition, parsed_struct, passed_name, data, offset):
            #print("({}) - {}".format(passed_name, definition))
            parsed_struct['name'] = passed_name
            if 'type' not in definition:
                parsed_struct['type'] = definition['name']
            else:
                parsed_struct['type'] = definition['type']

            if 'is_type' in definition:
                new_definition = self.definitions[definition['type']]
                if 'array_length' in definition:
                    parsed_struct['array_length'] = definition['array_length']
                offset = parse_definition(new_definition, parsed_struct, passed_name, data, offset)
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
                    offset = parse_definition(self.definitions[field['type']], nps, field['name'], data, offset)
                return offset
                
            if 'struct' in definition:
                parsed_struct['struct'] = definition['struct']
                if 'array_length' in parsed_struct:
                    v = list()
                    for i in range(0, parsed_struct['array_length']):
                      v.append(struct.unpack_from("{}{}".format(self.endian, definition['struct']['symbol']), data, offset+ i * definition['struct']['byte_size'])[0])
                    parsed_struct['value'] = v
                    return offset + definition['struct']['byte_size'] * parsed_struct['array_length']
                else:
                    parsed_struct['value'] =  struct.unpack_from("{}{}".format(self.endian, definition['struct']['symbol']), data, offset)[0]
                    return offset + definition['struct']['byte_size']
            return offset

        parse_definition(definition, parsed_struct, parse_type, data, 0)
        return ParsedStruct(parsed_struct)



class HeaderParser:
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
                    if array_type is not "":
                        size = cursor.type.get_size()
                        __field['type'] = array_type
                        if size > 0:
                            __field['array_length'] = size
                        else:
                            __field['variable_size_array'] = True
                    current_type['fields'].append(__field)
        for child_node in cursor.get_children():
            self.__traverse__(child_node, current_type, types)

    def get_definitions(self):
        return self.types
