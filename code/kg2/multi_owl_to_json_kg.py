#!/usr/bin/env python3
'''Builds the RTX "KG2" second-generation knowledge graph, from various OWL input files.

   Usage: multi_owl_to_json_kg.py --categoriesFile <categoriesFile.yaml> --curiesToURILALFile <curiesToURILALFile>
                                  --owlLoadInventoryFile <owlLoadInventoryFile.yaml> --outputFile <outputFile>
   (note: outputFile can end in .json or in .gz; if the latter, it will be written as a gzipped file;
   but using the gzip options for input or output seems to significantly increase transient memory
   usage)
'''

__author__ = 'Stephen Ramsey'
__copyright__ = 'Oregon State University'
__credits__ = ['Stephen Ramsey']
__license__ = 'MIT'
__version__ = '0.1.0'
__maintainer__ = ''
__email__ = ''
__status__ = 'Prototype'


import argparse
import errno
import functools
import hashlib
import kg2_util
import ontobio
import os.path
import pickle
import posixpath
import prefixcommons
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request


# -------------- define globals here ---------------

REGEX_ENSEMBL = re.compile('ENS[A-Z]{0,3}([PG])[0-9]{11}')
REGEX_YEAR = re.compile('([12][90][0-9]{2})')
REGEX_YEAR_MONTH_DAY = re.compile('([12][90][0-9]{2})_([0-9]{1,2})_([0-9]{1,2})')
REGEX_MONTH_YEAR = re.compile('([0-9]{1,2})_[12][90][0-9]{2}')
REGEX_YEAR_MONTH = re.compile('[12][90][0-9]{2}_([0-9]{1,2})')
REGEX_UMLS_CURIE = re.compile('UMLS:([^/]+)/(.*)')
REGEX_PUBLICATIONS = re.compile('((?:(?:PMID)|(?:ISBN)):\d+)')
REGEX_PURL = re.compile('http://purl.obolibrary.org/obo/([^_]+)_(.*)')
REGEX_IDORG = re.compile('https://identifiers.org/umls/([^/]+)/(.*)')
REGEX_XREF_END_DESCRIP = re.compile('.*\[([^\]]+)\]$')

CUI_BASE_IRI = 'https://identifiers.org/umls/cui'
IRI_OBO_XREF = 'http://purl.org/obo/owl/oboFormat#oboFormat_xref'
CURIE_OBO_XREF = 'oboFormat:xref'
OWL_BASE_CLASS = 'owl:Thing'
OWL_NOTHING = 'owl:Nothing'
MYSTERIOUS_BASE_NODE_ID_TO_FILTER = '_:genid'
ENSEMBL_LETTER_TO_CATEGORY = {'P': 'protein',
                              'G': 'gene',
                              'T': 'transcript'}

# -------------- subroutines with side-effects go here ------------------


def delete_ontobio_cachier_caches():
    kg2_util.purge("~/.cachier", ".ontobio*")
    kg2_util.purge("~/.cachier", ".prefixcommons*")


# this function is needed due to an issue with caching in Ontobio; see this GitHub issue:
#     https://github.com/biolink/ontobio/issues/301
def delete_ontobio_cache_json(file_name: str):
    file_name_hash = hashlib.sha256(file_name.encode()).hexdigest()
    temp_file_path = os.path.join("/tmp", file_name_hash)
    if os.path.exists(temp_file_path):
        try:
            kg2_util.log_message(message="Deleting ontobio JSON cache file: " + temp_file_path)
            os.remove(temp_file_path)
        except OSError as e:
            if e.errno == errno.ENOENT:
                kg2_util.log_message(message="Error deleting ontobio JSON cache file: " + temp_file_path)
            else:
                raise e


# this function will load the ontology object from a pickle file (if it exists) or
# it will create the ontology object by parsing the OWL-XML ontology file
def make_ontology_from_local_file(file_name: str):
    file_name_without_ext = os.path.splitext(file_name)[0]
    file_name_with_pickle_ext = file_name_without_ext + ".pickle"
    if not os.path.isfile(file_name_with_pickle_ext):
        # the ontology hsa not been saved as a pickle file, so we need to load it from a text file
        if not file_name.endswith('.json'):
            temp_file_name = tempfile.mkstemp(prefix=kg2_util.TEMP_FILE_PREFIX + '-')[1] + '.json'
            size = os.path.getsize(file_name)
            kg2_util.log_message(message="Reading ontology file: " + file_name + "; size: " + "{0:.2f}".format(size/1024) + " KiB",
                                 ontology_name=None)
            cp = subprocess.run(['owltools', file_name, '-o', '-f', 'json', temp_file_name])
            # robot commented out because it is giving a NullPointerException on umls_semantictypes.owl
            # Once robot no longer gives a NullPointerException, we can use it like this:
            #        cp = subprocess.run(['robot', 'convert', '--input', file_name, '--output', temp_file_name])
            if cp.stdout is not None:
                kg2_util.log_message(message="OWL convert result: " + cp.stdout, ontology_name=None, output_stream=sys.stdout)
            if cp.stderr is not None:
                kg2_util.log_message(message="OWL convert result: " + cp.stderr, ontology_name=None, output_stream=sys.stderr)
            assert cp.returncode == 0
            json_file = file_name_without_ext + ".json"
            shutil.move(temp_file_name, json_file)
        else:
            json_file = file_name
        size = os.path.getsize(json_file)
        kg2_util.log_message(message="Reading ontology JSON file: " + json_file + "; size: " + "{0:.2f}".format(size/1024) + " KiB",
                             ontology_name=None)

        ont_return = ontobio.ontol_factory.OntologyFactory().create(json_file, ignore_cache=True)
    else:
        size = os.path.getsize(file_name_with_pickle_ext)
        kg2_util.log_message("Reading ontology file: " + file_name_with_pickle_ext + "; size: " + "{0:.2f}".format(size/1024) + " KiB", ontology_name=None)
        ont_return = pickle.load(open(file_name_with_pickle_ext, "rb"))
    return ont_return


