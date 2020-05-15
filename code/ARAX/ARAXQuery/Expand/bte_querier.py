#!/bin/env python3
import sys
import os
import traceback
import requests

from biothings_explorer.user_query_dispatcher import SingleEdgeQueryDispatcher

sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../../UI/OpenAPI/python-flask-server/")
from swagger_server.models.node import Node
from swagger_server.models.edge import Edge
from swagger_server.models.edge_attribute import EdgeAttribute


class BTEQuerier:

    def __init__(self, response_object):
        self.response = response_object

    def answer_one_hop_query(self, query_graph):
        qedge, input_qnode, output_qnode = self.__validate_and_pre_process_input_for_bte(query_graph)
        if self.response.status != 'OK':
            return None

        answer_kg = {'nodes': dict(), 'edges': dict()}
        for curie in input_qnode.curie:
            try:
                seqd = SingleEdgeQueryDispatcher(input_cls=input_qnode.type,
                                                 output_cls=output_qnode.type,
                                                 pred=qedge.type,
                                                 input_id=self.__get_curie_prefix_for_bte(curie),
                                                 values=self.__get_curie_local_id(curie))
                seqd.query()
                reasoner_std_response = seqd.to_reasoner_std()
            except:
                trace_back = traceback.format_exc()
                error_type, error, _ = sys.exc_info()
                self.response.error(f"Encountered a problem while using BioThings Explorer. {trace_back}",
                                    error_code=error_type.__name__)
                return None
            else:
                self.__add_answers_to_kg(answer_kg, reasoner_std_response, input_qnode.id, output_qnode.id, qedge.id)
                if answer_kg['edges']:
                    counts_by_qg_id = self.__get_counts_by_qg_id(answer_kg)
                    num_results_string = ", ".join([f"{qg_id}: {count}" for qg_id, count in sorted(counts_by_qg_id.items())])
                    self.response.info(f"Query for edge {qedge.id} returned results ({num_results_string})")
                else:
                    if self.response.data['parameters']['continue_if_no_results']:
                        self.response.warning(f"No paths were found in BTE satisfying this query graph")
                    else:
                        self.response.error(f"No paths were found in BTE satisfying this query graph. BTE log: {' '.join(seqd.log)}", error_code="NoResults")
                return answer_kg

    def __validate_and_pre_process_input_for_bte(self, query_graph):
        # Make sure we have a valid one-hop query graph
        if len(query_graph.edges) != 1 or len(query_graph.nodes) != 2:
            self.response.error(f"BTE can only accept one-hop query graphs (your QG has {len(query_graph.nodes)} "
                                f"nodes and {len(query_graph.edges)} edges)", error_code="InvalidQueryGraph")
            return None, None, None

        # Figure out which query node is input vs. output
        input_qnode = [node for node in query_graph.nodes if node.curie]
        if not input_qnode:
            self.response.error(f"One of the input qnodes must have a curie for BTE queries", error_code="InvalidQueryGraph")
            return None, None, None
        input_qnode = input_qnode[0]
        output_qnode = next(node for node in query_graph.nodes if node.id != input_qnode.id)
        qedge = query_graph.edges[0]

        valid_bte_inputs_dict = self.__get_valid_bte_inputs_dict()
        if self.response.status != 'OK':
            return None, None, None

        # Make sure predicate is allowed
        if qedge.type not in valid_bte_inputs_dict['predicates'] and qedge.type is not None:
            self.response.error(f"BTE does not accept predicate '{qedge.type}'. Valid options are "
                                f"{valid_bte_inputs_dict['predicates']}", error_code="InvalidInput")
            return None, None, None

        # Convert node types to preferred format and check if they're allowed
        input_qnode.type = self.__convert_string_to_pascal_case(input_qnode.type)
        output_qnode.type = self.__convert_string_to_pascal_case(output_qnode.type)
        for node_type in [input_qnode.type, output_qnode.type]:
            if node_type not in valid_bte_inputs_dict['node_types']:
                self.response.error(f"BTE does not accept node type '{node_type}'. Valid options are "
                                    f"{valid_bte_inputs_dict['node_types']}", error_code="InvalidInput")
                return None, None, None

        # Make sure node type pair is allowed
        if (input_qnode.type, output_qnode.type) not in valid_bte_inputs_dict['node_type_pairs']:
            self.response.error(f"BTE cannot do {input_qnode.type}->{output_qnode.type} queries.", error_code="InvalidInput")
            return None, None, None

        # Make sure our input node curies are in list form
        input_qnode.curie = input_qnode.curie if type(input_qnode.curie) is list else [input_qnode.curie]

        return qedge, input_qnode, output_qnode

    def __add_answers_to_kg(self, answer_kg, reasoner_std_response, input_qnode_id, output_qnode_id, qedge_id):
        kg_to_qg_ids_dict = self.__build_kg_to_qg_id_dict(reasoner_std_response['results'])
        if reasoner_std_response['knowledge_graph']['edges']:  # Note: BTE response currently includes some nodes even when no edges found
            for node in reasoner_std_response['knowledge_graph']['nodes']:
                swagger_node = Node()
                swagger_node.id = node.get('id')
                swagger_node.name = node.get('name')
                swagger_node.type = self.__convert_string_to_snake_case(node.get('type'))
                # Map the returned BTE qg_ids back to the original qnode_ids in our query graph
                bte_qg_id = kg_to_qg_ids_dict['nodes'].get(swagger_node.id)
                if bte_qg_id == "n0":
                    swagger_node.qnode_id = input_qnode_id
                elif bte_qg_id == "n1":
                    swagger_node.qnode_id = output_qnode_id
                else:
                    self.response.error("Could not map BTE qg_id to ARAX qnode_id", error_code="UnknownQGID")
                answer_kg['nodes'][swagger_node.id] = swagger_node
            for edge in reasoner_std_response['knowledge_graph']['edges']:
                swagger_edge = Edge()
                swagger_edge.id = edge.get("id")
                swagger_edge.type = edge.get('type')
                swagger_edge.source_id = edge.get('source_id')
                swagger_edge.target_id = edge.get('target_id')
                swagger_edge.is_defined_by = "BTE"
                swagger_edge.provided_by = edge.get('edge_source')
                # Map the returned BTE qg_id back to the original qedge_id in our query graph
                bte_qg_id = kg_to_qg_ids_dict['edges'].get(swagger_edge.id)
                if bte_qg_id == "e1":
                    swagger_edge.qedge_id = qedge_id
                else:
                    self.response.error("Could not map BTE qg_id to ARAX qedge_id", error_code="UnknownQGID")
                answer_kg['edges'][swagger_edge.id] = swagger_edge
        return answer_kg

    def __get_valid_bte_inputs_dict(self):
        valid_values_dict = {'node_types': set(), 'curie_prefixes': set(), 'predicates': set(), 'node_type_pairs': set()}
        r = requests.get("https://smart-api.info/registry/translator/meta-kg")
        if r.status_code == 200:
            bte_associations = r.json()['associations']
            for bte_association in bte_associations:
                subject_type = bte_association['subject']['semantic_type']
                object_type = bte_association['object']['semantic_type']
                subject_curie_prefix = bte_association['subject']['identifier']
                object_curie_prefix = bte_association['object']['identifier']
                predicate = bte_association['predicate']['label']
                valid_values_dict['node_types'].add(subject_type)
                valid_values_dict['node_types'].add(object_type)
                valid_values_dict['curie_prefixes'].add(subject_curie_prefix)
                valid_values_dict['curie_prefixes'].add(object_curie_prefix)
                valid_values_dict['predicates'].add(predicate)
                valid_values_dict['node_type_pairs'].add((subject_type, object_type))
        else:
            self.response.error(f"Ran into a problem trying to grab BTE meta-kg page ({r.status_code} error)", error_code="FailedRequest")
        return valid_values_dict

    def __get_counts_by_qg_id(self, knowledge_graph):
        counts_by_qg_id = dict()
        for node in knowledge_graph['nodes'].values():
            if node.qnode_id not in counts_by_qg_id:
                counts_by_qg_id[node.qnode_id] = 0
            counts_by_qg_id[node.qnode_id] += 1
        for edge in knowledge_graph['edges'].values():
            if edge.qedge_id not in counts_by_qg_id:
                counts_by_qg_id[edge.qedge_id] = 0
            counts_by_qg_id[edge.qedge_id] += 1
        return counts_by_qg_id

    def __build_kg_to_qg_id_dict(self, results):
        kg_to_qg_ids = {'nodes': dict(), 'edges': dict()}
        for node_binding in results['node_bindings']:
            node_id = node_binding['kg_id']
            qnode_id = node_binding['qg_id']
            if node_id in kg_to_qg_ids['nodes'] and kg_to_qg_ids['nodes'][node_id] != qnode_id:
                self.response.error(f"Node {node_id} has been returned as an answer for multiple query graph nodes"
                                    f" ({kg_to_qg_ids['nodes'][node_id]} and {qnode_id})", error_code="MultipleQGIDs")
            kg_to_qg_ids['nodes'][node_id] = qnode_id
        for edge_binding in results['edge_bindings']:
            edge_ids = edge_binding['kg_id'] if type(edge_binding['kg_id']) is list else [edge_binding['kg_id']]
            qedge_ids = edge_binding['qg_id']
            for kg_id in edge_ids:
                kg_to_qg_ids['edges'][kg_id] = qedge_ids
        return kg_to_qg_ids

    def __convert_string_to_pascal_case(self, input_string):
        # Converts a string like 'chemical_substance' or 'chemicalSubstance' to 'ChemicalSubstance'
        if "_" in input_string:
            words = input_string.split('_')
            return "".join([word.capitalize() for word in words])
        elif len(input_string) > 1:
            return input_string[0].upper() + input_string[1:]
        else:
            return input_string.capitalize()

    def __convert_string_to_snake_case(self, input_string):
        # Converts a string like 'ChemicalSubstance' or 'chemicalSubstance' to 'chemical_substance'
        if len(input_string) > 1:
            snake_string = input_string[0].lower()
            for letter in input_string[1:]:
                if letter.isupper():
                    snake_string += "_"
                snake_string += letter.lower()
            return snake_string
        else:
            return input_string.lower()

    def __get_curie_prefix_for_bte(self, curie):
        prefix = curie.split(':')[0]
        if prefix == "CUI":
            prefix = "UMLS"
        elif prefix == "SNOMEDCT":
            prefix = "SNOMED"
        return prefix

    def __get_curie_local_id(self, curie):
        return curie.split(':')[-1]  # Note: Taking last item gets around "PR:PR:000001" situation
