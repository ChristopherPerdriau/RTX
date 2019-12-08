#!/usr/bin/env python3
'''Utility functions used by various python scripts KG2 build system

   Usage:  import kg2_util
   (then call a function like kg2_util.log_message(), etc.)
'''

__author__ = 'Stephen Ramsey'
__copyright__ = 'Oregon State University'
__credits__ = ['Stephen Ramsey']
__license__ = 'MIT'
__version__ = '0.1.0'
__maintainer__ = ''
__email__ = ''
__status__ = 'Prototype'

import copy
import gzip
import io
import json
import os
import pathlib
import pprint
import re
import shutil
import ssl
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import yaml

CURIE_PREFIX_ENSEMBL = 'ENSEMBL'
TEMP_FILE_PREFIX = 'kg2'
FIRST_CAP_RE = re.compile('(.)([A-Z][a-z]+)')
ALL_CAP_RE = re.compile('([a-z0-9])([A-Z])')
BIOLINK_CATEGORY_BASE_IRI = 'http://w3id.org/biolink/vocab/'
BIOLINK_CURIE_PREFIX = 'Biolink'
IRI_OWL_SAME_AS = 'http://www.w3.org/2002/07/owl#sameAs'
CURIE_OWL_SAME_AS = 'owl:sameAs'
NCBI_TAXON_ID_HUMAN = 9606
CURIE_PREFIX_NCBI_GENE = 'NCBIGene'
CURIE_PREFIX_NCBI_TAXON = 'NCBITaxon'


def load_json(input_file_name):
    return json.load(open(input_file_name, 'r'))


def save_json(data, output_file_name: str, test_mode: bool = False):
    if not test_mode:
        indent_num = None
        sort_keys = False
    else:
        indent_num = 4
        sort_keys = True
    temp_output_file_name = tempfile.mkstemp(prefix='kg2-')[1]
    if not output_file_name.endswith('.gz'):
        temp_output_file = open(temp_output_file_name, 'w')
        json.dump(data, temp_output_file, indent=indent_num, sort_keys=sort_keys)
    else:
        temp_output_file = gzip.GzipFile(temp_output_file_name, 'w')
        temp_output_file.write(json.dumps(data, indent=indent_num, sort_keys=sort_keys).encode('utf-8'))
    shutil.move(temp_output_file_name, output_file_name)


def get_file_last_modified_timestamp(file_name: str):
    return time.gmtime(os.path.getmtime(file_name))


def read_file_to_string(local_file_name: str):
    with open(local_file_name, 'r') as myfile:
        file_contents_string = myfile.read()
    myfile.close()
    return file_contents_string


def head_list(x: list, n: int = 3):
    pprint.pprint(x[0:n])


def head_dict(x: dict, n: int = 3):
    pprint.pprint(dict(list(x.items())[0:(n-1)]))


def purge(dir, pattern):
    exp_dir = os.path.expanduser(dir)
    for f in os.listdir(exp_dir):
        if re.search(pattern, f):
            os.remove(os.path.join(exp_dir, f))


def allcaps_to_only_first_letter_capitalized(allcaps: str):
    return allcaps[0] + allcaps[1:].lower()


def safe_load_yaml_from_string(yaml_string: str):
    return yaml.safe_load(io.StringIO(yaml_string))


def log_message(message: str,
                ontology_name: str = None,
                node_curie_id: str = None,
                output_stream=sys.stdout):
    if node_curie_id is not None:
        node_str = ": " + node_curie_id
    else:
        node_str = ""
    if ontology_name is not None:
        ont_str = '[' + ontology_name + '] '
    else:
        ont_str = ''
    print(ont_str + message + node_str, file=output_stream)


def merge_two_dicts(x: dict, y: dict):
    ret_dict = copy.deepcopy(x)
    for key, value in y.items():
        stored_value = ret_dict.get(key, None)
        if stored_value is None:
            if value is not None:
                ret_dict[key] = value
        else:
            if value is not None and value != stored_value:
                if type(value) == str and type(stored_value) == str:
                    if value.lower() != stored_value.lower():
                        if key == 'description' or key == 'update date':
                            if len(value) > len(stored_value):  # use the longer of the two descriptions or update date fields
                                ret_dict[key] = value
                        elif key == 'ontology node type':
                            log_message("warning:  for key: " + key + ", dropping second value: " + value + '; keeping first value: ' + stored_value,
                                        output_stream=sys.stderr)
                            ret_dict[key] = stored_value
                        elif key == 'provided by':
                            if value.endswith('/STY'):
                                ret_dict[key] = value
                        elif key == 'category label':
                            if value != 'unknown category' and stored_value == 'unknown category':
                                stored_desc = ret_dict.get('description', None)
                                new_desc = y.get('description', None)
                                if stored_desc is not None and new_desc is not None:
                                    if len(new_desc) > len(stored_desc):
                                        ret_dict[key] = value
                        elif key == 'category':
                            if not value.endswith('/UnknownCategory') and stored_value.endswith('/UnknownCategory'):
                                stored_desc = ret_dict.get('description', None)
                                new_desc = y.get('description', None)
                                if stored_desc is not None and new_desc is not None:
                                    if len(new_desc) > len(stored_desc):
                                        ret_dict[key] = value
                        elif key == 'name' or key == 'full name':
                            if value.replace(' ', '_') != stored_value.replace(' ', '_'):
                                stored_desc = ret_dict.get('description', None)
                                new_desc = y.get('description', None)
                                if stored_desc is not None and new_desc is not None:
                                    if len(new_desc) > len(stored_desc):
                                        ret_dict[key] = value
                        else:
                            log_message("warning:  for key: " + key + ", dropping second value: " + value + '; keeping first value: ' + stored_value,
                                        output_stream=sys.stderr)
                elif type(value) == list and type(stored_value) == list:
                    ret_dict[key] = list(set(value + stored_value))
                elif type(value) == list and type(stored_value) == str:
                    ret_dict[key] = list(set(value + [stored_value]))
                elif type(value) == str and type(stored_value) == list:
                    ret_dict[key] = list(set([value] + stored_value))
                elif type(value) == dict and type(stored_value) == dict:
                    ret_dict[key] = merge_two_dicts(value, stored_value)
                elif key == 'deprecated' and type(value) == bool:
                    ret_dict[key] = True  # special case for deprecation; True always trumps False for this property
                else:
                    assert False
    return ret_dict