def load_owl_file_return_ontology_and_metadata(file_name: str,
                                               download_url: str = None,
                                               ontology_title: str = None):
    ontology = make_ontology_from_local_file(file_name)
    file_last_modified_timestamp = kg2_util.format_timestamp(kg2_util.get_file_last_modified_timestamp(file_name))
    print("file: " + file_name + "; last modified: " + file_last_modified_timestamp)
    ont_version = ontology.meta.get('version', None)
    bpv = ontology.meta.get('basicPropertyValues', None)
    title = ontology_title
    description = None
    umls_sver = None
    if bpv is not None:
        for bpv_dict in bpv:
            pred = bpv_dict['pred']
            value = bpv_dict['val']
            if 'description' in pred:
                description = value
            elif 'title' in pred:
                if title is None:
                    title = value
            elif 'umls/sver' in pred:
                ont_version = value
                umls_sver = value
    if ont_version is None:
        ont_version = 'downloaded:' + file_last_modified_timestamp
    ontology_id = None
    if download_url is not None:
        ontology_id = download_url
    else:
        ontology_id = ontology.id
        #    print(ontology_id)
        if not ontology_id.startswith('http:') and not ontology_id.startswith('https:'):
            ontology_id = os.path.basename(file_name)
    metadata_dict = {'id': ontology_id,
                     'handle': ontology.handle,
                     'file': file_name,
                     'file last modified timestamp': file_last_modified_timestamp,
                     'version': ont_version,
                     'title': title,
                     'description': description,
                     'umls-sver': umls_sver}
#    print(metadata_dict)
    return [ontology, metadata_dict]


def make_kg2(curies_to_categories: dict,
             uri_to_curie_shortener: callable,
             map_category_label_to_iri: callable,
             owl_urls_and_files: tuple,
             output_file_name: str,
             test_mode: bool = False):

    owl_file_information_dict_list = []

    # for each OWL file (or URL for an OWL file) described in the YAML config file...
    for ont_source_info_dict in owl_urls_and_files:
        if ont_source_info_dict['download']:
            # get the OWL file onto the local file system and get a full path to it
            local_file_name = kg2_util.download_file_if_not_exist_locally(ont_source_info_dict['url'],
                                                                          ont_source_info_dict['file'])
        else:
            local_file_name = ont_source_info_dict['file']
            assert os.path.exists(ont_source_info_dict['file'])
        # load the OWL file dadta into an ontobio.ontol.Ontology data structure and information dictionary
        [ont, metadata_dict] = load_owl_file_return_ontology_and_metadata(local_file_name,
                                                                          ont_source_info_dict['url'],
                                                                          ont_source_info_dict['title'])
        metadata_dict['ontology'] = ont
        owl_file_information_dict_list.append(metadata_dict)

    kg2_util.log_message('Calling make_nodes_dict_from_ontologies_list')

    nodes_dict = make_nodes_dict_from_ontologies_list(owl_file_information_dict_list,
                                                      curies_to_categories,
                                                      uri_to_curie_shortener,
                                                      map_category_label_to_iri)

    kg2_util.log_message('Calling make_map_of_node_ontology_ids_to_curie_ids')

    map_of_node_ontology_ids_to_curie_ids = make_map_of_node_ontology_ids_to_curie_ids(nodes_dict)

    kg2_util.log_message('Calling get_rels_dict')

    # get a dictionary of all relationships including xrefs as relationships
    all_rels_dict = get_rels_dict(nodes_dict,
                                  owl_file_information_dict_list,
                                  uri_to_curie_shortener,
                                  map_of_node_ontology_ids_to_curie_ids)

    kg2_dict = dict()
    kg2_dict['edges'] = [rel_dict for rel_dict in all_rels_dict.values()]
    kg2_util.log_message('Number of edges: ' + str(len(kg2_dict['edges'])))
    kg2_dict['nodes'] = list(nodes_dict.values())
    kg2_util.log_message('Number of nodes: ' + str(len(kg2_dict['nodes'])))
    del nodes_dict

    # delete xrefs from all_nodes_dict
    for node_dict in kg2_dict['nodes']:
        del node_dict['xrefs']
        del node_dict['ontology node ids']

    kg2_util.log_message('Saving JSON file')
    kg2_util.save_json(kg2_dict, output_file_name, test_mode)


