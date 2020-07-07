#!/usr/bin/python3
""" An interface to the SRI Node and Edge Normalizer https://nodenormalization-sri.renci.org/apidocs/
"""

import sys
def eprint(*args, **kwargs): print(*args, file=sys.stderr, **kwargs)

import os
import json
import ast
import time
import pickle
import re
import platform

import requests
import requests_cache


# Class that provides a simple interface to the SRI Node normalizer
class SriNodeNormalizer:


    # Constructor
    def __init__(self):
        requests_cache.install_cache('sri_node_normalizer_requests_cache')

        self.supported_types = None
        self.supported_prefixes = None
        self.cache = {
            'summary': {},
            'ids': {},
        }

        # Translation table of different curie prefixes ARAX -> normalizer
        self.curie_prefix_tx_arax2sri = {
            'REACT': 'Reactome',
            'Orphanet': 'ORPHANET',
            'ICD10': 'ICD-10',
        }
        self.curie_prefix_tx_sri2arax = {
            'Reactome': 'REACT',
            'ORPHANET': 'Orphanet',
            'ICD-10': 'ICD10',
        }


    # ############################################################################################
    # Store the cache of all normalizer results
    def store_cache(self):
        if self.cache is None:
            return
        filename = f"sri_node_normalizer_curie_cache.pickle"
        print(f"INFO: Storing SRI normalizer cache to {filename}")
        with open(filename, "wb") as outfile:
            pickle.dump(self.cache, outfile)
        print("Summary after store:")
        print(json.dumps(self.cache['summary'], indent=2, sort_keys=True))


    # ############################################################################################
    # Load the cache of all normalizer results
    def load_cache(self):
        filename = f"sri_node_normalizer_curie_cache.pickle"
        if os.path.exists(filename):
            print(f"INFO: Reading SRI normalizer cache from {filename}")
            with open(filename, "rb") as infile:
                self.cache = pickle.load(infile)
            #print("Summary after load:")
            #print(json.dumps(self.cache['summary'], indent=2, sort_keys=True))
        else:
            print(f"INFO: SRI node normalizer cache {filename} does not yet exist. Need to fill it.")


    # ############################################################################################
    # Fill the cache with KG nodes
    def fill_cache(self, kg_name):

        # Get a hash of curie prefixes supported
        self.get_supported_prefixes()

        filename = os.path.dirname(os.path.abspath(__file__)) + f"/../../../data/KGmetadata/NodeNamesDescriptions_{kg_name}.tsv"
        filesize = os.path.getsize(filename)

        # Open the file and read in the curies
        fh = open(filename, 'r', encoding="latin-1", errors="replace")
        print(f"INFO: Reading {filename} to pre-fill the normalizer cache")
        previous_percentage = -1
        line_counter = 0
        supported_curies = 0
        bytes_read = 0

        # Create dicts to hold all the information
        batch = []

        # Correction for Windows line endings
        extra_bytes = 0
        if platform.system() == 'Windows':
            extra_bytes = 1

        # Loop over each line in the file
        for line in fh:
            bytes_read += len(line) + extra_bytes
            match = re.match(r'^\s*$',line)
            if match:
                continue
            columns = line.strip().split("\t")
            node_curie = columns[0]

            curie_prefix = node_curie.split(':')[0]

            # If we use different curie prefixes than the normalizer, need to fix
            normalizer_curie_prefix = curie_prefix
            normalizer_node_curie = node_curie
            if curie_prefix in self.curie_prefix_tx_arax2sri:
                normalizer_curie_prefix = self.curie_prefix_tx_arax2sri[curie_prefix]
                normalizer_node_curie = re.sub(curie_prefix,normalizer_curie_prefix,node_curie)

            # Decide if we want to keep this curie in the batch of things to look up
            # By default, no
            keep = 0
            # If this is a curie prefix that is supported by the normalizer, then yes
            if normalizer_curie_prefix in self.supported_prefixes:
                keep = 1
            # Unless it's already in the cache, then no
            if normalizer_node_curie in self.cache['ids']:
                keep = 0
            # Or if we've reached the end of the file, then set keep to 1 and trigger end-of-file processing of the last batch
            if bytes_read + 3 > filesize and len(batch) > 0:
                keep = 99

            # If we want to put this curie in the batch, or drain the batch at end-of-file
            if keep:

                if keep == 1:
                    supported_curies += 1
                    batch.append(normalizer_node_curie)

                if len(batch) > 2000 or keep == 99:
                    if bytes_read + 3 > filesize:
                        print("Drain final batch")
                    results = self.get_node_normalizer_results(batch)
                    print(".", end='', flush=True)
                    for curie in batch:
                        if curie in self.cache['ids']:
                            continue
                        curie_prefix = curie.split(':')[0]
                        if curie_prefix not in self.cache['summary']:
                            self.cache['summary'][curie_prefix] = { 'found': 0, 'not found': 0, 'total': 0 }
                        if results is None or curie not in results or results[curie] is  None:
                            self.cache['ids'][curie] = None
                            self.cache['summary'][curie_prefix]['not found'] += 1
                        else:
                            self.cache['ids'][curie] = results[curie]
                            self.cache['summary'][curie_prefix]['found'] += 1
                        self.cache['summary'][curie_prefix]['total'] += 1

                    # Clear the batch list
                    batch = []

            # Print out some progress information
            line_counter += 1
            percentage = int(bytes_read*100.0/filesize)
            if percentage > previous_percentage:
                previous_percentage = percentage
                print(str(percentage)+"%..", end='', flush=True)

        # Close and summarize
        fh.close()
        print("")
        print(f"{line_counter} lines read")
        print(f"{bytes_read} bytes read of {filesize} bytes in file")
        print(f"{supported_curies} curies with prefixes supported by the SRI normalizer")

        # Store the results
        self.store_cache()


    # ############################################################################################
    # Retrieve the dict of supported BioLink types
    def get_supported_types(self):

        # If we've already done this before, return the cached result
        if self.supported_types is not None:
            return self.supported_types

        # Build the URL and fetch the result
        url = f"https://nodenormalization-sri.renci.org/get_semantic_types"
        response_content = requests.get(url, headers={'accept': 'application/json'})
        status_code = response_content.status_code

        # Check for a returned error
        if status_code != 200:
            eprint(f"ERROR returned with status {status_code} while retrieving supported types")
            eprint(response_content)
            return

        # Unpack the response into a dict and return it
        response_dict = response_content.json()
        if 'semantic_types' not in response_dict:
            eprint(f"ERROR Did not find expected 'semantic_types'")
            return
        if 'types' not in response_dict['semantic_types']:
            eprint(f"ERROR Did not find expected 'types' list")
            return

        node_types = {}
        for node_type in response_dict['semantic_types']['types']:
            node_types[node_type] = 1

        if len(node_types) == 0:
            node_types = None

        # Save this for future use
        self.supported_types = node_types

        return node_types


    # ############################################################################################
    # Retrieve the dict of supported curie prefixes
    def get_supported_prefixes(self):

        # If we've already done this before, return the cached result
        if self.supported_prefixes is not None:
            return self.supported_prefixes

        node_types = self.get_supported_types()
        supported_prefixes = {}
        types_to_skip = { 'named_thing', 'macromolecular_machine', 'genomic_entity', 'organismal_entity', 'disease_or_phenotypic_feature',
            'gene_or_gene_product', 'biological_process_or_activity', 'biological_entity', 'molecular_entity', 'ontology_class' }

        for node_type in node_types:

            if node_type in types_to_skip:
                continue

            # Build the URL and fetch the result
            #print(f"INFO: Get prefixes for {node_type}")
            url = f"https://nodenormalization-sri.renci.org/get_curie_prefixes?semantictype={node_type}"
            response_content = requests.get(url, headers={'accept': 'application/json'})
            status_code = response_content.status_code

            # Check for a returned error
            if status_code != 200:
                eprint(f"ERROR returned with status {status_code} while retrieving supported types")
                eprint(response_content)
                return

            # Unpack the response into a dict and return it
            response_dict = response_content.json()
            for entity_name,entity in response_dict.items():
                if 'curie_prefix' not in entity:
                    eprint(f"ERROR Did not find expected 'curie_prefix'")
                    return
                for item in entity['curie_prefix']:
                    for curie_prefix in item:
                        supported_prefixes[curie_prefix] = 1

        # Save this for future use
        self.supported_prefixes = supported_prefixes

        return supported_prefixes


    # ############################################################################################
    # Retrieve the dict of supported curie prefixes
    # This function might replace the one above if the SRI Node Normalizer fixes their API
    def get_supported_prefixesXXXXXXXXXXXXXXXXXXXXXXXXXXX(self):

        # If we've already done this before, return the cached result
        if self.supported_prefixes is not None:
            return self.supported_prefixes

        node_types = self.get_supported_types()
        node_types_string = "&semantictype=".join(node_types.keys())

        supported_prefixes = {}



        # Build the URL and fetch the result
        #print(f"INFO: Get prefixes for {node_type}")
        url = f"https://nodenormalization-sri.renci.org/get_curie_prefixes?semantictype={node_types_string}"
        print(url)
        response_content = requests.get(url, headers={'accept': 'application/json'})
        status_code = response_content.status_code

        # Check for a returned error
        if status_code != 200:
            eprint(f"ERROR returned with status {status_code} while retrieving supported types")
            eprint(response_content)
            return

        # Unpack the response into a dict and return it
        response_dict = response_content.json()
        print(json.dumps(response_dict, indent=2, sort_keys=True))
        #### FIXME ################################################################################
        sys.exit(1)
        for entity_name,entity in response_dict.items():
            if 'curie_prefix' not in entity:
                eprint(f"ERROR Did not find expected 'curie_prefix'")
                return
            for item in entity['curie_prefix']:
                for curie_prefix in item:
                    supported_prefixes[curie_prefix] = 1

        # Save this for future use
        self.supported_prefixes = supported_prefixes

        return supported_prefixes


    # ############################################################################################
    # Directly fetch a normalization for a CURIE from the Normalizer
    def get_node_normalizer_results(self, curies):

        if isinstance(curies,str):
            #print(f"INFO: Looking for curie {curies}")
            if curies in self.cache['ids']:
                #print(f"INFO: Using prefill cache for lookup on {curies}")
                result = { curies: self.cache['ids'][curies] }
                return result
            curies = [ curies ]

        # Build the URL and fetch the result
        url = f"https://nodenormalization-sri.renci.org/get_normalized_nodes?"

        prefix = ''
        for curie in curies:
            url += f"{prefix}curie={curie}"
            prefix = '&'

        try:
            response_content = requests.get(url, headers={'accept': 'application/json'})
        except:
            print("Uncaught error during web request to SRI normalizer. Try again after 1 second")
            time.sleep(1)
            response_content = requests.get(url, headers={'accept': 'application/json'})
        status_code = response_content.status_code

        # Check for a returned error
        if status_code == 404:
            #eprint(f"INFO: No normalization data for {curie}")
            return
        elif status_code != 200:
            eprint(f"ERROR returned with status {status_code} while searching for {curie}")
            eprint(response_content)
            return

        # Unpack the response into a dict and return it
        response_dict = response_content.json()
        return response_dict


    # ############################################################################################
    # Return a simple dict with the equivalence information and metadata about a CURIE
    def get_empty_equivalence(self, curie=''):

        response = { 'status': 'EMPTY', 'curie': curie, 'preferred_curie': '', 'preferred_curie_name': '',
            'type': '', 'equivalent_identifiers': [], 'equivalent_names': [] }
        return response


    # ############################################################################################
    # Return a simple dict with the equivalence information and metadata about a CURIE
    def get_curie_equivalence(self, curie):

        response = { 'status': 'ERROR', 'curie': curie, 'preferred_curie': '', 'preferred_curie_name': '',
            'type': '', 'equivalent_identifiers': [], 'equivalent_names': [] }

        # Do a translation for different curie prefixes
        curie_prefix = curie.split(':')[0]
        normalizer_curie = curie
        if curie_prefix in self.curie_prefix_tx_arax2sri:
            normalizer_curie = re.sub(curie_prefix,self.curie_prefix_tx_arax2sri[curie_prefix],curie)

        results = self.get_node_normalizer_results(normalizer_curie)
        #print(json.dumps(results, indent=2, sort_keys=True))

        if results is None:
            response['status'] = 'no information'
            return response

        # If input CURIE is not the key of the dict, this is highly unexpected
        if normalizer_curie not in results:
            eprint(f"ERROR: Did not find the curie {normalizer_curie} as a key in the results")
            return response

        if results[normalizer_curie] is None:
            response['status'] = 'no information'
            return response

        # If there is no id in the results, this a highly unexpected
        if 'id' not in results[normalizer_curie]:
            eprint(f"ERROR: Did not find 'id' as a key in the results from the SRI normalizer for curie {normalizer_curie}")
            return response

        # If there is a preferred CURIE, store it and its name
        response['preferred_curie'] = results[normalizer_curie]['id']['identifier']
        if 'label' in results[normalizer_curie]['id']:
            response['preferred_curie_name'] = results[normalizer_curie]['id']['label']

        # Translate the id if necessary
        if curie != normalizer_curie:
            response['preferred_curie'] = re.sub(self.curie_prefix_tx_arax2sri[curie_prefix],curie_prefix,results[normalizer_curie]['id']['identifier'])

        # If there is a returned type, store it
        if 'type' in results[normalizer_curie]:
            response['type'] = results[normalizer_curie]['type'][0]

        # If there are additional equivalent identifiers and names, store them
        names = {}
        if 'equivalent_identifiers' in results[normalizer_curie]:
            for equivalence in results[normalizer_curie]['equivalent_identifiers']:
                if 'identifier' in equivalence:
                    id = equivalence['identifier']
                    if curie != normalizer_curie:
                        id = re.sub(self.curie_prefix_tx_arax2sri[curie_prefix],curie_prefix,id)
                    response['equivalent_identifiers'].append(id)
                if 'label' in equivalence:
                    if equivalence['label'] not in names:
                        response['equivalent_names'].append(equivalence['label'])

        response['status'] = 'OK'
        return response