def compose_two_multinode_dicts(node1: dict, node2: dict):
    ret_dict = copy.deepcopy(node1)
    for key, value in node2.items():
        stored_value = ret_dict.get(key, None)
        if stored_value is None:
            ret_dict[key] = value
        else:
            if value is not None:
                ret_dict[key] = merge_two_dicts(node1[key], value)
    return ret_dict


def format_timestamp(timestamp: time.struct_time):
    return time.strftime('%Y-%m-%d %H:%M:%S %Z', timestamp)


def download_file_if_not_exist_locally(url: str, local_file_name: str):
    if url is not None:
        local_file_path = pathlib.Path(local_file_name)
        if not local_file_path.is_file():
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            # the following code is ugly but necessary because sometimes the TLS
            # certificates of remote sites are broken and some of the PURL'd
            # URLs resolve to HTTPS URLs (would prefer to just use
            # urllib.request.urlretrieve, but it doesn't seem to support
            # specifying an SSL "context" which we need in order to ignore the cert):
            temp_file_name = tempfile.mkstemp(prefix=TEMP_FILE_PREFIX + '-')[1]
            with urllib.request.urlopen(url, context=ctx) as u, open(temp_file_name, 'wb') as f:
                f.write(u.read())
            shutil.move(temp_file_name, local_file_name)
    return local_file_name


def convert_snake_case_to_camel_case(name: str):
    name = name.title().replace('_', '')
    if len(name) > 0:
        name = name[0].lower() + name[1:]
    return name


def convert_camel_case_to_snake_case(name: str):
    s1 = FIRST_CAP_RE.sub(r'\1_\2', name)
    converted = ALL_CAP_RE.sub(r'\1_\2', s1).lower()
    converted = converted.replace('sub_class', 'subclass')
    if converted[0].istitle():
        converted[0] = converted[0].lower()
    return converted.replace(' ', '_')


def convert_biolink_category_to_iri(biolink_category_label: str,
                                    biolink_category_base_iri: str = BIOLINK_CATEGORY_BASE_IRI):
    return urllib.parse.urljoin(biolink_category_base_iri,
                                biolink_category_label.title().replace(' ', ''))


def make_node(id: str,
              iri: str,
              name: str,
              category_label: str,
              update_date: str,
              provided_by: str):
    return {'id': id,
            'iri': iri,
            'name': name,
            'full name': name,
            'category': convert_biolink_category_to_iri(category_label),
            'category label': category_label.replace(' ', '_'),
            'description': None,
            'synonym': [],
            'publications': [],
            'creation date': None,
            'update date': update_date,
            'deprecated': False,
            'replaced by': None,
            'provided by': provided_by}


def make_edge_key(edge_dict: dict):
    return edge_dict['subject'] + '---' + \
           edge_dict['object'] + '---' + \
           edge_dict['relation curie'] + '---' + \
           edge_dict['provided by']


def make_edge(subject_id: str,
              object_id: str,
              relation: str,
              relation_curie: str,
              predicate_label: str,
              provided_by: str,
              update_date: str = None):

    return {'subject': subject_id,
            'object': object_id,
            'edge label': predicate_label,
            'relation': relation,
            'relation curie': relation_curie,
            'negated': False,
            'publications': [],
            'publications info': {},
            'update date': update_date,
            'provided by': provided_by}


def predicate_label_to_iri_and_curie(predicate_label: str,
                                     relation_curie_prefix: str,
                                     relation_iri_prefix: str):
    predicate_label = predicate_label.replace(' ', '_')
    if ':' not in predicate_label:
        predicate_label_to_use = convert_snake_case_to_camel_case(predicate_label)
    else:
        predicate_label_to_use = predicate_label.replace(':', '_')
    return [urllib.parse.urljoin(relation_iri_prefix, predicate_label_to_use),
            relation_curie_prefix + ':' + predicate_label]