def get_depth_of_ontology_term(ontology_node_id: str,
                               ontology: ontobio.ontol.Ontology,
                               ontology_node_ids_visited: set = None,
                               recursion_level: int = 0):
    if ontology_node_ids_visited is None:
        ontology_node_ids_visited = set()
    min_depth = None
    parents = ontology.parents(ontology_node_id, ['subClassOf'])
    if len(parents) == 0:
        return recursion_level
    for parent_ontology_node_id in parents:
        if parent_ontology_node_id not in ontology_node_ids_visited:
            ontology_node_ids_visited.add(parent_ontology_node_id)
            depth = get_depth_of_ontology_term(parent_ontology_node_id,
                                               ontology,
                                               ontology_node_ids_visited,
                                               recursion_level + 1)
            if min_depth is None or depth < min_depth:
                min_depth = depth
    return min_depth


def get_biolink_category_for_node(ontology_node_id: str,
                                  node_curie_id: str,
                                  ontology: ontobio.ontol.Ontology,
                                  curies_to_categories: dict,
                                  uri_to_curie_shortener: callable,
                                  ontology_node_ids_previously_seen: set,
                                  get_node_id_of_node_with_category: bool):

    # if we have already looked for a category for this node, return None
    if ontology_node_id in ontology_node_ids_previously_seen:
        return [None, None]

    if ontology_node_id == OWL_NOTHING or node_curie_id is None:
        return [None, None]

    ontology_node_ids_previously_seen.add(ontology_node_id)

    curie_prefix = get_prefix_from_curie_id(node_curie_id)

    # Inelegant hack to ensure that TUI: nodes get mapped to "semantic type" while still enabling us
    # to use get_biolink_category_for_node to determine the specific semantic type of a CUI: based on its
    # TUI: record. Need to think about a more elegant way to do this. [SAR]
    if curie_prefix == 'TUI' and ontology.id.endswith('/umls/STY/'):
        return ['semantic type', None]

    if get_node_id_of_node_with_category:
        ret_ontology_node_id_of_node_with_category = ontology_node_id
    else:
        ret_ontology_node_id_of_node_with_category = None

    curies_to_categories_prefixes = curies_to_categories['prefix-mappings']
    ret_category = curies_to_categories_prefixes.get(curie_prefix, None)
    if ret_category is None:
        # need to walk the ontology hierarchy until we encounter a parent term with a defined biolink category
        curies_to_categories_terms = curies_to_categories['term-mappings']
        ret_category = curies_to_categories_terms.get(node_curie_id, None)
        if ret_category is None:
            for parent_ontology_node_id in ontology.parents(ontology_node_id, ['subClassOf']):
                parent_node_curie_id = get_node_curie_id_from_ontology_node_id(parent_ontology_node_id,
                                                                               ontology,
                                                                               uri_to_curie_shortener)
                try:
                    [ret_category,
                     ontology_node_id_of_node_with_category] = get_biolink_category_for_node(parent_ontology_node_id,
                                                                                             parent_node_curie_id,
                                                                                             ontology,
                                                                                             curies_to_categories,
                                                                                             uri_to_curie_shortener,
                                                                                             ontology_node_ids_previously_seen,
                                                                                             get_node_id_of_node_with_category)
                    if get_node_id_of_node_with_category and ontology_node_id_of_node_with_category is not None:
                        ret_ontology_node_id_of_node_with_category = ontology_node_id_of_node_with_category
                except RecursionError:
                    kg2_util.log_message(message="recursion error: " + ontology_node_id,
                                         ontology_name=ontology.id,
                                         node_curie_id=node_curie_id,
                                         output_stream=sys.stderr)
                    assert False
                if ret_category is not None:
                    break
    if ret_category is None:
        if node_curie_id.startswith(kg2_util.CURIE_PREFIX_ENSEMBL + ':'):
            curie_suffix = node_curie_id.replace(kg2_util.CURIE_PREFIX_ENSEMBL + ':', '')
            ensembl_match = REGEX_ENSEMBL.match(curie_suffix)
            if ensembl_match is not None:
                ensembl_match_letter = ensembl_match[1]
                ret_category = ENSEMBL_LETTER_TO_CATEGORY.get(ensembl_match_letter, None)
                if ret_category is None:
                    kg2_util.log_message(message="unrecognized Ensembl ID: " + curie_suffix,
                                         ontology_name=ontology.id,
                                         node_curie_id=node_curie_id,
                                         output_stream=sys.stderr)

    return [ret_category, ret_ontology_node_id_of_node_with_category]


# --------------- subroutines that have no side effects except logging printing ----------


def make_rel_key(subject_id: str,
                 predicate_name: str,
                 object_id: str,
                 ontology_id: str = None):
    key = subject_id + ';' + predicate_name + ';' + object_id
    if ontology_id is not None:
        key += ';' + ontology_id
    return key