# ############################################################################################
# Command line interface for this class
def main():

    import argparse
    parser = argparse.ArgumentParser(
        description="Interface to the SRI Node Normalizer", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-b', '--build', action="store_true",
                        help="If set, (re)build the local SRI Node Normalizer cache from scratch", default=False)
    parser.add_argument('-l', '--load', action="store_true",
                        help="If set, load the previously built local SRI Node Normalizer cache", default=False)
    parser.add_argument('-c', '--curie', action="store",
                        help="Specify a curie to look up with the SRI Node Normalizer (e.g., UniProtKB:P01308, Orphanet:2322, DRUGBANK:DB11655", default=None)
    parser.add_argument('-p', '--prefixes', action="store_true",
                        help="If set, list the SRI Node Normalizer supported prefixes", default=None)
    args = parser.parse_args()

    if not args.build and not args.curie and not args.prefixes:
        parser.print_help()
        sys.exit(2)

    normalizer = SriNodeNormalizer()

    if args.prefixes:
        supported_prefixes = normalizer.get_supported_prefixes()
        print(json.dumps(supported_prefixes, indent=2, sort_keys=True))
        return

    if args.build:
        print("INFO: Beginning SRI Node Normalizer cache building process for both KG1 and KG2. Make sure you have a good network connection.")
        print("This might also be a nice time to go get a cup of coffee. This will take a while.")
        normalizer.fill_cache(kg_name='KG2')
        normalizer.fill_cache(kg_name='KG1')
        normalizer.store_cache()
        print("INFO: Build process complete")
        return

    if args.load:
        normalizer.load_cache()

    curie = 'UniProtKB:P01308'
    if args.curie:
        curie = args.curie

    #print(platform.system())

    print("==========================================================")
    print("Native SRI Node Normalizer results:")
    normalized_results = normalizer.get_node_normalizer_results(curie)
    print(json.dumps(normalized_results, indent=2, sort_keys=True))

    print("==========================================================")
    print("Local more compact and useful formatting:")
    equivalence = normalizer.get_curie_equivalence(curie)
    print(json.dumps(equivalence, indent=2, sort_keys=True))


if __name__ == "__main__": main()