def parse_umls_sver_date(umls_sver: str):
    umls_sver_match = REGEX_YEAR.match(umls_sver)
    updated_date = None
    if umls_sver_match is not None:
        updated_date = umls_sver_match[0]
    else:
        umls_sver_match = REGEX_YEAR_MONTH_DAY.match(umls_sver)
        if umls_sver_match is not None:
            updated_date = umls_sver_match[0] + '-' + ('%0.2d' % int(umls_sver_match[1])) + '-' + ('%0.2d' % int(umls_sver_match[2]))
        else:
            umls_sver_match = REGEX_MONTH_YEAR.match(umls_sver)
            if umls_sver_match is not None:
                updated_date = umls_sver_match[1] + '-' + ('%0.2d' % int(umls_sver_match[0]))
            else:
                umls_sver_match = REGEX_YEAR_MONTH.match(umls_sver)
                if umls_sver_match is not None:
                    updated_date = umls_sver_match[0] + ('%0.2d' % int(umls_sver_match[1]))
    return updated_date


def make_nodes_dict_from_ontologies_list(ontology_info_list: list,
                                         curies_to_categories: dict,
                                         uri_to_curie_shortener: callable,
                                         category_label_to_iri_mapper: callable):
    ret_dict = dict()
    ontologies_iris_to_curies = dict()

    for ontology_info_dict in ontology_info_list:
        ontology = ontology_info_dict['ontology']
        iri_of_ontology = ontology_info_dict['id']
        assert iri_of_ontology is not None

        ontology_curie_id = uri_to_curie_shortener(iri_of_ontology)
        if ontology_curie_id is None or len(ontology_curie_id) == 0:
            ontology_curie_id = iri_of_ontology
        umls_sver = ontology_info_dict.get('umls-sver', None)
        updated_date = None
        if umls_sver is not None:
            # if you can, parse sver string into a date string
            updated_date = parse_umls_sver_date(umls_sver)
        if updated_date is None:
            updated_date = ontology_info_dict['file last modified timestamp']

        ontology_node = kg2_util.make_node(ontology_curie_id,
                                           iri_of_ontology,
                                           ontology_info_dict['title'],
                                           'data source',
                                           updated_date,
                                           iri_of_ontology)
        ontology_node['description'] = ontology_info_dict['description']
        ontology_node['ontology node ids'] = [iri_of_ontology]
        ontology_node['xrefs'] = []
        ret_dict[ontology_curie_id] = ontology_node

        ontologies_iris_to_curies[iri_of_ontology] = ontology_curie_id

        for ontology_node_id in ontology.nodes():
            onto_node_dict = ontology.node(ontology_node_id)
            assert onto_node_dict is not None

            if ontology_node_id.startswith(MYSTERIOUS_BASE_NODE_ID_TO_FILTER):
                continue

            node_curie_id = get_node_curie_id_from_ontology_node_id(ontology_node_id,
                                                                    ontology,
                                                                    uri_to_curie_shortener)

            iri = onto_node_dict.get('id', None)
            if iri is None:
                iri = ontology_node_id

            if not iri.startswith('http:') and not iri.startswith('https:'):
                iri = prefixcommons.expand_uri(iri)

            if node_curie_id.startswith('NCBIGene:') or node_curie_id.startswith('HGNC:'):
                iri = prefixcommons.expand_uri(node_curie_id)

            generated_iri = prefixcommons.expand_uri(node_curie_id)
            if generated_iri != node_curie_id:
                if (generated_iri.startswith('http:') or generated_iri.startswith('https:')) and \
                   generated_iri != iri:
                    iri = generated_iri

            node_name = onto_node_dict.get('label', None)
            node_full_name = None

            [node_category_label,
             ontology_id_of_node_with_category] = get_biolink_category_for_node(ontology_node_id,
                                                                                node_curie_id,
                                                                                ontology,
                                                                                curies_to_categories,
                                                                                uri_to_curie_shortener,
                                                                                set(), False)

            node_deprecated = False
            node_description = None
            node_creation_date = None
            node_update_date = None
            node_replaced_by_curie = None
            node_full_name = None
            node_publications = set()
            node_synonyms = set()
            node_xrefs = set()
            node_tui = None

            node_meta = onto_node_dict.get('meta', None)
            if node_meta is not None:
                node_deprecated = node_meta.get('deprecated', False)
                node_definition = node_meta.get('definition', None)
                if node_definition is not None:
                    node_description = node_definition['val']
                    if node_description.startswith('OBSOLETE:') or node_description.startswith('Obsolete.'):
                        continue

                    node_definition_xrefs = node_definition.get('xrefs', None)
                    if node_definition_xrefs is not None:
                        assert type(node_definition_xrefs) == list
                        for xref in node_definition_xrefs:
                            xref_pub = xref_as_a_publication(xref)
                            if xref_pub is not None:
                                node_publications.add(xref_pub)

                node_synonyms_list = node_meta.get('synonyms', None)
                if node_synonyms_list is not None:
                    for syn_dict in node_synonyms_list:
                        syn_pred = syn_dict['pred']
                        if syn_pred == 'hasExactSynonym':
                            node_synonyms.add(syn_dict['val'])
                            syn_xrefs = syn_dict['xrefs']
                            if len(syn_xrefs) > 0:
                                for syn_xref in syn_xrefs:
                                    syn_xref_pub = xref_as_a_publication(syn_xref)
                                    if syn_xref_pub is not None:
                                        node_publications.add(syn_xref_pub)

                node_xrefs_list = node_meta.get('xrefs', None)
                if node_xrefs_list is not None:
                    for xref_dict in node_xrefs_list:
                        xref_curie = xref_dict['val']
                        if xref_curie.startswith('MESH:'):
                            xref_curie = xref_curie.replace('MESH:', 'MSH:')
                        node_xrefs.add(xref_curie)
                basic_property_values = node_meta.get('basicPropertyValues', None)
                if basic_property_values is not None:
                    node_tui_list = []
                    for basic_property_value_dict in basic_property_values:
                        bpv_pred = basic_property_value_dict['pred']
                        bpv_pred_curie = uri_to_curie_shortener(bpv_pred)
                        if bpv_pred_curie is None:
                            bpv_pred_curie = bpv_pred
                        bpv_val = basic_property_value_dict['val']
                        if bpv_pred_curie in ['OIO:creation_date', 'dcterms:issued', 'HGNC:DATE_CREATED']:
                            node_creation_date = bpv_val
                        elif bpv_pred_curie == 'HGNC:DATE_LAST_MODIFIED':
                            node_update_date = bpv_val
                        elif bpv_pred_curie == 'IAL:0100001':
                            assert node_deprecated
                            node_replaced_by_uri = bpv_val
                            node_replaced_by_curie = uri_to_curie_shortener(node_replaced_by_uri)
                        elif bpv_pred_curie == 'UMLS:STY':  # STY_BASE_IRI:
                            node_tui_list.append(bpv_val)
                        elif bpv_pred_curie == 'skos:prefLabel':
                            if not node_curie_id.startswith('HGNC:'):
                                node_name = bpv_val
                            else:
                                node_full_name = bpv_val
                        elif bpv_pred_curie == 'skos:altLabel':
                            node_synonyms.add(bpv_val)
                        elif bpv_pred_curie == 'skos:definition':
                            node_description = bpv_val
                        elif bpv_pred_curie == 'HGNC:GENESYMBOL':
                            node_name = bpv_val
                            node_synonyms.add(bpv_val)
                    if len(node_tui_list) > 0:
                        # fix some impedance mismatch between URIs used in umls2rdf and in umls_semantictypes.owl:
                        node_tui_info_list = []
                        for node_tui in node_tui_list:
                            node_tui_uri = posixpath.join('https://identifiers.org/umls/STY', node_tui)
                            node_tui_curie = uri_to_curie_shortener(node_tui_uri)
                            assert node_tui_curie is not None
                            [node_tui_category_label,
                             ontology_id_for_node_with_category] = get_biolink_category_for_node(node_tui_uri,
                                                                                                 node_tui_curie,
                                                                                                 ontology,
                                                                                                 curies_to_categories,
                                                                                                 uri_to_curie_shortener,
                                                                                                 set(), True)
                            assert ontology_id_for_node_with_category is not None
                            if ontology_id_for_node_with_category is not None:
                                ontology_depth_node_with_category = get_depth_of_ontology_term(ontology_id_for_node_with_category,
                                                                                               ontology)
                                assert ontology_depth_node_with_category is not None
                            if node_tui_category_label is not None:
                                tui_info_dict = {'curie': node_tui_curie,
                                                 'depth': ontology_depth_node_with_category,
                                                 'category_label': node_tui_category_label}
                                node_tui_info_list.append(tui_info_dict)
                        if len(node_tui_info_list) > 0:
                            node_tui_category_label = sorted(node_tui_info_list,
                                                             key=lambda node_tui_info_dict:
                                                             node_tui_info_dict['depth'])[-1]['category_label']
                        if node_tui_category_label is None:
                            node_tui_category_label = 'unknown category'
                            kg2_util.log_message(message='unknown category: ' + node_tui_uri)
                        else:
                            if node_category_label is None:
                                node_category_label = node_tui_category_label  # override the node category label if we have a TUI
                        node_tui_category_iri = category_label_to_iri_mapper(node_tui_category_label)
                node_comments = node_meta.get('comments', None)
                if node_comments is not None:
                    comments_str = 'COMMENTS: ' + (' // '.join(node_comments))
                    if node_description is not None:
                        node_description += ' // ' + comments_str
                    else:
                        node_description = comments_str

            if node_category_label is None:
                node_type = onto_node_dict.get('type', None)
                if node_type is not None and node_type == 'PROPERTY':
                    node_category_label = 'property'

            if node_category_label is None:
                if not node_deprecated:
                    kg2_util.log_message("Node does not have a category", ontology.id, node_curie_id, output_stream=sys.stderr)
                    node_category_label = 'unknown category'
                else:
                    node_category_label = 'deprecated node'

            ontology_curie_id = ontologies_iris_to_curies[iri_of_ontology]
            source_ontology_information = ret_dict.get(ontology_curie_id, None)
            if source_ontology_information is None:
                kg2_util.log_message(message="ontology IRI has no information dictionary available",
                                     ontology_name=iri_of_ontology,
                                     output_stream=sys.stderr)
                assert False
            source_ontology_update_date = source_ontology_information['update date']
            if node_update_date is None:
                node_update_date = source_ontology_update_date

            if node_description is not None:
                node_description_xrefs_match = REGEX_XREF_END_DESCRIP.match(node_description)
                if node_description_xrefs_match is not None:
                    node_description_xrefs_str = node_description_xrefs_match[1]
                    node_description_xrefs_list = node_description_xrefs_str.split(',')
                    for node_description_xref_str in node_description_xrefs_list:
                        node_description_xref_str = node_description_xref_str.strip()
                        if ':' in node_description_xref_str:
                            node_xrefs.add(node_description_xref_str)
                node_description_pubs = REGEX_PUBLICATIONS.findall(node_description)
                for pub_curie in node_description_pubs:
                    node_publications.add(pub_curie)

            # deal with node names that are ALLCAPS
            if node_name is not None and node_name.isupper():
                node_name = kg2_util.allcaps_to_only_first_letter_capitalized(node_name)

            node_dict = kg2_util.make_node(node_curie_id,
                                           iri,
                                           node_name,
                                           node_category_label,
                                           node_update_date,
                                           iri_of_ontology)
            node_dict['full name'] = node_full_name
            node_dict['description'] = node_description
            node_dict['creation date'] = node_creation_date   # slot name is not biolink standard
            node_dict['deprecated'] = node_deprecated         # slot name is not biolink standard
            node_dict['replaced by'] = node_replaced_by_curie  # slot name is not biolink standard
            node_dict['ontology node ids'] = [ontology_node_id]  # slot name is not biolink standard
            node_dict['xrefs'] = list(node_xrefs)            # slot name is not biolink standard
            node_dict['synonym'] = list(node_synonyms)       # slot name is not biolink standard
            node_dict['publications'] = list(node_publications)

            # check if we need to make a CUI node
            if node_meta is not None and basic_property_values is not None:
                for basic_property_value_dict in basic_property_values:
                    bpv_pred = basic_property_value_dict['pred']
                    bpv_pred_curie = uri_to_curie_shortener(bpv_pred)
                    bpv_val = basic_property_value_dict['val']
                    if bpv_pred_curie == 'UMLS:cui':   # CUI_BASE_IRI:
                        assert node_tui is not None
                        cui_node_dict = dict(node_dict)
                        cui_uri = bpv_pred + '/' + bpv_val
                        cui_curie = uri_to_curie_shortener(cui_uri)
                        assert cui_curie is not None
                        cui_node_dict['id'] = cui_curie
                        cui_node_dict['iri'] = cui_uri
                        cui_node_dict['synonym'] = []
                        cui_node_dict['category'] = node_tui_category_iri
                        cui_node_dict['category label'] = node_tui_category_label.replace(' ', '_')
                        cui_node_dict['ontology node ids'] = []
                        cui_node_dict['provided by'] = CUI_BASE_IRI
                        cui_node_dict['xrefs'] = []  # blanking the "xrefs" here is *vital* in order to avoid issue #395
                        cui_node_dict_existing = ret_dict.get(cui_curie, None)
                        if cui_node_dict_existing is not None:
                            cui_node_dict = kg2_util.merge_two_dicts(cui_node_dict,
                                                                     cui_node_dict_existing)
                        ret_dict[cui_curie] = cui_node_dict
                        node_dict_xrefs = node_dict['xrefs']
                        node_dict_xrefs.append(cui_curie)
                        node_dict['xrefs'] = list(set(node_dict_xrefs))
                    elif bpv_pred_curie == 'HGNC:ENTREZGENE_ID':
                        entrez_gene_id = bpv_val
                        entrez_node_dict = dict(node_dict)
                        entrez_curie = 'NCBIGene:' + entrez_gene_id
                        entrez_node_dict['id'] = entrez_curie
                        entrez_node_dict['iri'] = 'https://identifiers.org/NCBIGene/' + entrez_gene_id
                        ret_dict[entrez_curie] = entrez_node_dict
                        node_dict_xrefs = node_dict['xrefs']
                        node_dict_xrefs.append(entrez_curie)
                        node_dict['xrefs'] = list(set(node_dict_xrefs))
            if node_curie_id in ret_dict:
                node_dict = kg2_util.merge_two_dicts(ret_dict[node_curie_id], node_dict)
            ret_dict[node_curie_id] = node_dict
    return ret_dict


def get_rels_dict(nodes: dict,
                  owl_file_information_dict_list: list,
                  uri_to_curie_shortener: callable,
                  map_of_node_ontology_ids_to_curie_ids: dict):
    rels_dict = dict()

    for owl_file_information_dict in owl_file_information_dict_list:
        ontology = owl_file_information_dict['ontology']
        ontology_id = owl_file_information_dict['id']
        ont_graph = ontology.get_graph()
        ontology_curie_id = map_of_node_ontology_ids_to_curie_ids[ontology_id]
        for (object_id, subject_id, predicate_dict) in ont_graph.edges(data=True):
            assert type(predicate_dict) == dict

            ontology_node = nodes.get(ontology_curie_id, None)
            if ontology_node is not None:
                ontology_update_date = ontology_node['update date']

            if subject_id == OWL_BASE_CLASS or object_id == OWL_BASE_CLASS:
                continue

            if subject_id.startswith(MYSTERIOUS_BASE_NODE_ID_TO_FILTER) or \
               object_id.startswith(MYSTERIOUS_BASE_NODE_ID_TO_FILTER):
                continue

            # subject_id and object_id are IDs from the original ontology objects; these may not
            # always be the node curie IDs (e.g., for SNOMED terms). Need to map them
            subject_curie_id = map_of_node_ontology_ids_to_curie_ids.get(subject_id, None)
            if subject_curie_id is None:
                kg2_util.log_message(message="ontology node ID has no curie ID in the map",
                                     ontology_name=ontology.id,
                                     node_curie_id=subject_id,
                                     output_stream=sys.stderr)
                continue
            object_curie_id = map_of_node_ontology_ids_to_curie_ids.get(object_id, None)
            if object_curie_id is None:
                kg2_util.log_message(message="ontology node ID has no curie ID in the map",
                                     ontology_name=ontology.id,
                                     node_curie_id=object_id,
                                     output_stream=sys.stderr)
                continue

            predicate_label = None
            edge_pred_string = predicate_dict['pred']

            if subject_curie_id.startswith('TUI:') and object_curie_id.startswith('TUI:') and edge_pred_string == 'subClassOf':
                continue

            if not edge_pred_string.startswith('http:') and not edge_pred_string.startswith('https'):
                # edge_pred_string is not a URI; this is the most common case
                if ':' not in edge_pred_string:
                    # edge_pred_string is not a CURIE; this is the most common subcase
                    if edge_pred_string != 'subClassOf':
                        predicate_curie = 'owl:' + edge_pred_string
                    else:
                        predicate_curie = 'rdfs:subClassOf'
                    predicate_label = kg2_util.convert_camel_case_to_snake_case(edge_pred_string)
                else:
                    # edge_pred_string is a CURIE
                    predicate_curie = edge_pred_string
                    predicate_node = nodes.get(predicate_curie, None)
                    if predicate_node is not None:
                        predicate_label = predicate_node['name']
                    else:
                        # predicate has no node object defined; just pull the label out of the CURIE
                        if edge_pred_string.startswith('OBO:'):
                            test_curie = edge_pred_string.replace('OBO:', '').replace('_', ':')
                            predicate_node = nodes.get(test_curie, None)
                            if predicate_node is None:
                                predicate_label = edge_pred_string.split(':')[1].split('#')[-1]
                            else:
                                predicate_curie = test_curie
                        else:
                            predicate_label = edge_pred_string
                predicate_iri = prefixcommons.expand_uri(predicate_curie)
                predicate_curie_new = uri_to_curie_shortener(predicate_iri)
                if predicate_curie_new is not None:
                    predicate_curie = predicate_curie_new
            else:
                predicate_iri = edge_pred_string
                predicate_curie = uri_to_curie_shortener(predicate_iri)

            if predicate_curie is None:
                kg2_util.log_message(message="predicate IRI has no CURIE: " + predicate_iri,
                                     ontology_name=ontology.id,
                                     output_stream=sys.stderr)
                continue

            if subject_curie_id == object_curie_id and predicate_label == 'xref':
                continue

            if predicate_curie == 'UMLS:hasSTY':
                subject_node = nodes[subject_curie_id]
                object_node = nodes[object_curie_id]
                subject_description = subject_node['description']
                if subject_description is None:
                    subject_description = ''
                subject_node['description'] = '; '.join(list(filter(None, [subject_description,
                                                                           'UMLS Semantic Type: ' + object_node['id']])))
                continue

            rel_key = make_rel_key(subject_curie_id, predicate_curie, object_curie_id, ontology_curie_id)

            if predicate_label is None and ':' in predicate_curie:
                pred_node = nodes.get(predicate_curie, None)
                if pred_node is not None:
                    predicate_label = pred_node['name']
                    if predicate_label[0].isupper():
                        predicate_label = predicate_label[0].lower() + predicate_label[1:]

            assert predicate_label is not None
            predicate_label = predicate_label.replace(' ', '_')
            # Only tested on Food and Efo ontologies
            predicate_label = kg2_util.convert_camel_case_to_snake_case(predicate_label)
            if rels_dict.get(rel_key, None) is None:
                edge = kg2_util.make_edge(subject_curie_id,
                                          object_curie_id,
                                          predicate_iri,
                                          predicate_curie,
                                          predicate_label,
                                          ontology_id,
                                          ontology_update_date)
                rels_dict[rel_key] = edge
        for node_id, node_dict in nodes.items():
            xrefs = node_dict['xrefs']
            if xrefs is not None:
                for xref_node_id in xrefs:
                    if xref_node_id in nodes and node_id != xref_node_id:
                        provided_by = nodes[node_id]['provided by']
                        key = make_rel_key(node_id, CURIE_OBO_XREF, xref_node_id, provided_by)
                        if rels_dict.get(key, None) is None:
                            edge = kg2_util.make_edge(node_id,
                                                      xref_node_id,
                                                      IRI_OBO_XREF,
                                                      CURIE_OBO_XREF,
                                                      'xref',
                                                      provided_by,
                                                      ontology_update_date)
                            rels_dict[key] = edge

    return rels_dict


def get_node_curie_id_from_ontology_node_id(ontology_node_id: str,
                                            ontology: ontobio.ontol.Ontology,
                                            uri_to_curie_shortener: callable):
    node_curie_id = None
    if not ontology_node_id.startswith('http:') and not ontology_node_id.startswith('https:'):
        if not ontology_node_id.startswith('OBO:'):
            node_curie_id = ontology_node_id
        else:
            node_curie_id = uri_to_curie_shortener(prefixcommons.expand_uri(ontology_node_id))
    else:
        node_curie_id = uri_to_curie_shortener(ontology_node_id)
        if node_curie_id is None:
            kg2_util.log_message(message="could not shorten this IRI to a CURIE",
                                 ontology_name=ontology.id,
                                 node_curie_id=ontology_node_id,
                                 output_stream=sys.stderr)
            node_curie_id = ontology_node_id
    return node_curie_id

# --------------- pure functions here -------------------


def shorten_iri_to_curie(iri: str, curie_to_iri_map: list = []):
    if iri.startswith('owl:') or iri.startswith('OIO:'):
        return iri
    if "/GO/GO%3A" in iri:  # hack for fixing issue #410
        iri = iri.replace("/GO/GO%3A", "/GO/")
    curie_list = prefixcommons.contract_uri(iri,
                                            curie_to_iri_map)
    assert len(curie_list) in [0, 1]
    if len(curie_list) == 1:
        curie_id = curie_list[0]
    else:
        curie_id = None
    if curie_id is not None:
        # deal with IRIs like 'https://identifiers.org/umls/ATC/L01AX02' which get converted to CURIE 'UMLS:ATC/L01AX02'
        umls_match = REGEX_UMLS_CURIE.match(curie_id)
        if umls_match is not None:
            curie_id = umls_match[1] + ':' + umls_match[2]

    return curie_id


def is_ignorable_ontology_term(iri: str):
    parsed_iri = urllib.parse.urlparse(iri)
    iri_netloc = parsed_iri.netloc
    iri_path = parsed_iri.path
    return iri_netloc in ('example.com', 'usefulinc.com') or iri_path.startswith('/ontology/provisional')


def make_uri_to_curie_shortener(curie_to_iri_map: list = []):
    return lambda iri: shorten_iri_to_curie(iri, curie_to_iri_map)


def get_prefix_from_curie_id(curie_id: str):
    assert ':' in curie_id
    return curie_id.split(':')[0]


def make_map_of_node_ontology_ids_to_curie_ids(nodes: dict):
    ret_dict = dict()
    for curie_id, node_dict in nodes.items():
        ontology_node_ids = node_dict['ontology node ids']
        assert curie_id not in ret_dict
        assert ontology_node_ids is not None
        assert type(ontology_node_ids) == list
        for ontology_node_id in ontology_node_ids:
            ret_dict[ontology_node_id] = curie_id
    return ret_dict


def xref_as_a_publication(xref: str):
    ret_xref = None
    if xref.upper().startswith('PMID:') or xref.upper().startswith('ISBN:'):
        ret_xref = xref.upper()
    elif xref.startswith('https://') or xref.startswith('http://'):
        ret_xref = xref
    return ret_xref


def make_arg_parser():
    arg_parser = argparse.ArgumentParser(description='multi_owl_to_json_kg.py: builds the KG2 knowledge graph for the RTX system')
    arg_parser.add_argument('--test', dest='test', action="store_true", default=False)
    arg_parser.add_argument('--categoriesFile', type=str, nargs=1)
    arg_parser.add_argument('--curiesToURILALFile', type=str, nargs=1)
    arg_parser.add_argument('--owlLoadInventoryFile', type=str, nargs=1)
    arg_parser.add_argument('--outputFile', type=str, nargs=1)
    return arg_parser


# --------------- main starts here -------------------

if __name__ == '__main__':
    delete_ontobio_cachier_caches()
    args = make_arg_parser().parse_args()
    curies_to_categories_file_name = args.categoriesFile[0]
    curies_to_uri_lal_file_name = args.curiesToURILALFile[0]
    owl_load_inventory_file = args.owlLoadInventoryFile[0]
    output_file = args.outputFile[0]
    test_mode = args.test
    curies_to_categories = kg2_util.safe_load_yaml_from_string(kg2_util.read_file_to_string(curies_to_categories_file_name))
    curies_to_uri_lal = kg2_util.safe_load_yaml_from_string(kg2_util.read_file_to_string(curies_to_uri_lal_file_name))
    curies_to_uri_map = curies_to_uri_lal + prefixcommons.curie_util.default_curie_maps
    uri_to_curie_shortener = make_uri_to_curie_shortener(curies_to_uri_map)
    map_category_label_to_iri = functools.partial(kg2_util.convert_biolink_category_to_iri,
                                                  biolink_category_base_iri=kg2_util.BIOLINK_CATEGORY_BASE_IRI)

    owl_urls_and_files = tuple(kg2_util.safe_load_yaml_from_string(kg2_util.read_file_to_string(owl_load_inventory_file)))

    make_kg2(curies_to_categories,
             uri_to_curie_shortener,
             map_category_label_to_iri,
             owl_urls_and_files,
             output_file,
             test_mode)
